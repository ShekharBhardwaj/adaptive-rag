"""Pacing at the real HTTP boundary preserves budgets and provider provenance."""

import httpx
import pytest
from pydantic import ValidationError

from adaptive_rag.cli import _model_client, _router
from adaptive_rag.config import FoundationConfig, RequestPacingSettings
from adaptive_rag.evaluation.experiment_models import RunBudget
from adaptive_rag.evaluation.journal import CallJournal
from adaptive_rag.evaluation.runner import _clients
from adaptive_rag.generation.client import ModelCallNotStarted, ModelClientError, OpenAIChatClient
from adaptive_rag.generation.connections import request_pacers
from adaptive_rag.generation.pacing import RequestPacer
from adaptive_rag.retrieval.models import TokenUsage


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def config(**models):
    return FoundationConfig.model_validate(
        {
            "repository": {
                "url": "https://fixture.invalid/repo",
                "path": "/unused",
                "commit_sha": "a" * 40,
            },
            "models": {
                "base_url": "https://embedding.invalid/v1",
                "chat_base_url": "https://chat.invalid/v1",
                "embedding_model": "fixture-embedding",
                "chat_model": "fixture-chat",
                **models,
            },
            "experiment": {"dataset": "/unused/questions.jsonl", "conditions": ["adaptive_llm"]},
        }
    )


def response():
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": "fixture"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        },
    )


def client(pacer, handler):
    return OpenAIChatClient(
        base_url="https://fixture.invalid/v1",
        model="fixture-chat",
        transport=httpx.MockTransport(handler),
        pacer=pacer,
    )


def complete(chat, timeout=10):
    return chat.complete([], [], max_output_tokens=10, temperature=0, timeout=timeout)


def journal():
    class Store:
        events = []

        def event(self, event):
            self.events.append(event)

    store = Store()
    result = CallJournal(
        store,
        budget=RunBudget(max_model_calls=100, max_tokens=100000),
        base_usage=TokenUsage,
        base_attempts=lambda: 0,
        base_known_cost=lambda: 0,
        base_unknown_costs=lambda: 0,
        remaining_seconds=lambda: 100,
        price_schedule=None,
    )
    result.begin_job("fixture-job")
    return result, store


def test_all_chat_roles_share_pacer_without_changing_embedding_identity():
    settings = config(request_pacing={"min_interval_seconds": 6, "max_requests_per_minute": 10})
    clients = _clients(settings)
    assert clients.answer.pacer is clients.agent.pacer is clients.router.pacer
    assert clients.embedding.pacer is not clients.answer.pacer
    assert clients.answer.pacer.min_interval_seconds == 6
    assert clients.embedding.identity == {
        "base_url": "https://embedding.invalid/v1",
        "model": "fixture-embedding",
        "dimensions": None,
    }
    assert clients.answer.identity == {
        "base_url": "https://chat.invalid/v1",
        "model": "fixture-chat",
    }


def test_common_endpoint_uses_stricter_shared_gate_and_disabled_is_legacy():
    settings = config(
        chat_base_url=None,
        request_pacing={"min_interval_seconds": 3, "max_requests_per_minute": 30},
        chat_request_pacing={"min_interval_seconds": 6, "max_requests_per_minute": 10},
    )
    embedding, chat = request_pacers(settings.models)
    assert embedding is chat and chat.min_interval_seconds == 6
    assert chat.max_requests_per_minute == 10
    assert request_pacers(config().models) == (None, None)


def test_adaptive_cli_clients_share_command_scoped_gate():
    settings = config(request_pacing={"min_interval_seconds": 6})
    pacers = request_pacers(settings.models)
    agent = _model_client(settings, "chat", True, pacers=pacers)
    route = _router(settings, "llm", True, pacers=pacers)
    assert agent.pacer is route.client.pacer is pacers[1]


@pytest.mark.parametrize(
    "value",
    [
        {"min_interval_seconds": -1},
        {"min_interval_seconds": float("nan")},
        {"min_interval_seconds": float("inf")},
        {"max_requests_per_minute": 0},
        {"max_requests_per_minute": True},
    ],
)
def test_invalid_pacing_configuration_rejected(value):
    with pytest.raises(ValidationError):
        RequestPacingSettings.model_validate(value)


def test_http_wait_reduces_timeout_and_shared_roles_cannot_burst():
    clock = Clock()
    pacer = RequestPacer(min_interval_seconds=6, clock=clock, sleep=clock.sleep)
    seen = []

    def handler(request):
        seen.append((clock.now, request.extensions["timeout"]["read"]))
        clock.now += 1
        return response()

    complete(client(pacer, handler))
    complete(client(pacer, handler))
    assert seen == [(0, 10), (6, 5)]


def test_provider_cooldown_applies_even_with_malformed_error_body_and_no_retry():
    clock = Clock()
    pacer = RequestPacer(clock=clock, sleep=clock.sleep)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(429, headers={"Retry-After": "20"}, content=b"invalid-json")

    chat = client(pacer, handler)
    with pytest.raises(ModelClientError) as failed:
        complete(chat)
    assert failed.value.record.usage.total_tokens is None
    with pytest.raises(ModelCallNotStarted) as rejected:
        complete(chat, timeout=1)
    assert rejected.value.record is None
    assert len(seen) == 1


@pytest.mark.parametrize("interrupt", [None, KeyboardInterrupt(), SystemExit(4)])
def test_pacing_denial_or_cancellation_never_invents_network_usage(interrupt):
    clock = Clock()

    def wait(seconds):
        if interrupt is not None:
            raise interrupt
        clock.sleep(seconds)

    pacer = RequestPacer(min_interval_seconds=6, clock=clock, sleep=wait)
    seen = []
    chat = client(pacer, lambda request: (seen.append(request), response())[1])
    audit, store = journal()
    paced = audit.wrap_chat(chat)
    complete(paced)
    if interrupt is None:
        with pytest.raises(ModelCallNotStarted):
            complete(paced, timeout=1)
        assert store.events[-1]["event"] == "model_admission_rejected"
    else:
        with pytest.raises(type(interrupt)) as caught:
            complete(paced)
        assert caught.value is interrupt
        assert store.events[-1]["event"] == "model_admission_cancelled"
        assert store.events[-1]["unknown_usage"] is False
    assert len(seen) == audit.attempts == len(audit.calls) == 1
    assert audit.unknown_attempts == 0 and audit.usage.total_tokens == 7

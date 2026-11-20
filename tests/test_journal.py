"""Local fixture calls exercise durable admission; no provider requests are sent."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from adaptive_rag.evaluation.experiment_models import RunBudget
from adaptive_rag.evaluation.journal import CallJournal
from adaptive_rag.evaluation.pricing import PriceSchedule, PricingEntry
from adaptive_rag.evaluation.storage import RunStore
from adaptive_rag.generation.answers import GroundedAnswerGenerator
from adaptive_rag.generation.client import ModelCallNotStarted, ModelClientError
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage


class MemoryStore:
    def __init__(self):
        self.events = []

    def event(self, event):
        self.events.append(json.loads(json.dumps(event)))


def call(operation="chat", usage=None):
    return ModelCallRecord(
        operation=operation,
        model="fixture",
        base_url="https://fixture.invalid/v1",
        request={"model": "fixture"},
        response={"ok": True},
        usage=TokenUsage(input_tokens=10, output_tokens=5) if usage is None else usage,
    )


class FixtureClient:
    identity = {"model": "fixture", "base_url": "https://fixture.invalid/v1", "dimensions": 2}
    token_parameter = "max_completion_tokens"

    def __init__(self, outcome=None, operation="chat", usage=None):
        self.outcome = outcome
        self.operation = operation
        self.usage = usage
        self.requests = []

    def _request(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if callable(self.outcome):
            self.outcome(request)
        return SimpleNamespace(
            message={
                "role": "assistant",
                "content": json.dumps({"answer": "Fixture answer", "citation_ids": []}),
            },
            vectors=((1.0, 0.0),),
            call=call(self.operation, self.usage),
        )

    def complete(self, messages, tools, **kwargs):
        return self._request({"messages": messages, "tools": tools, **kwargs})

    def embed(self, texts, *, timeout):
        return self._request({"texts": texts, "timeout": timeout})


def make_journal(
    *,
    store=None,
    budget=None,
    usage=None,
    attempts=0,
    cost=0.0,
    unknown=0,
    seconds=10.0,
    prices=None,
):
    state = {
        "usage": TokenUsage() if usage is None else usage,
        "attempts": attempts,
        "cost": cost,
        "unknown": unknown,
        "seconds": seconds,
    }
    journal = CallJournal(
        MemoryStore() if store is None else store,
        budget=RunBudget() if budget is None else budget,
        base_usage=lambda: state["usage"],
        base_attempts=lambda: state["attempts"],
        base_known_cost=lambda: state["cost"],
        base_unknown_costs=lambda: state["unknown"],
        remaining_seconds=lambda: state["seconds"],
        price_schedule=prices,
    )
    journal.begin_job("job-1")
    return journal, state


def complete(client):
    return client.complete(
        [{"role": "user", "content": "fixture question"}],
        [],
        max_output_tokens=16,
        temperature=0.0,
        timeout=30.0,
    )


def prices():
    return PriceSchedule(
        as_of=date(2026, 11, 15),
        source="Synthetic test rates; not provider pricing",
        entries=(
            PricingEntry(
                base_url="https://fixture.invalid/v1",
                model="fixture",
                operation="chat",
                input_usd_per_million=1_000_000,
                output_usd_per_million=1_000_000,
            ),
        ),
    )


def test_successful_chat_logs_request_before_delegation_then_exact_result():
    journal, _ = make_journal()
    client = FixtureClient(lambda _request: assert_request_durable(journal.store))
    response = complete(journal.wrap_chat(client))
    assert [event["event"] for event in journal.store.events] == ["model_request", "model_result"]
    request, result = journal.store.events
    assert request["attempt_id"] == result["attempt_id"]
    assert request["job_id"] == "job-1"
    assert request["request"]["max_completion_tokens"] == 16
    assert request["request"]["model"] == "fixture"
    assert request["request"]["temperature"] == 0.0
    assert "timeout" not in request["request"]
    assert result["call"] == response.call.model_dump(mode="json")
    assert journal.attempts == 1
    assert journal.unknown_attempts == 0
    assert journal.usage.total_tokens == 15
    assert journal.calls == (response.call,)
    assert journal.blocked_reason is None
    assert client.requests[0]["timeout"] == 10.0


def assert_request_durable(store):
    assert store.events[-1]["event"] == "model_request"


def test_real_runstore_request_is_on_disk_before_client_delegation(tmp_path):
    directory = tmp_path / "run"
    with RunStore(directory, {"run_id": "fixture"}) as store:
        journal, _ = make_journal(store=store)

        def inspect_disk(_request):
            entries = [
                json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()
            ]
            assert entries[-1]["event"] == "model_request"
            assert entries[-1]["request"]["model"] == "fixture"

        complete(journal.wrap_chat(FixtureClient(inspect_disk)))
        store.finish("completed")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == ["model_request", "model_result"]


def test_embedding_logs_protocol_and_preserves_forwarded_dimensions():
    journal, _ = make_journal()
    client = FixtureClient(operation="embedding", usage=TokenUsage(input_tokens=5, output_tokens=0))
    wrapped = journal.wrap_embedding(client)
    response = wrapped.embed(["source"], timeout=30)
    assert wrapped.identity == client.identity
    assert journal.store.events[0]["request"] == {
        "model": "fixture",
        "input": ["source"],
        "encoding_format": "float",
        "dimensions": 2,
    }
    assert response.vectors == ((1.0, 0.0),)
    assert journal.usage.total_tokens == 5
    assert client.requests[0]["timeout"] == 10.0


def test_chat_tools_and_null_temperature_match_protocol():
    journal, _ = make_journal()
    tools = [{"type": "function", "function": {"name": "fixture_tool"}}]
    journal.wrap_chat(FixtureClient()).complete(
        [], tools, max_output_tokens=10, temperature=None, timeout=3
    )
    request = journal.store.events[0]["request"]
    assert request["tools"] == tools
    assert request["tool_choice"] == "auto"
    assert "temperature" not in request


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"budget": RunBudget(max_model_calls=0)}, "model-call"),
        ({"budget": RunBudget(max_model_calls=1), "attempts": 1}, "model-call"),
        ({"budget": RunBudget(max_tokens=0)}, "token"),
        ({"budget": RunBudget(max_tokens=10)}, "token"),
        ({"usage": TokenUsage(input_tokens=None)}, "unknown"),
        ({"seconds": 0}, "wall-clock"),
        ({"seconds": -1}, "wall-clock"),
        ({"seconds": float("inf")}, "wall-clock"),
        ({"budget": RunBudget(max_cost_usd=0), "prices": prices()}, "cost"),
        ({"budget": RunBudget(max_cost_usd=1), "prices": prices(), "cost": 1}, "cost"),
        ({"budget": RunBudget(max_cost_usd=1), "prices": prices(), "unknown": 1}, "unknown"),
        ({"budget": RunBudget(max_cost_usd=1)}, "rate"),
    ],
)
def test_preflight_denial_never_attempts_or_invents_unknown_accounting(kwargs, expected):
    journal, _ = make_journal(**kwargs)
    client = FixtureClient()
    with pytest.raises(ModelCallNotStarted, match=expected) as caught:
        complete(journal.wrap_chat(client))
    assert caught.value.attempted is False
    assert caught.value.record is None
    assert not client.requests
    assert journal.attempts == journal.unknown_attempts == 0
    assert journal.calls == ()
    assert journal.usage.total_tokens == 0
    assert journal.blocked_reason
    assert [event["event"] for event in journal.store.events] == ["model_admission_rejected"]


def test_cost_exhaustion_blocks_next_call_inside_the_same_job():
    journal, _ = make_journal(budget=RunBudget(max_cost_usd=10), prices=prices())
    client = FixtureClient()
    wrapped = journal.wrap_chat(client)
    complete(wrapped)
    with pytest.raises(ModelCallNotStarted, match="cost"):
        complete(wrapped)
    assert len(client.requests) == journal.attempts == 1
    assert journal.usage.total_tokens == 15
    assert len(journal.calls) == 1
    assert journal.unknown_attempts == 0


def test_token_overrun_disables_every_subsequent_call_in_job():
    journal, _ = make_journal(budget=RunBudget(max_tokens=1000))
    client = FixtureClient(usage=TokenUsage(input_tokens=1001, output_tokens=1))
    wrapped = journal.wrap_chat(client)
    complete(wrapped)
    with pytest.raises(ModelCallNotStarted, match="token"):
        complete(wrapped)
    assert len(client.requests) == 1
    assert journal.usage.total_tokens == 1002


def test_attempt_cap_applies_within_job_across_wrapper_types():
    journal, _ = make_journal(budget=RunBudget(max_model_calls=1))
    complete(journal.wrap_chat(FixtureClient()))
    embedding = FixtureClient(operation="embedding")
    with pytest.raises(ModelCallNotStarted, match="model-call"):
        journal.wrap_embedding(embedding).embed(["source"], timeout=1)
    assert not embedding.requests
    assert journal.attempts == 1


def test_failed_known_call_keeps_record_and_prevents_next_call_after_cost_overrun():
    failed = call()
    journal, _ = make_journal(budget=RunBudget(max_cost_usd=10), prices=prices())
    client = FixtureClient(ModelClientError("HTTP 500", failed))
    with pytest.raises(ModelClientError, match="HTTP 500"):
        complete(journal.wrap_chat(client))
    with pytest.raises(ModelCallNotStarted, match="cost"):
        complete(journal.wrap_chat(client))
    assert journal.calls == (failed,)
    assert journal.usage == failed.usage
    assert journal.attempts == 1
    assert journal.unknown_attempts == 0
    assert journal.store.events[1]["call"] == failed.model_dump(mode="json")


@pytest.mark.parametrize(
    "failure", [RuntimeError("unexpected"), ModelClientError("missing record")]
)
def test_unrecorded_failures_are_unknown_and_halt_next_call(failure):
    journal, _ = make_journal()
    client = FixtureClient(failure)
    with pytest.raises(type(failure)):
        complete(journal.wrap_chat(client))
    with pytest.raises(ModelCallNotStarted, match="unknown"):
        complete(journal.wrap_chat(client))
    assert len(client.requests) == journal.attempts == journal.unknown_attempts == 1
    assert journal.usage.input_tokens is None
    assert journal.usage.output_tokens is None
    assert journal.calls == ()
    assert journal.store.events[1]["unknown_usage"]


def test_missing_usage_in_known_record_halts_next_request():
    journal, _ = make_journal()
    client = FixtureClient(usage=TokenUsage(input_tokens=None, output_tokens=0))
    complete(journal.wrap_chat(client))
    with pytest.raises(ModelCallNotStarted, match="unknown"):
        complete(journal.wrap_chat(client))
    assert journal.attempts == 1
    assert journal.unknown_attempts == 0
    assert journal.usage.total_tokens is None


@pytest.mark.parametrize("failure", [KeyboardInterrupt("soft stop"), SystemExit("exit")])
def test_soft_interrupts_are_journaled_before_reraising(failure):
    journal, _ = make_journal()
    with pytest.raises(type(failure)):
        complete(journal.wrap_chat(FixtureClient(failure)))
    assert journal.attempts == journal.unknown_attempts == 1
    assert journal.usage.total_tokens is None
    assert [event["event"] for event in journal.store.events] == [
        "model_request",
        "model_error",
        "model_interrupted",
    ]
    assert journal.store.events[1]["interrupted"] is True


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("operation", ["chat", "embedding"])
def test_interrupted_pacing_before_slot_has_zero_attempts_and_known_zero_usage(
    interruption, operation
):
    failure = interruption("cancelled while waiting for pacing")
    failure._adaptive_rag_not_started = True
    journal, _ = make_journal()
    client = FixtureClient(failure, operation=operation)
    with pytest.raises(interruption) as caught:
        if operation == "chat":
            complete(journal.wrap_chat(client))
        else:
            journal.wrap_embedding(client).embed(["fixture"], timeout=30)
    assert caught.value is failure
    assert journal.attempts == journal.unknown_attempts == 0
    assert journal.usage == TokenUsage()
    assert journal.calls == ()
    assert [event["event"] for event in journal.store.events] == [
        "model_request",
        "model_admission_cancelled",
    ]
    intent, cancelled = journal.store.events
    assert cancelled["attempt_id"] == intent["attempt_id"]
    assert cancelled["attempted"] is False
    assert cancelled["unknown_usage"] is False
    assert cancelled["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert cancelled["interrupted"] is True


def test_cancelled_pacing_preserves_previous_delegated_usage():
    journal, _ = make_journal()
    complete(journal.wrap_chat(FixtureClient()))
    failure = KeyboardInterrupt("cancelled before another pacing slot")
    failure._adaptive_rag_not_started = True
    with pytest.raises(KeyboardInterrupt):
        complete(journal.wrap_chat(FixtureClient(failure)))
    assert journal.attempts == 1
    assert journal.unknown_attempts == 0
    assert journal.usage.total_tokens == 15
    assert len(journal.calls) == 1


def test_call_snapshots_cannot_be_mutated_by_later_provider_or_consumer_changes():
    journal, _ = make_journal()
    messages = [{"role": "user", "content": "original"}]

    def mutate(request):
        request["messages"][0]["content"] = "provider mutation"

    response = journal.wrap_chat(FixtureClient(mutate)).complete(
        messages, [], max_output_tokens=10, temperature=0, timeout=1
    )
    response.call.request["model"] = "mutated"
    snapshot = journal.calls
    snapshot[0].request["model"] = "mutated again"
    assert messages[0]["content"] == "original"
    assert journal.store.events[0]["request"]["messages"][0]["content"] == "original"
    assert journal.calls[0].request["model"] == "fixture"


def test_begin_job_resets_current_state_and_uses_updated_base_totals():
    journal, state = make_journal(budget=RunBudget(max_model_calls=1))
    complete(journal.wrap_chat(FixtureClient()))
    state["attempts"] = journal.attempts
    state["usage"] = journal.usage
    journal.begin_job("job-2")
    assert journal.calls == ()
    assert journal.attempts == 0
    assert journal.usage.total_tokens == 0
    with pytest.raises(ModelCallNotStarted, match="model-call"):
        complete(journal.wrap_chat(FixtureClient()))
    assert journal.store.events[-1]["job_id"] == "job-2"


def test_request_intent_write_failure_prevents_network_delegation():
    class BrokenStore:
        def event(self, _event):
            raise OSError("fixture disk unavailable")

    journal, _ = make_journal(store=BrokenStore())
    client = FixtureClient()
    with pytest.raises(OSError):
        complete(journal.wrap_chat(client))
    assert journal.attempts == journal.unknown_attempts == 0
    assert not client.requests


def test_generation_admission_denial_is_exhausted_with_zero_usage_and_attempts():
    journal, _ = make_journal(budget=RunBudget(max_model_calls=0))
    client = FixtureClient()
    result = GroundedAnswerGenerator(journal.wrap_chat(client)).generate("Question?", ())
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 0
    assert result.metadata["model_attempts"] == 0
    assert result.model_calls == ()
    assert journal.attempts == 0
    assert not client.requests


def fake_corpus():
    return SimpleNamespace(
        commit_sha="a" * 40,
        fingerprint="b" * 64,
        files=(),
        verify=lambda: None,
    )


def test_agentic_admission_denial_preserves_zero_actual_attempts_and_usage():
    from adaptive_rag.retrieval.agentic import AgenticRetriever
    from adaptive_rag.retrieval.models import RetrievalRequest

    journal, _ = make_journal(budget=RunBudget(max_model_calls=0))
    client = FixtureClient()
    result = AgenticRetriever(fake_corpus(), journal.wrap_chat(client)).retrieve(
        RetrievalRequest(query="Question?")
    )
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 0
    assert result.metadata["model_attempts"] == 0
    assert result.model_calls == ()
    assert journal.attempts == 0
    assert not client.requests


def test_agentic_later_denial_retains_prior_call_and_does_not_add_unknown_usage():
    from adaptive_rag.retrieval.agentic import AgenticRetriever
    from adaptive_rag.retrieval.models import RetrievalRequest

    journal, _ = make_journal(budget=RunBudget(max_model_calls=1))
    tool_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "fixture-1",
                "type": "function",
                "function": {"name": "list_directory", "arguments": "{}"},
            }
        ],
    }

    class NavigationClient(FixtureClient):
        def complete(self, messages, tools, **kwargs):
            result = super().complete(messages, tools, **kwargs)
            result.message = tool_message
            return result

    client = NavigationClient()
    result = AgenticRetriever(fake_corpus(), journal.wrap_chat(client)).retrieve(
        RetrievalRequest(query="Question?")
    )
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 15
    assert result.metadata["model_attempts"] == 1
    assert len(result.model_calls) == len(client.requests) == journal.attempts == 1
    assert journal.unknown_attempts == 0


def test_vector_query_admission_denial_has_no_unknown_usage_or_attempt():
    from adaptive_rag.retrieval.models import RetrievalRequest
    from adaptive_rag.retrieval.vector import VectorRetriever

    journal, _ = make_journal(budget=RunBudget(max_model_calls=0))
    client = FixtureClient(operation="embedding")
    wrapped = journal.wrap_embedding(client)
    retriever = VectorRetriever(fake_corpus(), wrapped)
    retriever._index = object()
    retriever._manifest = SimpleNamespace(embedding_identity=wrapped.identity)
    result = retriever.retrieve(RetrievalRequest(query="Question?"))
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 0
    assert result.metadata["model_attempts"] == 0
    assert result.model_calls == ()
    assert not client.requests


def test_vector_build_admission_denial_keeps_incomplete_manifest_usage_zero(tmp_path, monkeypatch):
    from adaptive_rag.retrieval import vector

    journal, _ = make_journal(budget=RunBudget(max_model_calls=0))
    client = FixtureClient(operation="embedding")
    monkeypatch.setattr(vector, "_dependencies", lambda: (object(), object()))
    monkeypatch.setattr(vector, "chunk_corpus", lambda *args: [SimpleNamespace(text="source")])
    target = tmp_path / "index"
    with pytest.raises(vector.IndexBudgetError, match="admission"):
        vector.VectorRetriever(fake_corpus(), journal.wrap_embedding(client)).build_index(target)
    saved = json.loads((target / "build-failure.json").read_text())
    assert saved["status"] == "budget_exhausted"
    assert saved["model_attempts"] == 0
    assert saved["input_token_byte_estimate"] == 0
    assert saved["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert not client.requests


def test_deadline_expired_during_durable_intent_prevents_delegation():
    class SlowStore(MemoryStore):
        def event(self, event):
            super().event(event)
            state["seconds"] = 0

    journal, state = make_journal(store=SlowStore())
    client = FixtureClient()
    with pytest.raises(ModelCallNotStarted, match="before delegation"):
        complete(journal.wrap_chat(client))
    assert journal.attempts == journal.unknown_attempts == 0
    assert not client.requests
    assert [event["event"] for event in journal.store.events] == [
        "model_request",
        "model_admission_rejected",
    ]


@pytest.mark.parametrize("admission_seconds,intent_seconds", [(0, 7), (3, 4)])
def test_admission_and_intent_time_reduce_the_stage_timeout(
    monkeypatch, admission_seconds, intent_seconds
):
    clock = [100.0]
    monkeypatch.setattr(
        "adaptive_rag.evaluation.journal.time", SimpleNamespace(monotonic=lambda: clock[0])
    )

    class SlowStore(MemoryStore):
        def event(self, event):
            super().event(event)
            if event["event"] == "model_request":
                clock[0] += intent_seconds

    journal, _ = make_journal(store=SlowStore(), seconds=100)
    original_admit = journal._admit

    def delayed_admit(*args, **kwargs):
        admitted = original_admit(*args, **kwargs)
        clock[0] += admission_seconds
        return admitted

    monkeypatch.setattr(journal, "_admit", delayed_admit)
    client = FixtureClient()
    journal.wrap_chat(client).complete([], [], max_output_tokens=10, temperature=0, timeout=10)
    assert client.requests[0]["timeout"] == 3
    assert journal.attempts == 1


def test_stage_expiration_during_intent_rejects_without_network_or_unknown_usage(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(
        "adaptive_rag.evaluation.journal.time", SimpleNamespace(monotonic=lambda: clock[0])
    )

    class SlowStore(MemoryStore):
        def event(self, event):
            super().event(event)
            if event["event"] == "model_request":
                clock[0] += 11

    journal, _ = make_journal(store=SlowStore(), seconds=100)
    client = FixtureClient()
    with pytest.raises(ModelCallNotStarted, match="stage wall-clock.*before delegation"):
        journal.wrap_chat(client).complete([], [], max_output_tokens=10, temperature=0, timeout=10)
    assert client.requests == []
    assert journal.attempts == journal.unknown_attempts == 0
    assert journal.usage == TokenUsage()
    assert journal.calls == ()
    assert journal.store.events[-1]["attempted"] is False


def test_run_remaining_time_still_limits_delegation_after_intent(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(
        "adaptive_rag.evaluation.journal.time", SimpleNamespace(monotonic=lambda: clock[0])
    )

    class SlowStore(MemoryStore):
        def event(self, event):
            super().event(event)
            if event["event"] == "model_request":
                clock[0] += 3
                state["seconds"] = 5

    journal, state = make_journal(store=SlowStore(), seconds=8)
    client = FixtureClient()
    complete(journal.wrap_chat(client))
    assert client.requests[0]["timeout"] == 5


def test_inner_admission_denial_does_not_become_unknown_actual_attempt():
    journal, _ = make_journal()
    client = FixtureClient(ModelCallNotStarted("inner stage refused"))
    with pytest.raises(ModelCallNotStarted, match="inner stage"):
        complete(journal.wrap_chat(client))
    assert journal.attempts == journal.unknown_attempts == 0
    assert journal.usage.total_tokens == 0
    assert journal.calls == ()


def test_vector_build_later_denial_retains_completed_batch_usage(tmp_path, monkeypatch):
    from adaptive_rag.retrieval import vector

    class FakeIndex:
        def __init__(self, _dimensions):
            pass

        def add(self, _vectors):
            pass

    journal, _ = make_journal(budget=RunBudget(max_model_calls=1))
    client = FixtureClient(operation="embedding")
    monkeypatch.setattr(
        vector, "_dependencies", lambda: (SimpleNamespace(IndexFlatIP=FakeIndex), object())
    )
    monkeypatch.setattr(vector, "_vectors", lambda *args: SimpleNamespace(shape=(1, 2)))
    monkeypatch.setattr(vector, "chunk_corpus", lambda *args: [SimpleNamespace(text="source")] * 2)
    target = tmp_path / "index"
    with pytest.raises(vector.IndexBudgetError, match="admission"):
        vector.VectorRetriever(
            fake_corpus(), journal.wrap_embedding(client), batch_size=1
        ).build_index(target)
    saved = json.loads((target / "build-failure.json").read_text())
    assert saved["model_attempts"] == 1
    assert saved["input_token_byte_estimate"] == len("source")
    assert saved["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert len(saved["model_calls"]) == len(client.requests) == 1
    assert journal.unknown_attempts == 0


def test_missing_call_record_is_an_unknown_actual_attempt():
    class MissingRecordClient(FixtureClient):
        def complete(self, *args, **kwargs):
            return SimpleNamespace(message={"role": "assistant", "content": "{}"})

    journal, _ = make_journal()
    with pytest.raises(ModelClientError, match="no valid model call record"):
        complete(journal.wrap_chat(MissingRecordClient()))
    assert journal.attempts == journal.unknown_attempts == 1
    assert journal.usage.total_tokens is None
    assert journal.store.events[-1]["event"] == "model_error"


def test_absent_begin_job_prevents_delegation():
    journal, _ = make_journal()
    journal._job_id = None
    client = FixtureClient()
    with pytest.raises(ValueError, match="begin_job"):
        complete(journal.wrap_chat(client))
    assert not client.requests
    assert journal.attempts == 0

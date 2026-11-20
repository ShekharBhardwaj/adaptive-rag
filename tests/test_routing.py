"""Routing tests use invented queries and manifest-only synthetic repositories."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from adaptive_rag.generation.client import ChatResponse, ModelCallNotStarted, ModelClientError
from adaptive_rag.retrieval.models import ModelCallRecord, RetrievalBudget, TokenUsage
from adaptive_rag.routing import (
    LLMRouter,
    RepositoryMetadata,
    RoutingRequest,
    RoutingResult,
    RuleBasedRouter,
)

COMMIT = "a" * 40
FINGERPRINT = "b" * 64


def corpus(paths=("src/widget.py", "src/view.ts", "README.md")):
    class ManifestOnlyCorpus:
        commit_sha = COMMIT
        fingerprint = FINGERPRINT
        files = tuple(SimpleNamespace(path=path) for path in paths)

        def text(self, _path):
            raise AssertionError("routers must not read source text")

    return ManifestOnlyCorpus()


def request(query="Explain the design goals", **budget):
    return RoutingRequest(
        query=query,
        repository=RepositoryMetadata.from_corpus(corpus()),
        budget=RetrievalBudget(**budget),
    )


class FakeChat:
    def __init__(self, message=None, *, usage=None, error=None, without_record=False):
        self.message = (
            message
            if message is not None
            else {
                "role": "assistant",
                "content": '{"strategy":"vector","reason":"A thematic query."}',
            }
        )
        self.usage = usage if usage is not None else TokenUsage(input_tokens=31, output_tokens=15)
        self.error = error
        self.without_record = without_record
        self.requests = []
        self.after_call = None
        self.record_overrides = {}

    @property
    def identity(self):
        return {"model": "router-test", "base_url": "https://router.invalid/v1"}

    def complete(self, messages, tools, **kwargs):
        payload = {"messages": deepcopy(messages), "tools": deepcopy(tools), **kwargs}
        self.requests.append(payload)
        if self.after_call:
            self.after_call()
        record = ModelCallRecord(
            operation="chat",
            model=self.identity["model"],
            base_url=self.identity["base_url"],
            request=payload,
            response={"choices": [{"message": deepcopy(self.message)}], "raw_marker": "kept"},
            usage=self.usage,
            elapsed_seconds=0.1,
            error=self.error,
        ).model_copy(update=self.record_overrides)
        if self.error:
            raise ModelClientError(self.error, None if self.without_record else record)
        return ChatResponse(message=deepcopy(self.message), call=record)


def test_repository_metadata_reads_only_manifest_and_tracks_complete_counts():
    metadata = RepositoryMetadata.from_corpus(corpus())
    assert metadata.model_dump() == {
        "schema_version": "1",
        "repo_commit": COMMIT,
        "corpus_fingerprint": FINGERPRINT,
        "file_count": 3,
        "root_file_count": 1,
        "extension_counts": {".md": 1, ".py": 1, ".ts": 1},
        "top_level_directory_counts": {"src": 2},
        "omitted_extension_file_count": 0,
        "omitted_directory_file_count": 0,
    }
    assert "widget" not in metadata.model_dump_json()


def test_repository_metadata_is_bounded_and_deterministically_ordered():
    paths = [f"dir{index:02}/file.ext{index:02}" for index in range(40)]
    paths.append("x" * 129 + "/file." + "z" * 129)
    forward = RepositoryMetadata.from_corpus(corpus(paths))
    reverse = RepositoryMetadata.from_corpus(corpus(reversed(paths)))
    assert forward == reverse
    assert len(forward.extension_counts) == len(forward.top_level_directory_counts) == 32
    assert forward.omitted_extension_file_count == forward.omitted_directory_file_count == 9
    assert forward.file_count == 41
    assert max(map(len, forward.extension_counts)) <= 128
    assert max(map(len, forward.top_level_directory_counts)) <= 128


def test_routing_boundary_rejects_annotations_and_unbounded_metadata():
    with pytest.raises(ValidationError, match="Extra inputs"):
        RoutingRequest(**request().model_dump(), ground_truth_answer="forbidden")
    values = request().repository.model_dump()
    with pytest.raises(ValidationError, match="Extra inputs"):
        RepositoryMetadata(**values, source_text="forbidden")
    values["extension_counts"] = {".py": 2}
    with pytest.raises(ValidationError, match="cover exactly all files"):
        RepositoryMetadata(**values)
    values["extension_counts"] = {f".{index}": 1 for index in range(33)}
    with pytest.raises(ValidationError, match="maximum number of groups"):
        RepositoryMetadata(**values)
    with pytest.raises(ValidationError):
        request("x" * 8001)


@pytest.mark.parametrize(
    ("query", "strategy", "matched_rule"),
    [
        ("Explain the design goals", "vector", "semantic_default"),
        ("Where is src/widget.py?", "vectorless", "exact_source_anchor"),
        ("Find build_widget", "vectorless", "exact_source_anchor"),
        ("Locate WidgetBuilder", "vectorless", "exact_source_anchor"),
        ("Where is `compose` defined?", "vectorless", "exact_source_anchor"),
        ("Trace build_widget across modules", "agentic", "navigation_intent"),
        ("Describe the call chain for a request", "agentic", "navigation_intent"),
        ("How do errors propagate?", "agentic", "navigation_intent"),
        ("Describe a tracer", "vector", "semantic_default"),
    ],
)
def test_rule_router_has_predeclared_priority_and_uses_zero_model_calls(
    query, strategy, matched_rule
):
    routed = RuleBasedRouter().route(request(query, max_model_calls=0, max_tokens=0))
    repeated = RuleBasedRouter().route(request(query, max_model_calls=0, max_tokens=0))
    assert routed.status == "completed"
    assert routed.selected_strategy == strategy
    assert routed.reason == repeated.reason
    assert routed.input_features == repeated.input_features
    assert routed.metadata["matched_rule"] == matched_rule
    assert routed.model_calls == ()
    assert routed.usage.total_tokens == 0
    assert routed.router_version == "routing-rules-v1"


def test_rule_router_revalidates_mutated_or_constructed_boundary_inputs():
    bad = request().model_copy(update={"query": ""})
    with pytest.raises(ValidationError):
        RuleBasedRouter().route(bad)
    valid = request()
    valid.repository.extension_counts[".evil"] = 100
    with pytest.raises(ValidationError, match="cover exactly all files"):
        RuleBasedRouter().route(valid)


@pytest.mark.parametrize("strategy", ["vector", "vectorless", "agentic"])
def test_llm_router_selects_one_literal_and_records_exact_inputs_usage_and_response(strategy):
    message = {
        "role": "assistant",
        "content": json.dumps({"strategy": strategy, "reason": "An observable query cue."}),
    }
    client = FakeChat(message)
    routed = LLMRouter(client, max_output_tokens=123, temperature=None).route(request())
    assert routed.status == "completed"
    assert routed.selected_strategy == strategy
    assert routed.reason == "An observable query cue."
    assert routed.router_version == "routing-llm-v3"
    assert routed.metadata["model_attempts"] == len(client.requests) == 1
    assert routed.usage == client.usage == routed.model_calls[0].usage
    assert routed.model_calls[0].response["raw_marker"] == "kept"
    assert routed.metadata["assistant_message"] == message
    assert routed.metadata["response_encoding"] == "json"
    payload = client.requests[0]
    assert payload["tools"] == []
    assert payload["max_output_tokens"] == 123
    assert payload["temperature"] is None
    assert 0 < payload["timeout"] <= request().budget.max_seconds
    user = json.loads(payload["messages"][1]["content"])
    assert set(user) == {"query", "repository", "input_features"}
    assert user["repository"] == request().repository.model_dump(mode="json")
    assert routed.elapsed_seconds >= 0
    assert RoutingResult.model_validate_json(routed.model_dump_json()) == routed


def test_llm_accepts_one_explicit_json_fence_and_preserves_raw_transport_response():
    content = '```json\n{"strategy":"vectorless","reason":"An exact source cue."}\n```'
    message = {"role": "assistant", "content": content}
    client = FakeChat(message)
    routed = LLMRouter(client).route(request())
    assert routed.status == "completed"
    assert routed.selected_strategy == "vectorless"
    assert routed.reason == "An exact source cue."
    assert routed.router_version == "routing-llm-v3"
    assert routed.metadata["response_encoding"] == "json_fence"
    assert routed.metadata["assistant_message"] == message
    assert routed.model_calls[0].response["choices"][0]["message"] == message
    assert routed.usage == client.usage
    assert len(client.requests) == len(routed.model_calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        '```json\n{"strategy":"vector","reason":"x"}\n',
        'Here is the route:\n```json\n{"strategy":"vector","reason":"x"}\n```',
        '```json\n{"strategy":"vector","reason":"x"}\n```\nExtra text',
        '```json\n{"strategy":"vector","reason":"x"}\n```\n'
        '```json\n{"strategy":"agentic","reason":"y"}\n```',
        '```javascript\n{"strategy":"vector","reason":"x"}\n```',
        '```json\n{"strategy":"vector","strategy":"agentic","reason":"x"}\n```',
        '```json\n{"strategy":"vector","reason":NaN}\n```',
        '{"strategy":"vector","strategy":"agentic","reason":"x"}',
        '{"strategy":"vector","reason":"x","extra":1}',
        '{"strategy":"vector"}',
        '{"strategy":["vector"],"reason":"x"}',
        '{"strategy":"adaptive","reason":"x"}',
        '{"strategy":"vector|agentic","reason":"x"}',
        '{"strategy":"vector","reason":" "}',
        '{"strategy":"vector","reason":123}',
        '{"strategy":"vector","reason":NaN}',
        '[{"strategy":"vector","reason":"x"}]',
        json.dumps({"strategy": "vector", "reason": "x" * 1001}),
    ],
)
def test_llm_malformed_responses_fail_closed_with_no_retry_or_fallback(content):
    client = FakeChat({"role": "assistant", "content": content})
    routed = LLMRouter(client).route(request())
    assert routed.status == "error"
    assert routed.selected_strategy is routed.reason is None
    assert len(client.requests) == len(routed.model_calls) == 1
    assert routed.model_calls[0].response["choices"][0]["message"]["content"] == content
    assert routed.usage == client.usage
    assert any("invalid router response" in error for error in routed.errors)


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "user"},
        {"content": None},
        {"tool_calls": [{"id": "not-allowed"}]},
        {"function_call": {"name": "forbidden"}},
        {"refusal": "declined"},
    ],
)
def test_llm_rejects_nonfinal_assistant_messages(changes):
    client = FakeChat()
    client.message.update(changes)
    result = LLMRouter(client).route(request())
    assert result.status == "error"
    assert result.selected_strategy is None
    assert len(client.requests) == 1


@pytest.mark.parametrize("budget", [{"max_model_calls": 0}, {"max_tokens": 1}])
def test_llm_budget_admission_makes_no_call(budget):
    client = FakeChat()
    result = LLMRouter(client).route(request(**budget))
    assert result.status == "budget_exhausted"
    assert result.selected_strategy is None
    assert result.model_calls == ()
    assert result.usage.total_tokens == 0
    assert result.metadata["model_attempts"] == 0
    assert client.requests == []


def test_llm_token_admission_reserves_full_output_cap():
    client = FakeChat()
    router = LLMRouter(client)
    initial = router.route(request())
    exact = sum(initial.metadata["admission"].values())
    client.requests.clear()
    rejected = router.route(request(max_tokens=exact - 1))
    assert rejected.status == "budget_exhausted"
    assert client.requests == []
    accepted = router.route(request(max_tokens=exact))
    assert accepted.status == "completed"
    assert len(client.requests) == 1


@pytest.mark.parametrize(
    ("usage", "status"),
    [
        (TokenUsage(input_tokens=None, output_tokens=10), "error"),
        (TokenUsage(input_tokens=10, output_tokens=None), "error"),
        (TokenUsage(input_tokens=16000, output_tokens=1), "budget_exhausted"),
        (TokenUsage(input_tokens=10, output_tokens=257), "budget_exhausted"),
    ],
)
def test_llm_usage_is_authoritative_and_failed_usage_never_selects(usage, status):
    client = FakeChat(usage=usage)
    result = LLMRouter(client).route(request())
    assert result.status == status
    assert result.selected_strategy is None
    assert result.usage == usage
    assert len(result.model_calls) == 1
    assert result.metadata["claimed_strategy"] == "vector"


def test_llm_provider_failure_preserves_raw_response_and_usage():
    client = FakeChat(error="provider rejected request")
    result = LLMRouter(client).route(request())
    assert result.status == "error"
    assert result.selected_strategy is None
    assert result.model_calls[0].error == "provider rejected request"
    assert result.model_calls[0].response["raw_marker"] == "kept"
    assert result.usage == client.usage
    assert len(client.requests) == 1


def test_llm_failure_without_usage_record_is_explicitly_unknown():
    client = FakeChat(error="transport failed", without_record=True)
    result = LLMRouter(client).route(request())
    assert result.status == "error"
    assert result.model_calls == ()
    assert result.metadata["model_attempts"] == 1
    assert result.usage.total_tokens is None
    assert result.selected_strategy is None


def test_llm_client_admission_rejection_does_not_count_as_model_attempt():
    class AdmissionChat(FakeChat):
        def complete(self, *_args, **_kwargs):
            raise ModelCallNotStarted("shared budget exhausted")

    result = LLMRouter(AdmissionChat()).route(request())
    assert result.status == "budget_exhausted"
    assert result.metadata["model_attempts"] == 0
    assert result.usage.total_tokens == 0
    assert result.model_calls == ()


def test_llm_detects_deadline_overrun_and_passes_remaining_timeout(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("adaptive_rag.routing.routers.time.monotonic", lambda: clock.now)
    client = FakeChat()
    client.after_call = lambda: setattr(clock, "now", 102.1)
    result = LLMRouter(client).route(request(max_seconds=2.0))
    assert result.status == "budget_exhausted"
    assert result.selected_strategy is None
    assert client.requests[0]["timeout"] == 2.0
    assert result.elapsed_seconds == pytest.approx(2.1)
    assert result.usage == client.usage


def test_llm_deadline_exhausted_before_admission_makes_no_call(monkeypatch):
    moments = iter([100.0, 103.0, 103.0])
    monkeypatch.setattr("adaptive_rag.routing.routers.time.monotonic", lambda: next(moments))
    client = FakeChat()
    result = LLMRouter(client).route(request(max_seconds=2.0))
    assert result.status == "budget_exhausted"
    assert result.selected_strategy is None
    assert client.requests == []
    assert result.metadata["model_attempts"] == 0


def test_rule_router_reports_deadline_exhaustion_without_a_selection(monkeypatch):
    moments = iter([100.0, 103.0])
    monkeypatch.setattr("adaptive_rag.routing.routers.time.monotonic", lambda: next(moments))
    result = RuleBasedRouter().route(request(max_seconds=2.0))
    assert result.status == "budget_exhausted"
    assert result.selected_strategy is None
    assert result.usage.total_tokens == 0


def test_llm_invalid_client_identity_is_an_observable_zero_call_error():
    class InvalidIdentityChat(FakeChat):
        @property
        def identity(self):
            return {"model": "router-test"}

    client = InvalidIdentityChat()
    result = LLMRouter(client).route(request())
    assert result.status == "error"
    assert result.selected_strategy is None
    assert client.requests == []
    assert result.usage.total_tokens == 0
    assert result.metadata["model_attempts"] == 0


def test_typed_results_cannot_claim_successful_llm_routing_without_accounting():
    result = LLMRouter(FakeChat()).route(request())
    values = result.model_dump()
    values["model_calls"] = ()
    with pytest.raises(ValidationError, match="exactly one model call"):
        RoutingResult(**values)
    values = result.model_dump()
    values["usage"] = {"input_tokens": None, "output_tokens": None}
    with pytest.raises(ValidationError, match="complete token usage"):
        RoutingResult(**values)


def test_completed_router_usage_must_equal_the_recorded_model_usage():
    result = LLMRouter(FakeChat()).route(request())
    for usage in (TokenUsage(), TokenUsage(input_tokens=100, output_tokens=100)):
        values = {**result.model_dump(), "usage": usage}
        with pytest.raises(ValidationError, match="must equal its model call usage"):
            RoutingResult(**values)


def test_failed_router_usage_cannot_undercount_known_records_or_invent_unknown_usage():
    result = LLMRouter(FakeChat(error="provider failure")).route(request())
    with pytest.raises(ValidationError, match="cannot undercount"):
        RoutingResult(**{**result.model_dump(), "usage": TokenUsage()})
    unrecorded = LLMRouter(FakeChat(error="transport failure", without_record=True)).route(
        request()
    )
    with pytest.raises(ValidationError, match="must remain unknown"):
        RoutingResult(**{**unrecorded.model_dump(), "usage": TokenUsage()})
    unknown = LLMRouter(
        FakeChat(error="provider failure", usage=TokenUsage(input_tokens=None, output_tokens=None))
    ).route(request())
    with pytest.raises(ValidationError, match="must remain unknown"):
        RoutingResult(**{**unknown.model_dump(), "usage": TokenUsage()})


def test_router_attempt_metadata_cannot_hide_a_call_or_claim_multiple_attempts():
    result = LLMRouter(FakeChat()).route(request())
    for attempts in (0, 2, True):
        values = {**result.model_dump(), "metadata": {"model_attempts": attempts}}
        with pytest.raises(ValidationError, match="model-attempt accounting"):
            RoutingResult(**values)


@pytest.mark.parametrize(
    "override",
    [
        {"operation": "embedding"},
        {"model": "wrong-model"},
        {"base_url": "https://wrong.invalid/v1"},
        {"error": "reported provider failure"},
    ],
)
def test_llm_rejects_contradictory_or_failed_call_record(override):
    client = FakeChat()
    client.record_overrides = override
    result = LLMRouter(client).route(request())
    assert result.status == "error"
    assert result.selected_strategy is None
    assert len(result.model_calls) == len(client.requests) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_output_tokens": 0},
        {"max_output_tokens": True},
        {"temperature": True},
        {"temperature": float("nan")},
        {"temperature": 2.1},
    ],
)
def test_llm_constructor_rejects_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        LLMRouter(FakeChat(), **kwargs)

"""Shared-budget orchestration tests with invented queries, manifests and source."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest

from adaptive_rag.retrieval.adaptive import AdaptiveRetriever
from adaptive_rag.retrieval.models import (
    EvidenceChunk,
    ModelCallRecord,
    RetrievalBudget,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalResult,
    TokenUsage,
)
from adaptive_rag.routing import RoutingFeatures, RoutingResult

COMMIT = "a" * 40
FINGERPRINT = "b" * 64
QUERY = "Describe a component"


class SyntheticCorpus:
    commit_sha = COMMIT
    fingerprint = FINGERPRINT
    files = (SimpleNamespace(path="lib/alpha.py"),)

    def __init__(self, clock=None, verification_seconds=0.0):
        self.clock = clock
        self.verification_seconds = verification_seconds
        self.verifications = 0

    def verify(self):
        self.verifications += 1
        if self.clock:
            self.clock.now += self.verification_seconds

    def text(self, _path):
        raise AssertionError("routing/orchestration must not read source text")

    def evidence(self, path, start_line, end_line, score=None, reason=""):
        if (path, start_line, end_line) != ("lib/alpha.py", 1, 1):
            raise ValueError("outside the synthetic source range")
        text = "def alpha(): return 1"
        excerpt = hashlib.sha256(text.encode()).hexdigest()
        identity = f"{self.commit_sha}\0{path}\0{start_line}\0{end_line}\0{excerpt}"
        return EvidenceChunk(
            id=hashlib.sha256(identity.encode()).hexdigest(),
            repo_commit=self.commit_sha,
            path=path,
            start_line=start_line,
            end_line=end_line,
            text=text,
            excerpt_sha256=excerpt,
            score=score,
            reason=reason,
        )


def call(usage, number=1):
    return ModelCallRecord(
        operation="chat",
        model="synthetic-model",
        base_url="https://synthetic.invalid/v1",
        request={"call": number},
        response={"synthetic": True},
        usage=usage,
        elapsed_seconds=0.01,
    )


class StubRouter:
    def __init__(
        self,
        strategy="vector",
        *,
        router="llm",
        status="completed",
        usage=None,
        clock=None,
        seconds=0.0,
    ):
        self.strategy = strategy
        self.router = router
        self.status = status
        self.usage = (
            usage
            if usage is not None
            else (TokenUsage(input_tokens=10, output_tokens=5) if router == "llm" else TokenUsage())
        )
        self.clock, self.seconds = clock, seconds
        self.requests = []
        self.result = None
        self.overrides = {}
        self.mutate = None

    def route(self, request):
        self.requests.append(request)
        if self.clock:
            self.clock.now += self.seconds
        if self.mutate:
            self.mutate(request)
        calls = (call(self.usage),) if self.router == "llm" else ()
        result = RoutingResult(
            router=self.router,
            router_version="synthetic-router-v1",
            query=request.query,
            repository=request.repository,
            status=self.status,
            selected_strategy=self.strategy if self.status == "completed" else None,
            reason="A synthetic observable query cue." if self.status == "completed" else None,
            input_features=RoutingFeatures(
                query_character_count=len(request.query),
                query_word_count=len(request.query.split()),
                has_explicit_path=False,
                has_code_identifier=False,
                has_navigation_intent=False,
            ),
            model_calls=calls,
            usage=self.usage,
            elapsed_seconds=self.seconds,
            errors=() if self.status == "completed" else ("synthetic routing failure",),
            metadata={"model_attempts": len(calls), "nested": {"original": True}},
        )
        self.result = result.model_copy(update=self.overrides)
        return self.result


class StubBackend:
    def __init__(self, strategy, corpus, *, clock=None, seconds=0.0):
        self.strategy, self.corpus = strategy, corpus
        self.clock, self.seconds = clock, seconds
        self.requests = []
        self.overrides = {}
        self.exception = None
        self.result = None
        self.usage = TokenUsage(input_tokens=20, output_tokens=10)
        self.calls = (call(self.usage),)
        self.include_evidence = False

    def retrieve(self, request):
        self.requests.append(request)
        if self.clock:
            self.clock.now += self.seconds
        if self.exception:
            raise self.exception
        result = RetrievalResult(
            strategy=self.strategy,
            query=request.query,
            repo_commit=self.corpus.commit_sha,
            corpus_fingerprint=self.corpus.fingerprint,
            status="completed",
            evidence=(self.corpus.evidence("lib/alpha.py", 1, 1),) if self.include_evidence else (),
            model_calls=self.calls,
            usage=self.usage,
            tool_call_count=1,
            elapsed_seconds=self.seconds,
            operations=(RetrievalOperation(name="synthetic_lookup"),),
            metadata={"model_attempts": len(self.calls), "nested": {"original": True}},
        )
        self.result = result.model_copy(update=self.overrides)
        return self.result


def setup(*, router=None, clock=None, routing_budget=None, verification_seconds=0.0):
    corpus = SyntheticCorpus(clock, verification_seconds)
    router = router or StubRouter(clock=clock)
    backends = {
        strategy: StubBackend(strategy, corpus, clock=clock)
        for strategy in ("vector", "vectorless", "agentic")
    }
    adaptive = AdaptiveRetriever(
        corpus,
        router,
        backends,
        policy="adaptive_llm" if router.router == "llm" else "adaptive_rule",
        routing_budget=routing_budget,
    )
    return adaptive, router, backends


def request(**limits):
    return RetrievalRequest(query=QUERY, top_k=3, budget=RetrievalBudget(**limits))


def assert_no_backend_calls(backends):
    assert all(backend.requests == [] for backend in backends.values())


def test_routing_and_selected_baseline_share_calls_tokens_and_elapsed_budget(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr("adaptive_rag.retrieval.adaptive.time.perf_counter", lambda: clock.now)
    router = StubRouter(clock=clock, seconds=1.0)
    route_limit = RetrievalBudget(max_model_calls=1, max_tokens=100, max_seconds=3.0)
    adaptive, router, backends = setup(
        router=router, clock=clock, routing_budget=route_limit, verification_seconds=0.25
    )
    backends["vector"].seconds = 2.0
    original = request(
        max_model_calls=3,
        max_tokens=500,
        max_seconds=10.0,
        max_tool_calls=4,
        max_evidence_chars=123,
    )
    result = adaptive.retrieve(original)
    admitted_route = router.requests[0]
    assert admitted_route.budget.max_model_calls == 1
    assert admitted_route.budget.max_tokens == 100
    assert admitted_route.budget.max_seconds == 3.0
    assert admitted_route.budget.max_tool_calls == 0
    assert admitted_route.budget.max_evidence_chars == 123
    admitted_backend = backends["vector"].requests[0]
    assert admitted_backend.query == QUERY
    assert admitted_backend.top_k == 3
    assert admitted_backend.budget.max_model_calls == 2
    assert admitted_backend.budget.max_tokens == 485
    assert admitted_backend.budget.max_seconds == pytest.approx(8.75)
    assert admitted_backend.budget.max_tool_calls == 4
    assert admitted_backend.budget.max_evidence_chars == 123
    assert original.budget.max_model_calls == 3
    assert original.budget.max_tokens == 500
    assert result.status == "completed"
    assert result.strategy == "adaptive_llm"
    assert result.selected_strategy == "vector"
    assert result.usage == TokenUsage(input_tokens=30, output_tokens=15)
    assert result.metadata["model_attempts"] == len(result.model_calls) == 2
    assert result.elapsed_seconds == pytest.approx(3.5)
    assert result.metadata["selected_retrieval_seconds"] == 2.0
    assert [operation.name for operation in result.operations] == ["route", "synthetic_lookup"]
    assert backends["vectorless"].requests == backends["agentic"].requests == []


def test_shared_limits_cap_larger_router_limits_without_consuming_tool_budget():
    large = RetrievalBudget(max_model_calls=20, max_tokens=10000, max_seconds=100.0)
    adaptive, router, backends = setup(routing_budget=large)
    backends["vector"].usage = TokenUsage()
    backends["vector"].calls = ()
    result = adaptive.retrieve(request(max_model_calls=1, max_tokens=90, max_seconds=10.0))
    admitted = router.requests[0].budget
    assert admitted.max_model_calls == 1
    assert admitted.max_tokens == 90
    assert 0 < admitted.max_seconds <= 10.0
    assert admitted.max_tool_calls == 0
    remaining = backends["vector"].requests[0].budget
    assert remaining.max_model_calls == 0
    assert remaining.max_tokens == 75
    assert result.status == "completed"


@pytest.mark.parametrize("strategy", ["vector", "vectorless", "agentic"])
def test_exactly_one_selected_independent_baseline_runs(strategy):
    adaptive, _, backends = setup(router=StubRouter(strategy))
    result = adaptive.retrieve(request())
    assert result.selected_strategy == strategy
    assert len(backends[strategy].requests) == 1
    assert all(not backend.requests for key, backend in backends.items() if key != strategy)


@pytest.mark.parametrize("status", ["error", "budget_exhausted"])
def test_unsuccessful_route_blocks_retrieval_and_preserves_router_error_and_cost(status):
    adaptive, router, backends = setup(router=StubRouter(status=status))
    result = adaptive.retrieve(request())
    assert_no_backend_calls(backends)
    assert result.status == status
    assert result.selected_strategy is None
    assert result.errors == ("synthetic routing failure",)
    assert result.model_calls == router.result.model_calls
    assert result.usage == router.result.usage
    assert result.metadata["routing"] == router.result.model_dump(mode="json")


def test_unknown_route_usage_blocks_retrieval_without_imputing_free_tokens():
    router = StubRouter(status="error", usage=TokenUsage(input_tokens=None, output_tokens=None))
    adaptive, _, backends = setup(router=router)
    result = adaptive.retrieve(request())
    assert_no_backend_calls(backends)
    assert result.status == "error"
    assert result.usage.total_tokens is None
    assert result.model_calls[0].usage.total_tokens is None


@pytest.mark.parametrize(
    "override",
    [
        {"selected_strategy": None},
        {"selected_strategy": "adaptive_llm"},
        {"usage": TokenUsage(input_tokens=None, output_tokens=None)},
        {"usage": TokenUsage()},
        {"model_calls": ()},
        {"metadata": {"model_attempts": 0}},
        {"metadata": {"model_attempts": 2}},
    ],
)
def test_forged_or_malformed_typed_route_is_revalidated_and_never_runs_a_backend(override):
    adaptive, router, backends = setup()
    router.overrides = override
    with pytest.raises(ValueError):
        adaptive.retrieve(request())
    assert_no_backend_calls(backends)
    assert adaptive.last_routing_result is None


@pytest.mark.parametrize("field", ["query", "repository", "router"])
def test_route_must_match_requested_query_corpus_and_policy(field):
    adaptive, router, backends = setup()
    if field == "repository":
        wrong = adaptive.repository_metadata.model_copy(update={"repo_commit": "c" * 40})
        router.overrides = {"repository": wrong}
    elif field == "router":
        adaptive.policy = "adaptive_rule"
    else:
        router.overrides = {"query": "A different synthetic query"}
    with pytest.raises(ValueError, match="query, corpus or policy"):
        adaptive.retrieve(request())
    assert_no_backend_calls(backends)


def test_router_receives_only_a_detached_bounded_manifest_and_query():
    adaptive, router, backends = setup()
    original = adaptive.repository_metadata.model_dump()

    def mutate_repository(route_request):
        assert set(type(route_request).model_fields) == {"query", "repository", "budget"}
        assert "alpha" not in route_request.repository.model_dump_json()
        route_request.repository.extension_counts.clear()
        route_request.repository.extension_counts[".ts"] = 1

    router.mutate = mutate_repository
    with pytest.raises(ValueError, match="query, corpus or policy"):
        adaptive.retrieve(request())
    assert adaptive.repository_metadata.model_dump() == original
    assert_no_backend_calls(backends)


@pytest.mark.parametrize(
    "override",
    [
        {"strategy": "vectorless"},
        {"query": "A different query"},
        {"repo_commit": "c" * 40},
        {"corpus_fingerprint": "d" * 64},
    ],
)
def test_selected_backend_strategy_query_and_provenance_must_agree_with_route(override):
    adaptive, _, backends = setup()
    backends["vector"].overrides = override
    with pytest.raises(ValueError):
        adaptive.retrieve(request())
    assert len(backends["vector"].requests) == 1
    assert backends["vectorless"].requests == backends["agentic"].requests == []


def test_selected_backend_evidence_must_match_pinned_source_identity():
    adaptive, _, backends = setup()
    chunk = adaptive.corpus.evidence("lib/alpha.py", 1, 1)
    forged = chunk.model_copy(update={"repo_commit": "c" * 40})
    backends["vector"].overrides = {"evidence": (forged,)}
    with pytest.raises(ValueError):
        adaptive.retrieve(request())
    assert len(backends["vector"].requests) == 1
    assert backends["vectorless"].requests == backends["agentic"].requests == []


def test_valid_selected_evidence_preserves_actual_baseline_and_corpus():
    adaptive, _, backends = setup()
    backends["vector"].include_evidence = True
    result = adaptive.retrieve(request())
    assert result.status == "completed"
    assert result.selected_strategy == "vector"
    assert result.repo_commit == COMMIT
    assert result.corpus_fingerprint == FINGERPRINT
    assert result.evidence == (adaptive.corpus.evidence("lib/alpha.py", 1, 1),)


@pytest.mark.parametrize("failure_kind", ["reported", "raised"])
def test_backend_failure_never_runs_a_fallback(failure_kind):
    adaptive, _, backends = setup()
    if failure_kind == "reported":
        backends["vector"].overrides = {"status": "error", "errors": ("synthetic failure",)}
        result = adaptive.retrieve(request())
        assert result.status == "error"
        assert result.selected_strategy == "vector"
        assert result.errors == ("synthetic failure",)
        assert result.usage.total_tokens == 45
        assert len(result.model_calls) == 2
    else:
        backends["vector"].exception = ValueError("synthetic backend crash")
        with pytest.raises(ValueError, match="synthetic backend crash"):
            adaptive.retrieve(request())
    assert len(backends["vector"].requests) == 1
    assert backends["vectorless"].requests == backends["agentic"].requests == []


@pytest.mark.parametrize("dimension", ["tokens", "model_calls", "tools", "time", "unknown"])
def test_selected_backend_cannot_exceed_shared_budget_even_if_it_claims_completion(
    dimension, monkeypatch
):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr("adaptive_rag.retrieval.adaptive.time.perf_counter", lambda: clock.now)
    adaptive, _, backends = setup(clock=clock)
    limits = {"max_tokens": 50, "max_model_calls": 3, "max_tool_calls": 2, "max_seconds": 5.0}
    if dimension == "tokens":
        backends["vector"].usage = TokenUsage(input_tokens=40, output_tokens=10)
        backends["vector"].calls = (call(backends["vector"].usage),)
    elif dimension == "model_calls":
        backends["vector"].usage = TokenUsage(input_tokens=15, output_tokens=15)
        backends["vector"].calls = tuple(
            call(TokenUsage(input_tokens=5, output_tokens=5), index) for index in range(3)
        )
    elif dimension == "tools":
        backends["vector"].overrides = {"tool_call_count": 3}
    elif dimension == "time":
        backends["vector"].seconds = 6.0
    else:
        backends["vector"].usage = TokenUsage(input_tokens=None, output_tokens=None)
        backends["vector"].calls = (call(backends["vector"].usage),)
    result = adaptive.retrieve(request(**limits))
    assert result.status == "budget_exhausted"
    assert result.selected_strategy == "vector"
    assert result.errors
    assert backends["vectorless"].requests == backends["agentic"].requests == []


def test_route_elapsed_time_is_subtracted_before_any_backend_runs(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr("adaptive_rag.retrieval.adaptive.time.perf_counter", lambda: clock.now)
    router = StubRouter(clock=clock, seconds=6.0)
    adaptive, _, backends = setup(router=router, clock=clock)
    result = adaptive.retrieve(request(max_seconds=5.0))
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 15
    assert_no_backend_calls(backends)


def test_result_metadata_is_a_detached_snapshot_and_does_not_mutate_backend_records():
    adaptive, router, backends = setup()
    result = adaptive.retrieve(request())
    router_before = deepcopy(router.result.model_dump())
    backend_before = deepcopy(backends["vector"].result.model_dump())
    result.metadata["routing"]["metadata"]["nested"]["original"] = False
    result.metadata["nested"]["original"] = False
    assert router.result.model_dump() == router_before
    assert backends["vector"].result.model_dump() == backend_before


@pytest.mark.parametrize("limits", [{"max_tokens": 10}, {"max_model_calls": 0}])
def test_router_exhausting_shared_usage_stops_before_backend(limits):
    adaptive, _, backends = setup()
    result = adaptive.retrieve(request(**limits))
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 15
    assert_no_backend_calls(backends)


@pytest.mark.parametrize("dimension", ["tokens", "model_calls", "time"])
def test_narrow_routing_budget_overrun_blocks_backend_under_larger_shared_budget(
    dimension, monkeypatch
):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr("adaptive_rag.retrieval.adaptive.time.perf_counter", lambda: clock.now)
    router = StubRouter(clock=clock, seconds=2.0 if dimension == "time" else 0.0)
    route_limits = {"max_tokens": 100, "max_model_calls": 1, "max_seconds": 3.0}
    if dimension == "tokens":
        route_limits["max_tokens"] = 10
    elif dimension == "model_calls":
        route_limits["max_model_calls"] = 0
    else:
        route_limits["max_seconds"] = 1.0
    adaptive, _, backends = setup(
        router=router, clock=clock, routing_budget=RetrievalBudget(**route_limits)
    )
    result = adaptive.retrieve(request(max_tokens=1000, max_model_calls=8, max_seconds=10.0))
    assert result.status == "budget_exhausted"
    assert result.selected_strategy == "vector"
    assert result.usage.total_tokens == 15
    assert result.model_calls == router.result.model_calls
    assert result.elapsed_seconds <= 10.0
    assert_no_backend_calls(backends)


@pytest.mark.parametrize("contradiction", ["undercount", "unknown_record", "unrecorded_attempt"])
def test_selected_backend_usage_cannot_contradict_call_accounting(contradiction):
    adaptive, _, backends = setup()
    if contradiction == "undercount":
        backends["vector"].overrides = {"usage": TokenUsage()}
    elif contradiction == "unknown_record":
        backends["vector"].calls = (call(TokenUsage(input_tokens=None, output_tokens=None)),)
    else:
        backends["vector"].overrides = {"metadata": {"model_attempts": 2}}
    with pytest.raises(ValueError, match="accounting contradicts"):
        adaptive.retrieve(request())
    assert len(backends["vector"].requests) == 1
    assert backends["vectorless"].requests == backends["agentic"].requests == []

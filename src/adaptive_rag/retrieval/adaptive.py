"""One pre-retrieval route, then one independent baseline under a shared budget."""

from __future__ import annotations

import time
from typing import Literal

from adaptive_rag.routing import RepositoryMetadata, Router, RoutingRequest, RoutingResult

from .base import Retriever
from .corpus import RepositoryCorpus
from .models import (
    RetrievalBudget,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalResult,
    TokenUsage,
)

AdaptivePolicy = Literal["adaptive_rule", "adaptive_llm"]


class AdaptiveRetriever:
    """Keep routing overhead and errors; never retry or silently change the route."""

    def __init__(
        self,
        corpus: RepositoryCorpus,
        router: Router,
        retrievers: dict[str, Retriever],
        *,
        policy: AdaptivePolicy = "adaptive_rule",
        routing_budget: RetrievalBudget | None = None,
    ):
        if policy not in {"adaptive_rule", "adaptive_llm"}:
            raise ValueError("adaptive policy must be adaptive_rule or adaptive_llm")
        if set(retrievers) != {"vector", "vectorless", "agentic"}:
            raise ValueError("adaptive retrieval requires all three independent baselines")
        self.corpus, self.router, self.retrievers = corpus, router, dict(retrievers)
        self.policy = policy
        self.routing_budget = routing_budget
        self.repository_metadata = RepositoryMetadata.from_corpus(corpus)
        self.last_routing_result: RoutingResult | None = None

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        self.last_routing_result = None
        self.corpus.verify()
        route_limit = self.routing_budget or request.budget
        route_budget = RetrievalBudget(
            max_tool_calls=0,
            max_model_calls=min(route_limit.max_model_calls, request.budget.max_model_calls),
            max_tokens=min(route_limit.max_tokens, request.budget.max_tokens),
            max_seconds=max(
                0.000001,
                min(
                    route_limit.max_seconds,
                    request.budget.max_seconds - (time.perf_counter() - started),
                ),
            ),
            max_evidence_chars=request.budget.max_evidence_chars,
        )
        route_started = time.perf_counter()
        route = self.router.route(
            RoutingRequest(
                query=request.query,
                repository=self.repository_metadata.model_copy(deep=True),
                budget=route_budget,
            )
        )
        route = RoutingResult.model_validate(route.model_dump())
        self.last_routing_result = route
        expected_router = "rule_based" if self.policy == "adaptive_rule" else "llm"
        if (
            route.query != request.query
            or route.repository != self.repository_metadata
            or route.router != expected_router
        ):
            raise ValueError("routing result contradicts the requested query, corpus or policy")
        attempts = route.metadata.get("model_attempts", len(route.model_calls))
        if type(attempts) is not int or attempts < len(route.model_calls):
            raise ValueError("invalid routing model-attempt accounting")
        route_operation = RetrievalOperation(
            name="route",
            arguments={"router": route.router, "query": request.query},
            elapsed_seconds=route.elapsed_seconds,
            details={
                "selected_strategy": route.selected_strategy,
                "reason": route.reason,
                "status": route.status,
                "router_version": route.router_version,
            },
        )

        def stopped(status, errors):
            return RetrievalResult(
                strategy=self.policy,
                selected_strategy=route.selected_strategy,
                query=request.query,
                repo_commit=self.corpus.commit_sha,
                corpus_fingerprint=self.corpus.fingerprint,
                status=status,
                operations=(route_operation,),
                model_calls=route.model_calls,
                usage=route.usage,
                elapsed_seconds=time.perf_counter() - started,
                errors=tuple(errors),
                metadata={
                    "routing": route.model_dump(mode="json"),
                    "model_attempts": attempts,
                    "escalation": "disabled; exactly one route and one selected baseline",
                },
            )

        if route.status != "completed" or route.selected_strategy is None:
            return stopped(route.status if route.status != "completed" else "error", route.errors)
        spent = route.usage.total_tokens
        remaining_seconds = request.budget.max_seconds - (time.perf_counter() - started)
        if spent is None:
            return stopped("budget_exhausted", ("routing usage unknown; retrieval disabled",))
        if (
            spent > request.budget.max_tokens
            or attempts > request.budget.max_model_calls
            or remaining_seconds <= 0
            or spent > route_budget.max_tokens
            or attempts > route_budget.max_model_calls
            or time.perf_counter() - route_started > route_budget.max_seconds
        ):
            return stopped("budget_exhausted", ("routing exhausted the shared retrieval budget",))
        remaining = request.budget.model_copy(
            update={
                "max_model_calls": request.budget.max_model_calls - attempts,
                "max_tokens": request.budget.max_tokens - spent,
                "max_seconds": remaining_seconds,
            }
        )
        selected = self.retrievers[route.selected_strategy].retrieve(
            request.model_copy(update={"budget": remaining})
        )
        selected = RetrievalResult.model_validate(selected.model_dump())
        if selected.strategy != route.selected_strategy:
            raise ValueError("selected baseline returned a different retrieval strategy")
        if (
            selected.query != request.query
            or selected.repo_commit != self.corpus.commit_sha
            or selected.corpus_fingerprint != self.corpus.fingerprint
        ):
            raise ValueError("selected baseline returned a different query or source corpus")
        backend_attempts = selected.metadata.get("model_attempts", len(selected.model_calls))
        if type(backend_attempts) is not int or backend_attempts < len(selected.model_calls):
            raise ValueError("invalid selected baseline model-attempt accounting")
        recorded = TokenUsage()
        for call in selected.model_calls:
            recorded = recorded.add(call.usage)
        for field in ("input_tokens", "output_tokens"):
            observed, reported = getattr(recorded, field), getattr(selected.usage, field)
            if (
                (backend_attempts > len(selected.model_calls) or observed is None)
                and reported is not None
            ) or (observed is not None and reported is not None and reported < observed):
                raise ValueError("selected baseline token accounting contradicts its call records")
        for chunk in selected.evidence:
            actual = self.corpus.evidence(chunk.path, chunk.start_line, chunk.end_line)
            if any(
                getattr(chunk, field) != getattr(actual, field)
                for field in (
                    "id",
                    "path",
                    "start_line",
                    "end_line",
                    "text",
                    "excerpt_sha256",
                    "repo_commit",
                )
            ):
                raise ValueError("selected baseline evidence contradicts the pinned source")
        self.corpus.verify()
        usage = route.usage.add(selected.usage)
        elapsed = time.perf_counter() - started
        status = selected.status
        errors = list(selected.errors)
        if (
            usage.total_tokens is None
            or usage.total_tokens > request.budget.max_tokens
            or attempts + backend_attempts > request.budget.max_model_calls
            or selected.tool_call_count > request.budget.max_tool_calls
            or elapsed > request.budget.max_seconds
        ):
            status = "budget_exhausted"
            errors.append(
                "selected retrieval exceeded or invalidated the shared routing/retrieval budget"
            )
        return selected.model_copy(
            update={
                "strategy": self.policy,
                "selected_strategy": route.selected_strategy,
                "operations": (route_operation,) + selected.operations,
                "model_calls": route.model_calls + selected.model_calls,
                "usage": usage,
                "status": status,
                "elapsed_seconds": elapsed,
                "errors": tuple(errors),
                "metadata": {
                    **selected.metadata,
                    "routing": route.model_dump(mode="json"),
                    "model_attempts": attempts + backend_attempts,
                    "selected_retrieval_seconds": selected.elapsed_seconds,
                    "escalation": "disabled; exactly one route and one selected baseline",
                },
            }
        )

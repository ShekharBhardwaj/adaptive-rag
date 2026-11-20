"""Typed execution plans and observations; annotations never enter model inputs."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, FiniteFloat, model_validator

from adaptive_rag.generation.models import AnswerResult, GenerationSettings
from adaptive_rag.models import (
    BenchmarkQuestion,
    Category,
    ContentSHA256,
    NonBlank,
    ResearchModel,
    Split,
)
from adaptive_rag.retrieval.models import ModelCallRecord, RetrievalResult, TokenUsage
from adaptive_rag.routing.models import RoutingResult

from .metrics import MechanicalMetrics

Condition = Literal[
    "vector",
    "vectorless",
    "agentic",
    "no_retrieval",
    "adaptive_rule",
    "adaptive_llm",
    "agentic_wrapup",
    "adaptive_cascade",
]
Count = Annotated[int, Field(strict=True, ge=0)]


class RunBudget(ResearchModel):
    max_model_calls: Count = 1000
    max_tokens: Count = 1_000_000
    max_seconds: Annotated[FiniteFloat, Field(gt=0)] = 3600
    max_cost_usd: Annotated[FiniteFloat, Field(ge=0)] | None = None
    unknown_usage_policy: Literal["stop", "reserve"] = "stop"


class ExperimentSettings(ResearchModel):
    dataset: Path
    split: Split = "development"
    conditions: Annotated[tuple[Condition, ...], Field(min_length=1)] = (
        "vector",
        "vectorless",
        "agentic",
        "no_retrieval",
    )
    repetitions: Annotated[int, Field(strict=True, ge=2, le=100)] = 3
    order_seed: Annotated[int, Field(strict=True)] = 17
    vector_index: Path | None = None
    require_pilot: bool = True
    answer_model: NonBlank | None = None
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    budget: RunBudget = Field(default_factory=RunBudget)
    price_schedule: Path | None = None

    @model_validator(mode="after")
    def unique_conditions(self) -> Self:
        if len(set(self.conditions)) != len(self.conditions):
            raise ValueError("experiment conditions must be unique")
        if (
            "adaptive_cascade" in self.conditions
            and not self.generation.report_evidence_sufficiency
        ):
            raise ValueError(
                "adaptive_cascade requires generation.report_evidence_sufficiency for every "
                "condition, because its escalation reads the shared answer's report"
            )
        return self


class PlannedJob(ResearchModel):
    job_id: ContentSHA256
    question_id: NonBlank
    condition: Condition
    repetition: Count


class ExperimentRecord(ResearchModel):
    schema_version: Literal["1"] = "1"
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: NonBlank
    job_id: ContentSHA256
    question_id: NonBlank
    question_sha256: ContentSHA256
    category: Category
    split: Split
    condition: Condition
    repetition: Count
    status: Literal["completed", "budget_exhausted", "error", "interrupted"]
    retrieval: RetrievalResult | None = None
    routing: RoutingResult | None = None
    answer: AnswerResult | None = None
    model_calls: tuple[ModelCallRecord, ...] = ()
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_call_count: Count = 0
    elapsed_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0
    errors: tuple[str, ...] = ()
    metrics: MechanicalMetrics | None = None
    estimated_cost_usd: Annotated[FiniteFloat, Field(ge=0)] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coherent_completed_output(self) -> Self:
        adaptive = self.condition in {"adaptive_rule", "adaptive_llm"}
        if not adaptive and self.routing is not None:
            raise ValueError("fixed conditions cannot contain routing decisions")
        if self.routing is not None:
            expected = "rule_based" if self.condition == "adaptive_rule" else "llm"
            if self.routing.router != expected:
                raise ValueError("routing decision does not match the adaptive condition")
            if self.model_calls[: len(self.routing.model_calls)] != self.routing.model_calls:
                raise ValueError("routing model calls must be preserved in overall accounting")
            if self.retrieval is not None and (
                self.retrieval.metadata.get("routing") != self.routing.model_dump(mode="json")
                or self.retrieval.selected_strategy != self.routing.selected_strategy
                or self.retrieval.query != self.routing.query
                or self.retrieval.repo_commit != self.routing.repository.repo_commit
                or self.retrieval.corpus_fingerprint != self.routing.repository.corpus_fingerprint
            ):
                raise ValueError("routing decision does not match the retrieval output")
        if (
            self.status == "completed"
            and adaptive
            and (
                self.routing is None
                or self.routing.status != "completed"
                or self.routing.selected_strategy is None
            )
        ):
            raise ValueError("completed adaptive records require a completed routing decision")
        recorded_usage = TokenUsage()
        for call in self.model_calls:
            recorded_usage = recorded_usage.add(call.usage)
        attempts = self.metadata.get("model_attempts", len(self.model_calls))
        if type(attempts) is not int or attempts < len(self.model_calls):
            raise ValueError("model_attempts must be an integer covering every recorded call")
        unrecorded = attempts > len(self.model_calls)
        for name in ("input_tokens", "output_tokens"):
            observed = getattr(recorded_usage, name)
            reported = getattr(self.usage, name)
            if (unrecorded or observed is None) and reported is not None:
                raise ValueError("unknown or unrecorded model usage must remain unknown")
            if reported is not None and observed is not None and reported < observed:
                raise ValueError("token usage cannot be below the sum of recorded model calls")
        if self.condition == "no_retrieval" and self.retrieval is not None:
            raise ValueError("no_retrieval records cannot contain retrieval output")
        if self.status == "completed":
            if (
                self.answer is None
                or self.answer.status != "completed"
                or not self.answer.answer
                or not self.answer.answer.strip()
            ):
                raise ValueError("completed records require a completed, nonblank answer")
            if self.condition != "no_retrieval" and (
                self.retrieval is None
                or self.retrieval.status != "completed"
                or self.retrieval.strategy != self.condition
            ):
                raise ValueError(
                    "completed retrieval conditions require matching, completed retrieval output"
                )
        if self.condition == "adaptive_cascade" and self.retrieval is not None:
            details = self.metadata.get("cascade")
            if (
                not isinstance(details, dict)
                or self.retrieval.selected_strategy is None
                or details.get("final_strategy") != self.retrieval.selected_strategy
                or self.retrieval.metadata.get("cascade", {}).get("policy_version")
                != details.get("policy_version")
            ):
                raise ValueError("cascade records require a matching recorded stage decision")
        return self


def question_sha256(question: BenchmarkQuestion) -> str:
    encoded = json.dumps(
        question.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

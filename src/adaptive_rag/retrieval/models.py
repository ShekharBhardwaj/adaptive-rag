"""Shared retrieval requests, provenance-bearing evidence, and observable decisions."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, FiniteFloat, StringConstraints

from adaptive_rag.models import CommitSHA, ContentSHA256, EvidenceReference, NonBlank, ResearchModel

Strategy = Literal["vector", "vectorless", "agentic"]
# A stage that actually retrieved evidence, including the reserved-selection navigator.
StageStrategy = Literal["vector", "vectorless", "agentic", "agentic_wrapup"]
RetrievalStrategy = Literal[
    "vector",
    "vectorless",
    "agentic",
    "agentic_wrapup",
    "adaptive_rule",
    "adaptive_llm",
    "adaptive_cascade",
]
Count = Annotated[int, Field(strict=True, ge=0)]


class RetrievalBudget(ResearchModel):
    max_tool_calls: Count = 20
    max_model_calls: Count = 8
    max_tokens: Count = 16000
    max_seconds: Annotated[FiniteFloat, Field(gt=0)] = 30.0
    max_evidence_chars: Annotated[int, Field(strict=True, ge=1)] = 24000


class RetrievalRequest(ResearchModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    top_k: Annotated[int, Field(strict=True, ge=1, le=100)] = 5
    budget: RetrievalBudget = Field(default_factory=RetrievalBudget)


class EvidenceChunk(EvidenceReference):
    id: ContentSHA256
    repo_commit: CommitSHA
    text: str
    score: FiniteFloat | None = None
    reason: str = ""


class TokenUsage(ResearchModel):
    """None is missing provider accounting, while zero means no tokens were used."""

    input_tokens: Count | None = 0
    output_tokens: Count | None = 0

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    def add(self, other: Self) -> Self:
        def plus(left: int | None, right: int | None) -> int | None:
            return None if left is None or right is None else left + right

        return type(self)(
            input_tokens=plus(self.input_tokens, other.input_tokens),
            output_tokens=plus(self.output_tokens, other.output_tokens),
        )


class ModelCallRecord(ResearchModel):
    operation: Literal["chat", "embedding"]
    model: NonBlank
    base_url: NonBlank
    started_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    request: dict[str, Any]
    response: dict[str, Any] = Field(default_factory=dict)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    elapsed_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0.0
    error: str | None = None


class RetrievalOperation(ResearchModel):
    name: NonBlank
    arguments: dict[str, Any] = Field(default_factory=dict)
    elapsed_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0.0
    returned_ids: tuple[str, ...] = ()
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(ResearchModel):
    schema_version: Literal["1"] = "1"
    strategy: RetrievalStrategy
    selected_strategy: StageStrategy | None = None
    query: str
    repo_commit: CommitSHA
    corpus_fingerprint: ContentSHA256
    status: Literal["completed", "budget_exhausted", "error"]
    evidence: tuple[EvidenceChunk, ...] = ()
    operations: tuple[RetrievalOperation, ...] = ()
    model_calls: tuple[ModelCallRecord, ...] = ()
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_call_count: Count = 0
    elapsed_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0.0
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

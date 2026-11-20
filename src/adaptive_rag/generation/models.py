"""Observable answer generation, separated from benchmark annotations."""

from typing import Annotated, Any, Literal

from pydantic import Field, FiniteFloat

from adaptive_rag.models import CommitSHA, ContentSHA256, EvidenceReference, ResearchModel
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage


class GenerationSettings(ResearchModel):
    temperature: Annotated[FiniteFloat, Field(strict=True, ge=0, le=2)] | None = 0.0
    max_output_tokens: Annotated[int, Field(strict=True, ge=1)] = 1024
    max_tokens: Annotated[int, Field(strict=True, ge=0)] = 16000
    max_seconds: Annotated[FiniteFloat, Field(strict=True, gt=0)] = 30.0
    max_evidence_chars: Annotated[int, Field(strict=True, ge=1)] = 24000
    # False keeps the original answer prompt and JSON keys. True uses the versioned
    # prompt that also requires a boolean self-report of evidence sufficiency.
    report_evidence_sufficiency: bool = False


class AnswerCitation(EvidenceReference):
    evidence_id: ContentSHA256
    repo_commit: CommitSHA


class AnswerResult(ResearchModel):
    schema_version: Literal["1"] = "1"
    status: Literal["completed", "budget_exhausted", "error"]
    answer: str | None = None
    citations: tuple[AnswerCitation, ...] = ()
    citation_claims: tuple[str, ...] = ()
    invalid_citation_ids: tuple[str, ...] = ()
    model_calls: tuple[ModelCallRecord, ...] = ()
    usage: TokenUsage = Field(default_factory=TokenUsage)
    elapsed_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0.0
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

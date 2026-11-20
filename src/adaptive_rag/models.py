"""Versioned benchmark annotations; these records must never reach future routers."""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CommitSHA = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
ContentSHA256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Category = Literal["conceptual", "structural", "cross_file"]
Split = Literal["development", "held_out"]


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceReference(ResearchModel):
    """Inclusive 1-based source lines, hashed without a terminal newline."""

    path: Annotated[str, StringConstraints(min_length=1)]
    start_line: Annotated[int, Field(strict=True, ge=1)]
    end_line: Annotated[int, Field(strict=True, ge=1)]
    excerpt_sha256: ContentSHA256

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or bool(PureWindowsPath(value).drive)
            or ".." in path.parts
            or "\\" in value
            or str(path) != value
            or value == "."
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("path must be a normalized, safe repository-relative POSIX path")
        return value

    @model_validator(mode="after")
    def ordered_lines(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class IndependentReview(ResearchModel):
    reviewer: NonBlank
    reviewed_at: AwareDatetime
    method: Literal["source_inspection", "executable_test"]
    notes: NonBlank


class EvidenceProvenance(ResearchModel):
    author: NonBlank
    created_at: AwareDatetime
    method: Literal["source_inspection", "executable_test"]
    notes: NonBlank
    review: IndependentReview | None = None

    @model_validator(mode="after")
    def independent_review(self) -> Self:
        if self.review is not None:
            if self.review.reviewer.casefold() == self.author.casefold():
                raise ValueError("reviewer must be different from annotation author")
            if self.review.reviewed_at < self.created_at:
                raise ValueError("review cannot predate annotation creation")
        return self


class BenchmarkQuestion(ResearchModel):
    schema_version: Literal["1"] = "1"
    id: NonBlank
    question: NonBlank
    category: Category
    ground_truth_answer: NonBlank
    evidence: Annotated[tuple[EvidenceReference, ...], Field(min_length=1)]
    repo_commit: CommitSHA
    provenance: EvidenceProvenance
    difficulty: Literal["easy", "medium", "hard"]
    split: Split

    @model_validator(mode="after")
    def unique_evidence(self) -> Self:
        locations = [(ref.path, ref.start_line, ref.end_line) for ref in self.evidence]
        if len(set(locations)) != len(locations):
            raise ValueError("duplicate supporting source ranges")
        return self

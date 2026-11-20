"""Serializable outcomes from the independent benchmark validation workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field

from adaptive_rag.ingestion import DiscoveryPolicy


class ValidationIssue(BaseModel):
    """A machine-readable error or warning with its dataset location, if known."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    question_id: str | None = None
    line: int | None = Field(default=None, ge=1)


class ValidationReport(BaseModel):
    """Audit record; valid means every requested validation check passed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    dataset_path: str
    dataset_sha256: str | None
    repository: str
    expected_commit: str
    validated_at: AwareDatetime
    question_count: int = Field(ge=0)
    category_counts: dict[str, int]
    split_counts: dict[str, int]
    category_split_counts: dict[str, dict[str, int]]
    require_reviewed: bool
    pilot: bool
    discovery_policy: DiscoveryPolicy
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()

    @computed_field
    @property
    def valid(self) -> bool:
        return not self.errors

"""Bounded, annotation-free inputs and observable one-baseline routing decisions."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import Field, FiniteFloat, StringConstraints, field_validator, model_validator

from adaptive_rag.ingestion.models import validate_source_path
from adaptive_rag.models import CommitSHA, ContentSHA256, ResearchModel
from adaptive_rag.retrieval.models import (
    Count,
    ModelCallRecord,
    RetrievalBudget,
    Strategy,
    TokenUsage,
)

if TYPE_CHECKING:
    from adaptive_rag.retrieval.corpus import RepositoryCorpus

MAX_METADATA_GROUPS = 32
MAX_METADATA_LABEL_CHARS = 128


class RepositoryMetadata(ResearchModel):
    """A manifest summary; source contents and per-file names are not router inputs.

    At most 32 extension and directory groups are exposed, ordered by descending
    count then label. Oversized labels and excess groups contribute to explicit
    omitted counts, so no truncation can accidentally fabricate a path label.
    """

    schema_version: Literal["1"] = "1"
    repo_commit: CommitSHA
    corpus_fingerprint: ContentSHA256
    file_count: Count
    root_file_count: Count = 0
    extension_counts: dict[str, Count] = Field(default_factory=dict)
    top_level_directory_counts: dict[str, Count] = Field(default_factory=dict)
    omitted_extension_file_count: Count = 0
    omitted_directory_file_count: Count = 0

    @field_validator("extension_counts", "top_level_directory_counts")
    @classmethod
    def bounded_groups(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > MAX_METADATA_GROUPS:
            raise ValueError("repository metadata exceeds the maximum number of groups")
        for label in value:
            if not label or len(label) > MAX_METADATA_LABEL_CHARS:
                raise ValueError("repository metadata labels must contain 1 to 128 characters")
            if any(ord(character) < 32 or ord(character) == 127 for character in label):
                raise ValueError("repository metadata labels cannot contain control characters")
            if "/" in label or "\\" in label or label in {".", ".."}:
                raise ValueError("repository metadata groups must be single path components")
        return dict(sorted(value.items(), key=lambda item: (-item[1], item[0])))

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        extension_files = sum(self.extension_counts.values()) + self.omitted_extension_file_count
        if extension_files != self.file_count:
            raise ValueError("extension groups and omitted counts must cover exactly all files")
        directory_files = (
            sum(self.top_level_directory_counts.values())
            + self.omitted_directory_file_count
            + self.root_file_count
        )
        if directory_files != self.file_count:
            raise ValueError("directory groups and root files must cover exactly all files")
        return self

    @classmethod
    def from_corpus(cls, corpus: RepositoryCorpus) -> Self:
        """Read only pinned identifiers and manifest paths, never corpus.text()."""
        extensions: Counter[str] = Counter()
        directories: Counter[str] = Counter()
        root_files = 0
        for source in corpus.files:
            path = PurePosixPath(validate_source_path(source.path))
            extensions[path.suffix.casefold() or "<none>"] += 1
            if len(path.parts) > 1:
                directories[path.parts[0]] += 1
            else:
                root_files += 1

        def bounded(counts: Counter[str]) -> tuple[dict[str, int], int]:
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            eligible = [item for item in ordered if len(item[0]) <= MAX_METADATA_LABEL_CHARS]
            selected = dict(eligible[:MAX_METADATA_GROUPS])
            return selected, sum(counts.values()) - sum(selected.values())

        extension_counts, omitted_extensions = bounded(extensions)
        directory_counts, omitted_directories = bounded(directories)
        return cls(
            repo_commit=corpus.commit_sha,
            corpus_fingerprint=corpus.fingerprint,
            file_count=len(corpus.files),
            root_file_count=root_files,
            extension_counts=extension_counts,
            top_level_directory_counts=directory_counts,
            omitted_extension_file_count=omitted_extensions,
            omitted_directory_file_count=omitted_directories,
        )


class RoutingRequest(ResearchModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    repository: RepositoryMetadata
    budget: RetrievalBudget = Field(default_factory=RetrievalBudget)


class RoutingFeatures(ResearchModel):
    """Predeclared syntactic features computed from the query alone."""

    query_character_count: Count
    query_word_count: Count
    has_explicit_path: bool
    has_code_identifier: bool
    has_navigation_intent: bool
    matched_navigation_terms: tuple[str, ...] = ()


class RoutingResult(ResearchModel):
    schema_version: Literal["1"] = "1"
    router: Literal["rule_based", "llm"]
    router_version: Annotated[str, StringConstraints(min_length=1)]
    query: str
    repository: RepositoryMetadata
    status: Literal["completed", "budget_exhausted", "error"]
    selected_strategy: Strategy | None = None
    reason: str | None = None
    input_features: RoutingFeatures
    model_calls: tuple[ModelCallRecord, ...] = ()
    usage: TokenUsage = Field(default_factory=TokenUsage)
    elapsed_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0.0
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_decision(self) -> Self:
        if len(self.model_calls) > 1:
            raise ValueError("a router can make at most one model call")
        attempts = self.metadata.get("model_attempts", len(self.model_calls))
        if type(attempts) is not int or not len(self.model_calls) <= attempts <= 1:
            raise ValueError("router model-attempt accounting must agree with its call records")
        if self.router == "rule_based" and self.model_calls:
            raise ValueError("the rule-based router cannot make model calls")
        if self.router == "rule_based" and attempts != 0:
            raise ValueError("the rule-based router cannot attempt model calls")
        if self.router == "rule_based" and self.usage.total_tokens != 0:
            raise ValueError("the rule-based router must report zero token usage")
        if self.status == "completed":
            if self.selected_strategy is None or self.reason is None or not self.reason.strip():
                raise ValueError("completed routing requires one strategy and a reason")
            if self.errors:
                raise ValueError("completed routing cannot contain errors")
            if self.router == "llm" and len(self.model_calls) != 1:
                raise ValueError("completed LLM routing requires exactly one model call record")
            if self.usage.total_tokens is None:
                raise ValueError("completed routing requires complete token usage")
            if self.router == "llm" and self.usage != self.model_calls[0].usage:
                raise ValueError("completed LLM routing usage must equal its model call usage")
        elif self.selected_strategy is not None:
            raise ValueError("failed routing cannot select a fallback strategy")
        if self.status != "completed":
            unrecorded_attempt = attempts > len(self.model_calls)
            for field in ("input_tokens", "output_tokens"):
                actual = getattr(self.usage, field)
                recorded = [getattr(call.usage, field) for call in self.model_calls]
                if unrecorded_attempt or any(value is None for value in recorded):
                    if actual is not None:
                        raise ValueError("unknown router call usage must remain unknown")
                elif self.model_calls and (actual is None or actual < sum(recorded)):
                    raise ValueError(
                        "reported router usage cannot undercount its model call records"
                    )
        return self

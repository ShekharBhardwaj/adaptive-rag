"""Validate benchmark records against independently inspectable repository evidence.

No answer generation or semantic answer judging occurs here. A passing report
certifies record integrity, evidence integrity, and recorded review provenance;
it cannot certify that a human-written answer is scientifically correct.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from adaptive_rag.ingestion import (
    DiscoveryPolicy,
    IngestionError,
    SourceFile,
    discover_files,
    read_source_file,
    verify_snapshot,
)
from adaptive_rag.models import BenchmarkQuestion

from .models import ValidationIssue, ValidationReport

_CATEGORIES = ("conceptual", "structural", "cross_file")
_SPLITS = ("development", "held_out")


class BenchmarkLoadError(ValueError):
    """One or more JSONL rows failed validation; no partial dataset is returned."""

    def __init__(self, errors: tuple[ValidationIssue, ...]):
        self.errors = errors
        details = "; ".join(
            f"line {error.line}: {error.message}" if error.line else error.message
            for error in errors
        )
        super().__init__(details)


def normalize_question(question: str) -> str:
    """Normalize Unicode presentation, letter case, and whitespace for duplicates.

    This is a deterministic duplicate check, not a semantic paraphrase detector.
    """

    return " ".join(unicodedata.normalize("NFKC", question).casefold().split())


def _issue(
    code: str,
    message: str,
    *,
    question: BenchmarkQuestion | None = None,
    line: int | None = None,
    question_id: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        question_id=question.id if question is not None else question_id,
        line=line,
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON numeric constant: {value}")


def _parse_benchmark(
    raw: bytes,
) -> tuple[list[tuple[int, BenchmarkQuestion]], list[ValidationIssue]]:
    records: list[tuple[int, BenchmarkQuestion]] = []
    errors: list[ValidationIssue] = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(
            _issue(
                "invalid_encoding",
                f"Benchmark must be UTF-8: {exc}",
                line=raw[: exc.start].count(b"\n") + 1,
            )
        )
        return records, errors

    ids: dict[str, tuple[int, BenchmarkQuestion]] = {}
    questions: dict[str, tuple[int, BenchmarkQuestion]] = {}
    # split on LF, the JSONL record separator, without counting a final newline
    # as an empty record. Blank records inside the file remain validation errors.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for number, source in enumerate(lines, start=1):
        if not source.strip():
            errors.append(_issue("blank_line", "JSONL records cannot be blank.", line=number))
            continue
        record_id: str | None = None
        try:
            value = json.loads(
                source,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            errors.append(_issue("invalid_json", f"Invalid JSON: {exc}", line=number))
            continue
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            record_id = value["id"]
        try:
            question = BenchmarkQuestion.model_validate(value)
        except ValidationError as exc:
            descriptions = []
            for error in exc.errors(include_url=False):
                location = ".".join(str(part) for part in error["loc"]) or "record"
                descriptions.append(f"{location}: {error['msg']}")
            errors.append(
                _issue(
                    "invalid_question",
                    "; ".join(descriptions),
                    line=number,
                    question_id=record_id,
                )
            )
            continue
        records.append((number, question))
        if question.id in ids:
            first_line, _ = ids[question.id]
            errors.append(
                _issue(
                    "duplicate_id",
                    f"Question ID {question.id!r} already occurs on line {first_line}.",
                    question=question,
                    line=number,
                )
            )
        else:
            ids[question.id] = (number, question)
        normalized = normalize_question(question.question)
        if normalized in questions:
            first_line, first_question = questions[normalized]
            leakage = question.split != first_question.split
            errors.append(
                _issue(
                    "split_leakage" if leakage else "duplicate_question",
                    (
                        f"Normalized question duplicates {first_question.id!r} on line "
                        f"{first_line}"
                        + (" across development and held-out splits." if leakage else ".")
                    ),
                    question=question,
                    line=number,
                )
            )
        else:
            questions[normalized] = (number, question)
    if not records:
        errors.append(_issue("empty_benchmark", "Benchmark contains no valid questions."))
    return records, errors


def load_benchmark(path: str | Path) -> tuple[BenchmarkQuestion, ...]:
    """Load all JSONL records or raise with line-specific, structured errors.

    Repository evidence verification requires :func:`validate_benchmark`.
    """

    try:
        raw = Path(path).expanduser().read_bytes()
    except OSError as exc:
        raise BenchmarkLoadError((_issue("dataset_read_error", str(exc)),)) from exc
    records, errors = _parse_benchmark(raw)
    if errors:
        raise BenchmarkLoadError(tuple(errors))
    return tuple(question for _, question in records)


def _read_evidence(
    repository: Path, path: str, source: SourceFile, expected_commit: str
) -> tuple[str, ...]:
    relative = PurePosixPath(path)
    # Check again at the filesystem boundary even though the question schema
    # rejects unsafe references. Do not resolve a symlink and then accept it.
    if (
        relative.is_absolute()
        or not relative.parts
        or path != relative.as_posix()
        or any(part in {".", ".."} for part in relative.parts)
        or "\\" in path
    ):
        raise ValueError(f"Evidence path is not a safe POSIX relative path: {path!r}")
    candidate = repository
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"Evidence path contains a symlink: {path!r}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(repository):
        raise ValueError(f"Evidence resolves outside the repository: {path!r}")
    if not resolved.is_file():
        raise ValueError(f"Evidence is not a regular file: {path!r}")
    # Evidence is anchored to Git blobs, so checkout newline/filter settings do
    # not change benchmark digests. The worktree checks above still forbid
    # symlink paths or absent files.
    text = read_source_file(repository, path, expected_commit=expected_commit)
    raw = text.encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != source.sha256.lower():
        raise ValueError(f"Evidence changed after repository discovery: {path!r}")
    return tuple(text.splitlines())


def validate_benchmark(
    path: str | Path,
    repository: str | Path,
    expected_commit: str,
    *,
    require_reviewed: bool = True,
    pilot: bool = False,
    policy: DiscoveryPolicy | None = None,
) -> ValidationReport:
    """Audit JSONL, snapshot identity, evidence checksums, provenance, and splits.

    ``require_reviewed=False`` permits an explicit authoring audit, with a
    warning; it does not assert independent verification. ``pilot=True`` enforces
    exactly 30 questions, 10 per category, and five questions per split in every category.
    Evidence digests cover UTF-8 ``"\n".join(text.splitlines()[start-1:end])``
    with inclusive one-based ranges and no appended newline.
    """

    dataset_path = Path(path).expanduser()
    repository_path = Path(repository).expanduser().resolve()
    effective_policy = policy if policy is not None else DiscoveryPolicy()
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    records: list[tuple[int, BenchmarkQuestion]] = []
    digest: str | None = None
    try:
        raw = dataset_path.read_bytes()
    except OSError as exc:
        errors.append(_issue("dataset_read_error", str(exc)))
    else:
        digest = hashlib.sha256(raw).hexdigest()
        records, parse_errors = _parse_benchmark(raw)
        errors.extend(parse_errors)

    eligible: dict[str, SourceFile] | None = None
    snapshot_verified = False
    try:
        verify_snapshot(repository_path, expected_commit)
        snapshot_verified = True
    except (IngestionError, OSError, ValueError) as exc:
        errors.append(_issue("snapshot_verification_failed", str(exc)))
    if snapshot_verified:
        try:
            eligible = {
                source.path: source
                for source in discover_files(
                    repository_path, effective_policy, expected_commit=expected_commit
                )
            }
        except (IngestionError, OSError, ValueError) as exc:
            errors.append(_issue("file_discovery_failed", str(exc)))

    if not require_reviewed:
        warnings.append(
            _issue(
                "review_not_required",
                "Authoring audit only: independent review is not required by this run.",
            )
        )
    cached_lines: dict[str, tuple[str, ...]] = {}
    for line, question in records:
        if question.repo_commit.lower() != expected_commit.lower():
            errors.append(
                _issue(
                    "question_commit_mismatch",
                    f"Question commit {question.repo_commit} differs from "
                    f"expected {expected_commit}.",
                    question=question,
                    line=line,
                )
            )
        review = question.provenance.review
        if review is None and require_reviewed:
            errors.append(
                _issue(
                    "missing_independent_review",
                    "Question requires an independently recorded evidence review.",
                    question=question,
                    line=line,
                )
            )
        if review is not None:
            # Schemas reject these too; retain boundary checks for model_construct
            # callers and future schema changes.
            if review.reviewer.strip().casefold() == question.provenance.author.strip().casefold():
                errors.append(
                    _issue(
                        "non_independent_review",
                        "Evidence author and reviewer must be different people.",
                        question=question,
                        line=line,
                    )
                )
            if review.reviewed_at < question.provenance.created_at:
                errors.append(
                    _issue(
                        "review_before_authoring",
                        "Independent review cannot precede evidence authoring.",
                        question=question,
                        line=line,
                    )
                )
        if eligible is None:
            continue
        for evidence in question.evidence:
            source = eligible.get(evidence.path)
            if source is None:
                errors.append(
                    _issue(
                        "ineligible_evidence_file",
                        f"Evidence file is not in the discovered snapshot: {evidence.path!r}.",
                        question=question,
                        line=line,
                    )
                )
                continue
            try:
                if evidence.path not in cached_lines:
                    cached_lines[evidence.path] = _read_evidence(
                        repository_path, evidence.path, source, expected_commit
                    )
                lines = cached_lines[evidence.path]
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(_issue("evidence_read_error", str(exc), question=question, line=line))
                continue
            if evidence.start_line > len(lines) or evidence.end_line > len(lines):
                errors.append(
                    _issue(
                        "evidence_line_range",
                        f"{evidence.path!r} has {len(lines)} lines; requested "
                        f"{evidence.start_line}-{evidence.end_line}.",
                        question=question,
                        line=line,
                    )
                )
                continue
            excerpt = "\n".join(lines[evidence.start_line - 1 : evidence.end_line])
            actual = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
            if actual != evidence.excerpt_sha256.lower():
                errors.append(
                    _issue(
                        "evidence_hash_mismatch",
                        f"Excerpt SHA256 mismatch for {evidence.path!r}:"
                        f"{evidence.start_line}-{evidence.end_line}; actual {actual}.",
                        question=question,
                        line=line,
                    )
                )

    category_counter = Counter(question.category for _, question in records)
    split_counter = Counter(question.split for _, question in records)
    category_counts = {category: category_counter[category] for category in _CATEGORIES}
    split_counts = {split: split_counter[split] for split in _SPLITS}
    category_split_counts = {
        category: {
            split: sum(
                question.category == category and question.split == split for _, question in records
            )
            for split in _SPLITS
        }
        for category in _CATEGORIES
    }
    if pilot:
        if len(records) != 30:
            errors.append(
                _issue(
                    "pilot_question_count",
                    f"Pilot requires exactly 30 questions; found {len(records)}.",
                )
            )
        for category in _CATEGORIES:
            if category_counts[category] != 10:
                errors.append(
                    _issue(
                        "pilot_category_count",
                        f"Pilot requires 10 {category} questions; "
                        f"found {category_counts[category]}.",
                    )
                )
            for split in _SPLITS:
                if category_split_counts[category][split] == 0:
                    errors.append(
                        _issue(
                            "pilot_missing_split",
                            f"Pilot category {category!r} must contain {split!r} questions.",
                        )
                    )
                elif category_split_counts[category][split] != 5:
                    errors.append(
                        _issue(
                            "pilot_split_balance",
                            f"Pilot category {category!r} requires five {split!r} questions; "
                            f"found {category_split_counts[category][split]}.",
                        )
                    )

    # Catch worktree changes during evidence inspection; a report must never
    # quietly combine references from multiple source states.
    if snapshot_verified and eligible is not None:
        try:
            verify_snapshot(repository_path, expected_commit)
        except (IngestionError, OSError, ValueError) as exc:
            errors.append(_issue("snapshot_changed_during_validation", str(exc)))
    return ValidationReport(
        dataset_path=str(dataset_path.resolve()),
        dataset_sha256=digest,
        repository=str(repository_path),
        expected_commit=expected_commit,
        validated_at=datetime.now(UTC),
        question_count=len(records),
        category_counts=category_counts,
        split_counts=split_counts,
        category_split_counts=category_split_counts,
        require_reviewed=require_reviewed,
        pilot=pilot,
        discovery_policy=effective_policy,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def export_benchmark_schema(path: str | Path) -> None:
    """Write the strict per-record JSON Schema for benchmark authoring."""

    Path(path).write_text(
        json.dumps(BenchmarkQuestion.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

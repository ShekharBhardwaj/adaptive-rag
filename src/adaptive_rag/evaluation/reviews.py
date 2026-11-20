"""Blinded human scoring bound to immutable, exact generated output.

These files are reviewer-only artifacts: reference answers and benchmark
annotations must never be fed to answer generation or future routing.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import AwareDatetime, Field, FiniteFloat

from adaptive_rag.models import BenchmarkQuestion, ContentSHA256, NonBlank, ResearchModel

from .benchmark import _reject_json_constant, _unique_json_object

if TYPE_CHECKING:
    from .experiment_models import ExperimentRecord

Score = Annotated[FiniteFloat, Field(ge=0, le=1, strict=True)]


class HumanScore(ResearchModel):
    schema_version: Literal["1"] = "1"
    run_id: NonBlank
    job_id: NonBlank
    output_sha256: ContentSHA256
    reviewer: NonBlank
    reviewed_at: AwareDatetime
    correctness: Score
    citation_support: Score | None = None
    notes: NonBlank
    rubric_version: Literal["manual-v1"] = "manual-v1"


def output_sha256(record: ExperimentRecord) -> str:
    """Digest canonical full AnswerResult JSON, including its recorded raw calls.

    The digest binds the exact frozen result. It does not bind mutable aggregate
    metrics or human scores. A missing answer cannot receive a review score.
    """

    if record.answer is None:
        raise ValueError(f"job {record.job_id!r} has no answer output to review")
    raw = json.dumps(
        record.answer.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _record_map(records: Sequence[ExperimentRecord]) -> dict[tuple[str, str], ExperimentRecord]:
    indexed: dict[tuple[str, str], ExperimentRecord] = {}
    for record in records:
        key = (record.run_id, record.job_id)
        if key in indexed:
            raise ValueError(f"duplicate experiment output: {key}")
        indexed[key] = record
    return indexed


def validate_reviews(
    records: Sequence[ExperimentRecord],
    scores: Sequence[HumanScore],
    *,
    questions: Sequence[BenchmarkQuestion] | None = None,
) -> dict[tuple[str, str], HumanScore]:
    """Reject duplicate, unknown, stale, and missing-output scores.

    Reviewer identity/notes are recorded attestations, not automated proof that a
    human carried out an independent review. Missing scores remain pending.
    """

    indexed = _record_map(records)
    known_questions = (
        {question.id: question for question in questions} if questions is not None else None
    )
    validated: dict[tuple[str, str], HumanScore] = {}
    for score in scores:
        key = (score.run_id, score.job_id)
        if key in validated:
            raise ValueError(f"duplicate human score: {key}")
        record = indexed.get(key)
        if record is None:
            raise ValueError(f"human score refers to unknown experiment output: {key}")
        if known_questions is not None and record.question_id not in known_questions:
            raise ValueError(f"unknown benchmark question: {record.question_id!r}")
        if known_questions is not None:
            from .experiment_models import question_sha256

            if record.question_sha256 != question_sha256(known_questions[record.question_id]):
                raise ValueError(f"benchmark question differs from experiment output: {key}")
        if record.answer is None or not record.answer.answer or not record.answer.answer.strip():
            raise ValueError(f"human score requires recorded answer text: {key}")
        if score.output_sha256 != output_sha256(record):
            raise ValueError(f"human score refers to modified or stale output: {key}")
        if score.reviewed_at < record.created_at:
            raise ValueError(f"human review cannot predate experiment output: {key}")
        validated[key] = score
    return validated


def load_reviews(path: str | Path) -> tuple[HumanScore, ...]:
    """Strict UTF-8 JSONL; all records must validate before any are returned."""

    raw = Path(path).read_text(encoding="utf-8")
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    scores: list[HumanScore] = []
    keys: set[tuple[str, str]] = set()
    for number, line in enumerate(lines, 1):
        try:
            if not line.strip():
                raise ValueError("blank JSONL record")
            score = HumanScore.model_validate(
                json.loads(
                    line,
                    object_pairs_hook=_unique_json_object,
                    parse_constant=_reject_json_constant,
                )
            )
            key = (score.run_id, score.job_id)
            if key in keys:
                raise ValueError(f"duplicate human score: {key}")
        except (ValueError, RecursionError) as exc:
            raise ValueError(f"invalid human score on line {number}: {exc}") from exc
        keys.add(key)
        scores.append(score)
    if not scores:
        raise ValueError("review file contains no human scores")
    return tuple(scores)


def export_review_template(
    records: Sequence[ExperimentRecord],
    questions: Sequence[BenchmarkQuestion] | Mapping[str, BenchmarkQuestion],
    *,
    seed: int = 0,
) -> tuple[dict[str, Any], ...]:
    """Create shuffled blinded items; no conditions, categories, or repetitions.

    Raw job IDs are opaque in harness output. A further review_id hash is
    included for display. The reviewer copies only the nested score object into
    the scores JSONL after filling every null field except citation_support.
    Conditions may still be inferred from answer content; blinding is limited.
    """

    _record_map(records)
    from .experiment_models import question_sha256

    by_id = dict(questions) if isinstance(questions, Mapping) else {q.id: q for q in questions}
    items: list[dict[str, Any]] = []
    for record in records:
        if record.answer is None or not record.answer.answer or not record.answer.answer.strip():
            continue
        question = by_id.get(record.question_id)
        if question is None:
            raise ValueError(f"unknown benchmark question: {record.question_id!r}")
        if record.question_sha256 != question_sha256(question):
            raise ValueError(
                f"benchmark question differs from experiment output: {record.job_id!r}"
            )
        digest = output_sha256(record)
        review_id = hashlib.sha256(f"{seed}:{record.run_id}:{record.job_id}".encode()).hexdigest()
        items.append(
            {
                "schema_version": "1",
                "review_id": review_id,
                "rubric": {
                    "version": "manual-v1",
                    "correctness": "0 = incorrect; 0.5 = partially correct; 1 = fully correct. "
                    "Intermediate scores require justification in notes.",
                    "citation_support": "0 to 1 semantic support of answer claims by cited source; "
                    "null when not applicable. Inspect the source, not just citation IDs.",
                },
                "question": question.question,
                "reference_answer": question.ground_truth_answer,
                "gold_evidence": [ref.model_dump(mode="json") for ref in question.evidence],
                "repo_commit": question.repo_commit,
                "generated_answer": record.answer.answer,
                "citations": [ref.model_dump(mode="json") for ref in record.answer.citations],
                "citation_claims": list(record.answer.citation_claims),
                "score": {
                    "schema_version": "1",
                    "run_id": record.run_id,
                    "job_id": record.job_id,
                    "output_sha256": digest,
                    "reviewer": None,
                    "reviewed_at": None,
                    "correctness": None,
                    "citation_support": None,
                    "notes": None,
                    "rubric_version": "manual-v1",
                },
            }
        )
    random.Random(seed).shuffle(items)
    return tuple(items)

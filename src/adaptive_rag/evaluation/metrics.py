"""Mechanical evidence measurements; semantic correctness requires human review.

Range recall gives each annotated source range equal weight and requires complete
coverage by the union of returned lines. Line recall weights unique gold lines.
Neither measures answer correctness or the relevance of extra retrieved material.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

from pydantic import Field, FiniteFloat

from adaptive_rag.models import BenchmarkQuestion, ResearchModel
from adaptive_rag.retrieval.models import EvidenceChunk

if TYPE_CHECKING:
    from adaptive_rag.generation.models import AnswerResult

Fraction = Annotated[FiniteFloat, Field(ge=0, le=1)]


class MechanicalMetrics(ResearchModel):
    evidence_recall: Fraction
    evidence_line_recall: Fraction
    citation_validity: Fraction | None = None
    # Intentionally pending. ID/range checks cannot establish these semantics.
    answer_correctness: None = None
    citation_correctness: None = None
    retrieval_relevance: None = None


def _merge(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _retrieved_ranges(
    question: BenchmarkQuestion, evidence: Sequence[EvidenceChunk]
) -> dict[str, list[tuple[int, int]]]:
    ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for chunk in evidence:
        if chunk.repo_commit == question.repo_commit:
            ranges[chunk.path].append((chunk.start_line, chunk.end_line))
    return {path: _merge(values) for path, values in ranges.items()}


def evidence_recall(question: BenchmarkQuestion, evidence: Sequence[EvidenceChunk]) -> float:
    """Fraction of gold ranges fully covered at the same path and commit.

    Overlapping/adjacent retrieved chunks can jointly cover a gold range. Extra
    source lines do not reduce recall. The no-retrieval baseline scores zero.
    """

    ranges = _retrieved_ranges(question, evidence)
    covered = sum(
        any(
            start <= ref.start_line and end >= ref.end_line
            for start, end in ranges.get(ref.path, ())
        )
        for ref in question.evidence
    )
    return covered / len(question.evidence)


def evidence_line_recall(question: BenchmarkQuestion, evidence: Sequence[EvidenceChunk]) -> float:
    """Fraction of unique annotated gold lines returned at the same commit/path."""

    gold: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for ref in question.evidence:
        gold[ref.path].append((ref.start_line, ref.end_line))
    ranges = _retrieved_ranges(question, evidence)
    total = covered = 0
    for path, references in gold.items():
        for start, end in _merge(references):
            total += end - start + 1
            for found_start, found_end in ranges.get(path, ()):
                covered += max(0, min(end, found_end) - max(start, found_start) + 1)
    return covered / total


def citation_validity(
    claimed_ids: Sequence[str], evidence: Sequence[EvidenceChunk]
) -> float | None:
    """Share of supplied citation ID occurrences present in returned evidence.

    Repeated claims remain repeated denominator entries. No claims is N/A,
    including an answer that omits needed citations. Semantic support and
    citation completeness must be judged separately.
    """

    if not claimed_ids:
        return None
    known = {chunk.id for chunk in evidence}
    return sum(identifier in known for identifier in claimed_ids) / len(claimed_ids)


def compute_mechanical_metrics(
    question: BenchmarkQuestion,
    evidence: Sequence[EvidenceChunk],
    answer: AnswerResult | None = None,
) -> MechanicalMetrics:
    return MechanicalMetrics(
        evidence_recall=evidence_recall(question, evidence),
        evidence_line_recall=evidence_line_recall(question, evidence),
        citation_validity=citation_validity(answer.citation_claims, evidence)
        if answer is not None
        else None,
    )

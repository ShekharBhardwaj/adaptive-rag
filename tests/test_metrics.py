from datetime import UTC, datetime

import pytest

from adaptive_rag.evaluation.metrics import (
    citation_validity,
    compute_mechanical_metrics,
    evidence_line_recall,
    evidence_recall,
)
from adaptive_rag.generation.models import AnswerResult
from adaptive_rag.models import BenchmarkQuestion, EvidenceReference
from adaptive_rag.retrieval.models import EvidenceChunk


def question(*ranges):
    return BenchmarkQuestion(
        id="fixture",
        question="What does the fixture implement?",
        category="conceptual",
        ground_truth_answer="A synthetic metric fixture.",
        evidence=tuple(
            EvidenceReference(path=path, start_line=start, end_line=end, excerpt_sha256="a" * 64)
            for path, start, end in (ranges or (("a.py", 1, 4),))
        ),
        repo_commit="b" * 40,
        provenance=dict(
            author="Fixture author",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            method="source_inspection",
            notes="Synthetic test only.",
        ),
        difficulty="easy",
        split="development",
    )


def chunk(start=1, end=4, path="a.py", commit="b" * 40, identifier="c" * 64):
    return EvidenceChunk(
        id=identifier,
        path=path,
        start_line=start,
        end_line=end,
        excerpt_sha256="d" * 64,
        repo_commit=commit,
        text="synthetic fixture",
    )


def test_adjacent_chunks_jointly_cover_whole_range():
    evidence = (chunk(1, 2), chunk(3, 4))
    assert evidence_recall(question(), evidence) == 1
    assert evidence_line_recall(question(), evidence) == 1


def test_partial_range_and_unique_line_weighting_are_distinct():
    gold = question(("a.py", 1, 4), ("a.py", 3, 8), ("b.py", 1, 2))
    evidence = (chunk(1, 4), chunk(2, 5), chunk(1, 1, "b.py"))
    assert evidence_recall(gold, evidence) == pytest.approx(1 / 3)
    assert evidence_line_recall(gold, evidence) == pytest.approx(6 / 10)


@pytest.mark.parametrize(
    "evidence",
    [(), (chunk(commit="e" * 40),), (chunk(path="other.py"),), (chunk(5, 8),)],
)
def test_no_matching_source_has_zero_recall(evidence):
    assert evidence_recall(question(), evidence) == 0
    assert evidence_line_recall(question(), evidence) == 0


def test_overlaps_and_duplicate_chunks_never_inflate_line_recall():
    evidence = (chunk(1, 8), chunk(1, 8), chunk(2, 3))
    assert evidence_line_recall(question(), evidence) == 1


def test_citation_validity_counts_occurrences_and_empty_is_not_perfect():
    assert citation_validity((), (chunk(),)) is None
    assert citation_validity(("c" * 64, "missing", "missing"), (chunk(),)) == pytest.approx(1 / 3)
    assert citation_validity(("missing",), ()) == 0


def test_mechanical_metrics_do_not_claim_semantic_correctness():
    answer = AnswerResult(
        status="completed", answer="An unchecked claim", citation_claims=("c" * 64,)
    )
    metrics = compute_mechanical_metrics(question(), (chunk(),), answer)
    assert metrics.evidence_recall == metrics.citation_validity == 1
    assert metrics.answer_correctness is None
    assert metrics.citation_correctness is None
    assert metrics.retrieval_relevance is None
    assert compute_mechanical_metrics(question(), ()).citation_validity is None

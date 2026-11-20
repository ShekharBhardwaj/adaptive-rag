from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptive_rag.models import BenchmarkQuestion, EvidenceProvenance, EvidenceReference


def evidence(**changes):
    return {
        "path": "src/module.py",
        "start_line": 1,
        "end_line": 2,
        "excerpt_sha256": "b" * 64,
        **changes,
    }


def test_question_schema_roundtrip_and_unknown_keys():
    now = datetime.now(UTC).isoformat()
    raw = dict(
        id="fixture-1",
        question="What does this fixture do?",
        category="conceptual",
        ground_truth_answer="A synthetic schema fixture, never a benchmark result.",
        evidence=[evidence()],
        repo_commit="a" * 40,
        provenance=dict(
            author="Author",
            created_at=now,
            method="source_inspection",
            notes="Unit test fixture only.",
        ),
        difficulty="easy",
        split="development",
    )
    question = BenchmarkQuestion.model_validate(raw)
    assert BenchmarkQuestion.model_validate_json(question.model_dump_json()) == question
    with pytest.raises(ValidationError):
        BenchmarkQuestion.model_validate({**raw, "unexpected": "setting"})
    with pytest.raises(ValidationError):
        question.split = "held_out"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../file",
        "a/../file",
        "a\\b",
        "a//b",
        "./file",
        ".",
        "a\nb",
        "a\x00b",
        "C:/file.py",
    ],
)
def test_evidence_rejects_unsafe_paths(path):
    with pytest.raises(ValidationError):
        EvidenceReference(**evidence(path=path))


@pytest.mark.parametrize(
    "changes",
    [
        {"start_line": 0},
        {"end_line": 0},
        {"start_line": 3, "end_line": 2},
        {"start_line": True},
        {"end_line": "2"},
        {"excerpt_sha256": "invalid"},
    ],
)
def test_evidence_rejects_invalid_ranges_and_hashes(changes):
    with pytest.raises(ValidationError):
        EvidenceReference(**evidence(**changes))


def test_evidence_preserves_legal_filename_whitespace():
    assert EvidenceReference(**evidence(path="dir/ file.py ")).path == "dir/ file.py "


def test_review_requires_independence_timezone_and_chronology():
    now = datetime.now(UTC)
    provenance = dict(
        author="Researcher", created_at=now, method="source_inspection", notes="Checked"
    )
    review = dict(
        reviewer="researcher", reviewed_at=now, method="source_inspection", notes="Checked"
    )
    with pytest.raises(ValidationError, match="different"):
        EvidenceProvenance(**provenance, review=review)
    with pytest.raises(ValidationError, match="predate"):
        EvidenceProvenance(
            **provenance,
            review={**review, "reviewer": "Other", "reviewed_at": now - timedelta(days=1)},
        )
    with pytest.raises(ValidationError):
        EvidenceProvenance(**{**provenance, "created_at": now.replace(tzinfo=None)})

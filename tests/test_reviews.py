import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptive_rag.evaluation.experiment_models import ExperimentRecord, question_sha256
from adaptive_rag.evaluation.reviews import (
    HumanScore,
    export_review_template,
    load_reviews,
    output_sha256,
    validate_reviews,
)
from adaptive_rag.generation.models import AnswerResult
from adaptive_rag.models import BenchmarkQuestion
from adaptive_rag.retrieval.models import RetrievalResult

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def question():
    return BenchmarkQuestion(
        id="fixture",
        question="What is the fixture?",
        category="structural",
        ground_truth_answer="A synthetic review fixture.",
        evidence=[dict(path="a.py", start_line=1, end_line=2, excerpt_sha256="a" * 64)],
        repo_commit="b" * 40,
        provenance=dict(
            author="Fixture author", created_at=NOW, method="source_inspection", notes="Synthetic"
        ),
        difficulty="easy",
        split="development",
    )


def record(**changes):
    return ExperimentRecord(
        **{
            "run_id": "run-uuid",
            "job_id": "c" * 64,
            "question_id": "fixture",
            "question_sha256": question_sha256(question()),
            "category": "structural",
            "split": "development",
            "condition": "vectorless",
            "repetition": 0,
            "created_at": NOW,
            "status": "completed",
            "answer": AnswerResult(status="completed", answer="Synthetic output"),
            "retrieval": RetrievalResult(
                strategy="vectorless",
                query=question().question,
                repo_commit=question().repo_commit,
                corpus_fingerprint="d" * 64,
                status="completed",
            ),
            **changes,
        }
    )


def score(result=None, **changes):
    result = result or record()
    return HumanScore(
        **{
            "run_id": result.run_id,
            "job_id": result.job_id,
            "output_sha256": output_sha256(result),
            "reviewer": "Independent person",
            "reviewed_at": NOW + timedelta(hours=1),
            "correctness": 0.5,
            "notes": "Synthetic score, no research result.",
            **changes,
        }
    )


def test_score_validates_exact_output_and_missing_scores_remain_missing():
    result = record()
    assert validate_reviews([result], []) == {}
    assert validate_reviews([result], [score()], questions=[question()]) == {
        (result.run_id, result.job_id): score()
    }


def test_score_is_rejected_after_any_answer_output_change():
    result = record(answer=AnswerResult(status="completed", answer="Changed output"))
    with pytest.raises(ValueError, match="stale"):
        validate_reviews([result], [score()])
    assert output_sha256(record()) != output_sha256(result)


@pytest.mark.parametrize(
    "scores,match",
    [([score(), score()], "duplicate"), ([score(run_id="other")], "unknown")],
)
def test_duplicate_and_unknown_reviews_rejected(scores, match):
    with pytest.raises(ValueError, match=match):
        validate_reviews([record()], scores)


def test_partial_failed_output_can_be_reviewed_but_predating_reviews_rejected():
    result = record(status="error")
    assert validate_reviews([result], [score()])
    with pytest.raises(ValueError, match="predate"):
        validate_reviews([record()], [score(reviewed_at=NOW - timedelta(seconds=1))])


def test_missing_answer_cannot_be_hashed_or_reviewed():
    with pytest.raises(ValueError, match="no answer"):
        output_sha256(record(status="error", answer=None))


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewer": " "},
        {"notes": ""},
        {"reviewed_at": NOW.replace(tzinfo=None)},
        {"correctness": True},
        {"correctness": -0.1},
        {"correctness": float("nan")},
        {"citation_support": 1.1},
        {"rubric_version": "llm-v1"},
    ],
)
def test_human_scores_require_valid_recorded_rubric(changes):
    with pytest.raises(ValidationError):
        score(**changes)


def test_review_template_blinds_conditions_and_preserves_reference_only_here():
    results = [record(job_id=f"{i:064x}", repetition=i) for i in range(8)]
    first = export_review_template(results, [question()], seed=4)
    assert first == export_review_template(results, {"fixture": question()}, seed=4)
    assert first != export_review_template(results, [question()], seed=5)
    assert first[0]["reference_answer"] == question().ground_truth_answer
    assert first[0]["generated_answer"] == "Synthetic output"
    assert first[0]["score"]["correctness"] is None
    serialized = json.dumps(first)
    for forbidden in ('"condition"', '"category"', '"repetition"', '"vectorless"'):
        assert forbidden not in serialized
    assert len({item["review_id"] for item in first}) == len(results)


def test_stale_benchmark_rejected_before_template_and_score_attachment():
    changed = question().model_copy(update={"ground_truth_answer": "Changed annotation"})
    with pytest.raises(ValueError, match="benchmark question differs"):
        export_review_template([record()], [changed])
    with pytest.raises(ValueError, match="benchmark question differs"):
        validate_reviews([record()], [score()], questions=[changed])
    assert export_review_template([record(status="error", answer=None)], [question()]) == ()


def test_review_jsonl_roundtrip(tmp_path):
    path = tmp_path / "reviews.jsonl"
    path.write_text(score().model_dump_json() + "\n")
    assert load_reviews(path) == (score(),)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "\n",
        '{"run_id":"a","run_id":"b"}',
        '{"correctness":NaN}',
        score().model_dump_json() + "\n" + score().model_dump_json(),
        score().model_dump_json() + "\n\n",
    ],
)
def test_review_jsonl_is_strict_and_all_or_nothing(tmp_path, raw):
    path = tmp_path / "reviews.jsonl"
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_reviews(path)

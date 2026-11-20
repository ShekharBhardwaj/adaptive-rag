import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptive_rag.evaluation.analysis import aggregate_results
from adaptive_rag.evaluation.experiment_models import ExperimentRecord, PlannedJob
from adaptive_rag.evaluation.reviews import HumanScore, output_sha256
from adaptive_rag.generation.models import AnswerResult
from adaptive_rag.retrieval.models import ModelCallRecord, RetrievalResult, TokenUsage

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def job(question="q1", condition="vectorless", repetition=0):
    identifier = hashlib.sha256(f"{question}:{condition}:{repetition}".encode()).hexdigest()
    return PlannedJob(
        job_id=identifier, question_id=question, condition=condition, repetition=repetition
    )


def record(plan=None, **changes):
    plan = plan or job()
    return ExperimentRecord(
        **{
            **plan.model_dump(),
            "run_id": "run-uuid",
            "question_sha256": "a" * 64,
            "category": "conceptual",
            "split": "development",
            "created_at": NOW,
            "status": "completed",
            "answer": AnswerResult(status="completed", answer="Synthetic output"),
            "retrieval": RetrievalResult(
                strategy=plan.condition,
                query="Synthetic fixture question",
                repo_commit="b" * 40,
                corpus_fingerprint="c" * 64,
                status="completed",
            )
            if plan.condition != "no_retrieval"
            else None,
            "elapsed_seconds": 2,
            "estimated_cost_usd": 1,
            **changes,
        }
    )


def score(result, correctness=0.5):
    return HumanScore(
        run_id=result.run_id,
        job_id=result.job_id,
        output_sha256=output_sha256(result),
        reviewer="Independent fixture reviewer",
        reviewed_at=NOW + timedelta(hours=1),
        correctness=correctness,
        notes="Synthetic test only.",
    )


def test_planned_denominators_retain_failures_missing_and_pending_reviews():
    plans = [job(repetition=i) for i in range(4)]
    results = [
        record(plans[0]),
        record(plans[1], status="error", answer=None),
        record(plans[2], status="budget_exhausted", answer=None),
    ]
    report = aggregate_results(results, plans)
    summary = report["conditions"]["vectorless"]
    assert report["planned"] == 4
    assert report["observed"] == 3
    assert summary["missing"] == summary["completed"] == summary["error"] == 1
    assert summary["budget_exhausted"] == 1
    assert summary["completion_rate"] == 0.25
    assert summary["pending_completed_reviews"] == 1
    assert summary["measurements_observed"]["correctness"]["mean"] is None
    assert summary["failure_aware_correctness"] == {
        "mean": None,
        "mean_resolved_only": 0,
        "resolved": 2,
        "failed_as_zero": 2,
        "pending": 2,
        "planned": 4,
        "coverage": 0.5,
    }


def test_partial_failed_review_does_not_change_failure_aware_zero():
    plans = [job(repetition=i) for i in range(3)]
    results = [record(plans[0]), record(plans[1], status="error"), record(plans[2], status="error")]
    report = aggregate_results(results, plans, scores=[score(results[0]), score(results[1], 1.0)])
    summary = report["conditions"]["vectorless"]
    assert summary["reviewed_outputs"] == 2
    assert summary["reviewed_completed"] == 1
    assert summary["pending_completed_reviews"] == 0
    assert summary["measurements_observed"]["correctness"]["mean"] == 0.75
    assert summary["failure_aware_correctness"]["mean"] == pytest.approx(0.5 / 3)


def test_unknown_usage_and_cost_are_never_imputed_as_zero():
    plans = [job(repetition=i) for i in range(2)]
    results = [
        record(plans[0], usage=TokenUsage(input_tokens=10, output_tokens=3), estimated_cost_usd=5),
        record(
            plans[1],
            usage=TokenUsage(input_tokens=None, output_tokens=None),
            estimated_cost_usd=None,
        ),
    ]
    summary = aggregate_results(results, plans)["conditions"]["vectorless"]["measurements_observed"]
    assert summary["total_tokens"] == {
        "mean": 13,
        "sum": None,
        "sum_known": 13,
        "known": 1,
        "unknown": 1,
        "coverage": 0.5,
    }
    assert summary["estimated_cost_usd"]["mean"] == 5
    assert summary["estimated_cost_usd"]["unknown"] == 1


def test_latency_and_tokens_include_observed_failures():
    plans = [job(repetition=i) for i in range(2)]
    results = [
        record(plans[0], elapsed_seconds=2),
        record(plans[1], status="error", elapsed_seconds=10),
    ]
    measurements = aggregate_results(results, plans)["conditions"]["vectorless"][
        "measurements_observed"
    ]
    assert measurements["latency_seconds"]["mean"] == 6
    assert measurements["latency_seconds"]["known"] == 2


def paired_fixture():
    plans, results = [], []
    for question, left, right in [("q1", [2, 4], [1, 1]), ("q2", [10, 14], [2, 2])]:
        for condition, times in [("vectorless", left), ("no_retrieval", right)]:
            for repetition, latency in enumerate(times):
                plan = job(question, condition, repetition)
                plans.append(plan)
                results.append(record(plan, elapsed_seconds=latency))
    return plans, results


def comparison(report, metric="latency_seconds"):
    return next(item for item in report["paired_comparisons"] if item["metric"] == metric)


def test_pairing_bootstraps_question_means_not_individual_repetitions():
    plans, results = paired_fixture()
    report = aggregate_results(
        results, plans, comparisons=[("vectorless", "no_retrieval")], bootstrap_samples=300, seed=9
    )
    paired = comparison(report)
    assert paired["paired_questions"] == 2
    assert paired["paired_question_ids"] == ["q1", "q2"]
    assert paired["mean_difference"] == 6
    assert paired["ci95_percentile_bootstrap"] == [2, 10]
    assert report == aggregate_results(
        list(reversed(results)),
        list(reversed(plans)),
        comparisons=[("vectorless", "no_retrieval")],
        bootstrap_samples=300,
        seed=9,
    )
    json.dumps(report, allow_nan=False)


def test_pairing_reports_missing_repetitions_and_unreviewed_answers():
    plans, results = paired_fixture()
    report = aggregate_results(
        results[1:], plans, comparisons=[("vectorless", "no_retrieval")], bootstrap_samples=20
    )
    assert comparison(report)["paired_questions"] == 1
    assert comparison(report)["unresolved_questions"] == 1
    assert comparison(report)["mean_difference"] == 10
    assert comparison(report, "correctness")["paired_questions"] == 0
    assert comparison(report, "correctness")["mean_difference"] is None
    assert comparison(report, "correctness")["ci95_percentile_bootstrap"] is None


def test_all_missing_plan_is_explicitly_unresolved():
    plans = [job(), job(condition="no_retrieval")]
    report = aggregate_results([], plans, bootstrap_samples=10)
    assert report["observed"] == 0
    assert report["missing"] == 2
    assert report["conditions"]["vectorless"]["failure_aware_correctness"]["pending"] == 1
    assert comparison(report)["paired_questions"] == 0


@pytest.mark.parametrize(
    "results,plans,match",
    [
        ([record(), record()], [job()], "duplicate experiment"),
        ([record()], [job(), job()], "duplicate planned"),
        ([record()], [], "unplanned"),
        ([record(question_id="wrong")], [job()], "differs"),
        (
            [record(), record(job(repetition=1), run_id="other")],
            [job(), job(repetition=1)],
            "one run",
        ),
    ],
)
def test_integrity_failures_are_rejected(results, plans, match):
    with pytest.raises(ValueError, match=match):
        aggregate_results(results, plans)


@pytest.mark.parametrize("samples", [0, -1, True, 1.5])
def test_bootstrap_requires_positive_sample_count(samples):
    with pytest.raises(ValueError, match="bootstrap_samples"):
        aggregate_results([record()], [job()], bootstrap_samples=samples)


def test_no_fictitious_condition_comparisons():
    with pytest.raises(ValueError, match="distinct planned conditions"):
        aggregate_results([record()], [job()], comparisons=[("vectorless", "adaptive")])


@pytest.mark.parametrize(
    "changes",
    [
        {"answer": None},
        {"answer": AnswerResult(status="completed", answer=" ")},
        {"answer": AnswerResult(status="error", answer="Partial")},
        {"retrieval": None},
        {"retrieval": record().retrieval.model_copy(update={"status": "error"})},
        {"retrieval": record().retrieval.model_copy(update={"strategy": "agentic"})},
    ],
)
def test_completed_record_requires_completed_matching_stages(changes):
    with pytest.raises(ValidationError, match="completed"):
        record(**changes)


def test_no_retrieval_cannot_hide_retrieval_output_even_in_failed_records():
    for status in ("completed", "error", "budget_exhausted"):
        with pytest.raises(ValidationError, match="cannot contain retrieval"):
            record(job(condition="no_retrieval"), status=status, retrieval=record().retrieval)


def test_failed_records_preserve_partial_inconsistent_stages_for_diagnosis():
    result = record(
        status="error",
        answer=AnswerResult(status="error", answer="Partial synthetic output"),
        retrieval=record().retrieval.model_copy(update={"strategy": "agentic"}),
    )
    assert result.retrieval.strategy == "agentic"
    assert result.answer.answer == "Partial synthetic output"


def call(usage=None):
    return ModelCallRecord(
        operation="chat",
        model="synthetic-model",
        base_url="https://fixture.invalid/v1",
        request={},
        usage=usage if usage is not None else TokenUsage(input_tokens=4, output_tokens=3),
    )


@pytest.mark.parametrize(
    "usage",
    [
        TokenUsage(),
        TokenUsage(input_tokens=3, output_tokens=3),
        TokenUsage(input_tokens=4, output_tokens=2),
    ],
)
def test_recorded_provider_usage_cannot_be_undercounted(usage):
    with pytest.raises(ValidationError, match="below the sum"):
        record(model_calls=(call(),), usage=usage)


def test_recorded_unknown_usage_cannot_be_changed_to_zero():
    provider = call(TokenUsage(input_tokens=None, output_tokens=3))
    with pytest.raises(ValidationError, match="must remain unknown"):
        record(model_calls=(provider,), usage=TokenUsage(input_tokens=0, output_tokens=3))
    assert (
        record(
            model_calls=(provider,), usage=TokenUsage(input_tokens=None, output_tokens=3)
        ).usage.input_tokens
        is None
    )


def test_unrecorded_model_attempt_forces_unknown_usage():
    with pytest.raises(ValidationError, match="must remain unknown"):
        record(
            model_calls=(call(),),
            usage=TokenUsage(input_tokens=4, output_tokens=3),
            metadata={"model_attempts": 2},
        )
    result = record(
        model_calls=(call(),),
        usage=TokenUsage(input_tokens=None, output_tokens=None),
        metadata={"model_attempts": 2},
    )
    assert result.usage.total_tokens is None


@pytest.mark.parametrize("attempts", [0, -1, True, "1"])
def test_reserved_attempt_count_cannot_hide_recorded_calls(attempts):
    with pytest.raises(ValidationError, match="covering every recorded call"):
        record(
            model_calls=(call(),),
            usage=TokenUsage(input_tokens=4, output_tokens=3),
            metadata={"model_attempts": attempts},
        )

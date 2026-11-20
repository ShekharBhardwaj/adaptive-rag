"""Offline, failure-aware summaries and paired question-cluster uncertainty.

Raw output is never rewritten here. Missing accounting stays unknown. Bootstrap
samples resample questions after averaging their planned repetitions, not model
answers as if repetitions were independent benchmark questions.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import TYPE_CHECKING, Any

from .reviews import HumanScore, validate_reviews

if TYPE_CHECKING:
    from .experiment_models import ExperimentRecord

_METRICS = (
    "latency_seconds",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "tool_call_count",
    "routing_latency_seconds",
    "routing_input_tokens",
    "routing_output_tokens",
    "routing_total_tokens",
    "routing_model_calls",
    "evidence_recall",
    "evidence_line_recall",
    "citation_validity",
    "correctness",
    "citation_support",
    "failure_aware_correctness",
)


def _field(job: Any, name: str) -> Any:
    return job[name] if isinstance(job, Mapping) else getattr(job, name)


def _measurement(values: Sequence[float | int | None]) -> dict[str, Any]:
    known = [value for value in values if value is not None]
    return {
        "mean": fmean(known) if known else None,
        "sum": math.fsum(known) if len(known) == len(values) and known else None,
        "sum_known": math.fsum(known),
        "known": len(known),
        "unknown": len(values) - len(known),
        "coverage": len(known) / len(values) if values else None,
    }


def _metric_value(
    record: ExperimentRecord,
    metric: str,
    scores: Mapping[tuple[str, str], HumanScore],
) -> float | int | None:
    if metric.startswith("routing_"):
        route = record.routing
        if route is None:
            return None if record.condition in {"adaptive_rule", "adaptive_llm"} else 0
        if metric == "routing_latency_seconds":
            return route.elapsed_seconds
        if metric == "routing_model_calls":
            return route.metadata.get("model_attempts", len(route.model_calls))
        return getattr(route.usage, metric.removeprefix("routing_"))
    if metric == "latency_seconds":
        return record.elapsed_seconds
    if metric in {"input_tokens", "output_tokens", "total_tokens"}:
        return getattr(record.usage, metric)
    if metric in {"estimated_cost_usd", "tool_call_count"}:
        return getattr(record, metric)
    if metric in {"evidence_recall", "evidence_line_recall", "citation_validity"}:
        return getattr(record.metrics, metric) if record.metrics is not None else None
    if metric == "failure_aware_correctness" and record.status != "completed":
        return 0.0
    score = scores.get((record.run_id, record.job_id))
    if score is None:
        return None
    if metric in {"correctness", "failure_aware_correctness"}:
        return score.correctness
    if metric == "citation_support":
        return score.citation_support
    raise ValueError(f"unknown metric: {metric}")


def _condition_summary(
    records: Sequence[ExperimentRecord],
    planned: Sequence[Any],
    scores: Mapping[tuple[str, str], HumanScore],
) -> dict[str, Any]:
    statuses = Counter(record.status for record in records)
    completed = statuses["completed"]
    missing = len(planned) - len(records)
    reviewed = sum(
        record.status == "completed" and (record.run_id, record.job_id) in scores
        for record in records
    )
    failures = len(records) - completed
    resolved_values = [
        value
        for record in records
        if (value := _metric_value(record, "failure_aware_correctness", scores)) is not None
    ]
    pending = completed - reviewed + missing
    measurements = {
        metric: _measurement([_metric_value(record, metric, scores) for record in records])
        for metric in _METRICS
        if metric != "failure_aware_correctness"
    }
    cascades = [
        record.metadata["cascade"]
        for record in records
        if isinstance(record.metadata.get("cascade"), dict)
    ]
    cascade_summary = (
        {
            "cascade": {
                "observed": len(cascades),
                "escalated": sum(bool(item.get("escalated")) for item in cascades),
                "escalation_reasons": dict(
                    Counter(
                        item["escalation_reason"]
                        for item in cascades
                        if item.get("escalation_reason") is not None
                    )
                ),
                "escalations_not_admitted": sum(
                    item.get("escalation_not_admitted") is not None for item in cascades
                ),
                "final_strategies": dict(Counter(item.get("final_strategy") for item in cascades)),
                "fell_back_to_first_stage": sum(
                    bool(item.get("fell_back_to_first_stage")) for item in cascades
                ),
            }
        }
        if cascades
        else {}
    )
    return {
        **cascade_summary,
        "planned": len(planned),
        "observed": len(records),
        "missing": missing,
        "completed": completed,
        "error": statuses["error"],
        "budget_exhausted": statuses["budget_exhausted"],
        "interrupted": statuses["interrupted"],
        "completion_rate": completed / len(planned) if planned else None,
        "reviewed_completed": reviewed,
        "reviewed_outputs": sum((record.run_id, record.job_id) in scores for record in records),
        "pending_completed_reviews": completed - reviewed,
        "selected_strategies": dict(
            Counter(
                record.routing.selected_strategy
                for record in records
                if record.routing is not None and record.routing.selected_strategy is not None
            )
        ),
        "routing_statuses": dict(
            Counter(record.routing.status for record in records if record.routing is not None)
        ),
        "review_coverage_completed": reviewed / completed if completed else None,
        "measurements_observed": measurements,
        "failure_aware_correctness": {
            "mean": fmean(resolved_values) if resolved_values and not pending else None,
            "mean_resolved_only": fmean(resolved_values) if resolved_values else None,
            "resolved": len(resolved_values),
            "failed_as_zero": failures,
            "pending": pending,
            "planned": len(planned),
            "coverage": len(resolved_values) / len(planned) if planned else None,
        },
    }


def _quantile(ordered: Sequence[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _paired_metric(
    *,
    left: str,
    right: str,
    metric: str,
    planned: Mapping[str, Mapping[str, Sequence[Any]]],
    observed: Mapping[str, ExperimentRecord],
    scores: Mapping[tuple[str, str], HumanScore],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    left_questions, right_questions = set(planned[left]), set(planned[right])
    common = sorted(left_questions & right_questions)
    differences: list[float] = []
    paired_ids: list[str] = []
    for question_id in common:
        condition_means: list[float] = []
        for condition in (left, right):
            values: list[float | int] = []
            jobs = planned[condition][question_id]
            for job in jobs:
                record = observed.get(_field(job, "job_id"))
                value = _metric_value(record, metric, scores) if record is not None else None
                if value is None:
                    break
                values.append(value)
            if len(values) != len(jobs):
                break
            condition_means.append(fmean(values))
        if len(condition_means) == 2:
            differences.append(condition_means[0] - condition_means[1])
            paired_ids.append(question_id)
    interval = None
    if differences:
        rng = random.Random(seed)
        count = len(differences)
        sampled_means = sorted(
            fmean(rng.choices(differences, k=count)) for _ in range(bootstrap_samples)
        )
        interval = [_quantile(sampled_means, 0.025), _quantile(sampled_means, 0.975)]
    return {
        "left": left,
        "right": right,
        "metric": metric,
        "difference": "left_minus_right",
        "unit": "question_mean_over_planned_repetitions",
        "planned_common_questions": len(common),
        "unmatched_planned_questions": len(left_questions ^ right_questions),
        "paired_questions": len(differences),
        "unresolved_questions": len(common) - len(differences),
        "paired_question_ids": paired_ids,
        "mean_difference": fmean(differences) if differences else None,
        "ci95_percentile_bootstrap": interval,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
    }


def aggregate_results(
    records: Sequence[ExperimentRecord],
    planned_jobs: Sequence[Any],
    *,
    scores: Sequence[HumanScore] = (),
    bootstrap_samples: int = 2000,
    seed: int = 0,
    comparisons: Sequence[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Summarize exactly one run against its frozen planned-job denominator.

    Costs, latency, tokens, and tools include all observed runs, even failures.
    Means with unknown entries are explicitly available-case estimates. Failure
    aware correctness assigns observed unsuccessful attempts zero; missing jobs
    and unreviewed completed answers remain unresolved. Paired comparisons
    require every planned repetition to have that metric for both conditions.
    Index construction is deliberately outside these per-query results.
    """

    if type(bootstrap_samples) is not int or bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be a positive integer")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if len({record.run_id for record in records}) > 1:
        raise ValueError("aggregate exactly one run at a time")
    indexed_jobs: dict[str, Any] = {}
    planned_by_condition: dict[str, list[Any]] = defaultdict(list)
    planned_questions: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    tuples: set[tuple[str, str, int]] = set()
    for job in planned_jobs:
        job_id = _field(job, "job_id")
        identity = tuple(_field(job, field) for field in ("question_id", "condition", "repetition"))
        if job_id in indexed_jobs or identity in tuples:
            raise ValueError("duplicate planned experiment job")
        indexed_jobs[job_id] = job
        tuples.add(identity)
        planned_by_condition[_field(job, "condition")].append(job)
        planned_questions[_field(job, "condition")][_field(job, "question_id")].append(job)
    observed: dict[str, ExperimentRecord] = {}
    by_condition: dict[str, list[ExperimentRecord]] = defaultdict(list)
    for record in records:
        job = indexed_jobs.get(record.job_id)
        if job is None:
            raise ValueError(f"unplanned experiment output: {record.job_id!r}")
        if record.job_id in observed:
            raise ValueError(f"duplicate experiment output: {record.job_id!r}")
        if any(
            getattr(record, field) != _field(job, field)
            for field in ("question_id", "condition", "repetition")
        ):
            raise ValueError(f"experiment output differs from its planned job: {record.job_id!r}")
        observed[record.job_id] = record
        by_condition[record.condition].append(record)
    validated_scores = validate_reviews(records, scores)
    conditions = sorted(planned_by_condition)
    pairs = (
        list(itertools.combinations(conditions, 2)) if comparisons is None else list(comparisons)
    )
    for left, right in pairs:
        if left == right or left not in conditions or right not in conditions:
            raise ValueError("comparison requires two distinct planned conditions")
    return {
        "schema_version": "1",
        "run_id": records[0].run_id if records else None,
        "planned": len(planned_jobs),
        "observed": len(records),
        "missing": len(planned_jobs) - len(records),
        "observed_split_counts": dict(Counter(record.split for record in records)),
        "observed_category_counts": dict(Counter(record.category for record in records)),
        "conditions": {
            condition: _condition_summary(
                by_condition[condition], planned_by_condition[condition], validated_scores
            )
            for condition in conditions
        },
        "paired_comparisons": [
            _paired_metric(
                left=left,
                right=right,
                metric=metric,
                planned=planned_questions,
                observed=observed,
                scores=validated_scores,
                bootstrap_samples=bootstrap_samples,
                seed=seed,
            )
            for left, right in pairs
            for metric in _METRICS
        ],
        "methodology": {
            "correctness": "Independent manual-v1 reviews; absent reviews are pending.",
            "citation_validity": "Mechanical presence of citation ID in retrieved evidence; "
            "semantic citation correctness is separately reviewed as citation_support.",
            "observed_measurements": "Include unsuccessful attempts; known-value means report "
            "accounting coverage and do not impute missing usage or cost.",
            "failure_aware_correctness": "Observed unsuccessful attempts score zero. Missing "
            "jobs and unreviewed completed answers remain pending; full mean is withheld.",
            "pairing": "Question clusters averaged across all planned repetitions; exclude "
            "a question for a metric if any planned value on either side is unavailable.",
            "uncertainty": "Seeded paired question-cluster percentile bootstrap. Intervals "
            "are descriptive for this benchmark, not broad claims from a 30-question pilot. "
            "A single paired question gives a degenerate interval.",
            "scope": "Per-query measurements exclude separately recorded indexing costs. "
            "Split/category counts describe observed records; restrict the frozen job set "
            "before aggregation when reporting a particular split or category.",
        },
    }

"""Confirmatory comparisons for the phase 7 held-out protocol. Offline; no model requests.

Written on November 19, 2026, before any held-out score existed, and checked
against the development run. It rates nothing: scores come from a frozen score
file and are only validated and aggregated here. Nothing is written into a run.

The statistics are the project's own ``aggregate_results``: failure-aware
correctness over every planned job, and the paired question-cluster percentile
bootstrap with 2,000 samples and seed 0. A second recomputation from the raw
JSON, further down this file, must agree with it before anything is saved.

``paper/phase7-held-out-protocol.md`` fixes the three comparisons and how each
result is worded. Readings it leaves implicit are fixed here, before scores:

* An interval "excludes zero" only if the nearer endpoint is beyond zero. An
  endpoint at zero counts as including zero. Endpoints use a 1e-9 tolerance.
* "Within ten points either side of zero" includes exactly ten points.
* The protocol words the cost result. Elapsed time uses the same general rule,
  with "the cascade takes less time" as the direction.
* A job "that fails because the provider could not be reached" is an
  unsuccessful job with a recorded model request that raised a transport error,
  so no response arrived. The sensitivity analysis removes those jobs from the
  plan and the results, so a question's mean covers its remaining repetitions.
* Every answer text must have a score. If one is missing, nothing is computed.

Usage, from the repository root:

    R=experiments/reviews/adaptive-cascade-heldout-20261119-001
    .venv/bin/python experiments/analysis/heldout-confirmatory-20261119/confirmatory.py \
        --run experiments/raw/adaptive-cascade-heldout-20261119-001 \
        --scores $R/answers.ai-scores.jsonl \
        --template $R/answers.review-template.jsonl \
        --freeze $R/ai-review/scores-frozen.json \
        --attestation $R/shekhar-review-attestation.json \
        --outcome experiments/preflight/cascade-heldout-2026-11-19-001/outcome.json \
        --protocol paper/phase7-held-out-protocol.md \
        --output experiments/analysis/heldout-confirmatory-20261119/heldout-confirmatory.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path
from statistics import fmean
from typing import Any

from adaptive_rag.cli import _validate_frozen_run_inputs
from adaptive_rag.evaluation.analysis import aggregate_results
from adaptive_rag.evaluation.reviews import load_reviews, output_sha256, validate_reviews
from adaptive_rag.evaluation.storage import load_run

BOOTSTRAP_SAMPLES, SEED = 2000, 0
SIMILARITY_MARGIN = 0.10
TOLERANCE = 1e-9
AGREEMENT = 1e-12
RUBRIC = "experiments/reviews/adaptive-cascade-development-20261119-001/ai-review/rubric.json"
RUBRIC_SHA256 = "3c53c294e7bf1f645d774c09a78bf4465848cb73b503e3c456b7257086dff4af"

CASCADE, VECTOR, WRAPUP, AGENTIC = "adaptive_cascade", "vector", "agentic_wrapup", "agentic"
CONDITIONS = (VECTOR, AGENTIC, WRAPUP, CASCADE, "no_retrieval")
CORRECTNESS, COST, ELAPSED = "failure_aware_correctness", "estimated_cost_usd", "latency_seconds"

# The protocol's order. Every difference is left minus right.
COMPARISONS = (
    (1, CASCADE, VECTOR, (CORRECTNESS,)),
    (2, CASCADE, WRAPUP, (CORRECTNESS, COST, ELAPSED)),
    (3, WRAPUP, AGENTIC, (CORRECTNESS,)),
)

# A request that raised one of these received no response from the provider.
TRANSPORT_ERRORS = frozenset(
    {
        "ConnectTimeout",
        "ConnectError",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ReadError",
        "WriteError",
        "CloseError",
        "RemoteProtocolError",
        "ProxyError",
        "NetworkError",
        "TimeoutException",
        "TransportError",
    }
)

RATING_FIELDS = ("reviewer", "reviewed_at", "correctness", "citation_support", "notes")
CONTENT_FIELDS = (
    "question",
    "reference_answer",
    "gold_evidence",
    "repo_commit",
    "generated_answer",
    "citations",
    "citation_claims",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def strings(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)
    elif isinstance(node, str):
        yield node


# ----------------------------------------------------------------- wording rules


def direction_verdict(mean: float, low: float, high: float, *, claim_is_higher: bool) -> str:
    """Supported / Direction only / Not supported, for a claim about left minus right."""
    if not claim_is_higher:
        mean, low, high = -mean, -high, -low
    if mean <= TOLERANCE:
        return "Not supported"
    return "Supported" if low > TOLERANCE else "Direction only"


def similarity_verdict(low: float, high: float) -> str:
    inside = low >= -SIMILARITY_MARGIN - TOLERANCE and high <= SIMILARITY_MARGIN + TOLERANCE
    return "Similar" if inside else "Not distinguishable at this sample size"


def worded(number: int, metric: str, mean: float, low: float, high: float) -> dict[str, str]:
    if number == 2 and metric == CORRECTNESS:
        return {
            "rule": "quality against Agentic: similar only if the whole interval is within "
            "ten points either side of zero",
            "verdict": similarity_verdict(low, high),
        }
    if number == 2 and metric == COST:
        return {
            "rule": "efficiency: supported if the paired cost interval lies below zero; "
            "otherwise the general rule; stated together with the quality result",
            "verdict": direction_verdict(mean, low, high, claim_is_higher=False),
        }
    if number == 2 and metric == ELAPSED:
        return {
            "rule": "general rule, direction 'the cascade takes less time'; the protocol "
            "fixes wording for cost only",
            "verdict": direction_verdict(mean, low, high, claim_is_higher=False),
        }
    return {
        "rule": "general rule, direction 'left is more correct than right'",
        "verdict": direction_verdict(mean, low, high, claim_is_higher=True),
    }


# ------------------------------------------------------- plain-JSON recomputation


def _quantile(ordered: Sequence[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


class PlainRun:
    """The raw files read with ``json`` alone, without the project's models."""

    def __init__(self, run: Path, scores: Path) -> None:
        self.planned = json.loads((run / "manifest.json").read_text("utf-8"))["planned_jobs"]
        self.results: dict[str, tuple[str, float | None, float | None]] = {}
        with (run / "results.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    self.results[row["job_id"]] = (
                        row["status"],
                        row["estimated_cost_usd"],
                        row["elapsed_seconds"],
                    )
        self.ratings = {row["job_id"]: row["correctness"] for row in read_jsonl(scores)}

    def value(self, job_id: str, metric: str) -> float | None:
        row = self.results.get(job_id)
        if row is None:
            return None
        status, cost, elapsed = row
        if metric == CORRECTNESS:
            return 0.0 if status != "completed" else self.ratings.get(job_id)
        return cost if metric == COST else elapsed

    def paired(self, left: str, right: str, metric: str, dropped: frozenset[str]) -> dict[str, Any]:
        jobs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for job in self.planned:
            if job["job_id"] not in dropped:
                jobs[job["condition"]][job["question_id"]].append(job["job_id"])
        differences: list[float] = []
        question_ids: list[str] = []
        for question_id in sorted(set(jobs[left]) & set(jobs[right])):
            sides: list[float] = []
            for condition in (left, right):
                values = [self.value(job_id, metric) for job_id in jobs[condition][question_id]]
                if any(value is None for value in values):
                    break
                sides.append(fmean(values))
            if len(sides) == 2:
                differences.append(sides[0] - sides[1])
                question_ids.append(question_id)
        rng = random.Random(SEED)
        count = len(differences)
        sampled = sorted(fmean(rng.choices(differences, k=count)) for _ in range(BOOTSTRAP_SAMPLES))
        return {
            "paired_questions": count,
            "paired_question_ids": question_ids,
            "mean_difference": fmean(differences),
            "interval": [_quantile(sampled, 0.025), _quantile(sampled, 0.975)],
        }


# ------------------------------------------------------------------ comparisons


def comparisons(
    records: Sequence[Any],
    planned_jobs: Sequence[Any],
    scores: Sequence[Any],
    plain: PlainRun,
    dropped: frozenset[str] = frozenset(),
) -> tuple[list[dict[str, Any]], dict[str, Any], float]:
    """The three comparisons from ``aggregate_results``, checked against ``PlainRun``."""
    kept_records = [record for record in records if record.job_id not in dropped]
    kept_jobs = [job for job in planned_jobs if job.job_id not in dropped]
    kept_scores = [score for score in scores if score.job_id not in dropped]
    summary = aggregate_results(
        kept_records,
        kept_jobs,
        scores=kept_scores,
        bootstrap_samples=BOOTSTRAP_SAMPLES,
        seed=SEED,
        comparisons=[(left, right) for _, left, right, _ in COMPARISONS],
    )
    rows = {
        (row["left"], row["right"], row["metric"]): row for row in summary["paired_comparisons"]
    }
    output: list[dict[str, Any]] = []
    largest_gap = 0.0
    for number, left, right, metrics in COMPARISONS:
        for metric in metrics:
            row = rows[(left, right, metric)]
            if row["mean_difference"] is None or row["ci95_percentile_bootstrap"] is None:
                raise SystemExit(f"comparison {number} ({metric}) has no paired question")
            mean = row["mean_difference"]
            low, high = row["ci95_percentile_bootstrap"]
            check = plain.paired(left, right, metric, dropped)
            gaps = [
                abs(mean - check["mean_difference"]),
                abs(low - check["interval"][0]),
                abs(high - check["interval"][1]),
            ]
            largest_gap = max(largest_gap, *gaps)
            if max(gaps) > AGREEMENT or check["paired_question_ids"] != row["paired_question_ids"]:
                raise SystemExit(
                    f"comparison {number} ({metric}): the plain-JSON recomputation disagrees"
                )
            planned_common = row["planned_common_questions"]
            output.append(
                {
                    "comparison": number,
                    "left": left,
                    "right": right,
                    "difference": "left_minus_right",
                    "metric": metric,
                    "mean_difference": mean,
                    "interval_95": [low, high],
                    "paired_questions": row["paired_questions"],
                    "questions_left_out_for_unknown_values": planned_common
                    - row["paired_questions"],
                    "paired_question_ids": row["paired_question_ids"],
                    **worded(number, metric, mean, low, high),
                }
            )
    return output, summary, largest_gap


# ----------------------------------------------------------------- input checks


def score_checks(
    records: Sequence[Any], scores: Sequence[Any], template: Path
) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    scorable = {
        (record.run_id, record.job_id): output_sha256(record)
        for record in records
        if record.answer is not None and record.answer.answer and record.answer.answer.strip()
    }
    scored = {(score.run_id, score.job_id): score.output_sha256 for score in scores}
    missing = sorted(job_id for _, job_id in set(scorable) - set(scored))
    extra = sorted(job_id for _, job_id in set(scored) - set(scorable))
    if missing:
        problems.append(f"{len(missing)} answer texts have no score")
    if extra:
        problems.append(f"{len(extra)} scores have no answer text")
    rows = read_jsonl(template)
    bindings = {
        (row["score"]["run_id"], row["score"]["job_id"]): row["score"]["output_sha256"]
        for row in rows
    }
    if bindings != scorable:
        problems.append("the review template does not bind exactly the run's answer texts")
    template_ratings = sum(
        row["score"][field] is not None for row in rows for field in RATING_FIELDS
    )
    if template_ratings:
        problems.append("the blinded review template contains ratings")
    by_job = {score.job_id: score for score in scores}
    cases: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        content = json.dumps(
            {field: row[field] for field in CONTENT_FIELDS},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cases[hashlib.sha256(content.encode("utf-8")).hexdigest()].append(row["score"]["job_id"])
    inconsistent = []
    for digest, job_ids in sorted(cases.items()):
        ratings = {
            (by_job[job_id].correctness, by_job[job_id].citation_support)
            for job_id in job_ids
            if job_id in by_job
        }
        if len(ratings) > 1:
            inconsistent.append(
                {"case": digest[:12], "items": len(job_ids), "distinct_ratings": len(ratings)}
            )
    reviewed = sorted(score.reviewed_at for score in scores)
    return {
        "answer_texts": len(scorable),
        "scores": len(scored),
        "answer_texts_without_score": missing,
        "scores_without_answer_text": extra,
        "template_items": len(rows),
        "template_binds_exactly_the_answer_texts": bindings == scorable,
        "template_rating_fields_filled": template_ratings,
        "distinct_answer_cases": len(cases),
        "identical_cases_rated_differently": inconsistent,
        "correctness_values": {
            str(value): count
            for value, count in sorted(Counter(score.correctness for score in scores).items())
        },
        "correctness_values_outside_0_half_1": sum(
            score.correctness not in (0.0, 0.5, 1.0) for score in scores
        ),
        "reviewer_labels": dict(Counter(score.reviewer for score in scores)),
        "reviewed_at_first": reviewed[0].isoformat() if reviewed else None,
        "reviewed_at_last": reviewed[-1].isoformat() if reviewed else None,
    }, problems


def freeze_checks(
    freeze: Path, scores_sha256: str, template_sha256: str, rubric: Path
) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    document = json.loads(freeze.read_text("utf-8"))
    recorded = set(strings(document))
    rubric_now = sha256_file(rubric)
    checks = {
        "score_file_sha256_is_in_the_freeze_record": scores_sha256 in recorded,
        "template_sha256_is_in_the_freeze_record": template_sha256 in recorded,
        "protocol_rubric_sha256_is_in_the_freeze_record": RUBRIC_SHA256 in recorded,
        "protocol_rubric_file_is_unchanged": rubric_now == RUBRIC_SHA256,
    }
    problems += [name.replace("_", " ") + ": no" for name, passed in checks.items() if not passed]
    described = {
        key: document.get(key)
        for key in ("kind", "frozen_at", "reviewer", "reviewer_type", "human_review", "item_count")
    }
    return {"file": str(freeze), "sha256": sha256_file(freeze), **described, **checks}, problems


def outcome_checks(
    outcome: Path, run: Path, template: Path, template_sha256: str, protocol: Path | None
) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    document = json.loads(outcome.read_text("utf-8"))
    raw = document.get("raw_file_sha256") or {}
    changed = sorted(name for name, digest in raw.items() if sha256_file(run / name) != digest)
    if not raw:
        problems.append("the outcome record lists no raw file hashes")
    if changed:
        problems.append(f"raw run files differ from the outcome record: {changed}")
    derived = document.get("derived_artifacts") or {}
    template_matches = derived.get("review_template_sha256") == template_sha256
    if not template_matches:
        problems.append("the review template differs from the outcome record")
    packets = derived.get("review_packets_sha256")
    packets_changed = None
    if packets is not None:
        folder = template.parent / "review-packets"
        packets_changed = sorted(
            name for name, digest in packets.items() if sha256_file(folder / name) != digest
        )
        if packets_changed:
            problems.append(f"review packets differ from the outcome record: {packets_changed}")
    protocol_matches = None
    if document.get("protocol_sha256") is not None:
        if protocol is None:
            problems.append("the outcome record names a protocol; pass --protocol")
        else:
            protocol_matches = sha256_file(protocol) == document["protocol_sha256"]
            if not protocol_matches:
                problems.append("the protocol file differs from the outcome record")
    return {
        "file": str(outcome),
        "sha256": sha256_file(outcome),
        "raw_files_checked": len(raw),
        "raw_files_changed": changed,
        "review_template_matches": template_matches,
        "review_packets_checked": None if packets is None else len(packets),
        "review_packets_changed": packets_changed,
        "protocol_matches": protocol_matches,
    }, problems


# ------------------------------------------------------------------ description


def rating_class(record: Any, by_job: dict[str, Any]) -> str:
    if record.status != "completed":
        return "failed"
    correctness = by_job[record.job_id].correctness
    if correctness == 1.0:
        return "full"
    return "zero" if correctness == 0.0 else "partial"


def question_means(
    records: Sequence[Any], planned_jobs: Sequence[Any], by_job: dict[str, Any]
) -> dict[str, dict[str, float]]:
    """Failure-aware mean per condition and question over its planned repetitions."""
    observed = {record.job_id: record for record in records}
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for job in planned_jobs:
        record = observed[job.job_id]
        value = by_job[job.job_id].correctness if record.status == "completed" else 0.0
        values[job.condition][job.question_id].append(value)
    return {
        condition: {question_id: fmean(items) for question_id, items in sorted(questions.items())}
        for condition, questions in values.items()
    }


def describe(
    records: Sequence[Any],
    planned_jobs: Sequence[Any],
    scores: Sequence[Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    by_job = {score.job_id: score for score in scores}
    conditions: dict[str, Any] = {}
    for condition in CONDITIONS:
        block = summary["conditions"][condition]
        measured = block["measurements_observed"]
        classes = Counter(
            rating_class(record, by_job) for record in records if record.condition == condition
        )
        conditions[condition] = {
            "planned": block["planned"],
            "completed": block["completed"],
            "failed_counted_as_zero": block["failure_aware_correctness"]["failed_as_zero"],
            "rated_full": classes["full"],
            "rated_partial": classes["partial"],
            "rated_zero": classes["zero"],
            "failure_aware_correctness": block["failure_aware_correctness"]["mean"],
            "correctness_among_completed": measured["correctness"]["mean"],
            "citation_support_mean": measured["citation_support"]["mean"],
            "citation_support_rated": measured["citation_support"]["known"],
            "known_cost_usd": measured["estimated_cost_usd"]["sum_known"],
            "jobs_with_unknown_cost": measured["estimated_cost_usd"]["unknown"],
            "mean_known_cost_per_job_usd": measured["estimated_cost_usd"]["mean"],
            "mean_elapsed_seconds": measured["latency_seconds"]["mean"],
            "mean_evidence_recall": measured["evidence_recall"]["mean"],
        }
    means = question_means(records, planned_jobs, by_job)
    escalations: Counter[str] = Counter()
    cascade_classes: dict[str, Counter[str]] = {"escalated": Counter(), "not_escalated": Counter()}
    for record in records:
        if record.condition == CASCADE:
            escalated = bool(record.metadata["cascade"]["escalated"])
            escalations[record.question_id] += escalated
            key = "escalated" if escalated else "not_escalated"
            cascade_classes[key][rating_class(record, by_job)] += 1
    question_count = len(means[CASCADE])
    gain_escalated = math.fsum(
        means[CASCADE][question_id] - means[VECTOR][question_id]
        for question_id in means[CASCADE]
        if escalations[question_id]
    )
    gain_never = math.fsum(
        means[CASCADE][question_id] - means[VECTOR][question_id]
        for question_id in means[CASCADE]
        if not escalations[question_id]
    )
    sufficiency: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record.condition == VECTOR and record.status == "completed":
            reported = record.answer.metadata.get("evidence_sufficient")
            key = {True: "reported_sufficient", False: "reported_insufficient"}.get(
                reported, "none"
            )
            sufficiency[key][rating_class(record, by_job)] += 1
    return {
        "conditions": conditions,
        "cascade": {
            **summary["conditions"][CASCADE]["cascade"],
            "final_answers_when_escalated": dict(cascade_classes["escalated"]),
            "final_answers_when_not_escalated": dict(cascade_classes["not_escalated"]),
            "first_stage_answers_kept_and_rated_below_full": cascade_classes["not_escalated"][
                "partial"
            ]
            + cascade_classes["not_escalated"]["zero"],
            "questions_escalated_at_least_once": sum(bool(count) for count in escalations.values()),
            "cascade_minus_vector_from_questions_escalated_at_least_once": gain_escalated
            / question_count,
            "cascade_minus_vector_from_questions_never_escalated": gain_never / question_count,
        },
        "vector_sufficiency_report_by_rating": {
            "note": "Not in the protocol's list of descriptive results; shown for context.",
            **{key: dict(counter) for key, counter in sorted(sufficiency.items())},
        },
        "question_means": {
            question_id: {
                **{condition: means[condition][question_id] for condition in CONDITIONS},
                "cascade_escalations": escalations[question_id],
            }
            for question_id in sorted(means[CASCADE])
        },
    }


# ---------------------------------------------------------------------- loading


def load(run: Path, scores_path: Path) -> tuple[Any, Sequence[Any], Sequence[Any]]:
    loaded = load_run(run)
    questions, planned_jobs = _validate_frozen_run_inputs(run, loaded)
    scores = load_reviews(scores_path)
    validate_reviews(loaded.records, scores, questions=questions)
    return loaded, planned_jobs, scores


def infrastructure_failures(records: Sequence[Any]) -> list[Any]:
    names = {call.error for record in records for call in record.model_calls if call.error}
    unclassified = sorted(names - TRANSPORT_ERRORS)
    if unclassified:
        raise SystemExit(
            f"model-request errors that this analysis does not classify: {unclassified}"
        )
    return [
        record
        for record in records
        if record.status != "completed"
        and any(call.error in TRANSPORT_ERRORS for call in record.model_calls)
    ]


def pooled(
    means: dict[str, dict[str, float]], other_run: Path, other_scores: Path
) -> dict[str, Any]:
    loaded, planned_jobs, scores = load(other_run, other_scores)
    _, problems = score_checks_coverage_only(loaded.records, scores)
    if problems:
        raise SystemExit("the pooled run is not fully scored: " + "; ".join(problems))
    other = question_means(loaded.records, planned_jobs, {score.job_id: score for score in scores})
    if set(means[VECTOR]) & set(other[VECTOR]):
        raise SystemExit("the two runs share questions; a pooled table would count them twice")
    return {
        "label": "Descriptive only. It mixes the development questions the design was built "
        "on with the held-out questions and supports no confirmatory statement.",
        "other_run_id": loaded.manifest["run_id"],
        "other_split": loaded.manifest["split"],
        "conditions": {
            condition: {
                "this_run_questions": len(means[condition]),
                "this_run_mean": fmean(means[condition].values()),
                "other_run_questions": len(other[condition]),
                "other_run_mean": fmean(other[condition].values()),
                "pooled_questions": len(means[condition]) + len(other[condition]),
                "pooled_mean": fmean([*means[condition].values(), *other[condition].values()]),
            }
            for condition in CONDITIONS
        },
    }


def score_checks_coverage_only(
    records: Sequence[Any], scores: Sequence[Any]
) -> tuple[int, list[str]]:
    scorable = {
        record.job_id
        for record in records
        if record.answer is not None and record.answer.answer and record.answer.answer.strip()
    }
    scored = {score.job_id for score in scores}
    problems = []
    if scorable - scored:
        problems.append(f"{len(scorable - scored)} answer texts have no score")
    if scored - scorable:
        problems.append(f"{len(scored - scorable)} scores have no answer text")
    return len(scorable), problems


# ------------------------------------------------------------------------- main


def points(value: float) -> str:
    return f"{value * 100:+.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--outcome", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--rubric", type=Path, default=Path(RUBRIC))
    parser.add_argument("--pooled-run", type=Path)
    parser.add_argument("--pooled-scores", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")
    if args.output.resolve().is_relative_to(args.run.resolve()):
        raise SystemExit("results must be saved outside the raw run directory")
    if (args.pooled_run is None) != (args.pooled_scores is None):
        raise SystemExit("--pooled-run and --pooled-scores go together")
    given = {
        "run": args.run,
        "scores": args.scores,
        "template": args.template,
        "freeze": args.freeze,
        "outcome": args.outcome,
        "protocol": args.protocol,
        "attestation": args.attestation,
        "rubric": args.rubric,
        "pooled-run": args.pooled_run,
        "pooled-scores": args.pooled_scores,
    }
    absent = [f"--{name} {path}" for name, path in given.items() if path and not path.exists()]
    if absent:
        raise SystemExit("Not computed. These inputs do not exist:\n  " + "\n  ".join(absent))

    scores_sha256 = sha256_file(args.scores)
    template_sha256 = sha256_file(args.template)
    loaded, planned_jobs, scores = load(args.run, args.scores)
    records = loaded.records

    problems: list[str] = []
    checked_scores, found = score_checks(records, scores, args.template)
    problems += found
    checked_freeze, found = freeze_checks(args.freeze, scores_sha256, template_sha256, args.rubric)
    problems += found
    checked_outcome = None
    if args.outcome is not None:
        checked_outcome, found = outcome_checks(
            args.outcome, args.run, args.template, template_sha256, args.protocol
        )
        problems += found
    attestation = None
    if args.attestation is not None:
        document = json.loads(args.attestation.read_text("utf-8"))
        names_scores = scores_sha256 in set(strings(document))
        if not names_scores:
            problems.append("the attestation does not name this score file")
        attestation = {
            "file": str(args.attestation),
            "sha256": sha256_file(args.attestation),
            "names_this_score_file": names_scores,
            **{
                key: document.get(key)
                for key in (
                    "kind",
                    "reviewer",
                    "reviewed_at",
                    "score_author",
                    "separate_per_item_human_scores_supplied",
                )
            },
        }
    if problems:
        print("Not computed. Problems found:")
        for problem in problems:
            print("  -", problem)
        return 2

    plain = PlainRun(args.run, args.scores)
    primary, summary, gap = comparisons(records, planned_jobs, scores, plain)
    failures = infrastructure_failures(records)
    dropped = frozenset(record.job_id for record in failures)
    sensitivity, _, sensitivity_gap = comparisons(records, planned_jobs, scores, plain, dropped)
    description = describe(records, planned_jobs, scores, summary)
    by_job = {score.job_id: score for score in scores}
    pooled_table = None
    if args.pooled_run is not None:
        pooled_table = pooled(
            question_means(records, planned_jobs, by_job), args.pooled_run, args.pooled_scores
        )

    result = {
        "schema_version": "1",
        "kind": "confirmatory_comparisons",
        "run_id": loaded.manifest["run_id"],
        "split": loaded.manifest["split"],
        "planned_jobs": len(planned_jobs),
        "observed_jobs": len(records),
        "method": {
            "primary_metric": "failure-aware correctness over all planned jobs",
            "interval": "95% paired question-cluster percentile bootstrap",
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "seed": SEED,
            "similarity_margin_points": SIMILARITY_MARGIN * 100,
            "endpoint_tolerance": TOLERANCE,
            "multiplicity_adjustment": None,
            "statistics_by": "adaptive_rag.evaluation.analysis.aggregate_results",
        },
        "inputs": {
            "run": str(args.run),
            "results_sha256": sha256_file(args.run / "results.jsonl"),
            "manifest_sha256": sha256_file(args.run / "manifest.json"),
            "scores": str(args.scores),
            "scores_sha256": scores_sha256,
            "template": str(args.template),
            "template_sha256": template_sha256,
            "analysis_script_sha256": sha256_file(Path(__file__)),
            "framework": loaded.manifest.get("framework"),
        },
        "score_checks": checked_scores,
        "score_freeze": checked_freeze,
        "execution_outcome": checked_outcome,
        "author_attestation": attestation,
        "confirmatory_comparisons": primary,
        "sensitivity_without_unreachable_provider_jobs": {
            "jobs_left_out": [
                {
                    "condition": record.condition,
                    "question_id": record.question_id,
                    "repetition": record.repetition,
                    "status": record.status,
                    "request_errors": sorted(
                        {call.error for call in record.model_calls if call.error}
                    ),
                }
                for record in failures
            ],
            "comparisons": sensitivity,
        },
        "plain_json_recomputation": {
            "agrees": True,
            "largest_absolute_gap": max(gap, sensitivity_gap),
            "allowed_gap": AGREEMENT,
        },
        "descriptive": description,
        "pooled_descriptive": pooled_table,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")

    print(f"run {result['run_id']} ({result['split']}); {len(scores)} scores validated")
    for row in primary:
        low, high = row["interval_95"]
        if row["metric"] == CORRECTNESS:
            shown = f"{points(row['mean_difference'])} [{points(low)}, {points(high)}] points"
        elif row["metric"] == COST:
            shown = f"{row['mean_difference']:+.4f} [{low:+.4f}, {high:+.4f}] USD per job"
        else:
            shown = f"{row['mean_difference']:+.2f} [{low:+.2f}, {high:+.2f}] s per job"
        print(
            f"  {row['comparison']}. {row['left']} - {row['right']}, {row['metric']}: {shown}; "
            f"{row['paired_questions']} questions; {row['verdict']}"
        )
    print(f"  jobs left out in the sensitivity analysis: {len(failures)}")
    print(f"saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

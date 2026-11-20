"""Development-only diagnosis of one reviewed run. Offline; makes no model requests.

Inputs are the raw run directory, its human score file and the derived
development-only benchmark view. The combined benchmark is never opened: gold
evidence is read from the development view, and every row there must be labelled
``development``. Nothing here is a model input, and nothing is written into the run.

Hindsight selections ("oracle", simulated escalation) reuse the outcomes they are
scored on. They bound what routing could gain on these questions; they are not
achieved results and must not be reported as such.

Usage, from the repository root:

    .venv/bin/python experiments/analysis/development-diagnosis-20261119/diagnose.py \
        --run experiments/raw/adaptive-anthropic-paced-development-20261117-001 \
        --reviews experiments/reviews/adaptive-anthropic-paced-development-20261117-001/answers.scores.jsonl \
        --development-view experiments/handoff/claude-redesign-2026-11-18/development-only.jsonl \
        --output experiments/analysis/development-diagnosis-20261119/diagnosis.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, median

from adaptive_rag.evaluation.reviews import load_reviews, validate_reviews
from adaptive_rag.evaluation.storage import load_run

CONDITIONS = ("vector", "agentic", "vectorless", "no_retrieval", "adaptive_rule", "adaptive_llm")
FIXED = ("vector", "vectorless", "no_retrieval", "agentic")
TOKEN_LIMIT = 128_000
BOOTSTRAP_SAMPLES, SEED = 2000, 0
# Written after reading the vector answers of this run, so it only shows that such a
# signal exists. It is not a policy and is not used by any retriever or router.
MISSING_EVIDENCE = re.compile(
    r"not (?:shown|included|present|provided|visible|available)"
    r"|does(?: not|n't) (?:show|include|contain|provide|specify|reveal)"
    r"|cannot (?:be )?(?:determine|confirm|verif|identif|locate|see)"
    r"|insufficient|not enough|no evidence|unable to|would need|not explicitly"
    r"|evidence (?:does not|doesn't|lacks)|not in the (?:provided|supplied)"
    r"|beyond the (?:provided|supplied)",
    re.IGNORECASE,
)


def quantile(ordered: list[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def bootstrap(differences: list[float]) -> list[float]:
    """Question-cluster percentile bootstrap, as in the run's own aggregate."""
    rng = random.Random(SEED)
    count = len(differences)
    means = sorted(fmean(rng.choices(differences, k=count)) for _ in range(BOOTSTRAP_SAMPLES))
    return [quantile(means, 0.025), quantile(means, 0.975)]


def executed(record) -> str:
    if record.routing is not None and record.routing.selected_strategy:
        return record.routing.selected_strategy
    return record.condition


def ending(record) -> str:
    if record.status == "completed":
        return "completed"
    last = record.errors[-1] if record.errors else ""
    for marker, label in (
        ("token budget cannot admit", "token limit"),
        ("model-call budget exhausted", "model-call limit"),
        ("final response must select", "prose instead of a selection"),
    ):
        if marker in last:
            return label
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--development-view", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    if args.output.resolve().is_relative_to(args.run.resolve()):
        raise ValueError("analysis output must be outside the raw run directory")

    gold: dict[str, dict] = {}
    for line in args.development_view.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("split") != "development":
                raise ValueError("the benchmark view contains a row that is not development")
            gold[row["id"]] = row
    loaded = load_run(args.run)
    records = loaded.records
    if {record.split for record in records} != {"development"}:
        raise ValueError("the run contains records that are not development")
    if {record.question_id for record in records} - gold.keys():
        raise ValueError("the run has questions missing from the development view")
    reviews = load_reviews(args.reviews)
    validate_reviews(records, reviews)
    scores = {review.job_id: review for review in reviews}
    questions = sorted(gold)
    repetitions = sorted({record.repetition for record in records})

    def score(record) -> float:
        """Failure-aware correctness: an unsuccessful job scores zero."""
        return scores[record.job_id].correctness if record.status == "completed" else 0.0

    job = {(r.question_id, r.condition, r.repetition): r for r in records}
    mean = {
        q: {c: fmean(score(job[q, c, n]) for n in repetitions) for c in CONDITIONS}
        for q in questions
    }
    cost = {
        q: {c: [job[q, c, n].estimated_cost_usd for n in repetitions] for c in CONDITIONS}
        for q in questions
    }

    def outcome(record) -> str:
        review = scores.get(record.job_id)
        if record.status != "completed":
            return "failed, text judged" if review is not None else "failed, no answer"
        if review.correctness == 1.0:
            return "correct"
        if review.correctness == 0.5:
            return "partial"
        return "zero score"

    outcomes = {}
    for condition in CONDITIONS:
        groups = defaultdict(list)
        for record in records:
            if record.condition == condition:
                groups[outcome(record)].append(record)
        outcomes[condition] = {
            name: {
                "jobs": len(rows),
                "mean_gold_evidence_recall": fmean(
                    [r.metrics.evidence_recall for r in rows if r.metrics is not None]
                )
                if any(r.metrics is not None for r in rows)
                else None,
            }
            for name, rows in sorted(groups.items())
        }
    by_execution = defaultdict(Counter)
    for record in records:
        label = f"{executed(record)} via {record.condition}"
        by_execution[label][outcome(record)] += 1

    picks = {
        q: {c: job[q, c, repetitions[0]].routing.selected_strategy for c in CONDITIONS[4:]}
        for q in questions
    }
    for q in questions:
        for condition in CONDITIONS[4:]:
            if {job[q, condition, n].routing.selected_strategy for n in repetitions} != {
                picks[q][condition]
            }:
                raise ValueError("a router changed its pick between repetitions")
    selection = {}
    for condition in CONDITIONS[4:]:
        best = [
            mean[q][picks[q][condition]]
            >= max(mean[q][s] for s in ("vector", "agentic", "vectorless")) - 1e-9
            for q in questions
        ]
        selection[condition] = {
            "picks": dict(Counter(picks[q][condition] for q in questions)),
            "expected_from_picks_using_fixed_results": fmean(
                mean[q][picks[q][condition]] for q in questions
            ),
            "actual": fmean(mean[q][condition] for q in questions),
            "always_vector": fmean(mean[q]["vector"] for q in questions),
            "picked_a_best_strategy_on_questions": sum(best),
        }

    order = {name: index for index, name in enumerate(FIXED)}

    def run_mean(q, condition, runs):
        return fmean(score(job[q, condition, n]) for n in runs)

    def run_cost(q, condition, runs):
        return fmean(job[q, condition, n].estimated_cost_usd for n in runs)

    def choose(q, candidates, runs):
        return max(
            candidates,
            key=lambda s: (round(run_mean(q, s, runs), 9), -run_cost(q, s, runs), -order[s]),
        )

    ceilings = {}
    for label, candidates in (
        ("vector_or_agentic", ("vector", "agentic")),
        ("any_fixed_strategy", FIXED),
    ):
        chosen = {q: choose(q, candidates, repetitions) for q in questions}
        held_scores, held_cost, differences = [], 0.0, []
        for q in questions:
            values = []
            for n in repetitions:
                pick = choose(q, candidates, [m for m in repetitions if m != n])
                values.append(score(job[q, pick, n]))
                held_cost += job[q, pick, n].estimated_cost_usd
            held_scores.append(fmean(values))
            differences.append(fmean(values) - mean[q]["vector"])
        ceilings[label] = {
            "hindsight_correctness": fmean(mean[q][chosen[q]] for q in questions),
            "hindsight_cost_usd": sum(sum(cost[q][chosen[q]]) for q in questions),
            "hindsight_picks": dict(Counter(chosen.values())),
            "leave_one_repetition_out_correctness": fmean(held_scores),
            "leave_one_repetition_out_cost_usd": held_cost,
            "leave_one_repetition_out_minus_vector": fmean(differences),
            "leave_one_repetition_out_minus_vector_ci95": bootstrap(differences),
        }

    agentic_runs = [r for r in records if executed(r) == "agentic" and r.retrieval is not None]

    def shown(record):
        chunks = []
        for operation in record.retrieval.operations:
            output = (operation.details or {}).get("output") or {}
            chunks.extend(
                (chunk["path"], chunk["start_line"], chunk["end_line"])
                for chunk in output.get("evidence") or []
            )
        return chunks

    def coverage(record):
        references = gold[record.question_id]["evidence"]
        chunks = shown(record)
        files = {reference["path"] for reference in references}
        touched = sum(
            any(
                path == reference["path"]
                and start <= reference["end_line"]
                and end >= reference["start_line"]
                for path, start, end in chunks
            )
            for reference in references
        )
        total = hit = 0
        for reference in references:
            lines = set()
            for path, start, end in chunks:
                if path == reference["path"]:
                    lines |= set(
                        range(
                            max(start, reference["start_line"]),
                            min(end, reference["end_line"]) + 1,
                        )
                    )
            total += reference["end_line"] - reference["start_line"] + 1
            hit += len(lines)
        return {
            "every_gold_file_shown": files <= {path for path, _, _ in chunks},
            "every_gold_range_touched": touched == len(references),
            "gold_line_coverage": hit / total,
        }

    def call_when_all_gold_files_shown(record):
        files = {reference["path"] for reference in gold[record.question_id]["evidence"]}
        turn_of = {}
        for number, call in enumerate(record.retrieval.model_calls, 1):
            choices = (call.response or {}).get("choices") or [{}]
            for requested in (choices[0].get("message") or {}).get("tool_calls") or []:
                turn_of[requested.get("id")] = number
        seen = set()
        for operation in record.retrieval.operations:
            output = (operation.details or {}).get("output") or {}
            seen |= {chunk["path"] for chunk in output.get("evidence") or []} & files
            if seen == files:
                return turn_of.get((operation.details or {}).get("tool_call_id"))
        return None

    def agentic_group(rows):
        groups = defaultdict(list)
        for record in rows:
            groups[ending(record)].append(record)
        summary = {}
        for name, members in sorted(groups.items(), key=lambda item: -len(item[1])):
            covered = [coverage(record) for record in members]
            tokens = [
                r.retrieval.usage.input_tokens
                for r in members
                if r.retrieval.usage.input_tokens is not None
            ]
            costs = [r.estimated_cost_usd for r in members if r.estimated_cost_usd is not None]
            summary[name] = {
                "runs": len(members),
                "median_model_calls": median(len(r.retrieval.model_calls) for r in members),
                "median_tool_calls": median(r.retrieval.tool_call_count for r in members),
                "median_retrieval_input_tokens": median(tokens) if tokens else None,
                "median_cost_usd": median(costs) if costs else None,
                "every_gold_file_shown": sum(item["every_gold_file_shown"] for item in covered),
                "every_gold_range_touched": sum(
                    item["every_gold_range_touched"] for item in covered
                ),
                "mean_gold_line_coverage": fmean(item["gold_line_coverage"] for item in covered),
            }
        return summary

    ratios, unspent, last_bytes, last_tokens = [], [], [], []
    tool_errors = Counter()
    prose_endings = []
    for record in agentic_runs:
        admissions = record.retrieval.metadata.get("admissions") or []
        for admission, call in zip(admissions, record.retrieval.model_calls, strict=False):
            if call.usage.input_tokens:
                ratios.append(admission["prompt_utf8_bytes"] / call.usage.input_tokens)
        for operation in record.retrieval.operations:
            if operation.error:
                tool_errors[f"{operation.name}: {operation.error[:70]}"] += 1
        if ending(record) == "token limit":
            unspent.append(TOKEN_LIMIT - record.retrieval.usage.total_tokens)
            last_bytes.append(admissions[-1]["prompt_utf8_bytes"])
            last_tokens.append(record.retrieval.model_calls[-1].usage.input_tokens)
        if ending(record) == "prose instead of a selection":
            call = record.retrieval.model_calls[-1]
            choice = ((call.response or {}).get("choices") or [{}])[0]
            prose_endings.append(
                {
                    "finish_reason": choice.get("finish_reason"),
                    "output_tokens": call.usage.output_tokens,
                    "allowed_output_tokens": admissions[-1]["reserved_output_tokens"],
                    "requested_tools": bool((choice.get("message") or {}).get("tool_calls")),
                }
            )
    ratios.sort()
    turns = defaultdict(list)
    for record in agentic_runs:
        turn = call_when_all_gold_files_shown(record)
        if turn is not None:
            turns["completed" if record.status == "completed" else "failed"].append(turn)
    category = {}
    for name in sorted({row["category"] for row in gold.values()}):
        members = [q for q in questions if gold[q]["category"] == name]
        category[name] = {
            "correctness": {c: fmean(mean[q][c] for q in members) for c in CONDITIONS},
            "fixed_agentic_completed": sum(
                job[q, "agentic", n].status == "completed" for q in members for n in repetitions
            ),
            "fixed_agentic_jobs": len(members) * len(repetitions),
        }

    vector_rows = []
    for q in questions:
        runs = [job[q, "vector", n] for n in repetitions]
        vector_rows.append(
            (
                mean[q]["vector"],
                fmean(max(chunk.score for chunk in r.retrieval.evidence) for r in runs),
                fmean(fmean(chunk.score for chunk in r.retrieval.evidence) for r in runs),
            )
        )

    def auc(index):
        positive = [row[index] for row in vector_rows if row[0] == 1.0]
        negative = [row[index] for row in vector_rows if row[0] < 1.0]
        wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
        return wins / (len(positive) * len(negative))

    def flagged(record) -> bool:
        if record.status != "completed":
            return True
        return bool(MISSING_EVIDENCE.search(record.answer.answer or ""))

    flags = Counter()
    for q in questions:
        for n in repetitions:
            record = job[q, "vector", n]
            good = record.status == "completed" and scores[record.job_id].correctness == 1.0
            flags["correct" if good else "imperfect or failed", flagged(record)] += 1

    def simulate(trigger, keep_first):
        values, spent, escalated = [], 0.0, 0
        for q in questions:
            for n in repetitions:
                first, second = job[q, "vector", n], job[q, "agentic", n]
                spent += first.estimated_cost_usd
                if trigger(first):
                    escalated += 1
                    spent += second.estimated_cost_usd
                    if second.status == "completed":
                        values.append(scores[second.job_id].correctness)
                    else:
                        values.append(score(first) if keep_first else 0.0)
                else:
                    values.append(score(first))
        return {"correctness": fmean(values), "cost_usd": spent, "escalated_jobs": escalated}

    per_strategy = {}
    for name in sorted({executed(r) for r in records}):
        members = [r for r in records if executed(r) == name]
        costs = [r.estimated_cost_usd for r in members if r.estimated_cost_usd is not None]
        per_strategy[name] = {
            "jobs": len(members),
            "median_cost_usd": median(costs),
            "mean_cost_usd": fmean(costs),
            "median_elapsed_seconds_including_pacing": median(r.elapsed_seconds for r in members),
        }

    result = {
        "schema_version": "1",
        "kind": "development_only_diagnosis",
        "run_id": loaded.manifest["run_id"],
        "inputs": {
            "run": str(args.run),
            "results_sha256": hashlib.sha256((args.run / "results.jsonl").read_bytes()).hexdigest(),
            "reviews_sha256": hashlib.sha256(args.reviews.read_bytes()).hexdigest(),
            "development_view_sha256": hashlib.sha256(
                args.development_view.read_bytes()
            ).hexdigest(),
            "questions": len(questions),
            "records": len(records),
            "reviews": len(reviews),
        },
        "caveats": [
            "Fifteen development questions with three repetitions each; not independent jobs.",
            "Hindsight ceilings and simulated escalation reuse the outcomes they are scored on.",
            "The missing-evidence phrase match was written after reading these answers.",
            "Categories are used for description only and are never a model input.",
        ],
        "failure_aware_correctness": {c: fmean(mean[q][c] for q in questions) for c in CONDITIONS},
        "known_cost_usd": {
            c: sum(value for q in questions for value in cost[q][c] if value is not None)
            for c in CONDITIONS
        },
        "per_question": {
            q: {"mean": mean[q], "router_picks": picks[q], "category": gold[q]["category"]}
            for q in questions
        },
        "outcomes_by_condition": outcomes,
        "outcomes_by_executed_strategy": {k: dict(v) for k, v in sorted(by_execution.items())},
        "selection_quality": selection,
        "hindsight_ceilings": ceilings,
        "agentic": {
            "all_executions": agentic_group(agentic_runs),
            "fixed_condition": agentic_group([r for r in agentic_runs if r.condition == "agentic"]),
            "prompt_bytes_per_reported_input_token": {
                "calls": len(ratios),
                "median": median(ratios),
                "p10": ratios[len(ratios) // 10],
                "p90": ratios[len(ratios) * 9 // 10],
            },
            "token_limit_stops": {
                "runs": len(unspent),
                "median_unspent_tokens": median(unspent),
                "min_unspent_tokens": min(unspent),
                "max_unspent_tokens": max(unspent),
                "median_last_admitted_prompt_bytes": median(last_bytes),
                "median_last_admitted_prompt_reported_tokens": median(last_tokens),
            },
            "prose_endings": prose_endings,
            "tool_errors": dict(tool_errors.most_common()),
            "model_call_by_which_every_gold_file_was_shown": {
                name: {
                    "runs": len(values),
                    "median": median(values),
                    "by_call_6": sum(value <= 6 for value in values),
                    "by_call_8": sum(value <= 8 for value in values),
                }
                for name, values in sorted(turns.items())
            },
        },
        "by_category": category,
        "vector_similarity_signal": {
            "perfect_questions": sum(row[0] == 1.0 for row in vector_rows),
            "imperfect_questions": sum(row[0] < 1.0 for row in vector_rows),
            "auc_top_score": auc(1),
            "auc_mean_top_k_score": auc(2),
        },
        "vector_answers_stating_missing_evidence": {
            "correct_flagged": flags["correct", True],
            "correct_total": flags["correct", True] + flags["correct", False],
            "imperfect_or_failed_flagged": flags["imperfect or failed", True],
            "imperfect_or_failed_total": flags["imperfect or failed", True]
            + flags["imperfect or failed", False],
        },
        "hindsight_escalation_simulations": {
            "vector_only": simulate(lambda first: False, True),
            "escalate_when_flagged_keep_vector_on_failure": simulate(flagged, True),
            "escalate_always_keep_vector_on_failure": simulate(lambda first: True, True),
        },
        "per_executed_strategy": per_strategy,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result["failure_aware_correctness"], indent=2))
    print("wrote", args.output)


if __name__ == "__main__":
    main()

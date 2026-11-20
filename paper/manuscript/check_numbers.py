"""Check the manuscript's figures against the recorded result files. Offline.

Each expected phrase below is built from a result file, never typed in, and must
appear in the manuscript. Run from the repository root:

    .venv/bin/python paper/manuscript/check_numbers.py

It exits with status 1 and lists what is missing if the text and the records
disagree. It checks numbers only: it cannot tell whether a sentence interprets
them fairly.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ANALYSIS = ROOT / "experiments/analysis/heldout-confirmatory-20261119"
REVIEWS = ROOT / "experiments/reviews/adaptive-cascade-heldout-20261119-001"
PREFLIGHT = ROOT / "experiments/preflight"

NAMES = {
    "vector": "Vector",
    "agentic": "Agentic, original",
    "agentic_wrapup": "Agentic, reserved selection",
    "adaptive_cascade": "Cascade",
    "no_retrieval": "No retrieval",
    "adaptive_rule": "Rule router",
    "adaptive_llm": "Model router",
    "vectorless": "Vectorless",
}
WORDS = {7: "Seven", 14: "Fourteen", 19: "Nineteen", 22: "Twenty-two"}


def load(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def points(value: float) -> str:
    shown = f"{value * 100:+.1f}"
    return "0.0" if shown in {"+0.0", "-0.0"} else shown


def mean_text(value: float) -> str:
    return "1" if value == 1 else "0" if value == 0 else f"{value:.2f}"


def normalise(text: str) -> str:
    text = text.replace("−", "-").replace("\\$", "$").replace("`", "")
    text = re.sub(r"\n\s*>\s?", "\n", text)
    return re.sub(r"\s+", " ", text)


def condition_rows(conditions: dict, keys: list[str], *, detailed: bool) -> list[str]:
    rows = []
    for key in keys:
        value = conditions[key]
        cost = f"${value['mean_known_cost_per_job_usd']:.4f}"
        elapsed = f"{value['mean_elapsed_seconds']:.1f}"
        correct = f"{value['failure_aware_correctness'] * 100:.1f}%"
        if detailed:
            middle = (
                f"{value['rated_full']} | {value['rated_partial']} | {value['rated_zero']} | "
                f"{value['failed_counted_as_zero']} | "
            )
        else:
            middle = ""
        rows.append(
            f"| {NAMES[key]} | {value['completed']} | {middle}{correct} | {cost} | {elapsed} |"
        )
    return rows


def main() -> int:
    text = normalise((HERE / "adaptive-rag-pilot.md").read_text("utf-8"))
    held = load(ANALYSIS / "heldout-confirmatory.json")
    dev = load(ANALYSIS / "development-validation.json")
    first = load(
        ROOT
        / "experiments/aggregates"
        / "adaptive-anthropic-paced-development-20261117-001-reviewed-creation-times-001.json"
    )
    diagnosis = load(ROOT / "experiments/analysis/development-diagnosis-20261119/diagnosis.json")
    expected: list[tuple[str, str]] = []

    def expect(what: str, phrase: str) -> None:
        expected.append((what, normalise(phrase)))

    # Table 3: the first development run
    for key in ("vector", "agentic", "adaptive_rule", "adaptive_llm", "vectorless", "no_retrieval"):
        block = first["conditions"][key]
        measured = block["measurements_observed"]
        expect(
            f"Table 3, {key}",
            f"| {NAMES[key]} | {block['completed']} | "
            f"{block['failure_aware_correctness']['mean'] * 100:.1f}% | "
            f"${measured['estimated_cost_usd']['mean']:.4f} | "
            f"{measured['latency_seconds']['mean']:.1f} |",
        )
    pairs = {(row["left"], row["right"], row["metric"]): row for row in first["paired_comparisons"]}
    for router, label in (("adaptive_rule", "rule router"), ("adaptive_llm", "model router")):
        row = pairs[(router, "vector", "failure_aware_correctness")]
        low, high = row["ci95_percentile_bootstrap"]
        expect(
            f"run 1, {label} minus Vector",
            f"{points(row['mean_difference'])} points for the {label}",
        )
        expect(f"run 1, {label} interval", f"{points(low)} to {points(high)})")

    # Section 6.2: the diagnosis
    selection = diagnosis["selection_quality"]
    expect(
        "router picks scored with fixed results",
        f"{selection['adaptive_rule']['expected_from_picks_using_fixed_results'] * 100:.1f}% "
        "for the rule router and "
        f"{selection['adaptive_llm']['expected_from_picks_using_fixed_results'] * 100:.1f}% "
        "for the model router",
    )
    endings = diagnosis["agentic"]["all_executions"]
    for key, label in (
        ("completed", "Completed with a selection"),
        ("token limit", "Stopped at the token limit"),
        ("prose instead of a selection", "Ended in prose instead of a selection"),
        ("model-call limit", "Stopped at the model-request limit"),
        ("other", "Connection failure"),
    ):
        expect(
            f"Table 4, {key}",
            f"| {label} | {endings[key]['runs']} | {endings[key]['every_gold_file_shown']} |",
        )
    total_runs = sum(item["runs"] for item in endings.values())
    stopped = total_runs - endings["completed"]["runs"]
    shown = sum(v["every_gold_file_shown"] for k, v in endings.items() if k != "completed")
    expect("navigator runs", f"The navigator ran {total_runs} times")
    expect("navigator runs that returned nothing", f"The other {stopped} returned nothing")
    expect("evidence shown in failed runs", f"in {shown} of them a chunk from every reference file")
    stops = diagnosis["agentic"]["token_limit_stops"]
    expect(
        "unspent tokens", f"a median of {stops['median_unspent_tokens']:,} budgeted tokens unspent"
    )
    expect("last prompt size", f"{stops['median_last_admitted_prompt_bytes']:,} bytes")
    ratio = diagnosis["agentic"]["prompt_bytes_per_reported_input_token"]["median"]
    expect("bytes per token", f"a median of {ratio:.2f} bytes per token")
    signal = diagnosis["vector_similarity_signal"]["auc_top_score"]
    expect("similarity signal", f"area under the curve of {signal:.2f}")

    # Tables 5 and 6
    keys = ["vector", "agentic", "agentic_wrapup", "adaptive_cascade", "no_retrieval"]
    for row in condition_rows(dev["descriptive"]["conditions"], keys, detailed=False):
        expect("Table 5", row)
    for row in condition_rows(held["descriptive"]["conditions"], keys, detailed=True):
        expect("Table 6", row)

    # Table 7 and the abstract
    rows = {(row["comparison"], row["metric"]): row for row in held["confirmatory_comparisons"]}

    def correctness(number: int) -> tuple[str, str, str, str]:
        row = rows[(number, "failure_aware_correctness")]
        low, high = row["interval_95"]
        return points(row["mean_difference"]), points(low), points(high), row["verdict"]

    one, two, three = correctness(1), correctness(2), correctness(3)
    expect("Table 7, 1", f"| {one[0]} points | {one[1]} to {one[2]} | {one[3]} |")
    expect("Table 7, 2 quality", f"| {two[0]} points | {two[1]} to {two[2]} | {two[3]} |")
    expect("Table 7, 3", f"| {three[0]} points | {three[1]} to {three[2]} | {three[3]} |")
    cost = rows[(2, "estimated_cost_usd")]
    expect(
        "Table 7, 2 cost",
        f"| -${abs(cost['mean_difference']):.3f} | -${abs(cost['interval_95'][0]):.3f} to "
        f"-${abs(cost['interval_95'][1]):.3f} | {cost['verdict']}",
    )
    time = rows[(2, "latency_seconds")]
    expect(
        "Table 7, 2 time",
        f"| {time['mean_difference']:.1f} s | {time['interval_95'][0]:.1f} to "
        f"{time['interval_95'][1]:.1f} | {time['verdict']}",
    )
    expect("abstract, 3", f"({three[0]} percentage points, 95% interval {three[1]} to {three[2]})")
    expect("abstract, 2", f"({two[0]} points, {two[1]} to {two[2]})")
    expect("abstract, 1", f"scored {one[0].lstrip('+')} points above vector search alone")

    held_c = held["descriptive"]["conditions"]
    cascade, navigator, vector = (
        held_c["adaptive_cascade"],
        held_c["agentic_wrapup"],
        held_c["vector"],
    )
    cost_share = cascade["mean_known_cost_per_job_usd"] / navigator["mean_known_cost_per_job_usd"]
    time_share = cascade["mean_elapsed_seconds"] / navigator["mean_elapsed_seconds"]
    expect("cost share", f"which is {cost_share * 100:.0f}% of the navigator's")
    expect("time share", f"which is {time_share * 100:.0f}% of the navigator's")
    expect("abstract, cost saving", f"cost {(1 - cost_share) * 100:.0f}% less")
    expect("abstract, time saving", f"took {(1 - time_share) * 100:.0f}% less time")
    cost_times = cascade["known_cost_usd"] / vector["known_cost_usd"]
    time_times = cascade["mean_elapsed_seconds"] / vector["mean_elapsed_seconds"]
    expect(
        "against Vector",
        f"{cost_times:.1f} times Vector's known cost and {time_times:.1f} times its elapsed time",
    )
    expect("abstract, against Vector", f"cost {cost_times:.1f} times as much as vector search")
    among = held_c["agentic"]["correctness_among_completed"]
    expect("original navigator when it answers", f"scored {among * 100:.1f}% on average")

    # Section 7.3: how close to zero
    questions = held["descriptive"]["question_means"]
    differences = [
        questions[q]["adaptive_cascade"] - questions[q]["vector"] for q in sorted(questions)
    ]
    rng = random.Random(0)
    samples = [fmean(rng.choices(differences, k=len(differences))) for _ in range(2000)]
    below = sum(sample < -1e-12 for sample in samples)
    at_zero = sum(abs(sample) <= 1e-12 for sample in samples)
    expect("bootstrap means at or below zero", f"{below} are below zero and {at_zero} equal zero")
    improved = sum(d > 1e-12 for d in differences)
    worse = sum(d < -1e-12 for d in differences)
    same = len(differences) - improved - worse
    if (improved, worse, same) != (6, 1, 8):
        expect(
            "questions improved, worse, unchanged", f"{improved} / {worse} / {same} (reword 7.3)"
        )
    else:
        expect(
            "questions improved, worse, unchanged",
            "Six questions improved, one got worse and eight",
        )

    # Section 7.4 and Table 8
    behaviour = held["descriptive"]["cascade"]
    dev_behaviour = dev["descriptive"]["cascade"]
    expect(
        "escalations",
        f"escalated {behaviour['escalated']} of {behaviour['observed']} jobs, against "
        f"{dev_behaviour['escalated']} of {dev_behaviour['observed']} in development",
    )
    insufficient = behaviour["escalation_reasons"]["evidence_reported_insufficient"]
    expect(
        "escalation reasons", f"{WORDS[insufficient]} followed a report of insufficient evidence"
    )
    expect(
        "questions that escalated",
        f"{WORDS[behaviour['questions_escalated_at_least_once']]} of the 15 questions escalated",
    )
    after = behaviour["final_answers_when_escalated"]
    expect("after escalating", f"{WORDS[after['full']]} answers scored full marks")
    kept = behaviour["final_answers_when_not_escalated"]
    expect("without escalating", f"{WORDS[kept['full']]} answers scored full marks")
    report = held["descriptive"]["vector_sufficiency_report_by_rating"]
    for key, label in (
        ("reported_sufficient", "Sufficient evidence"),
        ("reported_insufficient", "Insufficient evidence"),
    ):
        counts = report[key]
        total = sum(counts.values())
        expect(
            f"Table 8, {key}",
            f"| {label} | {total} | {counts.get('full', 0)} | {counts.get('partial', 0)} | "
            f"{counts.get('zero', 0)} |",
        )

    # Section 8: the cost approximation
    for label, result in (("development", dev), ("held-out", held)):
        block = result["descriptive"]["conditions"]
        rate = (
            result["descriptive"]["cascade"]["escalated"]
            / result["descriptive"]["cascade"]["observed"]
        )
        predicted = (
            block["vector"]["mean_known_cost_per_job_usd"]
            + rate * block["agentic_wrapup"]["mean_known_cost_per_job_usd"]
        )
        observed = block["adaptive_cascade"]["mean_known_cost_per_job_usd"]
        expect(f"cost approximation, {label}", f"${predicted:.4f}")
        expect(f"cost observed, {label}", f"${observed:.4f}")
        expect(f"escalation rate, {label}", f"{rate:.2f}")
        if abs(observed / predicted - 1) > 0.075:
            expect(
                f"cost approximation within 7%, {label}", "(approximation is off by more than 7%)"
            )
    even = sorted(
        1
        - result["descriptive"]["conditions"]["vector"]["mean_known_cost_per_job_usd"]
        / result["descriptive"]["conditions"]["agentic_wrapup"]["mean_known_cost_per_job_usd"]
        for result in (dev, held)
    )
    expect(
        "break-even escalation rate", f"{even[0] * 100:.0f}% to {even[1] * 100:.0f}% of questions"
    )

    # Appendix B
    for question_id, values in questions.items():
        cells = " | ".join(
            mean_text(values[key])
            for key in ("vector", "agentic", "agentic_wrapup", "adaptive_cascade", "no_retrieval")
        )
        expect(f"Table B1, {question_id}", f"| {cells} | {values['cascade_escalations']} |")

    # Appendix D
    outcomes = [
        load(PREFLIGHT / name / "outcome.json")
        for name in (
            "final-development-2026-11-17-001",
            "cascade-development-2026-11-19-001",
            "cascade-heldout-2026-11-19-001",
        )
    ]
    expect("Table D1, jobs", "| " + " | ".join(str(o["planned_jobs"]) for o in outcomes) + " |")
    done = [(o["result_counts"]["completed"], o["observed_jobs"]) for o in outcomes]
    expect(
        "Table D1, completed and failed",
        "| " + " | ".join(f"{completed} / {jobs - completed}" for completed, jobs in done) + " |",
    )
    expect(
        "Table D1, requests", "| " + " | ".join(f"{o['model_calls']:,}" for o in outcomes) + " |"
    )
    known = [o["provider_cost_estimate"]["known_subtotal_usd"] for o in outcomes]
    expect("Table D1, cost", "| " + " | ".join(f"${value:.2f}" for value in known) + " |")
    expect(
        "Table D1, unknown usage",
        "| "
        + " | ".join(str(o["provider_cost_estimate"]["unknown_calls"]) for o in outcomes)
        + " |",
    )
    expect("total cost", f"about ${sum(known):.0f} in model usage")
    for outcome in outcomes:
        expect("run identifier", outcome["run_id"])
    for label, path in (
        ("benchmark", ROOT / "benchmarks/pilot.jsonl"),
        ("protocol", ROOT / "paper/phase7-held-out-protocol.md"),
        ("analysis script", ANALYSIS / "confirmatory.py"),
        ("scores", REVIEWS / "answers.ai-scores.jsonl"),
        ("score freeze", REVIEWS / "ai-review/scores-frozen.json"),
        ("attestation", REVIEWS / "shekhar-review-attestation.json"),
        ("confirmatory output", ANALYSIS / "heldout-confirmatory.json"),
    ):
        expect(f"hash of the {label}", sha256(path))

    # Section 3.1: the corpus
    files = load(
        ROOT / "experiments/raw/adaptive-cascade-heldout-20261119-001/corpus-manifest.json"
    )["files"]
    python = sum(item["path"].endswith(".py") for item in files)
    megabytes = sum(item["size_bytes"] for item in files) / 1e6
    expect("corpus size", f"{len(files):,} files and {megabytes:.1f} MB of text")
    expect("Python files", f"{python:,} files are Python")

    missing = [(what, phrase) for what, phrase in expected if phrase not in text]
    print(f"{len(expected) - len(missing)} of {len(expected)} checked figures match the records")
    for what, phrase in missing:
        print(f"  MISSING ({what}): {phrase}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

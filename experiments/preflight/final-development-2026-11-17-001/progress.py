#!/usr/bin/env python3
"""Print one metadata-only progress snapshot; never start or resume a study."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUN_NAME = "adaptive-anthropic-paced-development-20261117-001"
REPOSITORY = Path(__file__).resolve().parents[3]
RUN_DIRECTORY = REPOSITORY / "experiments" / "raw" / RUN_NAME
REPORT = REPOSITORY / "paper" / "development-progress.md"
STATUSES = {"completed", "budget_exhausted", "error", "interrupted"}
INTERPRETATION = "Used-or-reserved admission estimates; not actual billed usage."


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _object(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise ValueError("not an object")
        return value
    except (OSError, ValueError, UnicodeError, RecursionError):
        issues.append(f"{path.name}: incomplete or unreadable metadata")
        return {}


def _rows(path: Path, issues: list[str]):
    if not path.exists():
        return
    try:
        with path.open("rb") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("not an object")
                    yield value
                except (ValueError, UnicodeError, RecursionError):
                    # A writer may be between bytes of its last JSONL record.
                    suffix = (
                        "partial tail ignored"
                        if not line.endswith(b"\n")
                        else "invalid row ignored"
                    )
                    issues.append(f"{path.name}: {suffix}")
    except OSError:
        issues.append(f"{path.name}: temporarily unreadable")


def _timestamp(raw: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.astimezone(UTC) if value.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def _short_error(value: Any) -> str | None:
    return " ".join(value.split())[:240] if isinstance(value, str) and value else None


def snapshot(directory: Path, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    issues: list[str] = []
    manifest = _object(directory / "manifest.json", issues)
    final = _object(directory / "status.json", issues)
    planned_jobs = manifest.get("planned_jobs")
    planned = len(planned_jobs) if isinstance(planned_jobs, list) else None
    counts: Counter[str] = Counter()
    seen = set()
    known_cost = 0.0
    unknown_usage = 0
    budget_cost = 0.0
    budget_usage: dict[str, int | None] = {"input_tokens": 0, "output_tokens": 0}
    reserved = unreserved = 0
    budget_complete = True
    policy = None
    last_error = None
    last_error_at = None
    last_event = None

    # Access only execution/accounting fields. Never inspect answer/question text,
    # model messages, reference annotations, request bodies, or receipt contents.
    for row in _rows(directory / "results.jsonl", issues):
        job_id, status = row.get("job_id"), row.get("status")
        if not isinstance(job_id, str) or status not in STATUSES or job_id in seen:
            issues.append("results.jsonl: invalid or duplicate identity/status ignored")
            continue
        seen.add(job_id)
        counts[status] += 1
        metadata = row.get("metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        cost = metadata.get("cost", {})
        subtotal = cost.get("known_subtotal_usd") if isinstance(cost, dict) else None
        if not _number(subtotal):
            subtotal = row.get("estimated_cost_usd")
        if _number(subtotal):
            known_cost += subtotal

        calls = row.get("model_calls", [])
        calls = calls if isinstance(calls, list) else []
        attempts = metadata.get("model_attempts", len(calls))
        unknown_usage += max(0, attempts - len(calls)) if _count(attempts) else 0
        for call in calls:
            usage = call.get("usage", {}) if isinstance(call, dict) else {}
            if not isinstance(usage, dict) or any(
                usage.get(key) is None for key in ("input_tokens", "output_tokens")
            ):
                unknown_usage += 1

        accounting = metadata.get("budget_accounting")
        if not isinstance(accounting, dict):
            budget_complete = False
        else:
            policy = accounting.get("policy", policy)
            charge = accounting.get("estimated_cost_usd")
            if _number(charge):
                budget_cost += charge
            else:
                budget_complete = False
            usage = accounting.get("usage", {})
            for key in budget_usage:
                value = usage.get(key) if isinstance(usage, dict) else None
                budget_usage[key] = (
                    budget_usage[key] + value
                    if budget_usage[key] is not None and _count(value)
                    else None
                )
            reserved_value = accounting.get("reserved_unknown_calls")
            unreserved_value = accounting.get("unreserved_unknown_calls")
            if _count(reserved_value) and _count(unreserved_value):
                reserved += reserved_value
                unreserved += unreserved_value
            else:
                budget_complete = False
        errors = row.get("errors", [])
        if isinstance(errors, list) and errors and (message := _short_error(errors[-1])):
            last_error = message
            last_error_at = _timestamp(row.get("created_at"))

    for event in _rows(directory / "events.jsonl", issues):
        if isinstance(event.get("event"), str):
            last_event = event["event"]
        message = _short_error(event.get("error")) or _short_error(event.get("reason"))
        at = _timestamp(event.get("at"))
        if message and (last_error_at is None or at is None or at >= last_error_at):
            last_error, last_error_at = message, at

    finished = bool(final.get("finished_at"))
    status = final.get("status") if finished else ("running" if seen or last_event else "preparing")
    elapsed = final.get("elapsed_seconds")
    approximate = not _number(elapsed)
    if approximate:
        start = _timestamp(manifest.get("created_at"))
        elapsed = max(0.0, (now - start).total_seconds()) if start is not None else None
    accounting = (
        {
            "policy": policy,
            "interpretation": INTERPRETATION,
            "usage": budget_usage,
            "estimated_cost_usd": round(budget_cost, 10) if budget_complete else None,
            "reserved_unknown_calls": reserved,
            "unreserved_unknown_calls": unreserved,
        }
        if seen
        else None
    )
    if isinstance(final.get("budget_accounting"), dict):
        recorded = final["budget_accounting"]
        accounting = {
            key: recorded.get(key)
            for key in (
                "policy",
                "interpretation",
                "usage",
                "estimated_cost_usd",
                "reserved_unknown_calls",
                "unreserved_unknown_calls",
                "unknown_cost_jobs",
            )
        }
    if _number(final.get("known_cost_subtotal_usd")):
        known_cost = final["known_cost_subtotal_usd"]
    actual_cost = final.get("estimated_cost_usd") if finished else None
    return {
        "run": directory.name,
        "status": status,
        "recorded": len(seen),
        "planned": planned,
        "status_counts": dict(sorted(counts.items())),
        "elapsed_minutes": round(elapsed / 60, 2) if _number(elapsed) else None,
        "elapsed_is_approximate": approximate,
        "accounting_scope": "final snapshot"
        if finished
        else "durable recorded jobs; excludes in-flight work",
        "known_cost_subtotal_usd": round(known_cost, 10) if seen or finished else None,
        "complete_estimated_cost_usd": actual_cost,
        "budget_used_or_reserved": accounting,
        "unknown_usage_calls": unknown_usage,
        "last_event": last_event,
        "last_error": last_error,
        "finished": finished,
        "read_notes": sorted(set(issues)),
    }


def write_report(data: dict[str, Any], target: Path) -> None:
    planned = data["planned"] if data["planned"] is not None else "not yet available"
    text = (
        "# Development progress (derived snapshot)\n\n"
        "Generated from execution/accounting metadata only. This is not an accuracy "
        "result or an instruction to start, retry, or resume a run.\n\n"
        f"Run: `{data['run']}`  \nStatus: **{data['status']}**  \n"
        f"Recorded/planned: **{data['recorded']} / {planned}**  \n"
        f"Finished: **{data['finished']}**\n\n"
        "Used-or-reserved figures are admission estimates, not actual billed totals. "
        "Unknown actual usage remains unknown. During execution, accounting covers "
        "durable job records and excludes the current in-flight job.\n\n"
        "```json\n" + json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n```\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Overwrite only derived paper/development-progress.md",
    )
    args = parser.parse_args()
    data = snapshot(RUN_DIRECTORY)
    if args.write_report:
        write_report(data, REPORT)
    print(json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

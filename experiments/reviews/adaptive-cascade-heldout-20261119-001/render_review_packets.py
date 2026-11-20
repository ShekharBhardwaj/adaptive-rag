#!/usr/bin/env python3
"""Render this run's shuffled review template into fresh Markdown packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PACKET_SIZE = 15
TEMPLATE_NAME = "answers.review-template.jsonl"
ITEM_FIELDS = {
    "schema_version",
    "review_id",
    "rubric",
    "question",
    "reference_answer",
    "gold_evidence",
    "repo_commit",
    "generated_answer",
    "citations",
    "citation_claims",
    "score",
}
BINDING_FIELDS = ("schema_version", "run_id", "job_id", "output_sha256", "rubric_version")
RATING_FIELDS = ("reviewer", "reviewed_at", "correctness", "citation_support", "notes")
SOURCE_FIELDS = {"path", "start_line", "end_line", "excerpt_sha256"}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _constant(_value: str) -> None:
    raise ValueError("nonstandard JSON constant")


def _validate(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
        raise ValueError("input must contain only exported blinded review-template fields")
    if item["schema_version"] != "1":
        raise ValueError("unsupported review-template schema")
    for field in ("review_id", "question", "reference_answer", "repo_commit", "generated_answer"):
        if not isinstance(item[field], str) or not item[field].strip():
            raise ValueError(f"{field} must be nonempty text")
    rubric = item["rubric"]
    if not isinstance(rubric, dict) or set(rubric) != {
        "version",
        "correctness",
        "citation_support",
    }:
        raise ValueError("unexpected rubric fields")
    if rubric["version"] != "manual-v1":
        raise ValueError("unsupported human-review rubric")
    score = item["score"]
    if not isinstance(score, dict) or set(score) != set(BINDING_FIELDS + RATING_FIELDS):
        raise ValueError("unexpected score fields")
    if score["schema_version"] != "1" or score["rubric_version"] != "manual-v1":
        raise ValueError("unsupported score schema or rubric")
    if any(not isinstance(score[key], str) or not score[key] for key in BINDING_FIELDS):
        raise ValueError("score bindings must remain nonempty strings")
    if any(score[key] is not None for key in RATING_FIELDS):
        raise ValueError("render only an unscored template; preserve existing human work")
    for field, allowed in (
        ("gold_evidence", SOURCE_FIELDS),
        ("citations", SOURCE_FIELDS | {"evidence_id", "repo_commit"}),
    ):
        if not isinstance(item[field], list) or any(
            not isinstance(ref, dict) or set(ref) != allowed for ref in item[field]
        ):
            raise ValueError(f"unexpected {field} reference fields")
    if not isinstance(item["citation_claims"], list) or any(
        not isinstance(claim, str) for claim in item["citation_claims"]
    ):
        raise ValueError("citation_claims must be a list of strings")


def load_template(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    items = []
    seen = set()
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        try:
            item = json.loads(line, object_pairs_hook=_unique, parse_constant=_constant)
            _validate(item)
            identity = (item["score"]["run_id"], item["score"]["job_id"])
            if identity in seen:
                raise ValueError("duplicate review job")
            seen.add(identity)
            items.append(item)
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError(f"invalid template line {number}: {exc}") from exc
    if not items:
        raise ValueError("review template contains no answer items")
    if len({item["score"]["run_id"] for item in items}) != 1:
        raise ValueError("review template mixes runs")
    return items, hashlib.sha256(raw).hexdigest()


def _block(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
    # Keep model/source Markdown literal, including any code fences in an answer.
    width = max([2, *(len(match.group()) for match in re.finditer(r"`+", text))]) + 1
    fence = "`" * width
    return f"{fence}\n{text}\n{fence}\n"


def render_item(item: dict[str, Any], position: int) -> str:
    bindings = {
        "review_id": item["review_id"],
        **{key: item["score"][key] for key in BINDING_FIELDS},
    }
    sections = [f"## Item {position}\n", "### Immutable review bindings\n", _block(bindings)]
    for title, field in (
        ("Question", "question"),
        ("Reference answer", "reference_answer"),
        ("Gold source references", "gold_evidence"),
        ("Generated answer", "generated_answer"),
        ("Citations", "citations"),
        ("Claimed evidence IDs", "citation_claims"),
    ):
        sections.extend([f"### {title}\n", _block(item[field])])
    sections.extend(
        [
            "### Source commit\n",
            _block(item["repo_commit"]),
            "### Human review\n",
            "Reviewer: \n\nReviewed at (with timezone): \n\nCorrectness: \n\n"
            "Citation support (or not applicable): \n\nNotes:\n\n\n",
        ]
    )
    return "\n".join(sections)


def write_packets(items: list[dict[str, Any]], digest: str, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=False)
    paths = []
    for offset in range(0, len(items), PACKET_SIZE):
        packet = items[offset : offset + PACKET_SIZE]
        number = offset // PACKET_SIZE + 1
        header = (
            f"# Review packet {number:03d}: items {offset + 1}–{offset + len(packet)}\n\n"
            "Order follows the shuffled template; no condition or strategy labels are added.\n\n"
            f"Template SHA-256: `{digest}`\n\n"
            "Only an actual human may fill the blank ratings. Preserve all bindings; "
            "transfer completed judgments to the matching nested score objects.\n\n"
            f"Correctness rubric: {items[0]['rubric']['correctness']}\n\n"
            f"Citation rubric: {items[0]['rubric']['citation_support']}\n\n"
        )
        path = output / f"packet-{number:03d}.md"
        with path.open("x", encoding="utf-8") as stream:
            stream.write(
                header
                + "\n---\n\n".join(
                    render_item(item, offset + index + 1) for index, item in enumerate(packet)
                )
            )
        paths.append(path)
    return paths


def main() -> int:
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=directory / "review-packets")
    args = parser.parse_args()
    try:
        # Deliberately fixed to this NEW run's template; never look up raw results.
        items, digest = load_template(directory / TEMPLATE_NAME)
        paths = write_packets(items, digest, args.output_dir)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"Review packet generation failed: {exc}\n")
    print(
        json.dumps(
            {
                "items": len(items),
                "packets": len(paths),
                "output_directory": str(args.output_dir.resolve()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

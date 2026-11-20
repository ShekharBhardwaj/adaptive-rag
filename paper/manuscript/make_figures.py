"""Draw the manuscript's figures as SVG from the recorded result files. Offline.

Every plotted value is read from the two analysis outputs named below; nothing is
typed in by hand. Run from the repository root:

    .venv/bin/python paper/manuscript/make_figures.py

Colours are the validated blue and red of the charting palette on a white page
(checked with its validator: lightness, chroma, colour-vision separation and
contrast all pass). The figures are static, for print; each mark carries a
<title> so the HTML preview shows its value on hover, and every plotted value is
also in a table of the manuscript.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = ROOT / "experiments/analysis/heldout-confirmatory-20261119"
HELD_OUT = ANALYSIS / "heldout-confirmatory.json"
DEVELOPMENT = ANALYSIS / "development-validation.json"
OUT = Path(__file__).resolve().parent / "figures"

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
BLUE, RED = "#2a78d6", "#e34948"
FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif'

NAMES = {
    "no_retrieval": "No retrieval",
    "vector": "Vector",
    "adaptive_cascade": "Cascade",
    "agentic_wrapup": "Agentic, reserved",
    "agentic": "Agentic, original",
}


def text(x: float, y: float, body: str, *, size: int = 13, fill: str = INK2, **attrs: str) -> str:
    extra = "".join(f' {key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    opening = f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}"{extra}>'
    return f"{opening}{escape(body)}</text>"


def signed(value: float, digits: int = 1) -> str:
    """A signed number with a true minus sign."""
    return f"{value:+.{digits}f}".replace("-", "−")


def svg(width: int, height: int, body: list[str], label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{escape(label)}" '
        f"font-family='{FONT}'>\n"
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


# ------------------------------------------------- Figure 2: correctness against cost

# Where each direct label sits relative to its dot: (text-anchor, dx, dy).
LABELS = {
    ("development", "no_retrieval"): ("start", 10, 4),
    ("development", "vector"): ("start", 10, 4),
    ("development", "adaptive_cascade"): ("start", 10, -8),
    ("development", "agentic_wrapup"): ("middle", 0, -12),
    ("development", "agentic"): ("end", -10, 4),
    ("held_out", "no_retrieval"): ("start", 10, 4),
    ("held_out", "vector"): ("start", 10, 4),
    ("held_out", "adaptive_cascade"): ("middle", 0, -12),
    ("held_out", "agentic_wrapup"): ("middle", 0, -12),
    ("held_out", "agentic"): ("end", -10, 4),
}


def quality_cost(development: dict, held_out: dict) -> str:
    width, height = 760, 372
    left, top, plot_w, plot_h, gap = 58, 62, 320, 240, 44
    x_max = 0.08
    body: list[str] = []
    body.append(f'<circle cx="{left + 5}" cy="22" r="5" fill="{BLUE}"/>')
    body.append(text(left + 16, 26, "Cascade (adaptive)"))
    body.append(f'<circle cx="{left + 176}" cy="22" r="5" fill="{MUTED}"/>')
    body.append(text(left + 187, 26, "Fixed strategy"))
    panels = (
        ("development", "Development questions (15)", development),
        ("held_out", "Held-out questions (15)", held_out),
    )
    for index, (split, title, result) in enumerate(panels):
        x0 = left + index * (plot_w + gap)

        def px(cost: float, x0: float = x0) -> float:
            return x0 + cost / x_max * plot_w

        def py(score: float) -> float:
            return top + plot_h - score / 100 * plot_h

        body.append(text(x0, top - 14, title, size=14, fill=INK, font_weight="600"))
        for tick in range(0, 101, 20):
            stroke = AXIS if tick == 0 else GRID
            body.append(
                f'<line x1="{x0}" x2="{x0 + plot_w}" y1="{py(tick):.1f}" y2="{py(tick):.1f}" '
                f'stroke="{stroke}" stroke-width="1"/>'
            )
            if index == 0:
                body.append(text(x0 - 8, py(tick) + 4, str(tick), fill=MUTED, text_anchor="end"))
        for step in range(5):
            cost = step * 0.02
            body.append(
                f'<line x1="{px(cost):.1f}" x2="{px(cost):.1f}" y1="{top}" y2="{top + plot_h}" '
                f'stroke="{AXIS if step == 0 else GRID}" stroke-width="1"/>'
            )
            label = "$0" if step == 0 else f"${cost:.2f}"
            body.append(text(px(cost), top + plot_h + 16, label, fill=MUTED, text_anchor="middle"))
        body.append(
            text(
                x0 + plot_w / 2,
                top + plot_h + 38,
                "Known cost per question (USD)",
                text_anchor="middle",
            )
        )
        conditions = result["descriptive"]["conditions"]
        for name in ("no_retrieval", "vector", "agentic", "agentic_wrapup", "adaptive_cascade"):
            cost = conditions[name]["mean_known_cost_per_job_usd"]
            score = conditions[name]["failure_aware_correctness"] * 100
            cascade = name == "adaptive_cascade"
            anchor, dx, dy = LABELS[(split, name)]
            body.append(
                f"<g><title>{escape(NAMES[name])}: {score:.1f}% correct, "
                f"${cost:.4f} per question</title>"
                f'<circle cx="{px(cost):.1f}" cy="{py(score):.1f}" r="5" '
                f'fill="{BLUE if cascade else MUTED}" stroke="{SURFACE}" stroke-width="2"/></g>'
            )
            body.append(
                text(
                    px(cost) + dx,
                    py(score) + dy,
                    NAMES[name],
                    fill=INK if cascade else INK2,
                    text_anchor=anchor,
                    **({"font_weight": "600"} if cascade else {}),
                )
            )
    mid_y = top + plot_h / 2
    body.append(
        f'<text transform="translate(16 {mid_y:.1f}) rotate(-90)" font-size="13" fill="{INK2}" '
        f'text-anchor="middle">Correctness (%), failed jobs count as zero</text>'
    )
    return svg(width, height, body, "Correctness against cost per question, by condition")


# ----------------------------------- Figure 3: per-question difference, cascade - Vector


def bar(x_zero: float, y: float, length: float, thickness: float, fill: str, tip: str) -> str:
    """A bar from the baseline with a 4px rounded data end and a square base."""
    r = min(4.0, abs(length), thickness / 2)
    sign = 1 if length > 0 else -1
    end = x_zero + length
    sweep = 1 if sign > 0 else 0
    return (
        f'<path d="M{x_zero:.1f},{y:.1f} H{end - sign * r:.1f} '
        f"A{r},{r} 0 0 {sweep} {end:.1f},{y + r:.1f} V{y + thickness - r:.1f} "
        f'A{r},{r} 0 0 {sweep} {end - sign * r:.1f},{y + thickness:.1f} H{x_zero:.1f} Z" '
        f'fill="{fill}"><title>{escape(tip)}</title></path>'
    )


def per_question(held_out: dict) -> str:
    questions = held_out["descriptive"]["question_means"]
    rows = sorted(
        (
            (
                values["adaptive_cascade"] - values["vector"],
                question_id,
                values["cascade_escalations"],
            )
            for question_id, values in questions.items()
        ),
        key=lambda row: (-row[0], row[1]),
    )
    width = 700
    left, top, plot_w, row_h, thickness = 78, 66, 380, 21, 12
    low, high = -60, 80
    bottom = top + row_h * len(rows)
    height = bottom + 52

    def px(points: float) -> float:
        return left + (points - low) / (high - low) * plot_w

    body: list[str] = []
    body.append(f'<rect x="{left}" y="14" width="12" height="10" fill="{BLUE}"/>')
    body.append(text(left + 18, 23, "Cascade higher"))
    body.append(f'<rect x="{left + 140}" y="14" width="12" height="10" fill="{RED}"/>')
    body.append(text(left + 158, 23, "Vector higher"))
    body.append(text(left - 10, top - 12, "Question", fill=MUTED, text_anchor="end"))
    note_x = left + plot_w + 24
    body.append(text(note_x, top - 12, "Cascade escalated", fill=MUTED))
    for tick in range(low, high + 1, 20):
        body.append(
            f'<line x1="{px(tick):.1f}" x2="{px(tick):.1f}" y1="{top - 4}" y2="{bottom}" '
            f'stroke="{AXIS if tick == 0 else GRID}" stroke-width="1"/>'
        )
        label = "0" if tick == 0 else signed(tick, 0)
        body.append(text(px(tick), bottom + 16, label, fill=MUTED, text_anchor="middle"))
    body.append(
        text(
            left + plot_w / 2,
            bottom + 38,
            "Cascade minus Vector, percentage points (mean of three repetitions)",
            text_anchor="middle",
        )
    )
    for index, (difference, question_id, escalations) in enumerate(rows):
        y = top + index * row_h
        middle = y + row_h / 2 + 4
        points = difference * 100
        body.append(text(left - 10, middle, question_id, text_anchor="end"))
        if abs(points) > 1e-9:
            tip = f"{question_id}: {signed(points)} points; escalated {escalations} of 3 times"
            body.append(
                bar(
                    px(0),
                    y + (row_h - thickness) / 2,
                    px(points) - px(0),
                    thickness,
                    BLUE if points > 0 else RED,
                    tip,
                )
            )
            if points > 0:
                body.append(text(px(points) + 6, middle, signed(points)))
            else:
                body.append(text(px(points) - 6, middle, signed(points), text_anchor="end"))
        else:
            body.append(text(px(0) + 6, middle, "0", fill=MUTED))
        note = "never" if escalations == 0 else f"{escalations} of 3 repetitions"
        body.append(text(note_x, middle, note, fill=MUTED if escalations == 0 else INK2))
    return svg(width, height, body, "Per-question difference in correctness, cascade minus Vector")


# --------------------------------------------------------------- Figure 1: the cascade


def box(x: float, y: float, w: float, h: float, lines: list[str], *, accent: bool = False) -> str:
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{SURFACE}" '
        f'stroke="{BLUE if accent else AXIS}" stroke-width="{2 if accent else 1}"/>'
    ]
    first = y + h / 2 - (len(lines) - 1) * 8 + 4.5
    for index, line in enumerate(lines):
        parts.append(
            text(
                x + w / 2,
                first + index * 16,
                line,
                fill=INK if index == 0 else INK2,
                text_anchor="middle",
                **({"font_weight": "600"} if index == 0 else {}),
            )
        )
    return "".join(parts)


def arrow(x1: float, y1: float, x2: float, y2: float, *, accent: bool = False) -> str:
    colour = BLUE if accent else MUTED
    marker = "tip-accent" if accent else "tip"
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
        f'stroke-width="{2 if accent else 1.25}" marker-end="url(#{marker})"/>'
    )


def cascade(held_out: dict) -> str:
    summary = held_out["descriptive"]["cascade"]
    escalated, observed = summary["escalated"], summary["observed"]
    kept = observed - escalated
    width, height = 760, 250
    body = [
        "<defs>"
        f'<marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker>'
        f'<marker id="tip-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{BLUE}"/>'
        "</marker></defs>"
    ]
    y1, y2, h = 34, 162, 56
    body.append(box(14, y1, 96, h, ["Question"]))
    body.append(box(150, y1, 150, h, ["Vector search", "top 5 chunks"]))
    body.append(
        box(340, y1, 190, h, ["Answer model", "answer, citations and", "“evidence sufficient?”"])
    )
    body.append(box(600, y1, 146, h, ["First answer"]))
    body.append(
        box(
            150,
            y2,
            190,
            h,
            ["Agentic navigation", "reserved selection,", "at most 5 chunks"],
            accent=True,
        )
    )
    body.append(box(380, y2, 150, h, ["Answer model", "same prompt"]))
    body.append(box(600, y2, 146, h, ["Second answer"]))
    body.append(arrow(110, y1 + h / 2, 148, y1 + h / 2))
    body.append(arrow(300, y1 + h / 2, 338, y1 + h / 2))
    body.append(arrow(530, y1 + h / 2, 598, y1 + h / 2))
    body.append(text(564, y1 + h / 2 - 8, "sufficient", text_anchor="middle"))
    body.append(
        text(564, y1 + h / 2 + 18, f"{kept} of {observed}", fill=MUTED, text_anchor="middle")
    )
    # the escalation path: down from the first answer, left, then into the navigator
    mid = (y1 + h + y2) / 2
    body.append(
        f'<path d="M435,{y1 + h} V{mid} H245 V{y2 - 2}" fill="none" stroke="{BLUE}" '
        f'stroke-width="2" marker-end="url(#tip-accent)"/>'
    )
    body.append(text(445, mid - 6, "insufficient, or the first stage failed"))
    body.append(text(445, mid + 9, f"{escalated} of {observed}", fill=MUTED))
    body.append(arrow(340, y2 + h / 2, 378, y2 + h / 2, accent=True))
    body.append(arrow(530, y2 + h / 2, 598, y2 + h / 2, accent=True))
    body.append(
        text(
            14,
            height - 8,
            "If the second stage does not complete, the completed first answer is kept. "
            "Counts are held-out jobs.",
            fill=MUTED,
        )
    )
    return svg(width, height, body, "The vector-first cascade")


def main() -> None:
    held_out = json.loads(HELD_OUT.read_text("utf-8"))
    development = json.loads(DEVELOPMENT.read_text("utf-8"))
    if held_out["split"] != "held_out" or development["split"] != "development":
        raise SystemExit("the result files are not the expected splits")
    OUT.mkdir(parents=True, exist_ok=True)
    figures = {
        "fig1-cascade.svg": cascade(held_out),
        "fig2-correctness-cost.svg": quality_cost(development, held_out),
        "fig3-per-question.svg": per_question(held_out),
    }
    for name, content in figures.items():
        (OUT / name).write_text(content, "utf-8")
        print("wrote", (OUT / name).relative_to(ROOT), len(content), "bytes")


if __name__ == "__main__":
    main()

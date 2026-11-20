# Human review: direct Anthropic development run

This guide applies only to
[`adaptive-anthropic-development-20261116-001`](../../raw/adaptive-anthropic-development-20261116-001/).
Its setup uses direct Anthropic Claude Haiku 4.5 chat for routing, navigation,
and answers, with Qwen query embeddings and the existing compatible vector
index. Execution stopped with **73 of 270 jobs observed**: 58 completed,
13 budget-exhausted, and 2 errors; 197 planned jobs remain unrun. An answer-request
timeout left usage unknown and stopped further requests. No automatic rerun is
scheduled. The answer prompt is unchanged, and the earlier run is preserved.

**59 answer texts are available, all pending human review**, including available
text from unsuccessful jobs. Use the
[shuffled template](answers.review-template.jsonl) or these readable packets:

- [Packet 1: items 1–15](review-packets/packet-001.md)
- [Packet 2: items 16–30](review-packets/packet-002.md)
- [Packet 3: items 31–45](review-packets/packet-003.md)
- [Packet 4: items 46–59](review-packets/packet-004.md)

The packets are already generated. The helper can create another working copy
only in a fresh output directory:

```sh
python3 experiments/reviews/adaptive-anthropic-development-20261116-001/render_review_packets.py \
  --output-dir /path/to/a/fresh/review-packets-copy
```

Start with Packet 1 and continue in packet order. The helper
preserves template order and bindings, adds blank human-rating fields, and
refuses to overwrite an existing packet directory. Use `--output-dir` with a
fresh directory if needed. It reads only this run's template. Packet notes are a
working aid; transfer genuine completed judgments to the matching nested `score`
objects before saving the score-only JSONL below.

1. Use the shuffled review template or packets. Keep conditions and
   selected retrieval strategies hidden: do not inspect raw results, traces,
   routing decisions, summaries, or job-ID mappings while scoring. Answer style
   can still reveal a condition.
2. Compare each generated answer with its question and reference answer, then
   check claims against the cited and gold source ranges in the
   [pinned checkout](../../../datasets/repos/langchain/) at
   [`ea17e48f0a4336c920394fd029de99f1568b4c38`](https://github.com/langchain-ai/langchain/tree/ea17e48f0a4336c920394fd029de99f1568b4c38).
   A matching reference or valid citation ID alone does not establish correctness
   or semantic citation support. Explain disagreements in your notes.
3. An actual human reviewer fills each nested `score` object. Use your real
   reviewer identity and actual review time. Never invent reviews or substitute
   an automated judgment for a claimed human review. Leave unfinished items
   pending; a missing judgment is not zero.
4. Save only completed nested `score` objects as `answers.scores.jsonl` in this
   directory, one JSON object per line. Exclude pending items and outer template
   fields; keep the filled template as your working copy. Do not modify raw runs,
   generated answers, source citations, or reference annotations.

| Editable field | Required value |
| --- | --- |
| `reviewer` | Nonempty human reviewer identity. |
| `reviewed_at` | Actual ISO 8601 review timestamp with timezone, not earlier than the answer output. |
| `correctness` | A finite number in [0, 1]: `0` incorrect, `0.5` partly correct, `1` fully correct. Justify other values in `notes`. |
| `citation_support` | A finite number in [0, 1] for semantic support of claims by cited source, or `null` when not applicable. |
| `notes` | Nonempty justification with source checks and limitations. |

Preserve `schema_version: "1"`, `rubric_version: "manual-v1"`, `run_id`, `job_id`,
and `output_sha256` exactly as supplied. The IDs and hash bind each score to the
exact frozen answer result, including recorded calls. Do not recompute them.
Use JSON numbers, not strings or booleans. All editable template nulls mean
pending except `citation_support`, which may remain null when not applicable.
Missing answer text cannot receive a score; available partial text may be judged
on its content while execution failures are accounted for separately.

After genuine scores are saved, run from the repository root with a fresh output
path:

```sh
uv run adaptive-rag experiment summarize \
  experiments/raw/adaptive-anthropic-development-20261116-001 \
  --reviews experiments/reviews/adaptive-anthropic-development-20261116-001/answers.scores.jsonl \
  --bootstrap-samples 2000 --seed 0 \
  --output experiments/aggregates/adaptive-anthropic-development-20261116-001-reviewed.json
```

The loader rejects stale hashes, duplicate/unknown jobs, invalid scores, and
scores without answer text. Report missing reviews and review coverage alongside
any correctness result. See the [scoring workflow](../../README.md#independent-answer-review).
The [execution report](../../../paper/phase5-development-run.md) contains condition
labels and aggregate outcomes; leave it closed until scoring is complete to
preserve blinding.

# Human scoring: adaptive development run

Review the answers from [this run](../../raw/adaptive-development-20261116-001/)
against the [pinned LangChain checkout](../../../datasets/repos/langchain/) at
[`ea17e48f0a4336c920394fd029de99f1568b4c38`](https://github.com/langchain-ai/langchain/tree/ea17e48f0a4336c920394fd029de99f1568b4c38).
This guide contains no completed reviews. The shuffled
`answers.review-template.jsonl` will be generated after execution.

1. Open the review template when it is available. Review each item independently
   using its question, reference answer, gold source ranges, generated answer,
   and citations. Keep conditions and selected retrieval strategies hidden:
   avoid raw results, traces, routing decisions, summaries, and job-ID lookups
   until scoring is complete. Answer style may still reveal a condition.
2. Inspect the pinned source, including the cited and gold ranges. Compare the
   answer with the reference, then verify its claims against source. A matching
   reference or valid citation ID alone does not establish correctness or
   semantic support. Explain source/reference disagreements in `notes`; do not
   edit the reference, generated answer, citations, or raw run.
3. Fill the nested `score` object using the fields below. Record only judgments
   actually made by the named human reviewer. Leave unfinished items pending;
   never invent reviews or assign zero merely because an item is unreviewed.
4. Save only completed nested `score` objects, one JSON object per line, as
   `answers.scores.jsonl` in this directory. Exclude pending items and all outer
   template fields. Use no blank lines, duplicate jobs, or extra fields. Keep
   the filled template as the review working copy.

| Field | What to enter |
| --- | --- |
| `reviewer` | Your nonempty reviewer identity. |
| `reviewed_at` | Actual review time in ISO 8601 with timezone, such as `2026-11-16T18:30:00-05:00`; it must not predate the output. |
| `correctness` | A finite number from 0 to 1: `0` incorrect, `0.5` partly correct, `1` fully correct. Justify other values in `notes`. |
| `citation_support` | A finite number from 0 to 1 for semantic support of claims by cited source; use `null` only when not applicable. Unsupported claimed citations deserve a low score, not an automatic null. |
| `notes` | A nonempty explanation of the correctness and citation judgments, with source checks or limitations. |

Keep `schema_version: "1"`, `rubric_version: "manual-v1"`, `run_id`, `job_id`,
and `output_sha256` exactly as supplied. The IDs and hash bind the score to the
exact saved answer result, including its recorded calls. Do not recompute them.
Numbers must be JSON numbers, not strings or booleans. Template nulls are pending
placeholders; only `citation_support` may remain null in a completed score.

Missing answer outputs cannot receive scores. Available partial answer text may
be judged on its content; the analysis separately accounts for execution failure.
Missing reviews remain pending and must be reported with review coverage.

After saving genuine scores, run this from the repository root, using a fresh
summary path:

```sh
uv run adaptive-rag experiment summarize \
  experiments/raw/adaptive-development-20261116-001 \
  --reviews experiments/reviews/adaptive-development-20261116-001/answers.scores.jsonl \
  --bootstrap-samples 2000 --seed 0 \
  --output experiments/aggregates/adaptive-development-20261116-001-reviewed.json
```

The loader rejects stale hashes, unknown/duplicate jobs, invalid scores, and
scores without answer text. See the [review workflow](../../README.md#independent-answer-review)
and [score schema](../../../src/adaptive_rag/evaluation/reviews.py).

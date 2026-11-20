# Review material: cascade development run

Run `efc5034c-b904-4a02-889f-f45e746a3e49`, raw output in
`experiments/raw/adaptive-cascade-development-20261119-001`. Development split only.

**Status on November 19, 2026: all 206 available answers have AI scores.**
The user explicitly requested this AI evaluation. The reviewer is
`Codex (AI reviewer)`; these are not human ratings or scores attributed to Shekhar.
There are no pending AI reviews. No human score file has been created.

**Reviewed by Shekhar — November 19, 2026 at 2:40 PM EST.**
Shekhar's [review attestation](shekhar-review-attestation.json) records his
additional review of this material. The existing scores retain their AI
attribution; no separate per-item human ratings were supplied.

The AI assessment found **127 correct, 37 partial, 32 abstentions and 10 incorrect
answers**. See the [final AI summary](final-ai-review-summary.json) and
[run report](../../../paper/phase6-cascade-development-run.md#ai-reviewed-development-results)
for condition comparisons and their limits.

| File | What it is |
| --- | --- |
| `answers.review-template.jsonl` | 206 blinded review items, shuffled with seed 0. SHA-256 `af02082dc3452bf6042194c5c7eeca89cc135df817531ca8cf5b71c2295227a9`. |
| `review-packets/packet-001.md` to `packet-014.md` | The same items as readable packets of 15 (the last has 11), in template order, with no condition or strategy labels. |
| `render_review_packets.py` | The renderer, copied unchanged from the previous run's review folder. |
| `answers.ai-scores.jsonl` | All 206 validated AI ratings, with original binding fields retained. SHA-256 `99d4a84742cf75b8b83483cf1e0b93d65471872f5de2adb32a9a1555a402d2c0`. |
| `ai-review/scored-packets/packet-001.ai-review.md` to `packet-014.ai-review.md` | Readable AI scores and reasons, with links to the original blinded packets. |
| `ai-review/item-assessments.jsonl` | Per-item classifications, source checks, flags and formal scores. |
| `ai-review/rubric.json` and `ai-review/adjudication.json` | Operational scoring criteria and decisions on borderline cases, frozen before unblinding. |
| `ai-review/inputs-manifest.json` and `ai-review/scores-frozen.json` | Input/source hashes, blinding method, score freeze and file-creation timestamp provenance. |
| `final-ai-review-summary.json` and `review-progress.json` | Explicitly AI-labelled results and complete review coverage. |
| `shekhar-review-attestation.json` | Shekhar's additional review attestation and its current New York timestamp. |

The 206 items are the completed jobs. The 19 failed jobs produced no answer text,
receive no rating, and count as zero in the failure-aware metric.

The rubric is `manual-v1`: correctness 0, 0.5 or 1; citation support 0 to 1 from
inspecting the cited source, or null when not applicable. Its existing schema is
reused for this explicitly AI-labelled assessment. The user's request supersedes
this folder's earlier human-only scoring instructions. A future human review
would be a separate evaluation in `answers.scores.jsonl`.

The original template remains blank and all original packets remain unchanged.
The 206 items contain 88 distinct question/answer/citation cases across 15
development questions. Exact repeats share an assessment; each original item
retains its own output binding. Delegated source inspection and Codex adjudication
form one AI evaluation workflow, without an independent human or inter-rater
reliability estimate. All 130 distinct cited/reference excerpt hashes were
checked against the pinned repository. Scores were frozen before examining
condition labels and aggregate results; answer style may still suggest strategy.

Review timestamps use the original creation times of the completed assessment
files, following the user's file-creation-time convention. The freeze record
preserves the original timestamps, hashes and derivation.

The project's `experiment summarize --reviews` command validated every rating
against its frozen output. Its unchanged result is in
`ai-review/cli-aggregate-validation.json`. That CLI emits legacy generic text
about independent reviews and a 30-question pilot; the
[final AI aggregate](../../aggregates/adaptive-cascade-development-20261119-001-ai-reviewed-001.json)
retains every numerical result and corrects those descriptions for this AI
review of 15 development questions. The historical unreviewed aggregate and
preflight outcome remain unchanged.

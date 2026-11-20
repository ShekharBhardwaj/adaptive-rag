# Review material: held-out run

Run `eb914cf0-4437-4d25-bfd3-2b4253f990a6`, raw output in
`experiments/raw/adaptive-cascade-heldout-20261119-001`. Held-out split only.

**Status on November 20, 2026: all 202 answers have frozen AI scores in `answers.ai-scores.jsonl`, recorded by `ai-review/scores-frozen.json` at 9:09 AM EST. No result or comparison existed when the scores were frozen.**

**Reviewed by Shekhar on November 20, 2026 at 9:14 AM EST.** The
[review attestation](shekhar-review-attestation.json) records Shekhar's
statement about the frozen AI score file. The scores keep their AI attribution;
no separate per-item human scores were supplied.

**Comparisons computed on November 20, 2026 at 9:15 AM EST,** after the freeze
and the attestation. They are in
[the results report](../../../paper/phase7-held-out-results.md).

| File | What it is |
| --- | --- |
| `answers.review-template.jsonl` | 202 blinded review items, shuffled with seed 0. SHA-256 `8518b2ff60d2aff5…`; the full value is in the run's `outcome.json`. |
| `review-packets/packet-001.md` to `packet-014.md` | The same items as readable packets of 15 (the last has 7), in template order, with no condition or strategy labels. |
| `render_review_packets.py` | The renderer, copied unchanged from the development run's review folder. |

The 202 items are the completed jobs. The 23 failed jobs produced no answer
text, receive no rating, and count as zero in the failure-aware metric.

## Scoring is fixed by the protocol

[The held-out protocol](../../../paper/phase7-held-out-protocol.md) was frozen
before this run and governs how these answers are scored:

- Codex, as an AI reviewer, scores each distinct answer against the pinned
  source with the `manual-v1` rubric and the operational criteria in
  `../adaptive-cascade-development-20261119-001/ai-review/rubric.json`
  (SHA-256 `3c53c294e7bf1f645d774c09a78bf4465848cb73b503e3c456b7257086dff4af`).
- The reviewer sees no condition label, selected strategy, raw trace or
  aggregate. Scores and borderline decisions are frozen, with hashes recorded,
  before any of those is examined.
- Shekhar's review of the scores is recorded as an attestation. Per-item human
  scores, if supplied, go in a separate `answers.scores.jsonl`.
- Results are described as scored by an AI reviewer and reviewed by the author.

Changing the criteria, the reviewer or the order of these steps after seeing
answers would depart from the protocol and must be recorded as a deviation.

## Where the scoring output goes

The comparisons are computed by
[confirmatory.py](../../analysis/heldout-confirmatory-20261119/confirmatory.py),
which was fixed before any held-out score existed. It reads three files from
this folder, named as in the development review:

| File | What it must contain |
| --- | --- |
| `answers.ai-scores.jsonl` | One line per review item: the item's `score` object from the template with `reviewer`, `reviewed_at`, `correctness` and `notes` filled, and `citation_support` filled or null. All 202 items, each once. |
| `ai-review/scores-frozen.json` | The freeze record. It must name the SHA-256 of the score file, of the unchanged template and of the frozen criteria file. |
| `shekhar-review-attestation.json` | Shekhar's review of the scores, naming the SHA-256 of the score file. |

The script stops without computing anything if an answer is unscored, if a
score is bound to a different output, or if the score file no longer matches the
hash in the freeze record.

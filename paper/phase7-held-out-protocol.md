# Phase 7: held-out evaluation protocol

Prepared November 19, 2026 by Claude (an AI assistant) for Shekhar. **Status:
proposed, not authorized, not run.** No held-out job has been started and no
model request was made in preparing this document.

This protocol fixes, before any held-out answer exists, what will be run, how
it will be scored and how the result will be worded. It is the one confirmatory
test of the phase 6 redesign. Everything measured so far used the 15
development questions on which the redesign was built, so it cannot show that
the design generalizes.

## What is frozen

The held-out run uses the code, prompts, policies, limits and settings of
development run `efc5034c-b904-4a02-889f-f45e746a3e49` with one change: the
split. An offline dry run of the planning command prepared 225 jobs over 15
held-out questions, none of which appear in the development run, and matched
the development run on every item below.

| Item | Frozen value |
| --- | --- |
| Configuration | [adaptive.cascade.heldout.proposed.local.yaml](../configs/adaptive.cascade.heldout.proposed.local.yaml); equal to the development configuration except `split: held_out` |
| Framework source | SHA-256 `b59ad0bce4ec8947…`, identical to the development run; full value in the freeze record |
| Benchmark | `benchmarks/pilot.jsonl`, SHA-256 `e4c33c295518876c…`; 15 held-out questions |
| Corpus | LangChain at `ea17e48f0a4336c920394fd029de99f1568b4c38` |
| Index | `phase4-002`, `index_sha256` `5217f824…`, manifest hash `15ac7923…`; not rebuilt |
| Navigation and answers | Anthropic `claude-haiku-4-5-20251001`, direct |
| Embeddings | OpenRouter `qwen/qwen3-embedding-8b` |
| Conditions | `vector`, `agentic`, `agentic_wrapup`, `adaptive_cascade`, `no_retrieval` |
| Policies | `vector-first-cascade-v1`; `agentic-wrapup-v1` with prompt `repository-navigation-v7-wrapup`; original navigator `repository-navigation-v6`; shared answer prompt `grounded-answer-v4-sufficiency` |
| Repetitions and order | 3 per question and condition; order seed 17 |
| Per retrieval | 12 model calls, 128,000 tokens, 24 tool calls, 300 seconds |
| Per answer | 64,000 tokens, 1,024 output tokens, 90 seconds |
| Pacing | one request in flight, 6 seconds between starts, 10 starts per rolling minute |
| Run limits | 2,400 model attempts, 14,000,000 budgeted tokens, 10,800 seconds, $12.00 admission estimate |
| Unknown usage | `reserve`; no automatic retries |

The full hashes are in the
[freeze record](../experiments/preflight/cascade-heldout-2026-11-19-001/protocol-freeze.json).
Any change to an item above after approval makes this a different protocol and
must be recorded as such before the run.

## Comparisons and how they will be worded

The primary metric is failure-aware correctness: the mean rubric score, with a
partial answer worth 0.5, over all 45 planned jobs of a condition, counting
every unsuccessful job as zero. Uncertainty is the paired question-cluster
percentile bootstrap with 15 clusters, 2,000 samples and seed 0, reported as a
95% interval with no multiplicity adjustment.

Three comparisons are confirmatory. Their order and direction are fixed here.

1. **Cascade minus Vector**, on correctness.
2. **Cascade against reserved-selection Agentic**, on correctness, on known
   cost per job and on elapsed time per job.
3. **Reserved-selection Agentic minus original Agentic**, on correctness.

The wording of each result is fixed in advance:

- **Supported:** the point estimate is in the stated direction and the 95%
  interval excludes zero.
- **Direction only:** the point estimate is in the stated direction and the
  interval includes zero.
- **Not supported:** the point estimate is zero or in the opposite direction.
- **Quality against Agentic:** the two are called similar only if the whole
  interval lies within ten points either side of zero. Otherwise the result is
  "not distinguishable at this sample size", whatever the point estimate.
- **Efficiency:** "the cascade costs less than always using Agentic" is
  supported if the paired cost interval lies below zero. It is stated together
  with the quality result, never instead of it.

Two things will not be claimed from this run: that the cascade is cheaper or
faster than Vector, which it cannot be because it always runs Vector first; and
that the result holds for other repositories, models or question sets.

## Descriptive results

These are reported without a confirmatory claim: the escalation rate and
reasons; how many zero-score or partial first-stage answers were not escalated;
citation support; mechanical evidence recall; request counts; and how the
reserved-selection navigator ended its runs.

A pooled table over all 30 questions may be shown. It mixes the development
questions the design was built on with the held-out questions, so it is labelled
as such and supports no confirmatory statement.

## Failures and accounting

- Nothing is retried, rerun, appended or replaced. The reserved-selection
  navigator's single in-budget selection retry is part of that condition.
- Every unsuccessful job counts as zero and stays in the denominator.
- A job that fails because the provider could not be reached counts as a
  failure in the primary analysis. One sensitivity analysis that leaves such
  jobs out is reported beside it, with the jobs listed.
- If the run stops at a limit, the jobs that did not run are missing. The
  affected results are reported as incomplete and no top-up run is merged in.
- Known cost is the estimate from reported usage at the frozen price schedule.
  A job with unknown usage is left out of its condition's subtotal and named.

## Scoring

Scoring follows the development run so that the two are comparable. It is fixed
here because it must not depend on what the answers turn out to be.

- Every answer text is exported blinded with seed 0 into a template and
  packets that carry no condition or strategy label.
- Codex, as an AI reviewer, scores each distinct answer against the pinned
  source using the `manual-v1` rubric with the operational criteria frozen in
  the development review's `ai-review/rubric.json` (SHA-256 `3c53c294…`).
- Scores and borderline decisions are frozen, with their hashes recorded,
  before any condition label, selected strategy or aggregate is examined.
- Shekhar's review of those scores is recorded as an attestation. Per-item
  scores by a human, if supplied, go in a separate `answers.scores.jsonl` and
  are analysed separately.
- Results are described as scored by an AI reviewer and reviewed by the author.
  They are not described as independent human scoring.

An optional addition, not part of this protocol unless chosen before the run: a
second blind AI rating of the same answers, with the agreement between the two
raters reported.

## Who has seen what

- The benchmark's authors and reviewers, including Codex during curation, have
  seen the held-out questions and their reference answers.
- The session that designed and built the phase 6 redesign has not opened a
  held-out question, a held-out reference answer or any held-out output. It
  handled the combined benchmark only by hash, by split counts and through the
  planning command's counts.
- No held-out job has run. The four recorded runs and both earlier frozen plans
  are development-split only.

After this run the held-out questions are spent for this design. Any later
change to a prompt, policy, limit or scoring rule needs new, untouched
questions before another confirmatory claim is made.

## Cost and time

| Item | Estimate |
| --- | --- |
| Jobs | 225 |
| Expected known cost | about $7.10 at the development run's escalation rate; about $6.50 to $9.00 across escalation rates from 0% to 100% |
| Admission estimate limit | $12.00 |
| Compatibility check on the day | at most $0.10, accounted separately |
| Expected duration | about 1.7 to 2.2 hours, set by pacing |
| Answers to score | up to 225 |

The estimate uses the development run's measured costs: $0.06 for
`no_retrieval`, $0.32 for `vector`, $3.25 for `agentic`, $2.58 for
`agentic_wrapup` and $0.82 for `adaptive_cascade`. Held-out questions may cost
more or less.

Leaving out the original `agentic` condition would cut the run to 180 jobs and
about $3.30 to $5.80. It would also drop the third comparison from the
held-out test, leaving the navigator fix supported by development data only.

## Procedure on the day

1. Confirm the published price of the chat model against the frozen schedule.
2. Run the synthetic compatibility check and require every stage to pass.
3. Write the frozen plan, archive the framework and record verification.
4. Start one run in a fresh output directory with sleep prevention on.
5. Confirm the run's manifest equals the frozen plan.
6. Afterwards verify coverage, accounting and pacing, record file hashes,
   export the blinded review material and back the project up.

## Limits that will remain

Fifteen questions can show direction, not proof; intervals of roughly ten to
twenty points either side are expected, as in development. The run covers one
repository, one
model and one benchmark. Scoring is by an AI reviewer with author review. The
sufficiency report cannot catch an answer that is confidently wrong, which was
seen once in development.

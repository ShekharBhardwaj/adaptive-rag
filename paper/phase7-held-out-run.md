# Phase 7: held-out run (execution only, answers unscored)

**Update, November 20, 2026:** the answers have since been scored and the three
comparisons computed. They are in [the results report](phase7-held-out-results.md).
The rest of this page is the execution record as written on November 19.

The held-out run recorded **all 225 planned jobs**: 202 completed, 15
budget-exhausted and 8 errors. No answer has been scored, so this report
contains no correctness result and none of the three confirmatory comparisons.
On execution alone, the cascade completed all 45 jobs and escalated 20 of them,
the reserved-selection navigator completed every retrieval and lost two jobs at
the answer step, and the original navigator completed 24 of 45.

Run ID: `eb914cf0-4437-4d25-bfd3-2b4253f990a6`. The
[raw run](../experiments/raw/adaptive-cascade-heldout-20261119-001/), the
[unreviewed aggregate](../experiments/aggregates/adaptive-cascade-heldout-20261119-001-unreviewed.json)
and the
[outcome record](../experiments/preflight/cascade-heldout-2026-11-19-001/outcome.json)
hold the records and file hashes behind these counts. What was fixed in advance
is in [the held-out protocol](phase7-held-out-protocol.md), which is unchanged
since it was frozen.

## Design

Fifteen held-out questions × five conditions × three repetitions, with 225
unique job IDs and 45 records per condition. None of the questions was in a
development run, and this is the first run on the held-out split. The code,
prompts, policies, limits and settings are those of development run
`efc5034c-b904-4a02-889f-f45e746a3e49`; only the split differs.

Shekhar authorized the run on November 19, 2026. It started at 15:11:42 and
finished at 17:06:20 local time. Its manifest equals the frozen plan on
configuration, benchmark, corpus, index, price schedule, seed, framework source
and the set of planned jobs. No whole job was retried, rerun or replaced.

## Coverage

| Condition | Planned | Observed | Completed | Budget-exhausted | Error | Missing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector | 45 | 45 | 45 | 0 | 0 | 0 |
| Agentic (original) | 45 | 45 | 24 | 15 | 6 | 0 |
| Agentic, reserved selection | 45 | 45 | 43 | 0 | 2 | 0 |
| Cascade | 45 | 45 | 45 | 0 | 0 | 0 |
| No retrieval | 45 | 45 | 45 | 0 | 0 | 0 |
| **Total** | **225** | **225** | **202** | **15** | **8** | **0** |

The terminal status is `completed_with_errors`, and the loader sets
`raw_run_partial: true` for that status. Planned and observed are both 225 and
nothing is missing.

The 23 failures were:

- **Original Agentic, 21:** 11 token-limit stops, six runs that ended in prose
  instead of a selection, three model-call-limit stops and one connection
  timeout.
- **Agentic with reserved selection, 2:** both at the answer step. Retrieval
  completed, and the answer model then wrapped its JSON in a code fence and
  added text after it, which the strict answer format rejects. Both were the
  same question.

The connection timeout is an infrastructure failure with unknown usage. Under
the protocol it counts as a failure in the primary analysis and is left out in
one sensitivity analysis.

## How the two new conditions behaved

**Reserved selection, 45 jobs.**

- All 45 retrievals completed. Selection was required by the token reserve in
  23 jobs; in 20 the navigator selected on its own; in two it began the single
  retry after a rejected selection of its own.
- Eight jobs used the retry and all eight then completed retrieval.
- 57 oversized reads were shortened, two tool calls were not executed because
  selection was required, and no tool output was withheld.
- Selection came through the tool call in 39 jobs and as text in six.
- The median job made seven navigation requests, with a maximum of eleven. The
  original navigator's median was eight, with a maximum of twelve.

**Cascade, 45 jobs.**

- Twenty jobs escalated: 19 because the first-stage answer reported that its
  evidence was insufficient, and one because the first-stage answer failed
  validation.
- Six questions escalated in all three repetitions, one in two of three, and
  eight never.
- All 20 second stages completed, so no job fell back to its first answer.
- The fixed Vector condition reported insufficient evidence in 18 of its 45
  answers.
- After escalation, six of the cascade's final answers still reported
  insufficient evidence.

## Cost and time

| Condition | Known query-cost subtotal (USD) | Jobs with unknown cost | Mean elapsed per attempt, seconds | Model requests |
| --- | ---: | ---: | ---: | ---: |
| Vector | 0.40034252 | 0 | 9.20 | 90 |
| Agentic (original) | 3.10280000 | 1 | 52.21 | 389 |
| Agentic, reserved selection | 2.96208600 | 0 | 52.68 | 388 |
| Cascade | 1.83478052 | 0 | 33.08 | 267 |
| No retrieval | 0.06326300 | 0 | 4.71 | 45 |

Costs include unsuccessful attempts and exclude indexing and the preflight. A
job with unknown usage is left out of its condition's subtotal, so the original
Agentic subtotal is incomplete. Elapsed times include pacing waits and are not
provider latency.

| Accounting quantity | USD | Interpretation |
| --- | ---: | --- |
| Run known cost subtotal | 8.37597204 | Estimate from reported usage and the frozen price schedule; incomplete. |
| Complete run cost estimate | Unknown (`null`) | One timed-out request has unknown usage. |
| Run used-or-reserved admission estimate | 8.39684304 | Separate budget ledger, below the $12.00 limit; not a bill. |
| Synthetic preflight | 0.01846328 | Nine provider requests, accounted separately. |
| Run + preflight known subtotal | 8.39443532 | Still incomplete for the same request. |

There were 1,179 model attempts: 1,089 Anthropic chat requests and 90 Qwen
query embeddings. Runner monotonic elapsed time was 6,877.90 seconds (114.6
minutes).

## Pacing

By recorded wall-clock request starts, the 1,089 Anthropic requests had five
adjacent gaps below six seconds, the smallest 5.913414 seconds, and a
rolling-60-second peak of eleven starts. The configured limits of six seconds
and ten starts per minute were therefore not verified for every recorded
timestamp. Monotonic admission times are not persisted, so delayed recording or
wall-clock variation is possible but unproven. The 90 Qwen requests had a
minimum gap of 6.005201 seconds and a peak of seven. The only recorded
model-call error was the one connection timeout.

## Mechanical evidence recall

This is the overlap between retrieved evidence and the reference source ranges,
computed without human judgment. It is not answer correctness. A failed job
contributes whatever evidence it recorded.

| Condition | Mean recall over 45 jobs | Mean recall among completed jobs |
| --- | ---: | ---: |
| Vector | 0.313 | 0.313 (45) |
| Agentic (original) | 0.499 | 0.936 (24) |
| Agentic, reserved selection | 0.678 | 0.678 (43) |
| Cascade | 0.489 | 0.489 (45) |
| No retrieval | 0.000 | 0.000 (45) |

## What is pending

All 202 answer texts were exported blinded with seed 0 into
[the review folder](../experiments/reviews/adaptive-cascade-heldout-20261119-001/),
as a template and 14 packets. Every rating field is null. The 23 failed jobs
have no answer text and receive no rating.

Scoring follows the frozen protocol: blind AI scoring by Codex with the frozen
criteria, a score freeze before any condition label or aggregate is examined,
and Shekhar's review recorded as an attestation. Only then are the three
confirmatory comparisons computed and worded as the protocol prescribes.

Completion counts, cost and evidence recall do not substitute for those
comparisons. Fifteen questions remain too few to settle a difference of ten
points, and the run covers one repository and one model.

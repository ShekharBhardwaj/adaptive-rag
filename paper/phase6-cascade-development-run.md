# Phase 6: cascade development run and AI evaluation

The run recorded **all 225 planned jobs**: 206 completed, 16 budget-exhausted
and 3 errors. At the user's request, **Codex scored all 206 completed answers**
against the pinned source. These are AI evaluations, not human reviews.
Including failures as zero, Cascade scores 90.0%, Vector 77.8%, and the
reserved-selection navigator 90.0%. Cascade uses more estimated cost and elapsed
time than Vector, so this development result does not establish the original
joint claim of higher quality, lower cost and lower latency.

Run ID: `efc5034c-b904-4a02-889f-f45e746a3e49`. The
[raw run](../experiments/raw/adaptive-cascade-development-20261119-001/), the
[unreviewed aggregate](../experiments/aggregates/adaptive-cascade-development-20261119-001-unreviewed.json)
and the
[outcome record](../experiments/preflight/cascade-development-2026-11-19-001/outcome.json)
hold the records and file hashes behind these counts. The design, its reasons
and the plan are in [the diagnosis and redesign](phase6-diagnosis-and-redesign.md).
The [AI-reviewed aggregate](../experiments/aggregates/adaptive-cascade-development-20261119-001-ai-reviewed-001.json)
adds the completed evaluation; the unreviewed artifacts remain historical records.
Earlier runs used a different answer prompt and human ratings. Do not pool them
with this run or attribute differences solely to the redesign.

## Design

Fifteen development questions × five conditions × three repetitions, with 225
unique job IDs and 45 records per condition. No held-out job ran. Direct
Anthropic `claude-haiku-4-5-20251001` served navigation and the shared answer.
Query embeddings used OpenRouter `qwen/qwen3-embedding-8b` against the existing
index, which was not rebuilt. The corpus is the pinned LangChain commit
`ea17e48f0a4336c920394fd029de99f1568b4c38`.

Every condition used the shared answer prompt `grounded-answer-v4-sufficiency`.
The conditions were `vector`, the original `agentic`, `agentic_wrapup`
(`agentic-wrapup-v1`), `adaptive_cascade` (`vector-first-cascade-v1`) and
`no_retrieval`. Shekhar authorized the run on November 19, 2026. It started at
12:23:05 and finished at 14:05:00 local time. Its manifest equals the frozen
plan on configuration, benchmark, corpus, index, price schedule, seed, framework
source and the set of planned jobs. No whole job was rerun or replaced. The
reserved-selection condition used its predeclared single selection retry in
eight jobs, as described below.

## Coverage

| Condition | Planned | Observed | Completed | Budget-exhausted | Error | Missing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector | 45 | 45 | 45 | 0 | 0 | 0 |
| Agentic (original) | 45 | 45 | 27 | 15 | 3 | 0 |
| Agentic, reserved selection | 45 | 45 | 44 | 1 | 0 | 0 |
| Cascade | 45 | 45 | 45 | 0 | 0 | 0 |
| No retrieval | 45 | 45 | 45 | 0 | 0 | 0 |
| **Total** | **225** | **225** | **206** | **16** | **3** | **0** |

The terminal status is `completed_with_errors`, and the loader sets
`raw_run_partial: true` for that status. Here the flag reflects retained
failures: planned and observed are both 225 and nothing is missing.

The 19 failures were:

- **Original Agentic, 18:** 14 token-limit stops, three runs that ended in prose
  instead of a selection, and one connection timeout.
- **Agentic with reserved selection, 1:** a connection timeout.

The two connection timeouts are infrastructure failures with unknown usage
(`agentic`, `lc-c-01`, repetition 0, and `agentic_wrapup`, `lc-s-03`,
repetition 1). They count as failures like any other.

## How the two new conditions behaved

**Reserved selection, 45 jobs.**

- Selection was required by the token reserve in 21 jobs. In 21 the navigator
  selected on its own, and in three it began the single retry after a rejected
  selection of its own.
- Eight jobs used the retry, five of them after selection had been required.
  In five the rejected response was text that was not a selection, and in three
  the navigator asked for navigation tools after selection was required; those
  three calls were not executed. All eight jobs then completed.
- 27 oversized reads were shortened and no tool output was withheld.
- Selection came through the tool call in 38 jobs and as text in six.
- The median job made six navigation requests, with a maximum of nine. The
  original navigator's median was eight, with a maximum of twelve.

**Cascade, 45 jobs.**

- Nine jobs escalated, each because the first-stage answer reported that its
  evidence was insufficient. No first stage failed.
- The escalations were three questions in all three repetitions (`lc-s-04`,
  `lc-x-03`, `lc-x-04`). The other twelve questions never escalated.
- All nine second stages completed, so no job fell back to its first answer.
  Selection was required by the token reserve in six of them.
- The fixed Vector condition reported insufficient evidence for the same three
  questions in all three repetitions, nine of its 45 answers.

## Cost and time

| Condition | Known query-cost subtotal (USD) | Jobs with unknown cost | Mean elapsed per attempt, seconds | Model requests |
| --- | ---: | ---: | ---: | ---: |
| Vector | 0.31978284 | 0 | 12.41 | 90 |
| Agentic (original) | 3.24500700 | 1 | 52.67 | 395 |
| Agentic, reserved selection | 2.58278400 | 1 | 46.89 | 342 |
| Cascade | 0.81583184 | 0 | 18.49 | 154 |
| No retrieval | 0.05959300 | 0 | 4.49 | 45 |

Costs include unsuccessful attempts and exclude indexing and the preflight. A
job with unknown usage is left out of its condition's subtotal, so the two
Agentic subtotals are incomplete. Elapsed times include pacing waits and are
not provider latency.

| Accounting quantity | USD | Interpretation |
| --- | ---: | --- |
| Run known cost subtotal | 7.08651568 | Estimate from reported usage and the frozen price schedule; incomplete. |
| Complete run cost estimate | Unknown (`null`) | Two timed-out requests have unknown usage. |
| Run used-or-reserved admission estimate | 7.14055368 | Separate budget ledger, below the $12.00 limit; not a bill. |
| Synthetic preflight | 0.01846328 | Nine provider requests, accounted separately. |
| Run + preflight known subtotal | 7.10497896 | Still incomplete for the same two requests. |

There were 1,026 model attempts: 936 Anthropic chat requests and 90 Qwen query
embeddings. Runner monotonic elapsed time was 6,115.07 seconds (101.9 minutes).

## Pacing

By recorded wall-clock request starts, the 936 Anthropic requests had a minimum
adjacent gap of 6.000046 seconds, none below six seconds, and a
rolling-60-second peak of ten starts. The 90 Qwen requests had a minimum gap of
6.004859 seconds and a peak of six. Monotonic admission times are not
persisted. The only recorded model-call errors were the two connection timeouts.

## Mechanical evidence recall

This is the overlap between retrieved evidence and the reference source ranges,
computed without human judgment. It is not answer correctness. A failed job
contributes whatever evidence it recorded.

| Condition | Mean recall over 45 jobs | Mean recall among completed jobs |
| --- | ---: | ---: |
| Vector | 0.600 | 0.600 (45) |
| Agentic (original) | 0.465 | 0.775 (27) |
| Agentic, reserved selection | 0.809 | 0.828 (44) |
| Cascade | 0.728 | 0.728 (45) |
| No retrieval | 0.000 | 0.000 (45) |

## AI-reviewed development results

All 206 available answer texts have validated scores in
[answers.ai-scores.jsonl](../experiments/reviews/adaptive-cascade-development-20261119-001/answers.ai-scores.jsonl).
The 19 failed attempts have no answer text and receive no rating; each contributes
zero to the primary correctness metric. Every condition's denominator is 45
planned and observed attempts. Percentages below are mean rubric scores, with
partial answers worth 0.5, rather than percentages fully correct.

| Condition | Correct | Partial | Abstained | Incorrect | Failed, no answer | Failure-aware mean correctness | Citation support (rated answers) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector | 28 | 14 | 0 | 3 | 0 | 77.8% | 0.789 (45) |
| Agentic (original) | 23 | 3 | 0 | 1 | 18 | 54.4% | 0.852 (27) |
| Agentic, reserved selection | 37 | 7 | 0 | 0 | 1 | 90.0% | 0.909 (44) |
| Cascade | 39 | 3 | 0 | 3 | 0 | 90.0% | 0.889 (45) |
| No retrieval | 0 | 10 | 32 | 3 | 0 | 11.1% | N/A (0) |
| **Completed answers** | **127** | **37** | **32** | **10** | **19 failures separately** | | |

Citation support evaluates the claims actually made, separately from answer
completeness. Across the 206 answers, 116 have full support, 45 partial support,
and 45 have no citations to rate. A supported citation alone does not make an
answer correct.

The predeclared quality comparisons use paired question means over all three
repetitions, with failures as zero. Descriptive 95% percentile bootstrap
intervals use 15 question clusters, 2,000 samples and seed 0, without multiplicity
adjustment:

| Comparison | Mean correctness difference, percentage points | 95% interval |
| --- | ---: | ---: |
| Cascade minus Vector | +12.2 | +3.3 to +23.3 |
| Cascade minus reserved-selection Agentic | 0.0 | −16.7 to +13.3 |
| Reserved-selection Agentic minus original Agentic | +35.6 | +14.4 to +56.7 |

Cascade's known estimated query cost is $0.8158 versus Vector's $0.3198, about
2.55 times as much. Its mean elapsed time is 18.49 versus 12.41 seconds, about
49% more. The paired cost and elapsed-time difference intervals both include
zero. The positive quality result therefore does not establish improvement on
all three research objectives.

Against reserved-selection Agentic, Cascade has the same observed mean quality
and lower mean elapsed time (18.49 versus 46.89 seconds). Its known cost subtotal
is also lower ($0.8158 versus $2.5828); the latter is incomplete for one attempt.
The paired elapsed-time difference is −28.40 seconds, interval −37.78 to −17.10.
The paired estimated-cost difference is −$0.0411 per attempt, interval −$0.0564
to −$0.0242, using 14 question pairs because one question has unknown cost.
The wide quality interval does not establish equivalence or non-inferiority.

## Review method and scope

The [review folder](../experiments/reviews/adaptive-cascade-development-20261119-001/)
contains the original blinded template and 14 unchanged packets, plus separate
AI scores, readable scored packets and a
[final AI summary](../experiments/reviews/adaptive-cascade-development-20261119-001/final-ai-review-summary.json).
The original template's rating fields remain null; there is no human score file.

Codex applied the `manual-v1` criteria through delegated source inspection and
root adjudication. The 206 items reduce to 88 exact question/answer/citation
cases; each distinct case was assessed once and repeats retain separate output
bindings. All 130 distinct reference/citation excerpts were hash-checked against
commit `ea17e48f0a4336c920394fd029de99f1568b4c38`. Scores, borderline decisions
and provenance were frozen before condition labels or aggregates were examined.
Answer style may still suggest a strategy. Review times come from assessment-file
creation times, following the user's timestamp convention.

This is one AI evaluation workflow, without independent human review or an
inter-rater reliability estimate. There are 15 development questions from one
repository, rather than 206 independent questions. Repetitions and exact-answer
reuse do not expand the question sample. No held-out job has run. AI scoring is
complete; the next research step is a development decision and a frozen held-out
protocol before testing generalization.

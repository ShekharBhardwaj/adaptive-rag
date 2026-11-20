# Phase 5: paced development execution

The single fresh development run recorded **all 270 planned jobs**, with
225 completed, 36 budget-exhausted, and 9 errors. Execution coverage is complete;
answer correctness and semantic citation support were unreviewed at the initial
export. All 16 review packets now have 227 validated user-submitted scores
from Shekhar, with no available answer texts left pending. Vector has the highest
failure-aware correctness point estimate (74.4%), followed by Agentic (62.2%).
These are development results under this budget profile; the paired uncertainty
and limitations below do not establish general superiority. See the
[completed review summary](../experiments/reviews/adaptive-anthropic-paced-development-20261117-001/final-review-summary.json).

Run ID: `04ebe642-5ec1-4301-98b2-2a17859c8ece`.
The preserved [raw run](../experiments/raw/adaptive-anthropic-paced-development-20261117-001/)
and [unreviewed aggregate](../experiments/aggregates/adaptive-anthropic-paced-development-20261117-001-unreviewed.json)
contain the records underlying these counts. The derived
[outcome record](../experiments/preflight/final-development-2026-11-17-001/outcome.json)
preserves coverage, accounting, and artifact hashes. Earlier runs, reports, and
reviews remain separate and unchanged.

The design was 15 development questions × six conditions × three repetitions,
with 270 unique job IDs and 45 records per condition. No held-out jobs ran.
Direct Anthropic `claude-haiku-4-5-20251001` served routing, navigation, and shared
answer generation. Query embeddings used OpenRouter
`qwen/qwen3-embedding-8b`; the existing repository index was unchanged and its
construction cost is excluded from these query costs. The corpus is the pinned
LangChain commit `ea17e48f0a4336c920394fd029de99f1568b4c38`. The manifest records
the frozen framework source SHA-256
`da28ce6622273fad0f3171886ee0ff05ef605639002d5a206062a8feb6c2f6bf`,
configuration, corpus/index identities, and dated price-schedule hashes.

The frozen profile allowed two hours of monotonic elapsed time, 12 million
budgeted tokens, 2,000 model attempts, and $9.90 in run admission estimates,
with at most $0.10 allocated separately to synthetic preflight. One shared
endpoint gate was configured for six seconds between starts and ten starts per
rolling minute. The opt-in `reserve` policy
used serialized-input-byte/full-output reservations to admit later jobs when
actual usage was missing. Default `stop` behavior is unchanged. Failed requests
were retained; there were no automatic retries, replacement answers, or reruns.

| Condition | Planned | Observed | Completed | Budget-exhausted | Error | Missing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector | 45 | 45 | 43 | 0 | 2 | 0 |
| Vectorless | 45 | 45 | 45 | 0 | 0 | 0 |
| No retrieval | 45 | 45 | 45 | 0 | 0 | 0 |
| Agentic | 45 | 45 | 28 | 13 | 4 | 0 |
| Adaptive rule | 45 | 45 | 36 | 9 | 0 | 0 |
| Adaptive LLM | 45 | 45 | 28 | 14 | 3 | 0 |
| **Total** | **270** | **270** | **225** | **36** | **9** | **0** |

The 36 terminal budget reasons were 29 token limits, six model-call limits, and
one `ConnectError` with shared-budget invalidation. The nine errors were seven
invalid evidence-ID selections and two answer citation IDs absent from supplied
evidence. These outputs remain failures; validation was not weakened and records
were not repaired. Both adaptive routers completed all 45 selections. The rule
router chose Agentic 12 times, Vector 12, and Vectorless 21; the LLM router chose
Agentic 27 times, Vector 6, and Vectorless 12. Selection and execution counts do
not establish answer quality.

The terminal status is `completed_with_errors`. The conservative CLI loader also
sets `raw_run_partial: true` and warns about that status. Here the flag reflects
retained failures, not absent jobs: planned = observed = 270 and missing = 0.
The harness and raw status were left unchanged.

There were 1,051 model attempts: 988 Anthropic chat calls and 63 Qwen query
embedding calls. Runner monotonic elapsed time was 6,293.04456858302 seconds
(104.884 minutes). The operational audit separately recorded a 340.5658-second
wall-clock gap before delegation. Pacing waits consume job/run deadlines;
elapsed execution times must not be read as raw provider latency.

| Cost/accounting quantity | USD | Interpretation |
| --- | ---: | --- |
| Run known cost subtotal | 7.56634852 | Estimate from reported usage and the frozen price schedule; incomplete. |
| Complete run cost estimate | Unknown (`null`) | One `ConnectError` has unknown actual usage/cost. |
| Run used-or-reserved admission estimate | 7.59391952 | Separate budget ledger, below $9.90; not an actual bill. |
| Synthetic preflight | 0.00677328 | Five calls, accounted separately. |
| Run + preflight known subtotal | 7.57312180 | Still incomplete because the run has one unknown call. |

Before execution, [verification](../experiments/preflight/final-development-2026-11-17-001/verification.json)
recorded 147 integrated tests passing in 81.11 seconds, Ruff lint/format passing,
and the five-call synthetic compatibility check passing. Its Anthropic start
gaps were 6.005144, 6.00258, and 6.005126 seconds. The operational audit confirmed
the coverage, accounting, and identity checks. These checks establish execution
contracts and observed endpoint compatibility, not scientific correctness.

The [final operational audit](../experiments/preflight/final-development-2026-11-17-001/operational-audit-final.json)
is `PASS_WITH_WALL_TIMESTAMP_PACING_EXCEPTION`. Chat wall timestamps include one
5.945952-second adjacent gap and a rolling-60-second peak of 11 in three
overlapping windows spanning about 59.98 seconds. Monotonic admission times were
not persisted; delayed recording or wall-clock variation is possible but
unproven. The configured 6-second/10-start limits were therefore not verified
for every recorded wall timestamp. Qwen timestamps had a 6.004482-second minimum
gap and rolling-minute peak of four. No HTTP error responses, including 429 or
503, were observed; the connection error is accounted for separately.

The seed-0 blinded export contains **227 answer texts**: 225 from completed jobs
and two invalid-citation answer texts. At initial export all human-rating fields were null and no score file existed.
The original template remains unchanged; the separate score file now contains
227 validated user-submitted reviews from all 16 packets. The final batch was
reviewed on November 17, 2026 at 10:27 PM EST. Its 17 suggested score pairs received
an AI source cross-check before being accepted unchanged; this is not a second
independent human review. Previous scores and times remain byte-for-byte
preserved in the [submission records](../experiments/reviews/adaptive-anthropic-paced-development-20261117-001/submissions/).
All output/question bindings were validated. The original template and pinned
raw artifacts remain unchanged.

## Reviewed development results

The [final aggregate](../experiments/aggregates/adaptive-anthropic-paced-development-20261117-001-reviewed.json)
contains the completed comparison. Of 227 available answer texts, Shekhar scored
100 fully correct, 31 partial, 84 abstentions and 12 incorrect attempted answers.
These text-level counts include the two outputs rejected for invalid citation
IDs. Forty-three failed jobs have no answer text and receive no invented human
rating. All 225 completed outputs and both error answer texts are reviewed.

The primary metric averages correctness over all 45 planned attempts in each
condition, assigns partial answers 0.5, and assigns all execution failures zero.
The two invalid-citation outputs retain their content ratings in the score file,
but count zero in this primary metric. This prevents high-quality surviving
answers from concealing failures to produce a valid completed answer.

| Condition | Completed / 45 | Answer texts reviewed | Correctness including failures | Citation support: mean (applicable n) |
| --- | ---: | ---: | ---: | ---: |
| Vector | 43 | 45 | **74.4%** | 83.3% (45) |
| Agentic | 28 | 28 | 62.2% | 94.6% (28) |
| Adaptive rule | 36 | 36 | 42.2% | 88.9% (27) |
| Adaptive LLM | 28 | 28 | 38.9% | 93.2% (22) |
| Vectorless | 45 | 45 | 27.8% | 85.7% (21) |
| No retrieval | 45 | 45 | 6.7% | N/A (0) |

These percentages are mean rubric scores with partial credit, not percentages
of fully correct answers. Citation support is conditional on applicability:
143 answers received a citation score and 84 were N/A. It is independent of
correctness; an abstention can contain supported factual claims. Citation
support means exclude N/A and jobs without text, so their denominators differ
from the primary correctness denominator.

Agentic's 28 completed answers were all fully correct, but 17 of its 45 attempts
failed. Vector's primary score is higher despite a lower mean among its reviewed
texts. Neither adaptive router exceeded the fixed Vector or Agentic condition
on the primary metric in this run. This development result does not support the
hypothesis that adaptive selection improves performance under the frozen profile.

| Condition | Known query-cost subtotal (USD) | Mean elapsed per attempt, seconds |
| --- | ---: | ---: |
| Vector | 0.30901184 | 9.44 |
| Agentic | 3.19331800 | 52.41 |
| Adaptive rule | 1.33411104 | 21.55 |
| Adaptive LLM | 2.46860864 (incomplete) | 42.24 |
| Vectorless | 0.19915600 | 8.05 |
| No retrieval | 0.05787800 | 5.15 |

Costs include observed unsuccessful attempts and exclude indexing and synthetic
preflight. Adaptive LLM has one job with unknown actual usage/cost, so its
subtotal and the run total remain incomplete. Elapsed times include configured
pacing waits and must not be interpreted as provider latency or unrestricted
serving throughput.

Uncertainty uses 2,000 paired question-cluster bootstrap samples with seed 0.
Each cluster averages three planned repetitions; all 15 unique development
questions are paired. The 227 texts are not 227 independent questions. Selected
failure-aware differences in percentage points are:

| Comparison (left minus right) | Mean difference | Descriptive 95% bootstrap interval |
| --- | ---: | ---: |
| Agentic minus Vector | -12.2 | [-35.6, 11.1] |
| Adaptive rule minus Vector | -32.2 | [-54.4, -12.2] |
| Adaptive LLM minus Vector | -35.6 | [-57.8, -15.6] |

Vector leads the point estimates, but the Agentic comparison interval includes
zero. These intervals have no multiplicity adjustment and describe this small
development benchmark; they do not establish performance on new questions,
repositories, models or budget profiles. A single reviewer supplied the scores,
answer style can reveal conditions, and no second independent human review was
performed. The AI source cross-check covered only the final 17 submitted scores.

Development answer review and this analysis are complete. Remaining research
work is to decide and freeze any protocol changes using development results,
then run held-out evaluation and its independent answer review before final
research conclusions. No held-out jobs or additional paid model calls were
started during review or this offline analysis.

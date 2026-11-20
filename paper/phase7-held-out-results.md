# Phase 7: held-out results

The held-out test supports two of the redesign's claims and leaves two open.
Reserving the navigator's final selection made Agentic retrieval more correct,
and the cascade cost less and took less time than always using Agentic. The
cascade's advantage over Vector is **direction only**: the estimate is +12.2
points, but the 95% interval starts at zero. The cascade's quality is **not
distinguishable** from Agentic's at this sample size.

Answers were scored by an AI reviewer and reviewed by the author. They were not
scored by independent humans.

Run ID: `eb914cf0-4437-4d25-bfd3-2b4253f990a6`. What was fixed in advance is in
[the held-out protocol](phase7-held-out-protocol.md), and how the run executed is
in [the run report](phase7-held-out-run.md). Every figure below comes from
[the confirmatory output](../experiments/analysis/heldout-confirmatory-20261119/heldout-confirmatory.json)
or [the AI-reviewed aggregate](../experiments/aggregates/adaptive-cascade-heldout-20261119-001-ai-reviewed-001.json).

## The three confirmatory comparisons

Correctness is failure-aware: the mean score over all 45 planned jobs of a
condition, with a partial answer worth 0.5 and every unsuccessful job counted as
zero. Intervals are the paired question-cluster percentile bootstrap with 15
questions, 2,000 samples and seed 0, without multiplicity adjustment. The
wording in the last column is the protocol's.

| # | Comparison | Estimate | 95% interval | Result |
| --- | --- | ---: | ---: | --- |
| 1 | Cascade minus Vector, correctness | +12.2 points | 0.0 to +25.6 | Direction only |
| 2 | Cascade minus reserved-selection Agentic, correctness | +1.1 points | −8.9 to +13.3 | Not distinguishable at this sample size |
| 2 | Same pair, known cost per job | −$0.025 | −$0.041 to −$0.009 | Supported: the cascade costs less |
| 2 | Same pair, elapsed time per job | −19.6 s | −31.4 to −7.4 | Supported: the cascade takes less time |
| 3 | Reserved-selection Agentic minus original Agentic, correctness | +32.2 points | +14.4 to +51.1 | Supported |

### 1. Cascade against Vector: direction only

The cascade scored 83.3% and Vector 71.1%. Six questions improved, one got
worse and eight did not change.

The lower end of the interval is zero to floating-point precision. Of the 2,000
bootstrap means, 23 are below zero and 28 equal zero, so the 2.5th percentile
falls on zero. The analysis script, fixed before any score existed, counts an
endpoint at zero as including zero. The result is therefore "direction only"
and not "supported". The estimate equals the development run's, where the
interval was +3.3 to +23.3.

The protocol rules out one claim regardless of this result: the cascade is not
cheaper or faster than Vector. It always runs Vector first, and here it used
4.6 times Vector's known cost and 3.6 times its elapsed time.

### 2. Cascade against always using Agentic

The protocol requires the quality and efficiency results to be stated together.

- **Quality:** the cascade scored 83.3% and reserved-selection Agentic 82.2%.
  The interval reaches 13.3 points on the upper side, beyond the ten-point
  margin, so the two cannot be called similar. This does not establish
  equivalence or non-inferiority.
- **Cost:** the cascade's known cost was $0.041 per job against $0.066, 62% of
  always using Agentic. The whole interval lies below zero.
- **Time:** the cascade took 33.1 seconds per job against 52.7, 63% of always
  using Agentic. Elapsed times include pacing waits and are not provider
  latency.

### 3. The navigator fix: supported

Reserved-selection Agentic scored 82.2% and the original 50.0%. The original
completed 24 of 45 jobs and reserved selection 43. The original's answers, when
it produced one, scored 93.8% on average; its loss comes from runs that never
reached an answer.

### Sensitivity analysis

One job failed because the provider could not be reached: original Agentic,
`lc-x-07`, repetition 0, a connection timeout. Leaving it out changes no
estimate, interval or wording, because that condition scored zero on that
question in every repetition.

## Results by condition

"Abstained" and "incorrect" both score zero; the split is the AI reviewer's
classification.

| Condition | Correct | Partial | Abstained | Incorrect | Failed, no answer | Failure-aware correctness | Citation support (rated answers) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector | 26 | 12 | 4 | 3 | 0 | 71.1% | 0.778 (45) |
| Agentic (original) | 21 | 3 | 0 | 0 | 21 | 50.0% | 0.938 (24) |
| Agentic, reserved selection | 35 | 4 | 4 | 0 | 2 | 82.2% | 0.938 (40) |
| Cascade | 36 | 3 | 3 | 3 | 0 | 83.3% | 0.826 (43) |
| No retrieval | 3 | 9 | 33 | 0 | 0 | 16.7% | N/A (0) |
| **Completed answers** | **121** | **31** | **44** | **6** | **23 failures separately** | | |

| Condition | Known cost per job (USD) | Jobs with unknown cost | Mean elapsed per job, seconds |
| --- | ---: | ---: | ---: |
| Vector | 0.0089 | 0 | 9.2 |
| Agentic (original) | 0.0705 | 1 | 52.2 |
| Agentic, reserved selection | 0.0658 | 0 | 52.7 |
| Cascade | 0.0408 | 0 | 33.1 |
| No retrieval | 0.0014 | 0 | 4.7 |

Costs are estimates from reported usage at the frozen price schedule and
include unsuccessful attempts. Request counts, mechanical evidence recall and
how the reserved-selection navigator ended its runs are in the run report.

## How the cascade behaved

These are descriptive and carry no confirmatory claim.

- **Escalation:** 20 of 45 jobs escalated, against 9 of 45 in development.
  Nineteen followed a first-stage report of insufficient evidence and one a
  first-stage answer that failed validation. Seven of the 15 questions
  escalated at least once.
- **After escalating:** 14 answers were correct, three partial and three scored
  zero.
- **Without escalating:** 22 answers were correct and three scored zero. No
  partial answer was kept.
- **Where the gain came from:** all 12.2 points over Vector came from the seven
  questions that escalated at least once.
- **A miss:** on `lc-x-07` the first stage reported sufficient evidence in all
  three repetitions and was wrong each time, so the cascade never escalated and
  scored zero. The protocol named this limit in advance. Reserved-selection
  Agentic scored 0.5, 0.5 and 0 there.
- **A loss:** on `lc-c-09` the fixed Vector condition was correct in all three
  repetitions. In the cascade, the first stage reported insufficient evidence
  twice, and one of the two escalated answers scored zero.

Vector's own sufficiency reports, which the protocol does not list among its
descriptive results, give context for the signal the cascade relies on. Of the
27 Vector answers that reported sufficient evidence, 24 were correct and three
scored zero. Of the 18 that reported insufficient evidence, two were correct, 12
partial and four scored zero.

## Development and held-out side by side

The pooled column mixes the development questions the design was built on with
the held-out questions. It is descriptive and supports no confirmatory
statement.

| Condition | Development, 15 questions | Held-out, 15 questions | Pooled, 30 questions |
| --- | ---: | ---: | ---: |
| Vector | 77.8% | 71.1% | 74.4% |
| Agentic (original) | 54.4% | 50.0% | 52.2% |
| Agentic, reserved selection | 90.0% | 82.2% | 86.1% |
| Cascade | 90.0% | 83.3% | 86.7% |
| No retrieval | 11.1% | 16.7% | 13.9% |

| Comparison | Development | Held-out |
| --- | ---: | ---: |
| Cascade minus Vector, points | +12.2 (+3.3 to +23.3) | +12.2 (0.0 to +25.6) |
| Cascade minus reserved-selection Agentic, points | 0.0 (−16.7 to +13.3) | +1.1 (−8.9 to +13.3) |
| Same pair, known cost per job | −$0.041 (−$0.056 to −$0.024) | −$0.025 (−$0.041 to −$0.009) |
| Same pair, elapsed seconds per job | −28.4 (−37.8 to −17.1) | −19.6 (−31.4 to −7.4) |
| Reserved-selection minus original Agentic, points | +35.6 (+14.4 to +56.7) | +32.2 (+14.4 to +51.1) |

The development cost comparison used 14 questions because one had an unknown
cost. The cascade's saving over Agentic is smaller on the held-out questions
because it escalated more than twice as often.

## What this supports

- **Supported on held-out questions:** reserving the final selection improves
  the Agentic navigator, and a Vector-first cascade costs less and takes less
  time than always using that navigator.
- **Direction only:** the cascade is more correct than Vector. The estimate is
  positive and matches development, and the interval includes zero.
- **Not shown:** that the cascade's quality is similar to Agentic's. The data
  do not distinguish them and do not establish equivalence.
- **Not claimed:** that the cascade is cheaper or faster than Vector, or that
  any of this holds for other repositories, models or question sets.

## How it was scored and analysed

- **Scoring:** Codex, as an AI reviewer, scored the 202 answer texts blind to
  condition with the `manual-v1` rubric and the criteria frozen for the
  development review. The 202 items are 105 distinct cases, and identical cases
  received identical scores. Its freeze record states that no condition label,
  aggregate or run report was inspected.
- **Order of events on November 20, 2026, local time:** score file written
  09:04; scores frozen 09:09; author's attestation recorded 09:14; comparisons
  computed 09:15.
- **Author review:** the attestation records Shekhar's statement that the
  scores were reviewed. It supplies no per-item human scores.
- **Analysis:** one run of
  [confirmatory.py](../experiments/analysis/heldout-confirmatory-20261119/confirmatory.py),
  fixed on November 19 at 21:06, before any held-out score existed. It
  reproduces the development results exactly, and its figures here equal the
  project's own `experiment summarize` output to within 2 × 10⁻¹⁵.

Three readings were written into that script after the protocol was frozen and
after the run, and before any score existed:

- **Zero endpoint:** an interval whose endpoint is at zero includes zero. This
  decided comparison 1.
- **Elapsed time:** the protocol fixes wording for cost only. Elapsed time uses
  the same rule, and this reading was written when the elapsed times were
  already known.
- **Unreachable provider:** such a job is an unsuccessful job with a model
  request that raised a transport error. The sensitivity analysis drops it from
  the plan and the results.

## Limits

- Fifteen questions from one repository, answered by one model. Repetitions do
  not add questions.
- One AI scoring workflow with the author's attestation. There is no
  independent human scoring and no estimate of agreement between raters. Answer
  style may reveal the strategy to a blind reviewer.
- Comparison 1 sits on the boundary of its rule. It is reported as the rule
  fixed in advance classifies it.
- Five of 1,088 gaps between Anthropic requests were recorded slightly under
  the six-second pacing limit, as the run report describes.
- The session that built the redesign and ran this analysis has not read a
  held-out question or answer text. Its scripts loaded them only to hash,
  validate and aggregate, and it worked from question identifiers, scores and
  run metadata.
- The held-out questions are now spent for this design. Any change to a prompt,
  policy, limit or scoring rule needs new, untouched questions before another
  confirmatory claim.

## Records

| File | SHA-256 |
| --- | --- |
| `experiments/analysis/heldout-confirmatory-20261119/heldout-confirmatory.json` | `7c1c20cdd76219ef774ab33677ad09db4991632828c16c07f251a8deddf681ad` |
| `experiments/analysis/heldout-confirmatory-20261119/confirmatory.py` | `5fdadf7958fe72942fa86e933e6ea592a48aa2178d31598739c0cabe01501506` |
| `experiments/analysis/heldout-confirmatory-20261119/analysis-freeze.json` | `23462c1848711696c937a67a4693f71b89e033f58104a629f3e75e76642263d3` |
| `experiments/analysis/heldout-confirmatory-20261119/cli-aggregate.json` | `13464e93b0f1b2e30b6d92bebc8ae9d09a28183c35965ac00bd0df17b6054d43` |
| `experiments/aggregates/adaptive-cascade-heldout-20261119-001-ai-reviewed-001.json` | `f618b34dd57f66b6875187edbe27605a8a2217ca573356c5c366a44dc84462ff` |
| `experiments/reviews/adaptive-cascade-heldout-20261119-001/answers.ai-scores.jsonl` | `5294d76222662ed3aaee5e2495da3d15158ea7f0f9a0312415a4953ae5148e55` |
| `experiments/reviews/adaptive-cascade-heldout-20261119-001/ai-review/scores-frozen.json` | `eb140dc6e54861d35b2d3358a6eea77e1a0f3f7845d3e01b56b01b76aaa16f81` |
| `experiments/reviews/adaptive-cascade-heldout-20261119-001/shekhar-review-attestation.json` | `450bb7e7c424afa1e4e35d82a76157a2affd0edcfd6006e7cbb5336104b4c135` |
| `paper/phase7-held-out-protocol.md` | `f5892af99dd4551f8703b9a67bcb32438d96a28934a3812d9d82705a7becf30b` |

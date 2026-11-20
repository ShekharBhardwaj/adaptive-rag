# Phase 5 development run: partial direct Anthropic pilot

The development comparison remains unfinished. This run observed **73 of 270
planned jobs**, with 58 completed, 13 budget-exhausted, 2 errors, and 197 missing
observations. No further paid requests or automatic reruns are scheduled. Human
correctness and citation-support ratings are pending; these execution and
mechanical measurements establish no accuracy or superiority finding.

The preserved [raw run](../experiments/raw/adaptive-anthropic-development-20261116-001/)
has run ID `e46a7d86-a64e-4312-9eca-f180bf8fe0a6`. Tables below come from its
[unreviewed aggregate](../experiments/aggregates/adaptive-anthropic-development-20261116-001-unreviewed.json).

## Setup and bounds

- Source: [LangChain at `ea17e48f0a4336c920394fd029de99f1568b4c38`](https://github.com/langchain-ai/langchain/tree/ea17e48f0a4336c920394fd029de99f1568b4c38).
  The frozen manifest records corpus fingerprint
  `3924731244e2e23840fc8930ff6d8cf39dc4cf3af55fcb17f02c96a75d8a5848`.
- Chat: direct Anthropic `claude-haiku-4-5-20251001` through
  `https://api.anthropic.com/v1` for routing, navigation, and shared answers.
  Embeddings: OpenRouter `qwen/qwen3-embedding-8b`, reusing the
  [existing completed index](../datasets/indexes/langchain-openrouter-qwen3-phase4-002/).
  Index construction is separate from query accounting.
- Plan: 15 development questions, six conditions, three repetitions each,
  shuffled with order seed 17; 45 jobs per condition. The seed controls ordering,
  not provider sampling. Held-out evaluation was not started.
- Retrieval: top-k 5; 24 tool calls, 12 model calls, 128,000 tokens, 120 seconds,
  and 24,000 evidence characters per stage. Adaptive routing consumes this
  shared stage allowance; its own cap is one model call, 6,000 tokens, 15 seconds,
  and 256 output tokens.
- Answers: temperature 0, 1,024 output tokens, 64,000 total tokens, 30 seconds,
  and 24,000 evidence characters. The grounded-answer prompt and strict citation
  provenance validation were unchanged.
- Global limits: 2,000 model attempts, 5,000,000 tokens, 5,400 seconds, and a
  $5 estimated-cost cap. No automatic retries, routing fallback, or escalation.

Before execution, 243 integration checks and 128 focused answer/parser checks
passed, along with Ruff. A separate five-call live compatibility check had an
estimated cost of **$0.00677328**. These checks verify exercised contracts and
endpoint behavior, not answer quality.

## Execution and stop cause

| Condition | Planned | Observed | Completed | Budget-exhausted | Error | Missing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vector | 45 | 9 | 8 | 0 | 1 | 36 |
| Vectorless | 45 | 16 | 15 | 1 | 0 | 29 |
| Agentic | 45 | 17 | 11 | 5 | 1 | 28 |
| No retrieval | 45 | 12 | 12 | 0 | 0 | 33 |
| Adaptive rule | 45 | 7 | 5 | 2 | 0 | 38 |
| Adaptive LLM | 45 | 12 | 7 | 5 | 0 | 33 |
| **Total** | **270** | **73** | **58** | **13** | **2** | **197** |

An Anthropic answer request reached its **30-second read timeout** without a
provider usage record. Unknown accounting then prevented further calls. The
saved run status is `budget_exhausted`; the recorded estimate did not reach the
$5 cap, and this stop is not evidence that provider credits were exhausted.

Recorded elapsed time is **845.591875 seconds (14.09 minutes)**, with **313 model
attempts**. The known query-cost subtotal is **$2.26749312**. Complete cost and
token totals are **unknown** because one call has unknown usage. The subtotal
includes known routing, retrieval, and answer work; it excludes the separate
compatibility check and prior index construction. It must not be presented as
the complete bill.

## Mechanical measurements on observed jobs

These are observed-job means with unequal coverage, including failed jobs where
measurements exist. They are not a balanced or completed paired comparison.

| Condition | Observed jobs | Source-range recall | Source-line recall | Citation-ID validity (applicable outputs) |
| --- | ---: | ---: | ---: | ---: |
| Vector | 9 | 0.472 | 0.464 | 0.963 (9) |
| Vectorless | 16 | 0.172 | 0.125 | 1.000 (5) |
| Agentic | 17 | 0.441 | 0.566 | 1.000 (11) |
| No retrieval | 12 | 0.000 | 0.000 | N/A (0) |
| Adaptive rule | 7 | 0.143 | 0.161 | 1.000 (4) |
| Adaptive LLM | 12 | 0.278 | 0.302 | 1.000 (6) |

Range/line recall measures coverage of annotated source, not retrieval precision
or semantic correctness. Citation-ID validity checks whether claimed IDs were
supplied, not whether the cited source supports the claims. All 19 observed
adaptive routing decisions completed; LLM routing made 12 calls and averaged
1.723 seconds per observed adaptive-LLM job. Routing overhead is included in job
totals. No human correctness or citation-support scores have been supplied.

## Remaining work

The [review guide and four readable packets](../experiments/reviews/adaptive-anthropic-development-20261116-001/README.md)
contain 59 available answer texts with pending human ratings. Available text from
unsuccessful jobs is retained for diagnostic review; 59 texts does not mean 59
completed jobs. Independent scoring can proceed without more provider requests.

The **197 unrun development jobs**, held-out evaluation, human scoring, and final
research analysis remain unfinished. Any future execution needs a fresh
preserved plan/path and an explicit timeout/accounting decision. Do not append
to this immutable partial run, silently replace failures, or blend it with the
earlier OpenRouter run. Preserve missing/failure and review coverage in any
subsequent analysis. The research objective has not been completed.

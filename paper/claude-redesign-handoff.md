# Claude handoff: test, diagnose, and redesign Adaptive RAG

Prepared November 18, 2026 for Shekhar. Workspace:
`/Users/shekhar/development/research/adaptive-rag`.

Start with offline tests and development-only diagnosis. This handoff did not
rerun the test suite, start a paid experiment, or change retrieval/routing code.

## Research aim and current finding

The hypothesis is that query-aware selection among Vector, Vectorless, and
Agentic retrieval can improve answer correctness while reducing inference cost
and latency against fixed strategies. Negative findings are valid. The current
adaptive implementation has not demonstrated that advantage.

The latest development comparison used 15 questions, six conditions and three
repetitions: 270 planned and observed jobs, with no missing jobs. There were
225 completed jobs, 36 budget-exhausted jobs and nine errors. All 227 available
answer texts have user-submitted scores from Shekhar: 100 fully correct,
31 partial, 84 abstentions and 12 incorrect attempted answers. The other
43 jobs have no answer text and receive no invented human review.

| Condition | Completed / 45 | Correctness including failures | Known query-cost subtotal, USD | Mean elapsed per attempt, seconds |
| --- | ---: | ---: | ---: | ---: |
| Vector | 43 | 74.4% | 0.30901184 | 9.44 |
| Agentic | 28 | 62.2% | 3.19331800 | 52.41 |
| Adaptive rule | 36 | 42.2% | 1.33411104 | 21.55 |
| Adaptive LLM | 28 | 38.9% | 2.46860864, incomplete | 42.24 |
| Vectorless | 45 | 27.8% | 0.19915600 | 8.05 |
| No retrieval | 45 | 6.7% | 0.05787800 | 5.15 |

Correctness is a mean rubric score: correct=1, partial=0.5, wrong/abstained=0.
The primary comparison also assigns every unsuccessful job zero. Vector has
two invalid-citation error outputs judged correct on content; their execution
failures still count zero in the primary score. Agentic's 28 completed answers
were all fully correct, but its 17 failures remain in the denominator.

These are 15 unique development questions, not 227 independent questions.
The 2,000-sample, seed-0 paired bootstrap clusters repetitions by question.
Agentic minus Vector is -12.2 percentage points with a descriptive 95% interval
[-35.6, 11.1]. Vector leads the point estimate; that comparison is uncertain.
Intervals have no multiplicity adjustment. No held-out execution has occurred.

Elapsed times include pacing waits. Costs exclude index construction and
synthetic preflight. The known run subtotal is $7.56634852; complete actual cost
remains unknown because one connection failure has unknown usage. The separate
$7.59391952 used-or-reserved ledger is an admission estimate, not a bill.

## Protect the held-out boundary

Use a fresh Claude conversation with this focused handoff. The full prior chat
contains held-out questions and reference/source-review material from benchmark
curation; do not paste that history into the redesign context.

`benchmarks/pilot.jsonl` combines 15 development and 15 held-out questions.
Do not display or inspect its held-out rows during policy design. A derived
development-only view is ready at:

- [development-only.jsonl](../experiments/handoff/claude-redesign-2026-11-18/development-only.jsonl)
- [derivation manifest](../experiments/handoff/claude-redesign-2026-11-18/manifest.json)

The view preserves the original development lines; the frozen benchmark is
unchanged. It includes development gold annotations for evaluation. Gold answers,
source ranges, categories, difficulty, split labels, human ratings and measured
strategy outcomes must not enter router/retriever/answer-generation inputs.
Development analysis may use outcomes, but do not hardcode question IDs or
answers into a routing policy. Version and document any learned or tuned policy.

If the Claude context used for redesign has already seen held-out material,
record that exposure and discuss an untouched final test set with Shekhar before
making a held-out generalization claim.

## Preserve the working directory and baseline

Most implementation files are untracked: Git currently tracks only two files,
with no tracked source or tests. A clone or commit alone will omit the framework.
Use the existing working directory or a complete, secure workspace copy. Preserve
untracked and ignored experiment/index artifacts before Git operations. Avoid
cleanup/reset operations that could discard them. Keep `.env` credentials local;
do not print them or include them in a shared handoff archive.

Treat these as immutable baseline artifacts:

- [Reviewed report](phase5-paced-development-run.md).
- [Final review summary](../experiments/reviews/adaptive-anthropic-paced-development-20261117-001/final-review-summary.json)
  and [current scores](../experiments/reviews/adaptive-anthropic-paced-development-20261117-001/answers.scores.jsonl).
- [Current aggregate](../experiments/aggregates/adaptive-anthropic-paced-development-20261117-001-reviewed-creation-times-001.json).
- [Raw run](../experiments/raw/adaptive-anthropic-paced-development-20261117-001/),
  run ID `04ebe642-5ec1-4301-98b2-2a17859c8ece`.
- [Baseline configuration](../configs/adaptive.anthropic.final.local.yaml).
- [Outcome and artifact hashes](../experiments/preflight/final-development-2026-11-17-001/outcome.json).
- [Frozen framework/test archive](../experiments/preflight/final-development-2026-11-17-001/framework-and-tests-0.4.0.tar.gz).
- Original benchmark, shuffled review template, review packets, submissions,
  timestamp corrections, and previous runs. Older runs use different protocols
  and must not be pooled with this run.

The raw status is `completed_with_errors`; the loader's `raw_run_partial=true`
reflects retained failures. It does not mean jobs or answer reviews are missing.

Review-time provenance is settled: Shekhar confirmed that earlier typed times
were incorrect and accepted original file creation times as the original review
times. Current `reviewed_at` values use filesystem birthtimes. The authoritative
[creation-time correction](../experiments/reviews/adaptive-anthropic-paced-development-20261117-001/corrections/creation-times-001/correction.json)
records the sources and marks the typed values incorrect and superseded.
Packet 1 uses its accepted submission-file creation time because no separate
batch score file was retained. The final batch time is November 17, 2026,
9:53:44 PM EST. Original incorrect values remain only in the audit history.
Timestamp corrections did not change grades or scientific aggregate results.

## Run the offline checks first

Python >=3.11 and Git are required. The existing `.venv` has the development,
vector and parser dependencies. From the workspace root:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
```

For environment recreation, the documented dependency setup is:

```sh
uv sync --frozen --extra dev --extra vector --extra parse
uv run --frozen --extra dev --extra vector --extra parse pytest -q
```

Tests use synthetic repositories, synthetic model outputs and local mock
transports; they require no live provider calls or real keys. Missing FAISS/NumPy
can skip important tests, so report skips and dependency versions. Run Ruff on
`src tests`, not the downloaded LangChain checkout. Historical verification
counts are not a fresh test result: the latest preserved preflight ran 147
selected integration tests, not the entire current suite. Report the actual
new pass/fail/skip count, runtime and environment.

## Provider, index and budget identities

- Chat, routing and navigation use direct Anthropic
  `claude-haiku-4-5-20251001`, with `ANTHROPIC_API_KEY`.
- Embeddings use OpenRouter `qwen/qwen3-embedding-8b`, with
  `OPENROUTER_API_KEY`. These are separate connections and credentials.
- Reuse the compatible existing index:
  `datasets/indexes/langchain-openrouter-qwen3-phase4-002`
  (9,404 chunks, 4,096 dimensions). An Anthropic chat key does not replace its
  embedding model. Any embedding/chunking/index change needs a new explicit
  preparation stage and separate cost accounting.
- The corpus is `datasets/repos/langchain`, pinned to
  `ea17e48f0a4336c920394fd029de99f1568b4c38`. Keep this checkout clean; modify
  framework code under `src/adaptive_rag`, not the repository under study.
- The preserved run allowed 12 million budgeted tokens, 2,000 model attempts,
  7,200 seconds and $9.90 estimated admission cost. Synthetic preflight had
  a separate maximum allocation of $0.10. Retrieval and answer stages have
  additional limits; inspect the baseline configuration rather than assuming
  the global limit is available to each request.
- Pacing is configured for one in-flight request, six seconds between starts
  and ten starts per rolling minute. Gates are per process: parallel experiment
  processes do not share an account-wide limiter.
- The final operational audit retained one 5.945952-second chat gap and a
  rolling-minute peak of 11; monotonic admission timestamps were not persisted.
  Do not claim every observed wall timestamp met the configured limit. No HTTP
  429/503 response was observed in this run.
- Unknown-usage policy is opt-in `reserve`; default `stop` remains available.
  Reservations permit bounded later admission while actual missing usage/cost
  stays unknown. Preserve that distinction and fail closed if no finite
  reservation can be formed. The baseline has no automatic retries.

## Code map and diagnostic priorities

| Area | Source under `src/adaptive_rag/` | Relevant tests under `tests/` |
| --- | --- | --- |
| Routing and adapter | `routing/routers.py`, `routing/models.py`, `retrieval/adaptive.py` | `test_routing.py`, `test_adaptive_retrieval.py`, `test_adaptive_runner.py` |
| Retrieval | `retrieval/agentic.py`, `vector.py`, `vectorless.py`, `tools.py` | `test_agentic.py`, `test_vector.py`, `test_vectorless.py`, `test_tools.py` |
| Execution and budgets | `evaluation/runner.py`, `journal.py`, `reservations.py` | `test_runner.py`, `test_runner_boundary.py`, `test_journal.py`, `test_reservation_accounting.py` |
| Connections and pacing | `generation/client.py`, `connections.py`, `pacing.py` | `test_model_client.py`, `test_chat_connections.py`, `test_pacing.py`, `test_paced_connections.py` |
| Analysis and review | `evaluation/analysis.py`, `reviews.py`, `storage.py`, `metrics.py` | `test_analysis.py`, `test_reviews.py`, `test_storage.py`, `test_experiment_cli.py` |

Current adaptive policies make one choice before retrieval, with no escalation
or fallback. The rule router prioritizes navigation terms for Agentic, then
path/identifier features for Vectorless, otherwise Vector. The LLM router uses
one structured-output call. Both share the fixed strategies and answer generator.

Diagnose from development traces before choosing a redesign:

1. Separate poor selection from navigation failure, evidence omission,
   generation abstention, strict citation failure, and budget/accounting failure.
   Rule routing selected Agentic/Vector/Vectorless 12/12/21 times; LLM routing
   selected them 27/6/12 times. Frequency alone does not establish optimality.
2. Explain the Agentic failures: distinguish productive search stopped by a
   budget from unproductive loops or invalid evidence selection. Do not assume
   larger budgets are an improvement without measuring their cost.
3. Compare fixed outcomes by development question and include routing overhead.
   A hindsight oracle can diagnose available routing headroom, but it is not a
   deployable router and must not be reported as achieved adaptive performance.
4. Investigate evidence coverage and abstention patterns. Vectorless had 27
   abstentions among its 45 outputs; the adaptive conditions had 12 and nine.
   Passing unit tests alone does not validate answer quality or routing quality.
5. Consider budget-aware selection or bounded escalation only as versioned
   development proposals. Escalation changes the current protocol and must
   account for every extra request, tool call, token and elapsed second.

See [Phase 4 methodology](phase4-methodology.md),
[Phase 3 methodology](phase3-methodology.md), and
[pacing/accounting notes](pacing-handoff.md). Older handoff documents describe
earlier implementation stages; use the reviewed report for current outcomes.

## Expected redesign deliverable and next experiment

Deliver a diagnosis, a concrete versioned redesign, meaningful tests, fresh
offline verification results, and a bounded experiment proposal. Preserve
negative findings. Do not weaken validators, drop failures, manufacture reviews,
or tune against held-out answers to obtain a favorable result.

Freeze the new routing policy/prompts, model identities, budgets, corpus/index,
split, repetitions, seed and analysis settings before the next comparison.
Keep the answer generator and settings shared across conditions. If they change,
rerun the appropriate fixed controls under the new protocol in fresh directories;
do not compare a changed adaptive generator with an old fixed baseline as though
only routing changed. Keep all planned jobs in the primary denominator and use
question-cluster uncertainty with explicit review and accounting coverage.

Initial scope is offline testing, diagnosis and redesign. Before any new paid
provider run, give Shekhar a finite plan stating the job count, provider/model
identities, request pacing, maximum elapsed time, token/call limits, estimated
spend and stopping rule, and obtain authorization for that run. Do not rebuild
the index or start the held-out experiment as an automatic side effect of tests.
Every later run needs a new frozen plan and output directory. Do not append,
silently retry or replace unsuccessful jobs in preserved experiments.

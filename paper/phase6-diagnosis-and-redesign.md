# Phase 6: development diagnosis and redesign

Prepared November 19, 2026 by Claude (an AI assistant) for Shekhar, following
[the redesign handoff](claude-redesign-handoff.md). Everything here is offline
work: no model request was made, no paid run was started, the index was not
rebuilt by a provider, and no preserved run was appended to or replaced.

The adaptive routers did not lose because selecting a strategy per question is
hopeless. They lost because they chose badly, and the Agentic baseline they
chose often was cut off after it had already found the evidence. This document
records the evidence for that, the versioned redesign that follows from it, and
a finite plan for one new development run that still needs authorization.

## Data boundary

Only development material was used. The inputs were the reviewed development
run `04ebe642-5ec1-4301-98b2-2a17859c8ece`, its 227 scores by Shekhar, and the
[development-only benchmark view](../experiments/handoff/claude-redesign-2026-11-18/development-only.jsonl)
(15 rows, all labelled `development`).

The session that did this work did not open `benchmarks/pilot.jsonl`, anything
under `benchmarks/`, the run's `benchmark.jsonl` copy, or any earlier
conversation. Those files were only hashed, or had their `split` labels counted
without printing rows. The run's `benchmark.jsonl` is a byte-identical copy of
the combined benchmark and therefore also holds the 15 held-out rows; the
handoff does not mention that copy. The offline planning command reads the
combined benchmark internally to select the development split; its output was
inspected only for counts, hashes and settings.

Gold answers, source ranges, categories, difficulty, split labels, human scores
and measured outcomes are not inputs to any router, retriever or answer prompt
described below, and no question is special-cased.

## Restored artifacts

On November 18, 2026 four files were found missing from the raw run folders and
two from the vector index folder. Codex's per-turn snapshots showed the three
`index-manifest.json` copies present at 19:41:10 and gone by 19:46:36, and
`results.jsonl` present at 19:46:36; its folder last changed at 19:52:08. The
cause is unknown. With Shekhar's approval they were restored on November 18
between 21:18:14 and 21:20:24, and not backdated:

| File | Restored from | Verified against |
| --- | --- | --- |
| `results.jsonl`, reviewed run (66,515,672 bytes) | git blob `065ef83290f6…` | SHA-256 `169f3c56…` recorded in `outcome.json` |
| `index-manifest.json`, reviewed run (1,427,771,473 bytes) | git blob `9dc4ebebccfd…` | SHA-256 `0b073eba…` recorded in `outcome.json` |
| `index-manifest.json`, two earlier runs | the same blob | the blob the 19:41:10 snapshot recorded at those paths |
| `index.faiss` (154,075,181 bytes) | rebuilt offline from the embeddings stored in the manifest | `index_sha256` `5217f824…`, exact match |
| index `manifest.json` | re-serialized from the restored manifest | `index_manifest_sha256` `15ac7923…` in the run manifest |

All ten raw files of the reviewed run match `outcome.json`, recomputing the
aggregate from the restored file reproduces the stored final aggregate exactly,
and `load_index` accepts the rebuilt index. No file hash of the original index
`manifest.json` was ever recorded, so its byte-for-byte identity cannot be
proven, although the builder's serializer reproduces the restored bytes. The
`phase4-001` index folder is empty and its former contents are not recoverable
from git. A same-disk copy of the project, without `.venv`, was made on
November 19 at 10:20 at
`/Users/shekhar/development/research/adaptive-rag-backup-2026-11-18`.

## What the reviewed run shows

Figures come from
[diagnose.py](../experiments/analysis/development-diagnosis-20261119/diagnose.py)
and its output
[diagnosis.json](../experiments/analysis/development-diagnosis-20261119/diagnosis.json).
Correctness is the run's failure-aware mean: partial answers score 0.5 and every
unsuccessful job scores zero. There are 15 questions with three repetitions
each, not 45 independent jobs per condition.

### The routers lose on what they choose

Each router picked the same strategy in all three repetitions of every question.

| Router | Questions sent to Vector / Vectorless / Agentic | Correctness expected from its picks | Actual correctness | Picked a best strategy |
| --- | ---: | ---: | ---: | ---: |
| Rule | 4 / 7 / 4 | 47.8% | 42.2% | 6 of 15 |
| LLM | 2 / 4 / 9 | 38.9% | 38.9% | 5 of 15 |

"Expected from its picks" scores each pick with the fixed condition's own result
for that question, so it isolates selection from execution. Always choosing
Vector gives 74.4%.

- The rule router sends a question with a code identifier or path, and no
  navigation wording, to Vectorless. Eleven of the 15 questions contain an
  identifier. Vectorless is the weakest retriever at 27.8%; its 30 zero-score
  answers had mean reference-evidence recall of 0.075.
- Both routers send every question with "trace", "propagation" or "call path"
  wording to Agentic. Those are the questions on which Agentic most often runs
  out of budget: fixed Agentic completed 5 of 15 cross-file runs, against 13 of
  15 structural and 10 of 15 conceptual runs.
- Neither router sees evidence. The choice is made from the question's wording
  before retrieval, and nothing follows a bad choice.

A selection made in hindsight from the fixed strategies' results would reach
88.9% for $0.97, against 74.4% for $0.31 with Vector alone and 62.2% for $3.19
with Agentic alone. Choosing on two repetitions and scoring on the third gives
85.6% for $0.91, which is 11.1 points above Vector with a paired bootstrap 95%
interval of 1.1 to 22.2 points. These are ceilings that reuse the outcomes they
are scored on. They are not results.

### Agentic is stopped after finding the evidence

The Agentic navigator ran 84 times: 45 as the fixed condition, 27 chosen by the
LLM router and 12 by the rule router.

| How the run ended | Runs | Median model calls | Median retrieval input tokens | Every reference file shown | Every reference range touched | Mean reference-line coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Completed | 41 | 8 | 63,302 | 40 | 35 | 0.97 |
| Token limit | 29 | 9 | 90,091 | 25 | 18 | 0.89 |
| Prose instead of a selection | 7 | 10 | 95,934 | 6 | 6 | 0.86 |
| Model-call limit | 6 | 12 | 88,977 | 3 | 0 | 0.56 |
| Connection failure | 1 | 3 | unknown | 1 | 0 | 0.09 |

"Shown" means a tool result displayed a chunk from the file to the navigator.

- **When it finishes it is right.** Of the 41 completed runs, 40 answers were
  fully correct and one was partial.
- **The fixed condition's 17 failures were productive searches.** Twelve hit the
  token limit, four ended in prose and one hit the model-call limit. A chunk
  from every reference file had been shown in 15 of them, and part of every
  reference range in 12.
- **The navigator is told one budget and held to another.** Before each request
  the gate charges the whole serialized prompt at one token per byte. The
  provider counted a median 2.99 bytes per token over 716 requests. The
  navigator is told only its remaining tokens. The 29 token-limit runs stopped
  with a median 37,019 tokens unspent. Their last admitted prompts had a median
  size of 43,584 bytes, which the provider counted as a median 14,673 tokens.
- **Nothing is reserved for selection.** At a stop the retriever returns the
  first `top_k` candidates in discovery order, which contained no reference
  evidence in any of the 17 fixed failures, and the runner generates no answer.
- **The seven "invalid selection" errors were not invalid IDs.** In each, the
  navigator stopped calling tools and began answering the question in prose,
  reached its 512-token output cap, and the text was not a selection.
- **Exploration continues long after the evidence is in view.** In the failed
  runs that were shown every reference file, the median request at which that
  happened was the second, and 31 of 35 had it by the sixth.
- **Tool errors waste requests.** There were 42: 35 `read_file` ranges longer
  than `max_lines`, six `search_files` path errors and one undeclared argument.
- **It is expensive.** The median job cost $0.092 against $0.0063 for Vector.

### Vector and Vectorless fail at retrieval

Vector's 27 fully correct completed answers had mean reference-evidence recall
of 0.77, its 13 partial answers 0.35 and its three zero-score answers 0.00. It
never abstained. Vectorless is a keyword and symbol heuristic; when it scores
zero it has almost none of the reference evidence.

### What could trigger escalation

Retrieval similarity does not predict Vector's failures. Over the 15 questions
the top score separates the eight Vector-perfect questions from the other seven
with an AUC of 0.39, and the mean top-five score with 0.30, where 0.5 is no
signal.

Vector's own answers do carry a signal. A crude phrase match for statements
that evidence is missing flags none of its 27 fully correct completed answers
and five of its 16 partial or zero-score answers. Escalating those five and the
two citation failures to Agentic, pairing runs by repetition and keeping
Vector's answer when Agentic failed, gives 80.0% for $0.81 in hindsight. The
phrase list was written after reading these answers, so this shows that a
signal exists. It is not a policy and no code uses it.

## Redesign

Three versioned components were added. Each is opt-in, so the earlier
configuration still runs the earlier protocol.

### `agentic_wrapup`: navigation that keeps a selection in reserve

Module `adaptive_rag.retrieval.agentic_wrapup`, policy `agentic-wrapup-v1`,
prompt `repository-navigation-v7-wrapup`. `adaptive_rag.retrieval.agentic` is
unchanged and its prompt hash is pinned by a test.

- **Same accounting.** Token admission still charges one token per prompt byte.
  No limit is raised.
- **Truthful budget.** Each request reports `request_charge`, the exact
  serialized size the gate charges, with `navigation_may_end_after_this_request`
  and `selection_required_now`.
- **Reserved selection.** A navigation request is sent only if, after charging
  this prompt and the next one at one token per byte, a full selection request
  still fits. The last model call and the last tool call are also reserved.
  When the reserve is reached the navigator gets one instruction to select and
  tools are no longer executed.
- **Metered tool output.** Output added in a turn may not consume the reserve.
  Output that would is withheld and cannot be selected.
- **Shortened reads.** A `read_file` range longer than `max_lines` returns
  `max_lines` lines from `start_line` with a notice, instead of an error.
- **One retry.** A response that fails selection validation may be repeated
  once if a model call remains. The validator is the original one, and a second
  failure ends the run as before.
- **Prompt.** The prompt adds the budget rule above and states that the
  navigator's only final output is the selection.

Replaying the 45 fixed Agentic jobs' recorded prompt sizes under this rule,
selection would be required in 26 of them, at request six to ten, including
nine that completed on their own in the reviewed run. The estimated cost is
$2.76 for the 45 jobs, against $3.19 recorded. The navigator's behaviour will
differ once it sees the new budget fields, so this is an estimate.

### Evidence-sufficiency report in the shared answer

Setting `generation.report_evidence_sufficiency`, default `false`. When `true`,
every condition uses prompt `grounded-answer-v4-sufficiency`, which adds one
required JSON boolean, `evidence_sufficient`: true only if the supplied excerpts
by themselves support every part of the answer. A missing or non-boolean value
is an error. Citation validation is unchanged. The value is stored in the
answer's metadata, which keeps the answer record's fields, and the review
digests of earlier runs, unchanged. The original prompt is pinned by a test.

### `adaptive_cascade`: Vector first, escalate once

Policy `vector-first-cascade-v1` in `adaptive_rag.evaluation.cascade`, run by
the experiment runner.

1. Run Vector retrieval and the shared answer, exactly as the fixed Vector
   condition does.
2. Escalate if Vector retrieval or its answer did not complete, or the answer
   did not report `evidence_sufficient: true`.
3. On escalation, run `agentic_wrapup` and the shared answer on its evidence.
4. Use the second answer if it completes. Otherwise keep the completed first
   answer. Otherwise the job fails.

Every request, token, tool call and second of both stages is charged to the job
through the same journal. The record keeps both stages, the reason, and which
stage supplied the answer. A first-stage failure is preserved even when the
second stage succeeds. Provenance or identity failures remain fatal.

### What did not change

- The fixed conditions, both earlier routers, Vectorless, the vector index, the
  selection and citation validators, token admission, pacing, pricing and the
  failure-aware metric.
- The rule that an unsuccessful job scores zero and stays in the denominator.
- The reviewed run: its 227 reviews still validate against their output digests
  and its aggregate still reproduces under the changed code.

## Offline verification

Run on November 19, 2026 on the finished code with provider API keys unset
(Python 3.13.9, pytest 9.2.0, FAISS 1.16.0, NumPy 2.5.4, Ruff 0.17.5).

- **Tests:** `pytest -q` reported 874 passed in 246.54 seconds, with none failed
  or skipped. Before the redesign the suite had 842 tests, all passing. The 32
  new tests are 14 for `agentic_wrapup`, nine for the cascade and nine for the
  sufficiency report.
- **Lint and format:** `ruff check src tests` passed, `ruff format --check src
  tests` reported 81 files already formatted, and `git diff --check` was clean.
- **Baseline unchanged:** `experiment summarize` on the reviewed run, using the
  changed code, wrote a file byte-identical to the stored final aggregate
  (SHA-256 `060228584d9c…`).
- **Plan prepares:** `experiment plan` on the run configuration prepared
  225 jobs without a model request, with the reviewed run's corpus fingerprint
  and index manifest hash.
- **Scope of change:** 17 lines of existing source were replaced across six
  files; the rest is additive. `retrieval/agentic.py`, the routers, Vector,
  Vectorless and the tools are untouched.

These checks establish that the code runs and that the baseline analysis path
is unchanged. They say nothing about answer quality.

## Development run plan

This section is the plan as authorized. It reports no result; what the run did
is in [the execution report](phase6-cascade-development-run.md). Shekhar
authorized it on November 19, 2026 by replying "Yes, run it" when asked whether
to authorize the 225-job run or a leaner 180-job version. The run was started
that day at 12:23:05 local time as run `efc5034c-b904-4a02-889f-f45e746a3e49`
in `experiments/raw/adaptive-cascade-development-20261119-001`. Its frozen
plan, framework archive, verification record and compatibility check are in
[the preflight folder](../experiments/preflight/cascade-development-2026-11-19-001/).

- **Compatibility check:** all six synthetic stages passed with nine provider
  requests for an estimated $0.01846328, every chat start at least six seconds
  after the previous one. Two assistant messages were simulated locally, and
  labelled as such, to exercise the two retry shapes with a real follow-up.
- **Price check:** the published pricing page listed Claude Haiku 4.5 at $1 per
  million input tokens and $5 per million output tokens on November 19, equal
  to the frozen schedule.
- **Plan match:** the run's own manifest equals the frozen plan on
  configuration, benchmark, corpus, index, price schedule, split, question
  count, order seed, framework source and the set of planned jobs.

The configuration is
[adaptive.cascade.development.final.local.yaml](../configs/adaptive.cascade.development.final.local.yaml).
It differs from the reviewed run's configuration only in the four run limits,
the conditions and the sufficiency report.

| Item | Proposal |
| --- | --- |
| Jobs | 225: 15 development questions × 5 conditions × 3 repetitions |
| Conditions | `vector`, `agentic`, `agentic_wrapup`, `adaptive_cascade`, `no_retrieval` |
| Chat, navigation, answers | Anthropic `claude-haiku-4-5-20251001`, direct |
| Embeddings | OpenRouter `qwen/qwen3-embedding-8b`, existing index `phase4-002`, not rebuilt |
| Pacing | one request in flight, 6 seconds between starts, 10 starts per rolling minute |
| Run limits | 2,400 model attempts, 14,000,000 budgeted tokens, 10,800 seconds, $12.00 admission estimate |
| Per retrieval | 12 model calls, 128,000 tokens, 24 tool calls, 300 seconds (unchanged) |
| Per answer | 64,000 tokens, 1,024 output tokens, 90 seconds (unchanged) |
| Unknown usage | `reserve`; no automatic retries |
| Expected requests | about 950 to 1,260 chat requests and 90 embedding requests |
| Expected duration | about 1.75 to 2.25 hours, set by pacing |
| Expected known cost | about $7.10 to $9.40 |
| Preflight | a synthetic compatibility check of the new request shapes, at most $0.10, accounted separately |
| Stopping rule | the runner stops admitting jobs when a run limit is reached; unrun jobs stay in the denominator as missing; nothing is rerun or appended |
| Human review | up to 225 answer texts |

The cost estimate uses the reviewed run's measured costs at the frozen price
schedule: $0.06 for `no_retrieval`, $0.31 for `vector`, $3.19 for `agentic`,
about $2.76 for `agentic_wrapup`, and $0.75 to $3.07 for `adaptive_cascade` as
its escalation rate goes from 16% to 100%. The escalation rate of the model's
own report is not known in advance. The price schedule is dated November 16,
2026 and should be confirmed on the day of the run.

Predeclared comparisons, on failure-aware correctness with cost and elapsed
time alongside, using the paired question-cluster bootstrap with 2,000 samples
and seed 0:

1. `adaptive_cascade` minus `vector`.
2. `adaptive_cascade` minus `agentic_wrapup`, with their costs.
3. `agentic_wrapup` minus `agentic`.

The original `agentic` condition is kept so that the effect of the wrap-up
change is measured under the same answer prompt. `vectorless` and the two
earlier routers are left out because the reviewed run already characterizes
them and they are not part of the claim.

## Limits and open decisions

- **Fifteen questions cannot settle a ten-point difference.** The reviewed
  run's intervals are roughly 20 points either side. A cascade that beats Vector
  by five to ten points would not be distinguishable from it here. A larger
  development set, with more questions that Vector gets wrong, would be needed
  for a claim against Vector.
- **The honest efficiency claim is against Agentic.** Vector is already the
  cheapest useful strategy. A cascade can only be more accurate than Vector for
  more money, or as accurate as Agentic for less.
- **The reserve ends navigation earlier.** Under one-token-per-byte charging,
  the replay requires selection in 26 of 45 jobs, nine of which finished on
  their own before. Counting the already-reported tokens of the unchanged
  prompt prefix would allow more exploration within the same limit; it was not
  adopted because it changes how admission counts.
- **The sufficiency report is unmeasured.** Its escalation rate and its
  accuracy are unknown until a run. It also changes the answer prompt for every
  condition, which is why the fixed controls are rerun.
- **The new request shapes are untested against the provider.** The selection
  instruction is a user message after tool results. The preflight exists to
  check that before the run.
- **Review remains single-reviewer.** No second independent human review exists.
- **Held-out evaluation comes after.** Freeze the protocol from development
  results, then run the held-out split with its own independent answer review.

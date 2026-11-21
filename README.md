# Adaptive RAG Research Framework

A Python research framework for testing whether query-aware selection among vector,
vectorless, and agentic retrieval can improve answer correctness while reducing
inference cost and latency for software repository questions. This is a hypothesis,
not a result; the protocol must permit null and negative findings.

The framework runs Vector, Vectorless, Agentic, no-retrieval, rule-based adaptive,
LLM adaptive, reserved-selection Agentic and a vector-first cascade. It records
shared answer generation, repeated execution, source metrics, dated price
estimates, review provenance and paired uncertainty reports. Routing decisions
and overhead are included in adaptive totals. A reviewed 30-question pilot and
the [research manuscript](paper/manuscript/adaptive-rag-pilot.md) are included.
Offline tests and live compatibility checks do not establish an answer-quality
result.

**Paper.** Shekhar Bhardwaj
([ORCID 0009-0008-8098-9483](https://orcid.org/0009-0008-8098-9483)), *Adaptive
Retrieval for Repository Question Answering: A Pre-Specified Pilot Study of a
Vector-First Cascade*, November 2026. The PDF is on Zenodo:
[doi.org/10.5281/zenodo.24408656](https://doi.org/10.5281/zenodo.24408656).

## Research files and reproducibility

This Git repository contains the framework, tests, benchmark and review history,
frozen protocols and scores, compact experiment metadata, existing analysis
outputs, and manuscript sources. Credentials, local configurations, downloaded
checkouts, vector indexes and bulk raw model traces are excluded.

Start with the [portable configuration guide](configs/README.md). Copy
[.env.example](.env.example) to `.env` and add your own provider keys for live
runs. The existing index must be restored and verified, or a new index must be
built under a separately identified study; no model-backed run is implicit.

The [artifact guide](docs/research-artifacts.md) and
[checksum inventory](experiments/artifact-inventory.json) identify the large files
omitted from ordinary Git. No downloadable archive has been published with this
commit. Replaying the original runs requires those immutable files at their
recorded paths; code and frozen scores alone do not provide the full execution
record. The original local configurations and historical hashes remain unchanged.

## Install and verify

Use Python 3.11 or later and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --frozen --extra dev --extra vector --extra parse
uv run --frozen --extra dev --extra vector --extra parse pytest -q
uv run adaptive-rag config validate --config configs/langchain.yaml
uv run adaptive-rag repo snapshot --config configs/langchain.yaml
```

The `vector` extra supplies FAISS and NumPy. The `parse` extra supplies Tree-sitter
and Python, JavaScript, and TypeScript grammars. Basic snapshot validation and
vectorless retrieval also work without those extras; Python parsing then uses the
standard library and unsupported languages use explicitly recorded fallbacks.
Pydantic, PyYAML, and HTTPX are the core dependencies. LangChain is the repository
under study, not an implementation dependency.

The configuration pins LangChain to an exact commit. Snapshot setup requires Git
and network access when that commit is absent locally. The checkout must remain
clean and complete: tracked edits, untracked or ignored files, sparse checkouts,
and flags hiding edits are rejected. Keep output artifacts outside that checkout.

## Run retrieval now

Vectorless retrieval makes no model requests and needs no API key:

```sh
uv run adaptive-rag retrieve \
  --config configs/langchain.yaml \
  --strategy vectorless \
  --query 'Where is BaseRetriever defined?' \
  --output experiments/raw/vectorless-smoke-001/result.json \
  --trace experiments/raw/vectorless-smoke-001/trace.jsonl
```

The JSON result contains source paths, inclusive one-based line ranges, excerpt
hashes, operations, resource accounting, and an explicit completion status. It is
retrieved evidence, not an answer or correctness judgment. Exit code `0` means the
command completed; `2` covers invalid input, errors, and exhausted retrieval
budgets. Inspect status, errors, and evidence even when a command exits nonzero.
Choose fresh output filenames and run directories on every attempt: artifacts
are created exclusively and are never silently overwritten.

Plan vector indexing before making model calls:

```sh
uv run adaptive-rag index plan \
  --config configs/langchain.yaml \
  --output experiments/raw/index-plan-001.json
```

Planning reports chunk count, UTF-8 input bytes, batch count, and indexing budget.
It requires no API or FAISS. Bytes are admission estimates, not provider token
counts or a price estimate. Parser availability can change chunking, so use the
same environment and chunk settings for planning and construction.

## Configure model-backed retrieval

Copy the example into the same directory so its relative repository path remains
valid, then edit the copy:

```sh
cp configs/retrieval.example.yaml configs/retrieval.local.yaml
```

Set `models.base_url` to your endpoint's API prefix, and replace the example's
`REPLACE_...` embedding and chat model identifiers with identifiers actually served
there. If authentication is required, set `models.api_key_env` to an environment
variable containing the key; keep credentials out of YAML and trace artifacts.
If the key is stored in the project `.env`, load it explicitly for each command:
`uv run --frozen --env-file .env --extra vector --extra parse adaptive-rag ...`.
The framework reads process environment variables; it does not load `.env`
automatically. For OpenRouter, use `https://openrouter.ai/api/v1` as the base URL
and `OPENROUTER_API_KEY` as `api_key_env`. See the
[OpenRouter API guide](https://openrouter.ai/docs/quickstart).

Optional `models.chat_base_url` and `models.chat_api_key_env` override the endpoint
and key environment variable for answer, navigation, and routing calls. Each
omitted override falls back to `base_url` or `api_key_env`; embeddings continue
using those original settings. For direct Anthropic chat through its OpenAI
compatibility endpoint, use `chat_base_url: https://api.anthropic.com/v1`,
`chat_api_key_env: ANTHROPIC_API_KEY`, and an Anthropic model ID. This preserves a
separate embedding provider and its existing index identity. The client still
sends Chat Completions requests; configure only optional parameters supported by
that endpoint and verify compatibility before a larger run.

To space requests, configure `models.request_pacing`:

```yaml
request_pacing:
  min_interval_seconds: 6
  max_requests_per_minute: 10
```

When enabled, one process-local gate serializes calls to each endpoint. Answer,
navigation, and routing share a gate; embeddings share it when using that same
endpoint. `models.chat_request_pacing` can override chat pacing; a common endpoint
uses the stricter settings. Defaults add no pacing. Concurrent CLI processes have
separate gates, so run one experiment process per provider account.

The gate honors `Retry-After` on HTTP 402/429/503 and exhausted Anthropic
remaining/reset headers, without retrying failed requests. Queue and cooldown
waits consume stage and run deadlines; a wait that cannot fit is rejected before
network delegation with zero incurred usage. Raw provider-call elapsed time
excludes this queue wait, while job/stage elapsed time includes it. Unknown usage
from a request actually sent remains unknown. The default
`experiment.budget.unknown_usage_policy: stop` stops further execution when that
accounting cannot be established.

Opting into `experiment.budget.unknown_usage_policy: reserve` allows later jobs
when a separate admission ledger can cover the unknown call using serialized
input bytes and the full requested output limit, priced with the configured
schedule. A timed-out job stays failed; its actual tokens and complete cost stay
unknown, and the request is never retried. `metadata.budget_accounting` and final
status `budget_accounting` report used-or-reserved estimates separately from
actual usage and known cost subtotals. An unavailable finite reservation still
stops later jobs.

The portable study profile, [configs/adaptive.anthropic.example.yaml](configs/adaptive.anthropic.example.yaml), uses this
opt-in policy, direct Anthropic Haiku 4.5 chat, and the existing Qwen index and
embedding connection. Its fresh 270-job development plan allows two hours,
12 million budgeted tokens, 2,000 model attempts, and $9.90 in admission estimates;
at most $0.10 is allocated separately to synthetic preflight. The gate is
configured for six seconds between starts and ten starts per rolling minute.
The final wall-timestamp audit recorded one 5.945952-second chat gap and a
rolling-minute peak of 11; configured limits and observed wall times differ.
See the [final audit](experiments/preflight/final-development-2026-11-17-001/operational-audit-final.json) and
[pacing handoff](paper/pacing-handoff.md) for accounting and execution limits.
Request pacing does not establish your account's input/output token quotas or
guarantee that a request will succeed. See
[Anthropic rate limits](https://platform.claude.com/docs/en/api/rate-limits).

`--allow-api` explicitly enables requests, including potentially billable requests.
The framework does not select a provider or model on your behalf.

The adapter sends nonstreaming `/embeddings` and `/chat/completions` requests.
Agentic retrieval requires a tool-capable chat model. Configure
`models.token_parameter` as `max_tokens` or `max_completion_tokens` according to your
endpoint, and set `temperature: null` if that endpoint does not accept temperature.
Optional `embedding_dimensions` is sent only when configured. Compatibility
varies by provider; an OpenAI-compatible label does not establish that every
parameter, usage field, or tool behavior is supported. Contract details and
limitations are in [the Phase 2 methodology](paper/phase2-methodology.md).

Agentic navigation exposes five read-only source tools and a `select_evidence`
control that selects only evidence IDs already shown to the model. The preferred
completion uses that control as the sole tool call in a message. It counts toward
the tool-call budget and completes retrieval without another model request.
Mixed selection/read batches and invalid selections fail with their raw response
preserved. Final text containing only strict raw JSON or one exact whole `json`
code fence remains supported; prose around JSON is rejected. The same declared
text formats apply to routing and answer responses, without repair requests.

Review the indexing plan and adjust `retrieval.indexing_budget`, chunk sizes, and
`embedding_batch_size` for your corpus and endpoint before construction. The example
budget is a configurable cap, not a promise that the entire LangChain corpus fits.
A request that exceeds an endpoint's context or batch limits fails and is preserved.

```sh
uv run adaptive-rag index plan --config configs/retrieval.local.yaml
uv run adaptive-rag index build \
  --config configs/retrieval.local.yaml \
  --output datasets/indexes/langchain-001 \
  --allow-api

uv run adaptive-rag retrieve \
  --config configs/retrieval.local.yaml \
  --strategy vector \
  --index datasets/indexes/langchain-001 \
  --query 'Where is BaseRetriever defined?' \
  --output experiments/raw/vector-smoke-001/result.json \
  --trace experiments/raw/vector-smoke-001/trace.jsonl \
  --allow-api

uv run adaptive-rag retrieve \
  --config configs/retrieval.local.yaml \
  --strategy agentic \
  --query 'Where is BaseRetriever defined?' \
  --output experiments/raw/agentic-smoke-001/result.json \
  --trace experiments/raw/agentic-smoke-001/trace.jsonl \
  --allow-api
```

Indexes record their snapshot, corpus policy fingerprint, embedding identity,
chunking/parser/runtime versions, checksums, and separate build calls, tokens, and
latency. Build stdout is a compact summary with the index/manifest paths and
accounting; the full raw embedding responses remain in the on-disk manifest and
durable build journal. A failed build retains `build-failure.json` and cannot be
loaded as a completed index. Use a new directory for a later attempt.

To explicitly reuse verified successful batches from a failed build, select that
source and a fresh destination:

```sh
uv run adaptive-rag index build \
  --config configs/retrieval.local.yaml \
  --reuse-from datasets/indexes/langchain-failed-001 \
  --output datasets/indexes/langchain-002 --allow-api
```

Reuse validates the source journal against the current corpus and embedding
settings before using its successful batch responses. Only missing batches make
new model requests. The failed source stays untouched, and the new build records
its lineage. Reuse requires this explicit option; there is no automatic retry or
in-place continuation. Retain the parent journal and failure artifact: earlier
failed request costs and unknown usage do not disappear when a later index
completes. Report the lineage's unique requests and avoid counting reused
successful calls twice. See
[index accounting](experiments/README.md#token-time-and-price-accounting).

`reuse_provenance` separates reused successful usage from newly incurred calls
and retains parent failure accounting. The indexing call/token budget applies to
new provider requests; its elapsed limit includes validation and replay. Source
and destination must not overlap. Reuse from an already recovered build is
currently rejected, so retain the original failed source for this operation.

Only load indexes from trusted local sources: checksums detect accidental
corruption and do not
authenticate a replaced manifest and FAISS payload.

Retrieval budgets cover tool/model counts, provider tokens, source evidence
characters, and cooperative elapsed-time checks. Missing provider usage remains
unknown and disables further model calls in the affected job. The default run
policy also stops later jobs; opt-in reservations can admit later jobs as
described above. UTF-8 byte admission is conservative
under common tokenizer assumptions; provider overhead can exceed it. These checks
are not a provider-enforced spending quota or a hard process termination deadline.
CLI metadata separately reports preparation and end-to-end time; the retrieval
deadline excludes corpus preparation and index loading.

## Inspect and run adaptive routing

`adaptive_rule` and `adaptive_llm` select Vector, Vectorless, or Agentic retrieval
before retrieving evidence. No-retrieval remains a separate baseline. The routers
use query features and bounded repository metadata; benchmark annotations and
reference answers are excluded from their inputs. Rule and prompt versions are
recorded. Freeze these settings before held-out evaluation.

Inspect a rule decision without model requests or retrieval:

```sh
uv run adaptive-rag route \
  --config configs/langchain.yaml --router rule \
  --query 'Where is BaseRetriever defined?' \
  --output experiments/raw/routing-rule-001.json
```

The command verifies the pinned source and records a decision, features, request,
corpus identity, configuration hash, and timing. It returns no source evidence or
answer. `route --router llm` uses the configured routing model and requires
`--allow-api`. Routing failure or malformed output is preserved without a fallback.

Copy and edit the adaptive example, then build a compatible index separately:

```sh
cp configs/adaptive.example.yaml configs/adaptive.local.yaml
uv run adaptive-rag index plan --config configs/adaptive.local.yaml
uv run adaptive-rag index build \
  --config configs/adaptive.local.yaml \
  --output datasets/indexes/langchain-adaptive-001 --allow-api
```

Set `experiment.vector_index` to that completed directory. Set actual endpoint,
embedding, and tool-capable chat model IDs. `routing.chat_model` optionally
overrides the chat model for routing; null uses `models.chat_model`. Routing uses
the configured chat endpoint and key environment variable. Set its temperature, output
limit, and `routing.budget` explicitly. There are no new dependencies.

```sh
uv run adaptive-rag retrieve \
  --config configs/adaptive.local.yaml --strategy adaptive_rule \
  --index datasets/indexes/langchain-adaptive-001 \
  --query 'Where is BaseRetriever defined?' \
  --output experiments/raw/adaptive-rule-001/result.json \
  --trace experiments/raw/adaptive-rule-001/trace.jsonl --allow-api

uv run adaptive-rag route \
  --config configs/adaptive.local.yaml --router llm \
  --query 'How do these components coordinate across modules?' \
  --output experiments/raw/routing-llm-001.json --allow-api

uv run adaptive-rag experiment plan \
  --config configs/adaptive.local.yaml \
  --output experiments/raw/adaptive-plan-001.json
uv run adaptive-rag experiment run \
  --config configs/adaptive.local.yaml \
  --output experiments/raw/adaptive-001 --allow-api
```

Use `--strategy adaptive_llm` for LLM-selected retrieval. Both adaptive retrieval
commands preflight all three candidates, require a compatible `--index`, and
require `--allow-api` even when the rule eventually chooses Vectorless. This
keeps candidate availability consistent and detects invalid index configuration
before paying for routing. The rule-only `route` command needs no model settings.

The adaptive example adds both policies to the four fixed conditions and retains
development-only execution with three repetitions. All conditions share the
answer-generation settings. Its six conditions schedule 270 jobs for the 15
development questions. Routing has a separate recorded budget that is also
bounded by the combined retrieval-stage and global run limits; its consumed
calls, tokens, and time reduce what remains for the selected retriever. Routing
calls, including failed attempts, count toward totals and estimated cost. Missing
usage remains unknown and prevents further model requests in that job. Later
jobs follow the run's explicit unknown-usage policy. Inspect routing and
execution failures alongside the full planned denominator. See the
[Phase 4 methodology](paper/phase4-methodology.md) and
[handoff](paper/phase4-handoff.md) for the protocol and implementation limits.

## Corpus, benchmark, and traces

The source snapshot, discovery rules, and file hashes define a shared corpus for
all strategies. Evidence preserves repository-relative paths, source line ranges,
and checksums. Validation can detect mismatched source references; it cannot prove
that a citation supports an answer. See [datasets/README.md](datasets/README.md).

The reviewed [30-question pilot](benchmarks/pilot.jsonl) contains 10 conceptual,
10 structural, and 10 cross-file questions, split in advance into five development
and five held-out questions per category. All annotations have Shekhar's recorded
source-inspection acceptance. The [freeze manifest](benchmarks/pilot.freeze.json)
binds the dataset, source, split, review history, and software environment.
Validate it with:

```sh
uv run adaptive-rag benchmark validate \
  benchmarks/pilot.jsonl --config configs/langchain.yaml --pilot
```

`--allow-unreviewed` permits authoring audits; it does not qualify drafts for
evaluation. See [benchmarks/README.md](benchmarks/README.md).

Optional JSONL traces store configuration and source identity, requests/responses,
operations, evidence, nullable provider token usage, timing, and failures behind a
replaceable `TraceSink` interface. API authorization headers are omitted. Trace
contents include the query and source text sent to a provider; review them before
sharing. The independent `retrieve` command returns evidence; experiment results
add the generated answer, source citations, raw generation calls, and scoring data.
Storage conventions are in [experiments/README.md](experiments/README.md).

## Run the baseline experiment

The reviewed pilot is ready; execution also requires working endpoint/model
credentials and a compatible vector index. The [completed human review packet](benchmarks/review/README.md)
preserves the source excerpts, decisions, and separate AI cross-check. The
development and held-out allocation is frozen; the example runs only development
questions. Keep held-out annotations out of router prompts, examples, and tuning.

Copy and edit the experiment example:

```sh
cp configs/experiment.example.yaml configs/experiment.local.yaml
```

Set the endpoint, actual embedding/chat model identifiers, and the environment
variable holding your API key. Set `experiment.dataset` to the reviewed pilot and
`experiment.vector_index` to a completed index built with this same repository,
policy, embedding model, and chunk settings. YAML paths are relative to the YAML
file. Keep the copied configuration in `configs/`, or update its paths.
`experiment.answer_model` can override the answer model; otherwise generation uses
`models.chat_model`. All four conditions use the same answer model, prompt,
temperature, and output limit. Agentic navigation has its own retrieval settings.

Build the vector index separately if one is not available. These requests may
incur charges:

```sh
uv run adaptive-rag index plan --config configs/experiment.local.yaml
uv run adaptive-rag index build \
  --config configs/experiment.local.yaml \
  --output datasets/indexes/langchain-experiment-001 \
  --allow-api
```

Ensure `experiment.vector_index` names that output directory. Inspect a model-free
execution plan, then run into a fresh directory:

```sh
uv run adaptive-rag experiment plan \
  --config configs/experiment.local.yaml \
  --output experiments/raw/baseline-plan-001.json

uv run adaptive-rag experiment run \
  --config configs/experiment.local.yaml \
  --output experiments/raw/baseline-001 \
  --allow-api

uv run adaptive-rag experiment summarize experiments/raw/baseline-001 \
  --output experiments/aggregates/baseline-001-unreviewed.json
```

The default example schedules three repetitions of each condition. On the pilot's
15 development questions, four conditions produce 180 planned jobs. Set limits
and models before running. `--allow-api` enables potentially billable requests;
it does not guarantee that provider access, budget, or model compatibility works.
Index construction is separate from the experiment and is never automatic.

Each run freezes its configuration, benchmark, source identity, and job schedule.
Results and event logs preserve failed and interrupted work. A summary without
human reviews reports mechanical measurements and leaves semantic correctness
pending. Export answers for independent scoring:

```sh
uv run adaptive-rag experiment review-template experiments/raw/baseline-001 \
  --output experiments/raw/baseline-001-review-template.jsonl
```

An independent human reviews each available answer against the reference and
pinned source, fills the nested `score` fields, and saves only those `score`
objects as `experiments/raw/baseline-001-scores.jsonl`. Template nulls are pending
fields, not valid scores. Then summarize with reviews:

```sh
uv run adaptive-rag experiment summarize experiments/raw/baseline-001 \
  --reviews experiments/raw/baseline-001-scores.jsonl \
  --bootstrap-samples 2000 --seed 0 \
  --output experiments/aggregates/baseline-001-reviewed.json
```

Cost estimates require an optional dated, user-supplied price schedule. Absent
rates or usage remain unknown; they are never treated as free calls. Stage and
run budgets stop further requests when exhausted. Unknown accounting stops
execution by default; the opt-in `reserve` policy uses a separate admission
estimate for later jobs and leaves actual missing usage and cost unknown.
These cooperative checks are not a provider-enforced spending quota. See
[experiments/README.md](experiments/README.md) for artifact, review, and pricing
formats and [the Phase 3 methodology](paper/phase3-methodology.md) for definitions.

## Research scope

Development and held-out execution records, frozen AI scoring, the
[held-out protocol](paper/phase7-held-out-protocol.md), and the
[manuscript](paper/manuscript/adaptive-rag-pilot.md) are included. The held-out
[AI score file](experiments/reviews/adaptive-cascade-heldout-20261119-001/answers.ai-scores.jsonl)
and [freeze record](experiments/reviews/adaptive-cascade-heldout-20261119-001/ai-review/scores-frozen.json)
retain their original bindings and hashes. AI scoring and author attestations
are identified separately from per-item human ratings.

The latest [cascade development run and AI evaluation](paper/phase6-cascade-development-run.md)
recorded all 225 planned jobs, with 206 completed answers. All 206 now have
validated, explicitly labelled **AI scores**; no AI reviews remain pending.
With 19 failures counted as zero, Cascade and reserved-selection Agentic each
score 90.0%, Vector 77.8%, original Agentic 54.4%, and no retrieval 11.1%.
Cascade has higher mean estimated cost and elapsed time than Vector, so the
joint quality/cost/latency hypothesis remains unproven. See the
[final AI summary](experiments/reviews/adaptive-cascade-development-20261119-001/final-ai-review-summary.json)
and [scored packets](experiments/reviews/adaptive-cascade-development-20261119-001/ai-review/scored-packets/).
These results cover 15 development questions and have no independent human
review. The held-out study followed a separately frozen protocol; its records
are separate from these development results.

The earlier [paced development run](paper/phase5-paced-development-run.md) recorded all
270 planned jobs: 225 completed, 36 budget-exhausted, and 9 errors. All 227
available answer texts now have validated user-submitted scores from Shekhar;
no answer reviews remain pending. Vector has the highest failure-aware
correctness point estimate in this development run (74.4%), followed by Agentic
(62.2%); the adaptive rule and LLM conditions score 42.2% and 38.9%.
See the [reviewed results](paper/phase5-paced-development-run.md#reviewed-development-results)
and [final review summary](experiments/reviews/adaptive-anthropic-paced-development-20261117-001/final-review-summary.json).
These earlier results also cover 15 development questions under their frozen
budget profile. The answer prompt and evaluator differ from the latest run;
do not pool the runs or treat cross-run score changes as an isolated redesign effect.

The offline test suite uses labeled synthetic model outputs and local HTTP
transports to verify execution and accounting without live API calls. Separate
live preflight checks establish only the observed endpoint/model compatibility
for the requests tested. A source-navigation smoke check does not establish
answer accuracy, comparative quality, or support for the research hypothesis.
Configure and check actual endpoint/model settings for each study, complete
independent review of generated answers, preserve negative findings, and report
incomplete review coverage.
Adaptive routing now uses the same experiment and review workflow. Offline tests
do not establish that adaptive selection improves the research outcomes. The
original protocol is in [paper/methodology.md](paper/methodology.md), and retrieval
behavior is documented in [paper/phase2-methodology.md](paper/phase2-methodology.md)
and the [Phase 4 methodology](paper/phase4-methodology.md).

```text
configs/                  Repository, model, retrieval, and experiment YAML
datasets/                 Snapshot metadata, local checkouts, and optional indexes
src/adaptive_rag/
  ingestion/              Pinned Git snapshots and source discovery
  retrieval/              Corpus, chunking, vector, vectorless, agentic, and tools
  generation/             HTTP clients and shared bounded answer generation
  observability/          Structured retrieval traces and sink interface
  evaluation/             Validation, execution, metrics, reviews, prices, summaries
  routing/                Query features, deterministic rules, bounded LLM routing
benchmarks/               Reviewed frozen pilot and authoring/review protocol
experiments/              Immutable raw runs and derived aggregate reports
paper/                    Protocol and implementation methodology
```

The framework uses the [MIT license](LICENSE). Repository contents under study
retain their own licenses.

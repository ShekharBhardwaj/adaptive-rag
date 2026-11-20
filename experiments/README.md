# Experiment and retrieval records

Phase 4 runs fixed Vector, Vectorless, Agentic, and no-retrieval comparisons plus
rule-based and LLM adaptive conditions with one shared answer-generation protocol.
It records routing decisions and overhead, source metrics, tokens, timing,
failures, optional price estimates, independent human scores, and paired bootstrap
comparisons. A reviewed pilot is included. Offline tests use synthetic responses;
separate live preflight checks assess observed endpoint/model compatibility.
Files under `smoke/` and `preflight/` are execution checks or planning artifacts,
not benchmark results or answer-quality measurements.

## Prepare and execute

Install dependencies and validate the source as described in [the main README](../README.md).
Validate the frozen pilot using [the benchmark guide](../benchmarks/README.md).
Copy `configs/experiment.example.yaml` to `configs/experiment.local.yaml`, then
configure real model identifiers, endpoint, credentials through an environment
variable, dataset, and a separately completed vector index. Configuration paths
are relative to the YAML file.

```sh
uv run adaptive-rag benchmark validate benchmarks/pilot.jsonl \
  --config configs/experiment.local.yaml --pilot

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

Planning makes no model requests. A run requires `--allow-api` and can incur API
charges, including for failed requests. No vector index is constructed implicitly.
Use at least two repetitions; the example uses three. Its development pilot has
15 questions, so four conditions and three repetitions schedule 180 jobs. Freeze
conditions, source, prompts, limits, and analysis choices before any held-out run.

Use fresh paths for every command. Artifacts are created exclusively and are never
silently overwritten. Retain failed, exhausted, and interrupted runs in the planned
denominators. Do not rerun a failed subset into the original run directory.

For the six-condition adaptive comparison, copy `configs/adaptive.example.yaml`
to `configs/adaptive.local.yaml` and configure the same source, endpoint, models,
dataset, and compatible vector index. That example adds `adaptive_rule` and
`adaptive_llm` to the four baseline conditions above; it schedules 270 jobs for
15 development questions and three repetitions. The baseline example retains
the four-condition workflow and its 180-job schedule.

```sh
uv run adaptive-rag experiment plan \
  --config configs/adaptive.local.yaml \
  --output experiments/raw/adaptive-plan-001.json

uv run adaptive-rag experiment run \
  --config configs/adaptive.local.yaml \
  --output experiments/raw/adaptive-001 --allow-api

uv run adaptive-rag experiment summarize experiments/raw/adaptive-001 \
  --output experiments/aggregates/adaptive-001-unreviewed.json
```

`routing.chat_model` optionally selects a separate routing model; otherwise it
uses `models.chat_model`. Routing shares the endpoint and key environment setting.
Set `routing.budget` alongside the combined retrieval-stage and run budgets.
Adaptive jobs preflight all three candidate retrievers, including a completed
vector index, and choose one before retrieval. The no-retrieval condition stays
separate. Freeze rule/prompt versions and settings before held-out evaluation;
keep held-out questions, reference answers, gold evidence, and review results out
of routing development and model inputs. See the
[adaptive workflow](../README.md#inspect-and-run-adaptive-routing).

## Immutable observations and derived reports

```text
experiments/
  raw/<run-id>/
    manifest.json          Frozen identities, settings, and complete planned jobs
    configuration.json     Effective configuration
    benchmark.jsonl        Frozen benchmark annotations
    validation.json        Benchmark validation report
    corpus-manifest.json   Included source manifest
    index-manifest.json    Referenced index for vector or adaptive conditions
    price-schedule.json    Supplied schedule, when configured
    events.jsonl           Jobs, durable model requests/results, interruptions
    results.jsonl          Observed per-job retrieval and answer results
    status.json            Final run accounting/status when finalization succeeds
  aggregates/<analysis-id>.json
```

The manifest includes configuration/benchmark hashes, snapshot SHA, corpus
fingerprint, framework identity, model identities, generation/retrieval settings,
and the full job schedule. Per-job results preserve evidence, answer text,
citations, raw model requests/responses, operations, nullable token usage, latency,
cost, status, and errors. Adaptive results retain the policy as their condition,
the concrete selected strategy, and the routing decision with its features,
provenance, usage, attempts, errors, and elapsed time. A process interrupted
between a request and result write can leave a planned job without a result.
Summaries retain it as missing work; they do not invent an answer, token count,
or success.

Before each provider delegation, a model-request intent is flushed and fsynced.
The event contains the API-protocol request and configured identity without
authorization headers. Exact call records or known/unknown failures follow as
separate events. A soft interruption during a request records the attempted call
with unknown usage and preserves an interrupted job; a hard process kill can
leave only the durable request intent. An admission rejection is recorded as a
rejection, with zero additional model attempts or incurred usage.

Summaries are separate derived files. Keep raw inputs intact and preserve the
summary seed and bootstrap settings. Corrected analyses should use new output
files and describe the correction. API authorization headers are omitted, but
queries, source excerpts, answers, and benchmark reference annotations are stored
locally and may be included in review exports.

## Independent answer review

```sh
uv run adaptive-rag experiment review-template experiments/raw/baseline-001 \
  --output experiments/raw/baseline-001-review-template.jsonl
```

The template shuffles available answers and hides condition, category, and
repetition labels. Answer style can still reveal a condition. Each item supplies
the question, reference answer, gold source references, generated answer,
citations, and a nested `score` object. The score binds `run_id`, opaque `job_id`,
and the SHA-256 of the exact saved answer result, including its raw model calls.
Do not change those identifiers or edit the raw answer after review.

Have an independent human inspect the pinned source and fill:

- `reviewer`: a reviewer identity.
- `reviewed_at`: an ISO 8601 timestamp with timezone.
- `correctness`: 0 for incorrect, 0.5 for partly correct, 1 for fully correct;
  other values in [0, 1] require justification.
- `citation_support`: semantic support of answer claims by cited source in [0, 1],
  or null when not applicable.
- `notes`: a nonempty explanation of the judgment.

Keep `rubric_version: manual-v1`. Template nulls are pending entries, not valid
completed scores. Reviewer metadata records an attestation; it cannot prove that
a human actually performed independent review. Source-ID validity is mechanical
and does not substitute for semantic inspection. Available partial or failed answer
text can receive a diagnostic raw semantic score; its unsuccessful execution still
counts as zero in the separate failure-aware accuracy metric. Missing answers
cannot be reviewed.

After filling the template, extract its nested score objects to a new JSONL file:

```sh
uv run python - <<'PY'
import json
from pathlib import Path

source = Path("experiments/raw/baseline-001-review-template.jsonl")
target = Path("experiments/raw/baseline-001-scores.jsonl")
with target.open("x", encoding="utf-8") as stream:
    for line in source.read_text(encoding="utf-8").splitlines():
        stream.write(json.dumps(json.loads(line)["score"], ensure_ascii=False) + "\n")
PY

uv run adaptive-rag experiment summarize experiments/raw/baseline-001 \
  --reviews experiments/raw/baseline-001-scores.jsonl \
  --bootstrap-samples 2000 --seed 0 \
  --output experiments/aggregates/baseline-001-reviewed.json
```

The loader rejects duplicate scores, unknown jobs, stale output hashes, invalid
scores, and scores without actual answer text. Missing reviews remain pending.
Read review coverage alongside correctness; a conditional mean over reviewed
answers cannot describe the entire workload. Failure-aware accuracy counts
observed execution failures as zero and leaves unreviewed successful answers and
missing planned observations pending. A complete failure-aware mean is available
only when the full planned workload is resolved.

## Mechanical metrics and uncertainty

Evidence recall is the share of annotated gold ranges fully covered by the union
of retrieved ranges at the same path and commit. Evidence line recall is the
share of unique annotated lines retrieved. Neither establishes relevance or answer
truth. Citation validity is the share of claimed ID occurrences actually supplied
as evidence; no citation claims is N/A. Semantic correctness and citation support
require human scores. No-retrieval evidence recall is zero.

Comparisons match conditions on the same questions and repetitions. Bootstrap
resampling uses questions as clusters after averaging matched repetitions, so
repeated answers do not become independent questions. A question with missing
repetitions is excluded from that paired metric and reported as unresolved.
Reports include the seed, paired-question coverage, and pending/missing
observations. Inspect those counts and failure-aware accuracy before interpreting
a difference or interval.

## Token, time, and price accounting

Optional `models.request_pacing` and `models.chat_request_pacing` settings are
frozen with the configuration. Enabled gates serialize calls within a process,
space starts, enforce a rolling request cap, and honor explicit provider
cooldowns. All chat roles share one gate. Queue/cooldown time is included in
stage, job, and run elapsed time; raw provider-call time starts after admission.
State the pacing settings when interpreting latency. Waits do not incur provider tokens
or cost. A deadline rejection before delegation is a zero-attempt admission
failure; a soft cancellation during the wait preserves zero additional usage
and stops execution. Request headers and pacing state never enter the persistent
embedding identity, so the existing compatible index remains usable.

Query accounting combines routing, retrieval, and answer-generation calls,
including failed attempts and their call records when available. The routing
stage has its own limits within the combined retrieval budget; its consumed
calls, tokens, and time reduce what remains for the selected retriever. Unknown
provider usage stays null and disables further model requests. Preflight UTF-8
byte estimates reserve output tokens; they are not exact tokenizer counts.
Stage budgets and global model-call, token, time,
and optional estimated-cost caps are checked before every provider call, including
successive calls during agent navigation and the later answer request. They are
cooperative controls, not a provider-enforced quota or hard process deadline. The
global wall-clock budget includes run preparation. A request already in flight
can exceed a cap; known exhaustion prevents the following call.

Per-job elapsed time covers condition execution against the prepared shared
corpus. Run preparation is recorded separately. The comparison therefore measures
the declared reuse policy; it is not a fresh-process, cold-start measurement for
every query. Index build calls, tokens, and latency are preserved in the referenced
build manifest and excluded from per-query totals. State a workload/query count
before reporting any amortization; the framework does not choose one implicitly.
Per-job time includes source-integrity checks and strategy tools as well as model
requests. Strategies perform different amounts of integrity work, so latency
reflects this implementation and provider effects together. `order_seed` controls
the schedule; no provider sampling seed is set.

Failed or interrupted index construction retains `build-failure.json` and the
durable `build-events.jsonl` journal. To reuse verified successful batches, pass
`index build --reuse-from SOURCE --output NEW_DIRECTORY` with the intended
configuration and `--allow-api`. The destination must be fresh, the source stays
unchanged, and provenance/response verification must succeed before a batch can
be reused. This is an explicit new build, with no automatic retries or in-place
continuation. Requests are made only for batches without a verified reusable
response; a failed or uncertain source request is not considered reusable.

Preserve the complete parent lineage, including each earlier failure, elapsed
time, known token subtotal, and any unknown usage or cost. A completed index does
not turn its parent's failed requests into free or successful calls. When
reporting the full construction workload, count unique billed attempts across
the lineage, avoiding a second charge for successful batch records reused in
the completed index. Separate newly incurred work from reused successful
provenance, and retain uncertainty for prior unsuccessful attempts. Build stdout
contains a compact summary; raw calls and vectors remain in the saved artifacts.

The completed manifest's `model_calls`, `model_attempts`, and `usage` describe
reused plus newly successful calls exactly once. `reuse_provenance` records the
source directory and journal/failure hashes, reused counts/usage, newly incurred
attempts/usage, and `parent_failure_accounting`. The latter retains excluded
failed attempts and uncertainty; successful-index usage alone is not the total
construction workload. Indexing call/token limits apply to new requests, while
elapsed time includes validation and replay. The stdout `reuse` summary omits
the full parent accounting and raw calls. Source/output overlap and source
symlinks are rejected, and recursive reuse from an already recovered build is
currently unsupported.

Agentic navigation has five read-only source tools and a `select_evidence`
control for finalizing a set of already observed evidence IDs. A selection
control must be the sole call in its message and counts as one tool operation;
successful selection returns directly without a further model request. Invalid
or mixed selection batches are preserved as failures. The control requires raw
strict JSON arguments. Final text selections remain compatible with strict raw
JSON or one exact whole `json` fence, with `selection_method: text_json` recorded;
native completion records `selection_method: tool_call`. Neither path extracts
JSON from surrounding prose or requests a format repair. The same declared text
encodings apply to routing and answers, with the observed encoding recorded.

Set `experiment.price_schedule` to a JSON file with this shape, using actual rates
and their source. The symbolic placeholders below must be replaced with numbers;
this is a format illustration, not a supplied price estimate:

```text
{
  "currency": "USD",
  "as_of": "YYYY-MM-DD",
  "source": "Dated provider pricing URL or contract reference",
  "entries": [
    {
      "base_url": "https://YOUR-ENDPOINT/v1",
      "model": "YOUR-CHAT-MODEL",
      "operation": "chat",
      "input_usd_per_million": INPUT_RATE,
      "output_usd_per_million": OUTPUT_RATE
    }
  ]
}
```

Provide an entry for every endpoint/model/operation used, including embeddings
and separate routing or answer models when configured. The schedule's content
hash and date are retained. No prices are fetched or guessed. Missing rates or
usage make the complete estimate unknown while retaining any known subtotal. Estimates use the
declared input/output token rates; provider billing adjustments require an
appropriate schedule and separate reconciliation.

Independent `retrieve` traces still use `TraceSink`/`JsonlTraceSink` and preserve
the common evidence and provenance format, adding routing metadata and the
selected strategy for adaptive results. They are useful for navigation diagnostics
but are not substitutes for complete experiment records. See
[Phase 3 methodology](../paper/phase3-methodology.md) for the analysis policy and
[Phase 4 methodology](../paper/phase4-methodology.md) for adaptive selection.

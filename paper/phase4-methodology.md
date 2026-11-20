# Phase 4 methodology: query-aware retrieval selection

Phase 4 compares a rule-based router and an LLM router with the existing fixed
Vector, Vectorless, Agentic, and no-retrieval conditions. It implements the
comparison; it does not establish that adaptive routing improves correctness,
cost, or latency. Null and negative findings remain valid study outcomes.

## Selection before retrieval

Each adaptive condition chooses one of the three retrieval strategies before
retrieving source evidence. The no-retrieval condition remains a separate
baseline. Routers receive the query and declared, reproducible query features.
They do not receive benchmark categories, difficulty labels, reference answers,
gold source ranges, split labels, reviews, or measured strategy outcomes.

The rule-based router is deterministic and versioned (`routing-rules-v1`).
Navigation terms take priority and select Agentic; otherwise an explicit path or
code identifier selects Vectorless; other queries select Vector. The recorded
syntactic features include character/word counts, path/identifier flags, and
matched navigation terms. These are generic heuristics, not optimality labels.
The decision includes the rule that selected the strategy. The LLM router uses a versioned
prompt with a closed strategy vocabulary and strict structured output. Routing
failure, invalid output, missing usage, and budget exhaustion remain observable
failures. There is no hidden retry, fallback model, or second strategy attempt.

Query text and generated routing explanations are untrusted input. A query can
mention strategy names or request that instructions be ignored; the framework
still validates the selected strategy and the response schema. Schema validation
does not establish that the choice is appropriate for a question.

Repository metadata includes the pinned commit, corpus fingerprint, file counts,
and aggregate extension/top-level-directory counts. It excludes source contents
and individual file names. Each group list is bounded to 32 labels of at most 128
characters, with omitted counts retained. The LLM prompt (`routing-llm-v3`) has no
tools and requires exactly a strategy and a brief rationale; one model request
is admitted at most. Provider calls and the prompt are retained for inspection.
The shared assistant-response decoder accepts raw JSON or one whole Markdown
`json` fence containing that JSON. It records the encoding and preserves the
original response. Extra text, multiple fences, duplicate keys, and nonstandard
numeric constants fail validation. Tool arguments still require raw JSON. This
format normalization does not add a model request, retry, or fallback.

The agentic navigation prompt (`repository-navigation-v6`) advertises the five
read tools and a `select_evidence` control tool. Finalization selects only unique
IDs already observed through source reads and obeys the same top-k limit. It
counts against the tool budget and is recorded as a control operation; it does
not read source or start another model request. A finalization call mixed with
read calls is rejected before any read executes. Strict raw or whole-fenced
JSON final text remains supported and its encoding is recorded.

Version 6 shows the remaining navigation budget before each request and recommends
bounded reads of known repository paths. Model-facing evidence contains its ID,
path, line range, and text; complete provenance remains in the audit records.
Assistant narration on tool turns is retained in raw responses and omitted from
subsequent request history. These generic engineering changes were informed by
aggregate development failures; they do not use held-out questions or outcomes.

## Frozen policy and held-out discipline

Freeze the routing policy version, rule settings, LLM prompt, model identifiers,
temperature, output limit, budgets, corpus, index, split, repetitions, and analysis
settings before a comparison. The rule policy and prompt are generic software
repository heuristics; they are not fitted against the included pilot answers or
per-question strategy results. Any development tuning must use development data
only and retain its provenance. Held-out questions and annotations must stay out
of router development, prompts, examples, and manual policy selection.

Model identifiers and request parameters are recorded, but a provider alias does
not pin remote model weights. The schedule seed controls job order, not provider
sampling. Record environment and source identity alongside every run.

## Shared retrieval and answer generation

Adaptive jobs execute the selected existing retriever and then use the same
answer model, prompt, generation settings, source evidence format, and scoring
path as the fixed baselines. A selected strategy is a routing observation, not a
replacement for the experimental condition: summaries compare `adaptive_rule`
and `adaptive_llm` as conditions while preserving the concrete strategy chosen
for each query.

An adaptive strategy must not silently rebuild an index, change the corpus,
substitute another model, or retry a failed request. Index construction remains
a separate measured stage. State index reuse and any amortization assumption
when comparing workload costs.

An explicitly requested index recovery can reuse verified successful embedding
batches from one failed local build into a fresh directory. It validates source
identity, chunk inputs/order, model identity, receipts, vectors, and token usage
before any new request. The completed manifest counts successful reused and new
calls once and embeds hashed parent lineage, excluded failed calls, and unknown
attempts separately. Incremental budgets apply to new requests; elapsed time
includes validation and replay. Complete construction cost remains unknown if a
parent attempt has unknown usage. Preserve the failed parent and report cumulative
preparation history; recursive recovery is currently rejected.

## Routing overhead and failure accounting

Record the routing decision, policy and prompt provenance, selected strategy,
query features, elapsed time, raw model calls, usage, and errors separately from
retrieval and answer generation. Include routing calls, tokens, elapsed time,
and estimated cost in each adaptive job and in the shared run totals. A rule
decision uses zero model calls; its computation still has measured elapsed time.

Experiment attempt counts cover failed and interrupted requests, including
requests with no complete provider response. Missing provider usage remains unknown, even when a
partial response or error record exists. Preserve known subtotals without
reporting an unknown complete estimate as zero. Unknown accounting or an
exhausted budget prevents further model calls. Admission estimates and elapsed
checks are cooperative; an in-flight operation can exceed a configured limit.
These controls are not provider-enforced billing quotas or process deadlines.
Standalone decision and retrieval commands write returned failure results; an
external process interruption can occur before their final artifact is written.
The experiment event log provides durable per-call attempt records.

Keep routing failures in the full planned denominator. Do not drop failed jobs,
replace them with successful reruns, or report only successful routing decisions
without coverage and failure counts. A malformed decision is not evidence that a
different strategy would have succeeded.

## Evaluation and interpretation

The Phase 3 definitions continue to apply to source-range recall, source-line
recall, mechanical citation validity, independent semantic review, failure-aware
correctness, and paired question-cluster bootstrap intervals. See
[Phase 3 methodology](phase3-methodology.md). A routing decision has no gold
strategy label: its usefulness is assessed through the complete answer outcome,
cost, latency, and coverage comparison, with overhead included.

Report the distribution of selected strategies and routing failures alongside
condition results. A frequent choice alone does not show that it was optimal.
Separate router, retrieval, generation, shared preparation, and index costs so
readers can assess the workload and reuse policy. Preserve paired coverage,
review coverage, missing observations, and unreviewed successful answers.

Offline tests use synthetic queries, source repositories, provider responses,
and local transports. They verify protocol behavior and accounting without real
API requests. They do not measure answer quality, router quality, provider
compatibility, or evidence for the research hypothesis. Live compatibility checks
and study execution require an explicitly configured endpoint and `--allow-api`.

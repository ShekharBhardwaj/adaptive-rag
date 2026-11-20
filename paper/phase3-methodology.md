# Phase 3 baseline experiment methodology

This document describes the implemented evaluation harness and its limits. It
does not report an experiment or support the research hypothesis. The
[study protocol](methodology.md) remains the research design, and
[Phase 2 methodology](phase2-methodology.md) defines the retrieval baselines.
Phase 3 adds common answer generation and reproducible execution of fixed Vector,
Vectorless, Agentic, and no-retrieval conditions. Adaptive routers remain Phase 4.

## Inputs, splits, and fair comparisons

Experiments use an independently reviewed benchmark tied to the same pinned
repository commit as the corpus. The pilot requires 30 questions: ten per category,
with five development and five held-out questions per category. The reviewed
pilot and its freeze manifest are included under `benchmarks/`.
`require_pilot: false` permits other reviewed datasets; it does not
turn synthetic fixtures into research measurements. A run selects one explicit
split. Researchers must freeze the allocation and baseline settings before using
held-out questions, and avoid tuning from held-out results.

Retrieval receives only the question string, top-k, and stage budgets. Generation
receives only the question string and retrieved evidence. Category, split, gold
answer, and gold evidence are excluded from both model-facing interfaces. The
evaluation layer retains these annotations for validation, metrics, grouping, and
human review. The local frozen benchmark and review exports contain reference
annotations and should remain separate from model inputs.

All conditions share the source snapshot, corpus selection policy, and answer
model/settings. `experiment.answer_model` optionally overrides `models.chat_model`
for all four conditions. Agentic retrieval may use `models.chat_model` for its
navigation requests. Vector retrieval requires an existing compatible index;
there is no automatic build or synthetic-embedding fallback. No-retrieval skips
source retrieval and passes an empty evidence tuple to the shared generator.

The runner schedules all selected question/condition/repetition combinations;
repetitions must be at least two and default to three. It shuffles execution order
with the recorded `order_seed`. Repeated deterministic settings still test system
variation; a seed does not guarantee deterministic remote model behavior. Query
order controls neither remote service load nor provider changes.

## Shared answer generation and citation provenance

`GroundedAnswerGenerator` uses one versioned system prompt, model request, and
configured temperature/output cap per job. The prompt and parameters are identical
across conditions; only question and evidence differ. Source text is serialized
as untrusted data. Retrieval scores and navigation reasons are excluded from the
generation payload. The prompt permits model knowledge with stated uncertainty
when evidence is absent or insufficient and forbids invented citations. This is
a declared answer policy, not proof that a model will comply.

The final response must be strict JSON containing exactly a nonempty `answer`
and a list of `citation_ids`. Duplicate object keys, nonstandard numeric constants,
extra fields, invalid shapes, and unexpected tools fail explicitly. There are no
format-repair calls, automatic retries, or fallback models. Raw provider call
records and invalid outputs remain available, so malformed output cannot receive
extra inference opportunities in one condition.

Before the request, evidence is checked for valid source metadata, matching text
hash, source-derived stable ID, complete line count, unique IDs, and one commit.
Citations are mapped only to supplied excerpts; the model never supplies a source
path or range to be trusted. Unknown IDs and duplicate claims are retained as
diagnostics and cause an error. A parseable answer with citation errors remains
in the raw result. These checks establish provenance only: a genuine excerpt can
be irrelevant or fail to support an answer claim. They do not establish semantic
truth, citation completeness, or immunity to prompt injection.

The generator reserves its full configured output allowance at admission, without
reducing it for evidence-heavy conditions. Evidence exceeding the character cap
fails before the request; no source excerpt is silently truncated midline.
Preflight token admission uses serialized UTF-8 bytes plus reserved output tokens.
It assumes byte-based tokenizer behavior and does not include every possible
provider overhead. Provider-reported usage remains authoritative. A response can
therefore consume more tokens than admitted and is recorded as exhausted.

## Execution, budgets, and immutable records

`experiment plan` validates and describes execution without making model requests.
`experiment run` requires `--allow-api` and creates a fresh output directory. It
freezes the configuration, benchmark, validation report, included source manifest,
optional price schedule, and any referenced vector-index manifest. The run
manifest records content hashes, source/corpus identity, framework metadata,
model identities, settings, and the full planned schedule.

Append-only event and result JSONL preserve execution observations. Successful,
failed, exhausted, and interrupted work remains part of the planned workload.
An in-flight job interrupted before a result is written is represented by its
events and a missing planned result, rather than a fabricated token count or
answer. A final status file records accounting when finalization succeeds. A
later summary derives missing counts from the original plan even if finalization
did not succeed. Raw artifacts are not silently overwritten or resumed in place.

Every model request passes through a run-wide call journal. Its request intent is
flushed and fsynced before provider delegation; the exact call record or failure
is journaled immediately afterward. Authorization headers and API keys are not
part of the protocol request event. Admission rejection records no new model
attempt and does not fabricate unknown usage. Soft interruptions during a call
retain the actual attempt, unknown usage, and interruption events before the
runner writes an interrupted result. A hard process kill can leave only the
durable request intent, which cannot establish a provider outcome or cost.

Retrieval stage caps include tools, calls, tokens, elapsed time, and source
characters. Generation has its own token/output, elapsed-time, and evidence caps.
Global run caps bound calls, tokens, time, and optional estimated USD cost. The run
wall-clock limit includes preparation. Non-completed retrieval prevents answer
generation; partial evidence and navigation output are retained for audit. A failed
or exhausted answer request likewise retains its raw call, usage, and any parseable
answer.

Global admission checks occur before every provider call, including successive
agent-navigation requests and the answer request. Known exhaustion or unknown
usage prevents any following call. One in-flight response can overrun a token or
estimated USD cap; these checks do not promise a provider-enforced price ceiling.

Missing provider usage is unknown rather than zero and stops further model calls.
A failed request without a record can have unknown usage and cost. Measurable
overruns remain explicit budget failures. HTTP timeouts and elapsed-time checks
are cooperative, and a native or in-flight operation can finish after its limit.
The caps are not provider-enforced quotas or guarantees of exact maximum billing.
Do not remove failed jobs from a comparison or substitute a later successful
rerun without reporting the change in study protocol.

## Mechanical metrics and independent semantic review

Mechanical evidence recall weights each annotated source range equally and counts
it only when retrieved ranges jointly cover the full range at the correct path
and commit. Evidence line recall weights unique annotated source lines. Extra
irrelevant material does not lower either recall measure. No-retrieval has zero
evidence recall. These measures depend on the completeness of gold annotations
and do not estimate retrieval precision or relevance.

Citation validity measures the share of claimed ID occurrences present in the
supplied evidence. Repeated claims remain repeated denominator entries; no claims
is N/A. A fully valid ID list can still cite unsupported claims or omit necessary
citations. Mechanical `answer_correctness`, `citation_correctness`, and
`retrieval_relevance` remain unset.

`experiment review-template` exports available answer text in shuffled order with
condition, category, and repetition hidden. It supplies questions, reference
answers, source references, generated answers, and source citations. Opaque job
IDs and an output SHA-256 bind each nested score to the exact saved answer result,
including its raw model calls. This limits stale or mismatched scoring; it does
not guarantee perfect blinding, since content may reveal a condition. Missing
answers cannot receive a score. Available failed or partial answers can receive a
raw semantic score for diagnostics, with execution status accounted separately.

An independent human inspects source and assigns correctness in [0, 1], using
0 for incorrect, 0.5 for partially correct, and 1 for fully correct. Intermediate
values require justification. The reviewer separately assigns semantic citation
support in [0, 1], or null when not applicable, and records identity, timezone-aware
time, rubric version, and notes. Identity metadata is an attestation, not automated
proof of independence. Template nulls are pending entries. The score loader rejects
unknown, duplicate, stale, malformed, and missing-answer scores.

Summary correctness over reviewed outputs is conditional on review availability.
Review coverage, planned counts, failures, missing results, and pending reviews
must accompany it. Failure-aware accuracy assigns observed execution failures zero
regardless of a partial answer's semantic score. Unreviewed successes and missing
planned observations remain pending; neither is silently equated with an incorrect
answer. A complete failure-aware mean requires the full planned workload to be
resolved. Report conditional and failure-aware metrics with their denominators
rather than quoting a favorable subset alone.

## Uncertainty, latency, and cost interpretation

Paired comparisons match questions and repetitions between conditions before
averaging within each question. Bootstrap resampling uses questions as clusters;
repeated outputs are not independent question samples. Any question with a missing
repetition is excluded for that paired metric and counted as unresolved. Record
bootstrap count, seed, paired coverage, and missing observations. Intervals describe
the available paired workload under these analysis choices; selective review and
informative failures can still bias a completed-only comparison. A small pilot
cannot support broad generalization to other repositories or query populations.

Per-job latency measures condition execution against a shared prepared corpus.
Run preparation is retained separately, so the experiment has a declared warm
reuse policy rather than fresh corpus/index setup for each query. Shared setup,
index build, query embedding, navigation, and answer generation are distinguishable
in the records. Query call/token accounting includes retrieval and generation,
including failed calls when records exist. Native I/O, process scheduling, remote
service load, and provider aliases can affect reproducibility; a model identifier
does not pin remote weights.

Job latency includes source-integrity verification and strategy tools as well as
network/model execution. Different strategies can perform different amounts of
integrity work, so reported latency reflects this implementation and provider
effects together. The recorded schedule seed is not a provider sampling seed;
the runner does not set a provider stochastic seed.

Index construction is measured separately and referenced by the run. It is not
silently rebuilt or charged once per query. No default workload size or indexing
amortization is assumed. State the number of queries and reuse policy whenever
combining build and inference costs or comparing end-to-end workloads.

Price estimates use a dated, user-supplied USD schedule keyed by endpoint, model,
and operation, with separate input/output rates per million tokens. The source,
date, and schedule hash are retained; no live prices are fetched or guessed.
Absent rates or incomplete usage yield an unknown complete estimate while
preserving known subtotals. The estimate does not independently reconstruct
provider-specific billing adjustments. An optional USD run cap requires adequate
pricing/accounting and cannot prevent an already-started request from overrunning.

## Verification and remaining researcher work

Implementation tests use labeled synthetic outputs and local HTTP transports.
They exercise orchestration, provenance, malformed outputs, budgets, accounting,
failure preservation, review binding, and analysis without live API requests.
They do not measure semantic answer quality or establish provider compatibility.

Before a research run, author and independently review the pilot, configure and
verify the actual endpoint/model credentials, build the matching index, freeze
the split/settings/analysis policy, and decide whether a dated price schedule is
needed. After execution, complete independent answer review, inspect failure and
coverage counts, and preserve null or negative findings. Phase 4 adaptive routing
and the full hypothesis comparison remain separate work.

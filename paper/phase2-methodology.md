# Phase 2 retrieval baseline methodology

This document describes implemented retrieval behavior and its limits. It is not
an experimental results report. The original [study protocol](methodology.md)
remains the research design; the Phase 1 handoff is a historical implementation
record. Phase 2 adds three independent evidence-returning baselines and model
clients. Answer generation, benchmark execution/scoring, no-retrieval answer
comparison, cost estimation, adaptive routers, and statistical analysis remain
future work.

## Shared inputs and source integrity

Each strategy accepts a `RetrievalRequest` containing only a query, top-k, and
resource budget. It receives a `RepositoryCorpus` built from the same exact Git
commit, discovery policy, and included Git blobs. Benchmark category, split,
reference answers, and gold evidence are absent from this interface. Corpus
fingerprints identify source selection as well as file content. No corpus code
is executed during retrieval.

Returned evidence contains the pinned commit, repository-relative path, inclusive
one-based source line range, excerpt checksum, stable identifier, text, optional
score, and retrieval reason. A valid location does not establish relevance or
answer correctness. The independent benchmark review protocol still applies.

## Vector baseline

`VectorRetriever` chunks all included nonempty files and embeds source text using
the explicitly configured client. Default chunk limits are 80 lines and 12,000
characters, with eight overlapping lines when a bounded window cuts through a
larger block. Top-level Tree-sitter boundaries are used for Python, JavaScript,
and TypeScript when installed. Python uses the standard-library AST if its grammar
is unavailable. Unsupported languages, parse errors, and incompatible grammars use
explicitly recorded line-window fallbacks. Leading/trailing comments and decorators
remain covered by source ranges; a final line needs no terminal newline.

Chunks contain complete original lines. One line exceeding `max_chars` remains
intact, with an explicit oversized-line marker: the character bound is soft for
that case, and endpoint input limits can still reject it. The configured batch
size limits embedding inputs per request. Adjust chunking and batching to the
provider's limits before any paid run; no provider-specific tokenizer or automatic
truncation is used.

Embeddings must have consistent positive dimensions, finite entries, and nonzero
norms. Vectors and query embeddings are normalized and indexed by FAISS
`IndexFlatIP`. Ranking therefore uses cosine similarity, following the official
[FAISS metric guidance](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances).
The implementation uses all flat-index candidates to resolve equal scores by
stable source order, then returns top-k chunks that fit the evidence budget.
Scores are similarities, not calibrated probabilities.

An index directory is created once. `chunks.json` stores source provenance and
row order; `index.faiss` stores the native index; `manifest.json` is written only
on completion. The manifest pins corpus/commit, model endpoint and identifier,
optional dimensions, chunk settings, parser and runtime versions, dimensions,
checksums, and build calls/usage/latency. Loading rejects mismatched identities,
versions, provenance, order, shape, norms, missing artifacts, or checksum failures.
No pickle is used. Hashes are checked before native deserialization, but loading
still assumes trusted local artifacts, consistent with
[FAISS I/O guidance](https://github.com/facebookresearch/faiss/wiki/Index-IO,-cloning-and-hyper-parameter-tuning).

Build failures retain raw call records, known or unknown usage, elapsed time,
and errors in `build-failure.json`; incomplete indexes are never queryable.
Indexing tokens and latency are recorded separately from each retrieval query.
There is no silent rebuild, embedding fallback, or synthetic runtime embedding.

## Vectorless baseline

`VectorlessRetriever` applies declared deterministic rules to query content:
extract identifiers and path hints, inspect directory hierarchy, search filenames,
search symbol definitions, search keywords, rank candidates, and inspect bounded
source ranges. Candidate scoring and tie-breaking are explicit in code and trace
reasons. Filename, symbol, and keyword scores are heuristic values rather than
probabilities. This strategy uses no embeddings, vector store, or model calls.

The tools operate only on the included corpus. Python definitions use AST parsing;
other supported languages use recorded approximate textual symbol patterns.
Tree-sitter is currently used for vector chunking, not symbol search. Reference
inspection finds textual occurrences, not a resolved static call graph. File exclusions and parser
coverage can remove useful evidence. No structural-category superiority is assumed.

## Agentic baseline

`AgenticRetriever` uses a configured tool-capable chat model with five read-only
tools: `list_directory`, `search_files`, `search_symbols`, `read_file`, and
`inspect_references`. It iteratively receives bounded tool output and may refine
navigation. Repository text is treated as untrusted data; instructions prohibit
executing code or following instructions in source text. No general shell, web,
or write tool is exposed.

Prompts, assistant messages, tool arguments/results, errors, and observable
navigation decisions are retained. Tool schemas and argument validation constrain
paths, ranges, sizes, and unknown fields. The final response must be strict JSON
containing only unique `evidence_ids` actually shown to the model, within top-k.
Fabricated identifiers, invalid JSON, and unsupported final prose fail explicitly.
Model prose is never accepted as evidence or as a final research answer.

This interface follows the function/tool exchange described in the official
[OpenAI function-calling guide](https://developers.openai.com/api/docs/guides/function-calling).
A compatible transport and valid source IDs do not establish that the selected
evidence is relevant, sufficient, or robust against every prompt injection.

## HTTP contracts and provider compatibility

The synchronous HTTPX adapter sends JSON requests to the configured API prefix,
using `/embeddings` with float encoding and optional dimensions, and
`/chat/completions` with tools and a configured output-token parameter. Embedding
responses are reordered by their declared input indices and validated before use.
Chat responses must contain one assistant message. No SDK, automatic retry,
redirect following, fallback model, or implicit provider/model selection is used.

The official [Embeddings API reference](https://developers.openai.com/api/reference/python/resources/embeddings/methods/create)
and [Chat Completions API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
define the reference JSON contracts. Providers may support different model IDs,
context sizes, dimensions, temperature settings, tool behavior, and token-cap
parameters. Choose `max_tokens` or `max_completion_tokens` explicitly; the latter
can include non-visible reasoning tokens. A model identifier or alias does not
pin remote model weights; record provider revision information when available.
Endpoint access and actual provider integration are unverified until a researcher
runs that exact configuration.

## Budgets, failures, and timing

A retrieval budget caps requested tool/model calls, provider-reported total tokens,
evidence characters, and elapsed time. Index construction uses a separately
configured indexing budget. A completed operation can still have insufficient
relevant evidence; inspect its returned chunks rather than treating completion
as a quality score.

Before a model request, the implementation admits UTF-8 input-byte estimates
against remaining tokens; agentic retrieval also reserves output tokens. This is
a conservative approximation for common byte-based tokenizers, not a tokenizer
or a provider-enforced quota. Providers can add hidden prompt overhead or report
more tokens than estimated. Reported usage is authoritative, and excess usage
causes an explicit exhausted result. Missing usage remains null, never zero, and
prevents further model calls. Failed requests may already incur provider costs.

Elapsed-time checks and HTTP timeouts are cooperative. Native work or a blocking
transport operation can finish after the requested deadline; the result records
the overrun and failure status rather than claiming hard cancellation. Tool/model
limits, token limits, time limits, and evidence limits should be preregistered for
evaluation and reported separately.

`RetrievalResult.elapsed_seconds` covers the strategy invocation. CLI metadata
separately records `preparation_seconds` for snapshot/corpus preparation and index
loading, plus `end_to_end_seconds` through retrieval completion. The retrieval
deadline excludes preparation, and the reported end-to-end metadata excludes
final artifact serialization. Reuse policies, warm/cold state, I/O, and process
startup must be controlled and measured in the later evaluation harness.

## Observability and verification status

`TraceSink` keeps observability independent of any external ledger service.
The local JSONL sink creates a fresh file per run. Traces contain configuration
and hash, framework source hash/revision/dirty state when available, corpus
identity, query, operations, evidence, raw model request/response records, nullable
tokens, errors, and timing. Authorization headers are omitted. Traces still contain
queries and source excerpts and must be reviewed before publication. The reserved
`final_answer` remains null in Phase 2.

Tests use deterministic synthetic embeddings/chat outputs and local HTTP fixture
transports clearly labeled as test data. They verify parsing, provenance, index
round trips, budgets, malformed responses, errors, and trace behavior without
calling a live model provider. A real-source vectorless smoke query can establish
that navigation executes against pinned LangChain; it is not a benchmark outcome.
No comparative retrieval quality, correctness, price, or hypothesis conclusion
follows from these tests.

Next, author and independently review the pilot and implement Phase 3 after an
explicit request: consistent answer generation, no-retrieval comparison,
reproducible execution, reviewed scoring, complete cost/timing accounting, and
uncertainty estimates. Keep held-out questions untouched during baseline and
router tuning. Adaptive routing remains Phase 4.

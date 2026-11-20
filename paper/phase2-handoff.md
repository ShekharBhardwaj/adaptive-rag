# Phase 2 handoff

Implemented on 2026-11-15. This is an engineering verification record, not a report
of comparative retrieval quality or research findings.

## Scope delivered

- Common query-only retrieval request/interface, configurable budgets, structured
  results, source evidence, operations, model calls, nullable usage, and errors.
- An immutable corpus read efficiently from exact Git objects, with a fingerprint
  covering the commit, origin, discovery policy, and included source identities.
- Language-aware chunking using Tree-sitter where supported, Python AST fallback,
  and recorded line-window fallbacks; source ranges cover complete original lines.
- Actual FAISS normalized-inner-product vector retrieval, immutable index storage,
  provenance/version/checksum checks, and separately retained indexing accounting.
- Deterministic vectorless hierarchy, filename, symbol, keyword, and inspection
  rules without embedding or model calls.
- An iterative tool-calling retrieval agent exposing only five read-only corpus
  tools. Final selections must name evidence actually shown in tool output.
- Configurable OpenAI-compatible HTTP embeddings and Chat Completions clients,
  with no automatic retries or default model/provider selection.
- A replaceable trace sink and local exclusive JSONL artifacts containing request,
  configuration, source/framework identity, operations, evidence, and failures.
- CLI retrieval, index planning/building, configuration examples, tests, and docs.

Answer generation, benchmark execution/scoring, price estimates, adaptive routers,
and statistical comparison remain later phases. No reviewed pilot was fabricated.

## Main changed and created files

Core implementation is in `src/adaptive_rag/retrieval/`: `base.py`, `models.py`,
`corpus.py`, `chunking.py`, `vector.py`, `vectorless.py`, `symbols.py`, `tools.py`,
and `agentic.py`. The package exports are updated in `__init__.py`.

Model transport is in `src/adaptive_rag/generation/client.py`; tracing is in
`src/adaptive_rag/observability/traces.py`. Their package descriptions/exports are
updated. Bulk pinned source reading extends `ingestion/git.py` and its exports.
`cli.py`, `config.py`, the framework version, `pyproject.toml`, `uv.lock`, and
`.gitignore` are updated. The framework version is now `0.2.0`.

New configuration: `configs/retrieval.example.yaml`. Local copies matching
`configs/*.local.yaml` and derived `datasets/indexes/` are ignored by Git.

Tests added: `test_chunking.py`, `test_vector.py`, `test_vectorless.py`,
`test_tools.py`, `test_agentic.py`, `test_model_client.py`, and `test_phase2_cli.py`.
The Phase 1 tests remain in place.

Documentation: updated `README.md`, `datasets/README.md`, `experiments/README.md`;
new `paper/phase2-methodology.md` and this handoff. The Phase 1 handoff remains a
historical record.

## Commands executed

Primary commands, excluding routine source inspection and targeted development
test invocations:

```sh
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv sync --extra dev --extra vector --extra parse
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache UV_PROJECT_ENVIRONMENT=/private/tmp/adaptive-rag-py311 uv sync --extra dev --extra vector --extra parse --frozen --python /usr/local/bin/python3.11
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv run --frozen --extra dev --extra vector --extra parse pytest -q
/private/tmp/adaptive-rag-py311/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv build --offline --out-dir /private/tmp/adaptive-rag-phase2-dist
.venv/bin/adaptive-rag retrieve --config configs/langchain.yaml --strategy vectorless --query 'Where is BaseRetriever defined and how does invoke call document retrieval?' --output experiments/smoke/phase2-vectorless.json --trace experiments/smoke/phase2-vectorless.jsonl
.venv/bin/adaptive-rag index plan --config configs/langchain.yaml --output experiments/smoke/phase2-index-plan.json
```

## Verification

- Python 3.13.9: **229 tests passed**, 110.34 seconds.
- Python 3.11.15: **229 tests passed**, 160.06 seconds.
- Ruff lint, formatting of all 38 Python files, and Git whitespace checks pass.
- Source distribution and wheel `adaptive_rag_research-0.2.0` build successfully.
- Actual FAISS round trips, OpenAI-compatible HTTP parsing, all three CLI paths,
  agent tool histories, raw trace round trips, source pin drift, identity mismatch,
  corruption, malformed responses, missing usage, failed requests, and budget
  boundaries are tested with isolated source repositories and labeled fixtures.
- Review identified and fixed missing vector post-query source verification,
  inconsistent provider identity records, and zero accounting on failures lacking
  usage records. CLI rejects colliding artifacts and writes inside the source
  checkout before any model request. HTTP history is snapshotted so later turns
  cannot change earlier recorded requests.

No live embedding/chat provider was called. Deterministic embedding/chat outputs
exist only in clearly labeled tests. Their outcomes are implementation checks,
not benchmark data or measurements of language-model quality.

## Actual-source smoke artifacts

The LangChain commit remains `ea17e48f0a4336c920394fd029de99f1568b4c38`.
The source policy selects 3,119 files. The saved vectorless smoke completed with
five source excerpts and zero model calls; the leading excerpt is from
`libs/core/langchain_core/retrievers.py`. Raw result and trace are saved in
`experiments/smoke/phase2-vectorless.json` and `.jsonl`.

`experiments/smoke/phase2-index-plan.json` records 9,404 chunks, 20,031,728 UTF-8
input bytes including chunk overlap, and 294 planned embedding calls at batch
size 32 in the current parser environment. These are corpus planning counts,
not provider token counts, API prices, benchmark outcomes, or quality estimates.
Adjust the indexing budget and provider input limits before an actual build.

## Limits and next step

Live provider access and compatibility require user-selected endpoint/model IDs
and, when required, an environment credential. Model-backed CLI commands require
`--allow-api`. Missing usage stays unknown and stops further calls. Byte-based
token admission and elapsed-time checks are conservative/cooperative controls,
not provider-enforced quotas or hard process termination. Native indexes require
trusted local artifacts. Parser and source-selection limits are documented in
`phase2-methodology.md`.

The next implementation phase is Phase 3: consistent answer generation,
no-retrieval comparison, reproducible benchmark execution, reviewed scoring,
complete resource/cost accounting, and uncertainty analysis. The balanced
30-question pilot still requires source-based authoring and independent review
before evaluation. Adaptive routing remains Phase 4. No later phase was started.

# Phase 1 implementation and verification

Date: 2026-11-15. This report describes engineering verification, not retrieval
experiment outcomes. No model calls, benchmark answers, or research conclusions
were generated.

## Delivered

- Python 3.11+ package with a console command and `python -m adaptive_rag` entry point.
- Frozen, versioned Pydantic schemas for snapshots, source manifests, benchmark
  questions, evidence, review provenance, and validation reports.
- Inert YAML loading with unknown-field and duplicate-key rejection. Paths resolve
  relative to the configuration file; full commit pins are mandatory.
- Explicit-commit fetch and detached checkout, origin verification, and strict
  cleanliness checks. Existing checkouts are verified without advancing revisions.
- Deterministic discovery from pinned Git blobs with hierarchy, full-file hashes,
  language hints, and line counts. Inspection artifacts record the complete policy.
- JSONL benchmark auditing with source ranges and excerpt hashes, independent
  review metadata, normalized duplicate detection, and a balanced pilot gate.
- Research protocol, storage conventions, MIT license, and local Git fixture tests.
- Reserved namespaces for later phases; they contain no retrieval, routing,
  generation, or tracing implementation.

## Repository snapshot

URL: <https://github.com/langchain-ai/langchain.git>

Exact commit: `ea17e48f0a4336c920394fd029de99f1568b4c38`.

The checkout is in `datasets/repos/langchain` and is ignored by this framework's
Git repository. `datasets/langchain.snapshot.json` preserves the compact identity
record; `datasets/langchain.manifest.json` records 3,119 eligible files, their
hashes, line counts, and effective policy. A separate fresh scan matched all saved
records. This file count describes the selected corpus, not retrieval quality.

## Files

Updated existing files: `README.md`, `.gitignore`.

Created:

```text
LICENSE
pyproject.toml
uv.lock
configs/langchain.yaml
datasets/README.md
datasets/langchain.snapshot.json
datasets/langchain.manifest.json
benchmarks/README.md
benchmarks/question.schema.json
experiments/README.md
paper/methodology.md
paper/phase1-handoff.md
src/adaptive_rag/__init__.py
src/adaptive_rag/__main__.py
src/adaptive_rag/cli.py
src/adaptive_rag/config.py
src/adaptive_rag/models.py
src/adaptive_rag/ingestion/__init__.py
src/adaptive_rag/ingestion/git.py
src/adaptive_rag/ingestion/models.py
src/adaptive_rag/evaluation/__init__.py
src/adaptive_rag/evaluation/benchmark.py
src/adaptive_rag/evaluation/models.py
src/adaptive_rag/retrieval/__init__.py
src/adaptive_rag/routing/__init__.py
src/adaptive_rag/generation/__init__.py
src/adaptive_rag/observability/__init__.py
tests/test_ingestion.py
tests/test_benchmark.py
tests/test_models.py
tests/test_config.py
tests/test_cli.py
```

The local virtual environment and cloned corpus are intentionally excluded from
version control. No Git commit or publication was made.

## Commands and outcomes

Primary executed commands are below; routine file reads and inspection commands
are omitted. Temporary paths isolate caches, the minimum-version environment,
and build output from unrelated user files.

```sh
git ls-remote https://github.com/langchain-ai/langchain.git HEAD
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv sync --extra dev
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache UV_PROJECT_ENVIRONMENT=/private/tmp/adaptive-rag-py311 uv sync --extra dev --frozen --python /usr/local/bin/python3.11
.venv/bin/adaptive-rag config validate --config configs/langchain.yaml
.venv/bin/adaptive-rag repo snapshot --config configs/langchain.yaml --output datasets/langchain.snapshot.json
.venv/bin/adaptive-rag repo inspect --config configs/langchain.yaml --output datasets/langchain.manifest.json
.venv/bin/adaptive-rag benchmark schema --output benchmarks/question.schema.json
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv run --frozen --extra dev pytest -q
/private/tmp/adaptive-rag-py311/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv build --offline --out-dir /private/tmp/adaptive-rag-phase1-final-dist
```

- Python 3.13.9: **100 passed**, 36.92 seconds.
- Python 3.11.15: **100 passed**, 45.03 seconds.
- Ruff lint passed; all 20 Python files passed formatting checks.
- Git whitespace verification passed.
- Wheel and source distribution built successfully in the temporary output folder.
- The saved JSON Schema matches the current question model; snapshot/manifest
  models validate and agree with the configured repository identity.
- Source reads were checked against an actual pinned LangChain file as well as
  isolated test repositories. Tests include drift, contamination, hidden index
  flags, CRLF checkouts, literal filenames, symlinks, submodules, LFS pointers,
  exclusions, invalid evidence, leakage, review requirements, and split balance.

Initial sandboxed network attempts could not resolve GitHub/PyPI; the authorized
network-enabled retries succeeded. An intermediate suite exposed an unreliable
newline-conversion test fixture. That fixture was corrected to use a fresh clone;
both final complete suites pass. No test failures remain.

## Limits and next step

There is no research benchmark JSONL yet. Structural validation cannot prove an
answer correct, confirm a reviewer's identity, or detect semantic paraphrases and
shared answer facts across splits. Those require independent source/test review.
File exclusions are explicit heuristics and require corpus auditing; non-UTF-8
files, oversized files, submodule contents, and LFS pointers are excluded. Snapshot
support currently requires SHA-1 Git repositories and a clean, complete checkout.

The next data task is to author and independently review 30 questions at the pinned
commit: 10 per category, with five development and five held-out questions per
category. Record provenance and excerpt checksums, freeze the split before tuning,
then run:

```sh
uv run adaptive-rag benchmark validate benchmarks/pilot.jsonl --config configs/langchain.yaml --pilot
```

Phase 2 implementation requires explicit approval. No retrieval comparisons or
scientific performance claims are possible from Phase 1 verification alone.

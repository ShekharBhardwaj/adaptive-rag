# Phase 3 handoff: reproducible baseline evaluation

Phase 3 implements execution and measurement for the fixed Vector, Vectorless,
Agentic, and no-retrieval conditions. This handoff describes implementation
verification, not research findings. Adaptive routers remain Phase 4.

## Delivered

- Shared grounded answer generation with a versioned prompt, identical answer
  settings across conditions, strict JSON, and citations mapped to supplied
  source excerpts. Source validity is separate from semantic support.
- Typed experiment configuration, reviewed-benchmark preflight, frozen source and
  configuration hashes, explicit split selection, repeated jobs, and a seeded
  execution schedule. Ground-truth annotations never enter model requests.
- Append-only raw results and durable per-call request/result/error/interruption
  events. Failures, unknown usage, and missing planned results remain visible.
- Stage and global call, token, elapsed-time, and optional estimated USD budgets.
  No automatic retries, fallback models, index builds, or in-place run resumes.
- Mechanical evidence/citation metrics, independent human review templates and
  score validation, failure-aware summaries, and paired question-cluster
  bootstrap intervals with coverage counts.
- Explicit user-supplied dated prices, separate indexing accounting, environment
  capture, and checks binding derived reports to the complete frozen plan.
- `experiment plan`, `run`, `review-template`, and `summarize` CLI commands;
  `configs/experiment.example.yaml`; and execution/review/methodology documentation.

The main implementation is under `src/adaptive_rag/evaluation/` and
`src/adaptive_rag/generation/`. See [the experiment guide](../experiments/README.md)
for the runnable workflow and [the methodology](phase3-methodology.md) for metric
definitions and limitations.

## Verification

Verification uses local Git repositories, labeled synthetic provider fixtures,
local HTTP transports, and real FAISS indexes with explicitly synthetic test
embeddings. These fixtures verify execution behavior and are not benchmark data.

```sh
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv sync --offline \
  --frozen --extra dev --extra vector --extra parse
.venv/bin/pytest -q
/private/tmp/adaptive-rag-py311/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv build --offline
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv run --frozen --offline \
  adaptive-rag experiment --help
UV_CACHE_DIR=/private/tmp/adaptive-rag-uv-cache uv run --frozen --offline \
  adaptive-rag config validate --config configs/experiment.example.yaml
```

The Python 3.11 interpreter above is a local verification environment; another
researcher should run the same tests in their own Python 3.11+ environment.
Distribution version: **0.3.0**. Source and wheel builds succeed; the wheel contains
the Phase 3 implementation modules. Verification results on 2026-11-15:

- Python 3.13.9: **499 passed** in 133.30 seconds.
- Python 3.11.15: **499 passed** in 172.18 seconds.
- Ruff lint and formatting checks pass for all 58 Python files.
- `git diff --check`, the CLI help check, and example configuration validation pass.

## Researcher inputs and next step

No independently reviewed 30-question LangChain pilot is bundled. No live model
request or comparative answer-quality experiment was run for this implementation.
No result supports or rejects the adaptive retrieval hypothesis yet.

The next execution step is to author and independently review the pilot, configure
actual model identifiers and credentials through environment variables, inspect
and set indexing/run budgets, build the matching vector index separately, and
freeze development settings. Then plan and execute the development baselines,
complete independent answer review, and inspect missing/failure/coverage counts
alongside comparative metrics. Preserve held-out questions for the frozen study.

Phase 4 can implement rule-based and LLM routers after explicit scope approval.
Live compatibility, remote model reproducibility, semantic answer quality, and
provider billing remain unverified by the offline tests. Cooperative limits can
be exceeded by an already-started operation; they are not provider-enforced quotas.

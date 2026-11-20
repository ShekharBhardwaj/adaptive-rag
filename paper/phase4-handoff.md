# Phase 4 handoff: adaptive routing implementation

Phase 4 adds rule-based and LLM adaptive conditions to the common retrieval and
experiment workflow. Both select exactly one of Vector, Vectorless, and Agentic
before retrieving. Fixed baselines and no-retrieval remain available. This is an
implementation handoff, with no comparative research result or accuracy claim.

## Delivered

- Typed annotation-free routing requests, bounded manifest metadata, query-only
  syntactic features, deterministic versioned rules, and a versioned single-call
  LLM prompt with strict selection validation.
- A common adaptive retriever that preserves the adaptive condition, selected
  fixed strategy, complete routing decision, evidence provenance, stage timing,
  model attempts, token usage, and errors. Failed routing has no fallback.
- Separate routing limits within the combined retrieval-stage and global run
  budgets. Routing overhead and failed attempts contribute to total accounting
  and dated user-supplied cost estimates. Missing usage remains unknown.
- Shared answer generation, independent review, failure-aware summaries, and
  paired analysis across fixed and adaptive conditions. Ground-truth annotations
  stay outside routing, retrieval, and answer model inputs.
- `route --router rule|llm` decision inspection and
  `retrieve --strategy adaptive_rule|adaptive_llm` evidence retrieval; both use
  fresh immutable output paths. Adaptive retrieval validates all three candidates
  and the compatible vector index before a routing request can be sent.
- [Adaptive configuration example](../configs/adaptive.example.yaml),
  [runnable workflow](../README.md), and
  [Phase 4 methodology](phase4-methodology.md).

Routing lives in `src/adaptive_rag/routing/`; the shared retrieval adapter is
`src/adaptive_rag/retrieval/adaptive.py`. The experiment runner retains the
original frozen-plan and raw-event workflow. The implementation introduces no
new runtime dependencies or provider credentials.

## Verification and study boundary

Verification uses isolated synthetic source repositories, explicit synthetic
provider responses, local HTTP transports, and synthetic embedding indexes.
Tests cover route-only execution, API opt-in, explicit routing-model selection,
immutable artifacts, invalid selection preservation, index preflight before
paid routing, and adaptive evidence/trace integration, as well as routing and
experiment accounting contracts.

```sh
.venv/bin/pytest -q tests/test_phase4_cli.py tests/test_phase2_cli.py tests/test_experiment_cli.py
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/adaptive-rag config validate --config configs/adaptive.example.yaml
.venv/bin/adaptive-rag route --help
git diff --check
```

The recovery-enabled integrated suite passed 734 tests on Python 3.13. Five
additional lineage-tampering cases then passed in the 27-test recovery/journal
subset; the current collection contains 739 tests. Ruff lint/format checks and
wheel/source-distribution builds also passed.
Routing and runner tests cover shared budgets, failure accounting, frozen inputs,
and analysis behavior. The dated verification record is
`experiments/preflight/phase4-2026-11-16/recovery-verification.json`.
An exact source/test/lockfile archive and its digest are retained beside it while
the framework working tree remains uncommitted.
Offline fixtures establish execution contracts, not
semantic router quality, answer correctness, endpoint compatibility, remote
weight reproducibility, or provider billing behavior.

Bounded live compatibility checks have exercised the configured embedding and
chat endpoints using synthetic queries and evidence. Their raw calls, failures,
known token usage, and estimated costs are retained under
`experiments/preflight/phase4-2026-11-16/`. Compatibility checks are not comparative
benchmark results. The full index and development comparison are separate stages.
The successful compatibility gate is `live-compatibility-008/summary.json`;
earlier failed attempts remain alongside it. The final native-tool probe uses an
explicit two-step synthetic instruction to test transport and finalization.
It does not measure navigation quality.

The first live index build stopped on HTTP 429 after 541 successful batches.
Explicit recovery can reuse only a fully verified successful prefix into a new
directory, with source artifact hashes and failed-parent accounting retained.
Its successful-call usage is distinct from complete construction cost: the
earlier failed request has unknown usage. Recovery does not overwrite the failed
build or silently retry model calls. See `recovery-plan.json` beside the dated
verification record for the actual build and pacing plan.

The agent responsible for routing policy design received no benchmark questions,
reference answers, gold evidence, or review packets. Existing benchmark artifacts
and split assignments were not changed. Generic rules and prompts have not been
tuned to pilot strategy outcomes. Preserve that boundary for held-out use.

## Researcher execution

Configure actual endpoint/model identifiers and credentials through environment
variables, build a compatible index separately, and inspect the adaptive plan.
Freeze policies, prompt versions, models, budgets, split, repetitions, prices,
and analysis settings before the comparison. The example selects development
only and includes all six conditions. A rule-only decision can be inspected
without model settings; full adaptive retrieval requires compatible candidates
and explicit `--allow-api` because any selectable strategy can use a model.

After execution, complete independent answer review and report planned workload,
failures, missing outputs, review coverage, selected-strategy distribution,
routing overhead, and complete job totals. Keep index construction and shared
preparation visible, state reuse/amortization assumptions, and preserve null or
negative findings. An observed selection is not a gold optimal-strategy label.

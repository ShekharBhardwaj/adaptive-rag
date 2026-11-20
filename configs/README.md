# Configuration examples

The generic `retrieval.example.yaml`, `experiment.example.yaml`, and
`adaptive.example.yaml` contain placeholder model IDs. The new portable examples
below preserve the model identities and settings of the reviewed local study
profiles, with environment-variable names for credentials and paths relative to
the YAML file:

| Portable example | Settings represented |
| --- | --- |
| `adaptive.anthropic.example.yaml` | Six development conditions: Vector, Vectorless, Agentic, no retrieval, rule routing, and LLM routing; three repetitions. |
| `adaptive.cascade.development.example.yaml` | Five development conditions: Vector, Agentic, Agentic wrap-up, adaptive cascade, and no retrieval; three repetitions and shared evidence-sufficiency reporting. |
| `adaptive.cascade.heldout.example.yaml` | Held-out profile matching the cascade development settings except for the split. |

These are new portable examples, not replacements for the original hash-bound
study configs. Their new comments change their file hashes. Existing experiment
metadata and frozen inputs continue to refer to the original local files:
`adaptive.anthropic.final.local.yaml`,
`adaptive.cascade.development.final.local.yaml`, and
`adaptive.cascade.heldout.proposed.local.yaml` (historical filename). Preserve those
files and existing run lineage; use fresh output directories for new runs. See the
[held-out protocol](../paper/phase7-held-out-protocol.md) for the study design.

## Create a local copy

Run from the repository root, using a fresh destination filename. Keep copies in
`configs/` so the relative paths continue to resolve correctly:

```sh
cp -n .env.example .env
cp -n configs/adaptive.anthropic.example.yaml configs/adaptive.anthropic.portable.local.yaml
cp -n configs/adaptive.cascade.development.example.yaml configs/adaptive.cascade.development.portable.local.yaml
cp -n configs/adaptive.cascade.heldout.example.yaml configs/adaptive.cascade.heldout.portable.local.yaml
```

`cp -n` preserves existing destination files, including any credentials in `.env`.

`.env` and `configs/*.local.yaml` are ignored by Git. Supply your own credentials
in your local environment or `.env`: `OPENROUTER_API_KEY` for Qwen embeddings and
`ANTHROPIC_API_KEY` for Anthropic chat. The framework does not automatically load
`.env`; load it explicitly for provider commands, for example
with `uv run --env-file .env`. Never put credential values in YAML or commit them.

The examples retain `qwen/qwen3-embedding-8b` at
`https://openrouter.ai/api/v1` and `claude-haiku-4-5-20251001` at
`https://api.anthropic.com/v1`. The latter serves answers, navigation, and routing.
The settings describe the study configuration; validate endpoint compatibility,
availability, and your account limits before a new run.

Copying, editing, or validating a config does not start model requests. Provider
commands require explicit `--allow-api` and may incur charges.

## Local validation and prerequisites

With the environment installed as described in the [project README](../README.md),
these commands only parse and validate the strict `FoundationConfig` schema;
they make no provider calls and do not require credentials or an index:

```sh
uv run --frozen adaptive-rag config validate --config configs/adaptive.anthropic.example.yaml
uv run --frozen adaptive-rag config validate --config configs/adaptive.cascade.development.example.yaml
uv run --frozen adaptive-rag config validate --config configs/adaptive.cascade.heldout.example.yaml
```

Schema validation does not verify that the repository checkout or vector index
exists or that an endpoint works. Model-free
index/experiment planning is a separate operation with corpus/index prerequisites.

All examples pin LangChain commit
`ea17e48f0a4336c920394fd029de99f1568b4c38` and use:

- `../datasets/repos/langchain` for the clean pinned repository checkout;
- `../benchmarks/pilot.jsonl` for the frozen reviewed benchmark;
- `../datasets/indexes/langchain-openrouter-qwen3-phase4-002` for the compatible
  completed Qwen vector index;
- [the dated 2026-11-16 price schedule](../experiments/preflight/anthropic-development-2026-11-16-001/prices.json)
  for the original admission estimates.

The repository checkout and vector index are local prerequisites, ignored by Git;
a clone of this project does not contain them. Obtain a trusted compatible index
archive and verify its manifest/checksums and study provenance, or plan a fresh
build. A completed index includes `manifest.json`,
`chunks.json`, and `index.faiss`; preserve its journal and any reuse lineage when
archiving it. An archive must match the pinned corpus, discovery policy, embedding
endpoint/model, chunking, parser/runtime, and dimensions. A fresh build is a new
artifact and may make billable embedding requests; it is not automatically a
replacement for the original study index. Review the model-free `index plan`
before `index build --allow-api`, use a fresh output directory, and
set `experiment.vector_index` in your local copy to that completed directory.
See [index identity and storage](../datasets/README.md#retrieval-corpus-and-vector-indexes)
and [index accounting](../experiments/README.md#token-time-and-price-accounting).

The price schedule is a historical estimate dated 2026-11-16, not current pricing
or an invoice. The copied run budgets, request pacing, and `reserve` policy are
recorded settings: unknown actual usage remains unknown, while reservations govern
admission of later jobs. Reusing these estimates does not guarantee cost, provider
quotas, or successful execution. Changes to paths or settings create a new config
identity; preserve the originals and existing frozen artifacts.

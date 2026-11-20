# Benchmark authoring and validation

The benchmark is evidence about a fixed snapshot, not generated answer text.
The 30-question [reviewed pilot](pilot.jsonl) is frozen after Shekhar's
source-inspection acceptance of all annotations. Its [freeze manifest](pilot.freeze.json)
records the dataset and annotation hashes, fixed split, source identity,
strict validation, review provenance, and software environment.

The [completed source-linked review packet](review/README.md) preserves the
human decisions and separately labeled AI cross-check. `pilot.draft.jsonl` retains
the final authoring record and is byte-identical to the frozen evaluation input.
Use `pilot.jsonl` for experiments. Preserve the frozen files; future annotation or
split changes require a new benchmark version and renewed validation.

## Pilot design

Author 30 questions against the commit in `configs/langchain.yaml`:

| Category | Development | Held out | Total |
| --- | ---: | ---: | ---: |
| `conceptual` | 5 | 5 | 10 |
| `structural` | 5 | 5 | 10 |
| `cross_file` | 5 | 5 | 10 |
| Total | 15 | 15 | 30 |

Conceptual questions ask about behavior, responsibilities, or design in the source.
Structural questions ask where a symbol lives or how an implementation is organized.
Cross-file questions connect evidence across files. Assign categories by reasoning
required, not by which strategy should win. Structural questions need not favor
vectorless retrieval.

Freeze IDs, categories, answers, evidence, difficulty, and split before tuning.
Keep related or near-duplicate questions in the same split. Held-out answers and
labels must not enter router features, prompts, examples, or development choices.
Later infrastructure must enforce this; Phase 1 validation cannot do so alone.

## Record format

Store one JSON object per line in `benchmarks/pilot.jsonl`. Generate the
authoritative schema from the installed models:

```sh
uv run adaptive-rag benchmark schema --output /tmp/benchmark-question.schema.json
```

Output files are created exclusively, so use a fresh path on subsequent exports.
Each record contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Schema version, currently the string `"1"`. |
| `id` | Stable, unique question identifier. |
| `question` | The repository question. |
| `category` | `conceptual`, `structural`, or `cross_file`. |
| `ground_truth_answer` | An answer verified from source or a reproducible test. |
| `evidence` | References containing `path`, `start_line`, `end_line`, `excerpt_sha256`. |
| `repo_commit` | The full commit SHA of the snapshot. |
| `provenance` | Author identity, timestamp, method, notes, and review. |
| `difficulty` | `easy`, `medium`, or `hard`, assigned with a documented rationale. |
| `split` | `development` or `held_out`, assigned before tuning. |

Evidence paths are relative to the snapshot root and refer to included source.
Line ranges are inclusive and one-based. Compute `excerpt_sha256` using
`sha256("\n".join(text.splitlines()[start_line - 1:end_line]).encode("utf-8"))`, with no
added trailing newline. Cross-file questions should cite the files needed for the
reasoning.

`provenance` contains `author`, `created_at`, `method`, `notes`, and `review`.
Authoring `method` is `source_inspection` or `executable_test`. A review records
`reviewer`, `reviewed_at`, `method`, and `notes`, with a reviewer distinct from the
author. Use timezone-aware timestamps. Notes explain verification; for tests,
record the command, environment, and observed behavior. Review may be absent
during authoring, but is required for the evaluation-ready pilot.

## Independent ground-truth workflow

1. Inspect the pinned snapshot and manifest. Confirm candidate evidence is included.
2. Formulate questions from source or executable checks. Record answers, ranges,
   hashes, difficulty rationale, and provenance. Check any LLM suggestion against
   source; it is never sufficient evidence by itself.
3. Assign the balanced split before tuning. Avoid shared answer facts across splits.
4. Have another reviewer inspect the exact commit and verify answers, source
   ranges, completeness of evidence, category, and ambiguity. Correct or reject
   unsupported questions and record the review.
5. Resolve mechanical validation errors, then freeze and version the pilot with
   the snapshot, policy, schema, and software revision.

During authoring, checks may run with pending review:

```sh
uv run adaptive-rag benchmark validate benchmarks/pilot.jsonl --config configs/langchain.yaml --allow-unreviewed
```

Before evaluation, require the complete reviewed and balanced pilot:

```sh
uv run adaptive-rag benchmark validate benchmarks/pilot.jsonl --config configs/langchain.yaml --pilot
```

The validator emits JSON and exits `0` on success or `2` on invalid data. Checks
cover typed records, duplicate IDs, commit consistency, file inclusion, ranges,
excerpt hashes, and review metadata. Pilot validation also checks category/split
balance. `--allow-unreviewed` is an authoring option, not independent review or
permission to evaluate unfinished data.

Source checks cannot prove semantic truth, reviewer identity, independence, or
freedom from leakage. Reviewers must inspect whether citations support claims.
Public content may occur in model pretraining; compare against no retrieval and
record that risk. Thirty questions support feasibility checks and failure discovery,
not broad claims or well-powered subgroup comparisons.

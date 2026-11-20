# Repository snapshots

The first corpus is [LangChain](https://github.com/langchain-ai/langchain). Its URL
does not identify a reproducible corpus: `configs/langchain.yaml` must also contain
the exact 40-character Git commit SHA. Never substitute the current default branch
when a configured commit is missing or unavailable.

`datasets/repos/langchain/` is the local checkout, ignored by Git.
`datasets/langchain.snapshot.json` records the selected snapshot. Generate a full
manifest using the same configuration:

```sh
uv run adaptive-rag repo snapshot --config configs/langchain.yaml
uv run adaptive-rag repo inspect --config configs/langchain.yaml --output /tmp/langchain.manifest.json
```

Choose a new output path if a manifest already exists; output files are not
overwritten. Snapshot setup and inspection verify the configured commit. Treat the
checkout as research input. Verification rejects tracked edits, untracked files,
and ignored files inside the clone, as well as sparse checkouts and index flags
that could hide changes. Keep test environments and verification artifacts outside
the snapshot checkout. Retain the configuration, commit record, file hashes,
and software revision with each future experiment. To study a newer commit, create
a separately identified snapshot, recheck evidence, and label results accordingly.

## File discovery policy

The YAML policy defines the corpus using `include_globs`, `exclude_globs`, and
`max_file_bytes`. Discovery preserves relative paths and folder hierarchy and
records line counts and hashes. Evidence uses inclusive one-based line ranges.
Repository metadata, generated files, binaries, vendored code, irrelevant build
artifacts, credential-like paths, and oversized files are excluded according to
policy. Source bytes and file hashes come from Git blobs at the pinned commit,
so local newline-conversion settings do not change the recorded corpus.

Review included and omitted files before authoring questions. An extension
allowlist and path exclusions are operational choices, not proof of irrelevance.
A question may become unanswerable if evidence is excluded; source selection can
also favor one retrieval method. Record policy changes and regenerate the
manifest. All compared systems must receive the same included corpus.

Do not follow symlinks outside the repository or use `.git` metadata as evidence.
Discovery does not execute corpus code. Executable verification of an answer is a
separate authoring action with a documented environment.

## Evidence checksums

An excerpt checksum is SHA-256 over decoded source lines joined with `\n`, without
an added trailing newline:

```python
excerpt = "\n".join(text.splitlines()[start_line - 1 : end_line])
excerpt_sha256 = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
```

This differs from a whole-file byte hash. Hash the exact Git source and range, not
a rendered web page, edited copy, or checkout modified by Git content filters.
Mechanical checks detect mismatched references;
a reviewer must determine whether those lines support the answer.

The reviewed 30-question pilot, source-linked review history and frozen split are
included under [../benchmarks/](../benchmarks/README.md). Existing study metadata
and score records are versioned separately from the large execution artifacts;
see the [artifact guide](../docs/research-artifacts.md) for their availability and
checksum inventory. Preserve the frozen annotations when studying this snapshot.

## Retrieval corpus and vector indexes

All Phase 2 strategies use a `RepositoryCorpus` containing the same included Git
blobs, source policy, commit, and deterministic fingerprint. Changing file
selection changes this identity even when the repository commit remains the
same. Rebuild or separately identify derived artifacts after any corpus change.

Vector indexing is optional and requires the `vector` extra plus an explicitly
configured embedding provider. `adaptive-rag index plan --config ...` performs
model-free chunk planning before construction. The `parse` extra enables
Tree-sitter boundaries for supported languages. Parser availability and settings
are part of index identity; use a consistent environment across planning,
building, and querying.

Keep each immutable index outside `datasets/repos/langchain/`, for example under
`datasets/indexes/<index-id>/`. A successful index contains `manifest.json`,
`chunks.json`, and `index.faiss`. Its manifest pins corpus, embedding identity,
chunk/parser/runtime settings, checksums, dimensions, and separate indexing
usage/latency. Failure records remain in a fresh build directory as
`build-failure.json`; use a new directory to retry. Never relabel an old index as
belonging to a new snapshot, provider, model, or discovery policy.

Only load trusted local FAISS artifacts. Checksums detect corruption but cannot
authenticate a maliciously replaced index and manifest. Chunk source references
are mechanically verified against the corpus; their relevance still requires
evaluation. See [Phase 2 methodology](../paper/phase2-methodology.md).

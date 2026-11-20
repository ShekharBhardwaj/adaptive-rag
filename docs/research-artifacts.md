# Research artifact preservation

The small [artifact inventory](../experiments/artifact-inventory.json) records
repository-relative paths, byte sizes, and SHA-256 digests for 19 immutable local
files: 15 raw run files and the four files in
`datasets/indexes/langchain-openrouter-qwen3-phase4-002/`. The inventory contains
metadata only. It does not summarize answers, scores, or experimental comparisons.

No archive has been uploaded or provided yet. The immutable artifact bytes remain
local; there is no download URL to supply. A Git checkout with this inventory is
therefore not a complete copy of the research evidence. Keep these large files
outside ordinary Git and retain their local copies until a separate archive has
been created and verified.

## Verify local or restored artifacts

From the repository root, use the standard-library verifier:

```sh
python3 scripts/research_artifacts.py
```

It streams each file in bounded blocks, compares size and whole-file SHA-256, and
prints counts only. It never parses artifact contents, runs models, computes
research results, accesses the network, writes files, extracts archives, or deletes
anything. Exit status is zero only when all listed artifacts verify. Missing,
unreadable, changed, or mismatched files and invalid inventory entries produce a
nonzero exit status. Hashing the multi-gigabyte collection can take time.

Both locations can be set explicitly. A relative `--inventory` is resolved under
`--root`; the default root is the repository containing the script.

```sh
python3 scripts/research_artifacts.py --root /path/to/adaptive-rag --inventory experiments/artifact-inventory.json
```

The verifier intentionally reports no artifact contents. Inspect the inventory's
path list to identify the files that need to be present.

## Restore the original bytes

Obtain the original artifacts from the research custodian or a future separately
published archive. Restore every file to its exact inventory path under the
repository root:

- `datasets/indexes/langchain-openrouter-qwen3-phase4-002/` must contain
  `build-summary.json`, `chunks.json`, `index.faiss`, and `manifest.json`.
- Each of these five `experiments/raw/` directories must contain `events.jsonl`,
  `index-manifest.json`, and `results.jsonl`:
  `adaptive-anthropic-development-20261116-001`,
  `adaptive-anthropic-paced-development-20261117-001`,
  `adaptive-cascade-development-20261119-001`,
  `adaptive-cascade-heldout-20261119-001`, and
  `adaptive-development-20261116-001`.

Preserve the other committed run metadata alongside these restored files. Run the
verifier before using the artifacts for research reruns or reanalysis. Restore the
original index as a complete unit; keep its manifest, chunks, FAISS bytes, and build
summary together. Rebuilding an index or making new provider calls produces a new
artifact and cannot substitute for restoration of historical evidence. Use a
separately identified destination for new runs.

The source is `https://github.com/langchain-ai/langchain.git` at commit
`ea17e48f0a4336c920394fd029de99f1568b4c38`, as recorded by
[the snapshot record](../datasets/langchain.snapshot.json) and
[the source configuration](../configs/langchain.yaml). Restore that exact source
snapshot at `datasets/repos/langchain/` using the
[repository snapshot instructions](../datasets/README.md). Preserve the recorded
source discovery policy, corpus fingerprint, embedding identity, parser settings,
and index checksums. Do not substitute a different source revision or relabel an
index as belonging to a different source, model, or policy.

## Publish a separate archive

1. Verify all 19 local files against the committed inventory before packaging.
2. Package the exact bytes with their repository-relative paths, the inventory,
   and [the retained LangChain MIT notice](../experiments/SOURCE-LICENSE.txt).
   Use an archive format and host that support the total size and the individual
   manifest sizes. Preserve the run metadata needed to interpret the files.
3. Upload that archive to a stable research artifact host outside ordinary Git.
   Record its actual persistent identifier or download URL, archive byte size,
   archive SHA-256, and the repository revision it accompanies. No such archive
   location is currently available.
4. Restore a copy into a separate location and run the verifier with `--root`
   pointing to that location and `--inventory` pointing to the committed inventory.
   Confirm all 19 files verify before announcing availability or removing any
   local preservation copy.
5. Update this document and the inventory's `archive_status` only after the upload
   and verification succeed. Retain the existing per-file paths, sizes, and hashes
   unchanged. Publish the small inventory and instructions with the code.

The source license notice was copied unchanged from the pinned LangChain checkout.
Keep that copyright and MIT permission notice with published source excerpts and
derived evidence containing substantial portions of the source. The retained
notice identifies the upstream source license; it does not assign a license to the
research project's original code or establish rights for unrelated material.

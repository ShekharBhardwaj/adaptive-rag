"""Pinned Git snapshots and deterministic discovery without executing repo code."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from .models import (
    DiscoveryPolicy,
    RepositorySnapshot,
    SourceFile,
    validate_commit_sha,
    validate_source_path,
)

GIT_TIMEOUT_SECONDS = 60
FETCH_TIMEOUT_SECONDS = 300
_BLOB_BATCH_BYTES = 16 * 1024 * 1024


class IngestionError(ValueError):
    """Repository ingestion could not produce trustworthy evidence."""


class SnapshotVerificationError(IngestionError):
    """The repository does not match a clean, explicitly pinned snapshot."""


def _git(
    repository: Path,
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    timeout: int = GIT_TIMEOUT_SECONDS,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> bytes:
    # Ambient Git variables can redirect an otherwise explicit -C invocation.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"})
    command = [
        "git",
        "--no-replace-objects",
        "--literal-pathspecs",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "protocol.ext.allow=never",
        "-C",
        str(repository),
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            input=input_bytes,
            capture_output=True,
            env=environment,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IngestionError(f"Git {arguments[0]} could not complete: {error}") from error
    if result.returncode not in allowed_returncodes:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:2000]
        raise IngestionError(f"Git {arguments[0]} failed (exit {result.returncode}): {detail}")
    return result.stdout


def _repository_root(repository: Path) -> Path:
    root = Path(repository).expanduser().resolve()
    if not root.is_dir():
        raise SnapshotVerificationError(f"repository is not a directory: {root}")
    try:
        actual = _git(root, ["rev-parse", "--show-toplevel"]).decode("utf-8").rstrip("\n")
        if Path(actual).resolve() != root:
            raise SnapshotVerificationError("repository must be the exact Git working-tree root")
        if _git(root, ["rev-parse", "--is-bare-repository"]).strip() != b"false":
            raise SnapshotVerificationError("a non-bare Git working tree is required")
    except IngestionError as error:
        raise SnapshotVerificationError(str(error)) from error
    return root


def _head_commit(repository: Path) -> str:
    try:
        return validate_commit_sha(
            _git(repository, ["rev-parse", "--verify", "HEAD^{commit}"]).decode("ascii").strip()
        )
    except (IngestionError, ValueError) as error:
        raise SnapshotVerificationError(
            "repository must have a SHA-1 commit checked out"
        ) from error


def _require_clean(repository: Path) -> None:
    for setting in ("core.sparseCheckout", "index.sparse"):
        enabled = _git(
            repository, ["config", "--bool", "--get", setting], allowed_returncodes=(0, 1)
        ).strip()
        if enabled == b"true":
            raise SnapshotVerificationError("sparse checkouts and sparse indexes are not supported")
    indexed = _git(repository, ["ls-files", "-v", "-z"])
    for record in indexed.split(b"\0"):
        if record and (record[:1] == b"S" or record[:1].islower()):
            raise SnapshotVerificationError(
                "index skip-worktree/assume-unchanged flags can hide modifications "
                "and are forbidden"
            )
    status = _git(
        repository,
        [
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
            "--ignore-submodules=none",
        ],
    )
    if status:
        raise SnapshotVerificationError(
            "repository must be clean: tracked modifications and untracked/ignored "
            "files are forbidden"
        )


def _snapshot(repository: Path, commit_sha: str) -> RepositorySnapshot:
    origin = _git(repository, ["remote", "get-url", "origin"], allowed_returncodes=(0, 2))
    url = origin.decode("utf-8").strip() or repository.as_uri()
    return RepositorySnapshot(url=url, commit_sha=commit_sha, captured_at=datetime.now(UTC))


def verify_snapshot(repository: Path, expected_commit: str) -> RepositorySnapshot:
    """Require a clean complete checkout at an exact, full commit SHA.

    Ignored files count as contamination too. This function neither fetches nor
    checks out a different revision. Local repositories without an origin use
    their absolute file URI as their provenance URL.
    """
    try:
        validate_commit_sha(expected_commit)
    except ValueError as error:
        raise SnapshotVerificationError(str(error)) from error
    root = _repository_root(repository)
    actual = _head_commit(root)
    if actual != expected_commit:
        raise SnapshotVerificationError(
            f"commit mismatch: expected {expected_commit}, found {actual}"
        )
    _require_clean(root)
    return _snapshot(root, actual)


def create_snapshot(repository: Path, expected_commit: str | None = None) -> RepositorySnapshot:
    """Record a first explicit pin, or verify a previously recorded pin."""
    if expected_commit is not None:
        return verify_snapshot(repository, expected_commit)
    root = _repository_root(repository)
    return verify_snapshot(root, _head_commit(root))


def clone_snapshot(url: str, destination: Path, commit_sha: str) -> RepositorySnapshot:
    """Fetch and detach at only the requested commit, refusing nonempty targets.

    A failed checkout remains on disk for inspection; subsequent attempts must
    use a fresh directory. Fetches have a bounded five-minute timeout.
    """
    validate_commit_sha(commit_sha)
    if not isinstance(url, str) or not url.strip() or "\0" in url:
        raise IngestionError("url must be a nonempty Git repository URL or local path")
    target = Path(destination).expanduser().resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise IngestionError(f"destination must be absent or empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    _git(target, ["init", "--quiet", "--template="])
    _git(target, ["config", "core.autocrlf", "false"])
    _git(target, ["remote", "add", "--", "origin", url])
    _git(
        target,
        ["fetch", "--quiet", "--no-tags", "--depth=1", "origin", commit_sha],
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    _git(target, ["checkout", "--quiet", "--detach", commit_sha])
    return verify_snapshot(target, commit_sha)


def _matches_glob(path: str, pattern: str) -> bool:
    path_parts, pattern_parts = path.split("/"), pattern.split("/")

    @cache
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        if pattern_parts[pattern_index] == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts) and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], pattern_parts[pattern_index])
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def _decode_source(content: bytes) -> str | None:
    if b"\0" in content:
        return None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(character) < 32 and character not in "\t\n\r\f" for character in text):
        return None
    if text.startswith("version https://git-lfs.github.com/spec/v1\n") or text.startswith(
        "version https://git-lfs.github.com/spec/v1\r\n"
    ):
        return None
    header = "\n".join(text.splitlines()[:8]).lower()
    if re.search(r"\b(?:auto[- ]?generated|generated|codegen)\b", header) and (
        "do not edit" in header or "do not modify" in header
    ):
        return None
    return text


_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".json": "json",
    ".jsonl": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".proto": "protobuf",
    ".r": "r",
    ".jl": "julia",
}


def _read_blob_batch(repository: Path, entries: list[tuple[str, str, int]]) -> list[bytes]:
    output = _git(
        repository,
        ["cat-file", "--batch"],
        input_bytes="".join(f"{object_id}\n" for _, object_id, _ in entries).encode("ascii"),
    )
    position = 0
    blobs: list[bytes] = []
    for _, expected_id, expected_size in entries:
        end = output.find(b"\n", position)
        if end < 0:
            raise IngestionError("Git returned a truncated blob batch")
        header = output[position:end].split()
        if header != [expected_id.encode("ascii"), b"blob", str(expected_size).encode("ascii")]:
            raise IngestionError("Git blob metadata differs from the pinned tree")
        position = end + 1
        content = output[position : position + expected_size]
        if (
            len(content) != expected_size
            or output[position + expected_size : position + expected_size + 1] != b"\n"
        ):
            raise IngestionError("Git returned incomplete blob contents")
        blobs.append(content)
        position += expected_size + 1
    if position != len(output):
        raise IngestionError("Git returned unexpected data after the blob batch")
    return blobs


def discover_files(
    repository: Path,
    policy: DiscoveryPolicy | None = None,
    *,
    expected_commit: str | None = None,
) -> list[SourceFile]:
    """Return sorted tracked UTF-8 source records from authoritative Git blobs.

    Paths retain the repository hierarchy. Symlinks, gitlinks, binaries, LFS
    pointers, generated headers, oversized files, and configured globs are
    excluded. Revalidate the checkout after reading to detect concurrent edits.
    """
    policy = policy if policy is not None else DiscoveryPolicy()
    snapshot = create_snapshot(repository, expected_commit=expected_commit)
    root = Path(repository).expanduser().resolve()
    tree = _git(root, ["ls-tree", "-r", "-l", "-z", "--full-tree", snapshot.commit_sha])
    entries: list[tuple[str, str, int]] = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, object_id, raw_size = metadata.split()
        if mode not in (b"100644", b"100755") or object_type != b"blob":
            continue
        try:
            path = validate_source_path(raw_path.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise IngestionError(
                "tracked file paths must be safe normalized UTF-8 POSIX paths"
            ) from error
        size = int(raw_size)
        if (
            size > policy.max_file_bytes
            or not any(_matches_glob(path, pattern) for pattern in policy.include_globs)
            or any(_matches_glob(path, pattern) for pattern in policy.exclude_globs)
        ):
            continue
        entries.append((path, object_id.decode("ascii"), size))
    entries.sort(key=lambda entry: entry[0])
    files: list[SourceFile] = []
    batch: list[tuple[str, str, int]] = []
    batch_size = 0

    def collect(current: list[tuple[str, str, int]]) -> None:
        for (path, _, size), content in zip(current, _read_blob_batch(root, current), strict=True):
            text = _decode_source(content)
            if text is not None:
                files.append(
                    SourceFile(
                        path=path,
                        sha256=hashlib.sha256(content).hexdigest(),
                        size_bytes=size,
                        line_count=len(text.splitlines()),
                        language=_LANGUAGES.get(Path(path).suffix.lower()),
                    )
                )

    for entry in entries:
        if batch and batch_size + entry[2] > _BLOB_BATCH_BYTES:
            collect(batch)
            batch, batch_size = [], 0
        batch.append(entry)
        batch_size += entry[2]
    if batch:
        collect(batch)
    verify_snapshot(root, snapshot.commit_sha)
    return files


def read_source_files(
    repository: Path, sources: Sequence[SourceFile], expected_commit: str
) -> dict[str, str]:
    """Bulk-read a discovered manifest from verified blobs without per-file Git processes."""
    root = Path(repository).resolve()
    verify_snapshot(root, expected_commit)
    selected = {source.path: source for source in sources}
    if len(selected) != len(sources):
        raise IngestionError("source manifest contains duplicate paths")
    tree = _git(root, ["ls-tree", "-r", "-l", "-z", "--full-tree", expected_commit])
    entries = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if path not in selected:
            continue
        mode, kind, object_id, size = metadata.split()
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise IngestionError(f"manifest path is not a regular Git blob: {path}")
        if int(size) != selected[path].size_bytes:
            raise IngestionError(f"source size does not match the pinned manifest: {path}")
        entries.append((path, object_id.decode("ascii"), int(size)))
    if {entry[0] for entry in entries} != set(selected):
        raise IngestionError("source manifest includes paths absent from the pinned tree")
    texts: dict[str, str] = {}
    batch: list[tuple[str, str, int]] = []
    batch_size = 0

    def collect() -> None:
        for (path, _, _), content in zip(batch, _read_blob_batch(root, batch), strict=True):
            text = _decode_source(content)
            if text is None or hashlib.sha256(content).hexdigest() != selected[path].sha256:
                raise IngestionError(f"source does not match the pinned text manifest: {path}")
            texts[path] = text

    for entry in entries:
        if batch and batch_size + entry[2] > _BLOB_BATCH_BYTES:
            collect()
            batch, batch_size = [], 0
        batch.append(entry)
        batch_size += entry[2]
    if batch:
        collect()
    verify_snapshot(root, expected_commit)
    return texts


def read_source_file(repository: Path, path: str, expected_commit: str) -> str:
    """Read exact UTF-8 Git bytes for a safe path at a verified commit.

    Callers should first use discover_files to enforce their discovery policy.
    This helper also refuses symlinks, submodules, binary/generated files, and
    LFS pointers, but does not apply globs or a configurable file size cap.
    """
    validate_source_path(path)
    snapshot = verify_snapshot(repository, expected_commit)
    root = Path(repository).expanduser().resolve()
    tree = _git(root, ["ls-tree", "-z", snapshot.commit_sha, "--", path])
    records = [record for record in tree.split(b"\0") if record]
    if len(records) != 1:
        raise IngestionError(f"path is not a single tracked source file: {path}")
    metadata, raw_path = records[0].split(b"\t", 1)
    mode, object_type, object_id = metadata.split()
    if (
        raw_path != path.encode("utf-8")
        or mode not in (b"100644", b"100755")
        or object_type != b"blob"
    ):
        raise IngestionError(f"path is not a tracked regular file: {path}")
    content = _git(root, ["cat-file", "blob", object_id.decode("ascii")])
    text = _decode_source(content)
    if text is None:
        raise IngestionError(f"path is not eligible UTF-8 source text: {path}")
    verify_snapshot(root, expected_commit)
    return text

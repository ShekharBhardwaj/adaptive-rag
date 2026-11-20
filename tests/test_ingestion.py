from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptive_rag.ingestion import (
    DiscoveryPolicy,
    IngestionError,
    RepositorySnapshot,
    SnapshotManifest,
    SnapshotVerificationError,
    SourceFile,
    clone_snapshot,
    create_snapshot,
    discover_files,
    read_source_file,
    verify_snapshot,
)


def git(repository: Path, *arguments: str) -> str:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    ).stdout.strip()


def commit(repository: Path) -> str:
    git(repository, "add", "--all")
    git(repository, "commit", "--quiet", "-m", "fixture")
    return git(repository, "rev-parse", "HEAD")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "upstream"
    root.mkdir()
    git(root, "init", "--quiet", "--template=")
    git(root, "config", "user.name", "Test Researcher")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    commit(root)
    return root


def test_snapshot_records_commit_origin_and_aware_timestamp(repository: Path) -> None:
    sha = git(repository, "rev-parse", "HEAD")
    snapshot = create_snapshot(repository)
    assert snapshot.commit_sha == sha
    assert snapshot.url == repository.as_uri()
    assert snapshot.captured_at.utcoffset() is not None
    git(repository, "remote", "add", "origin", "https://example.invalid/research.git")
    assert verify_snapshot(repository, sha).url == "https://example.invalid/research.git"


@pytest.mark.parametrize("pin", ["HEAD", "main", "abcdef0", "a" * 39, "A" * 40, "g" * 40])
def test_verification_requires_exact_full_sha(repository: Path, pin: str) -> None:
    with pytest.raises(SnapshotVerificationError, match="40 lowercase"):
        verify_snapshot(repository, pin)


def test_verification_refuses_switching_pins_or_subdirectory_roots(repository: Path) -> None:
    original = create_snapshot(repository)
    (repository / "next.txt").write_text("second\n", encoding="utf-8")
    current = commit(repository)
    with pytest.raises(SnapshotVerificationError, match="commit mismatch"):
        verify_snapshot(repository, original.commit_sha)
    assert git(repository, "rev-parse", "HEAD") == current
    (repository / "folder").mkdir()
    with pytest.raises(SnapshotVerificationError, match="exact Git working-tree root"):
        verify_snapshot(repository / "folder", current)


@pytest.mark.parametrize("contamination", ["tracked", "staged", "deleted", "untracked", "ignored"])
def test_verification_rejects_checkout_contamination(repository: Path, contamination: str) -> None:
    (repository / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    sha = commit(repository)
    if contamination in ("tracked", "staged"):
        (repository / "README.md").write_text("edited\n", encoding="utf-8")
        if contamination == "staged":
            git(repository, "add", "README.md")
    elif contamination == "deleted":
        (repository / "README.md").unlink()
    else:
        (repository / f"{contamination}.txt").write_text("contamination\n", encoding="utf-8")
    with pytest.raises(SnapshotVerificationError, match="must be clean"):
        verify_snapshot(repository, sha)
    with pytest.raises(SnapshotVerificationError):
        discover_files(repository)


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_verification_rejects_flags_hiding_tracked_edits(repository: Path, flag: str) -> None:
    sha = create_snapshot(repository).commit_sha
    git(repository, "update-index", flag, "README.md")
    (repository / "README.md").write_text("hidden edit\n", encoding="utf-8")
    with pytest.raises(SnapshotVerificationError, match="flags"):
        verify_snapshot(repository, sha)


def test_verification_rejects_sparse_checkout_configuration(repository: Path) -> None:
    sha = create_snapshot(repository).commit_sha
    git(repository, "config", "core.sparseCheckout", "true")
    with pytest.raises(SnapshotVerificationError, match="sparse"):
        verify_snapshot(repository, sha)


def test_clone_checks_out_the_requested_commit_and_refuses_existing_target(
    repository: Path,
    tmp_path: Path,
) -> None:
    original = create_snapshot(repository)
    (repository / "new.py").write_text("new = True\n", encoding="utf-8")
    latest = commit(repository)
    destination = tmp_path / "clone"
    snapshot = clone_snapshot(repository.as_uri(), destination, original.commit_sha)
    assert snapshot.commit_sha == original.commit_sha
    assert snapshot.commit_sha != latest
    assert not (destination / "new.py").exists()
    assert git(destination, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    with pytest.raises(IngestionError, match="absent or empty"):
        clone_snapshot(repository.as_uri(), destination, latest)
    assert git(destination, "rev-parse", "HEAD") == original.commit_sha


def test_clone_rejects_unpinned_commit_before_creating_files(
    repository: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "not-created"
    with pytest.raises(ValueError, match="40 lowercase"):
        clone_snapshot(repository.as_uri(), destination, "HEAD")
    assert not destination.exists()


def test_discovery_preserves_hierarchy_hashes_lines_and_order(repository: Path) -> None:
    (repository / "pkg").mkdir()
    content = "def café():\r\n    return 1\r\n".encode()
    (repository / "pkg" / "logic.py").write_bytes(content)
    (repository / "empty.txt").write_bytes(b"")
    (repository / "no-newline").write_text("one line", encoding="utf-8")
    sha = commit(repository)
    files = discover_files(repository)
    assert [source.path for source in files] == [
        "README.md",
        "empty.txt",
        "no-newline",
        "pkg/logic.py",
    ]
    source = next(source for source in files if source.path == "pkg/logic.py")
    assert source.sha256 == hashlib.sha256(content).hexdigest()
    assert source.size_bytes == len(content)
    assert source.line_count == 2
    assert source.language == "python"
    assert next(source for source in files if source.path == "empty.txt").line_count == 0
    assert read_source_file(repository, source.path, sha).encode("utf-8") == content
    assert discover_files(repository) == files


def test_discovery_requires_callers_expected_pin(repository: Path) -> None:
    original = create_snapshot(repository)
    (repository / "new.py").write_text("new = True\n", encoding="utf-8")
    commit(repository)
    with pytest.raises(SnapshotVerificationError, match="commit mismatch"):
        discover_files(repository, expected_commit=original.commit_sha)


def test_git_blobs_preserve_evidence_despite_clean_checkout_line_endings(repository: Path) -> None:
    source = repository / "source.py"
    source.write_bytes(b"x = 1\ny = 2\n")
    sha = commit(repository)
    checkout = repository.parent / "crlf-checkout"
    git(repository, "clone", "--quiet", "-c", "core.autocrlf=true", str(repository), str(checkout))
    assert (checkout / "source.py").read_bytes() == b"x = 1\r\ny = 2\r\n"
    record = next(source for source in discover_files(checkout) if source.path == "source.py")
    assert record.sha256 == hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()
    assert read_source_file(checkout, "source.py", sha) == "x = 1\ny = 2\n"


def test_discovery_excludes_artifacts_binaries_symlinks_submodules_and_lfs(
    repository: Path,
) -> None:
    candidates = {
        "node_modules/dep/source.py": b"source = True\n",
        "pkg/vendor/dep.py": b"source = True\n",
        "pkg/build/generated.py": b"source = True\n",
        "pkg/.env": b"TOKEN=sample\n",
        "credentials.json": b"{}\n",
        "data.bin": b"\x00\xff\x00",
        "legacy.txt": b"caf\xe9",
        "controls.txt": b"abc\x01\n",
        "something.min.js": b"function x(){}",
        "uv.lock": b"version = 1\n",
        "custom.py": b"# Automatically generated; DO NOT EDIT\nx = 1\n",
        "data.dat": b"version https://git-lfs.github.com/spec/v1\noid sha256:"
        + b"a" * 64
        + b"\nsize 42\n",
        "pkg/keep.py": b"x = 1\n",
    }
    for path, content in candidates.items():
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (repository / "external.py").symlink_to(repository.parent / "external.py")
    (repository / "nested").mkdir()
    git(repository, "add", "--all")
    git(
        repository,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{git(repository, 'rev-parse', 'HEAD')},nested",
    )
    git(repository, "commit", "--quiet", "-m", "mixed files")
    assert [source.path for source in discover_files(repository)] == ["README.md", "pkg/keep.py"]


def test_discovery_applies_segment_globs_and_size_limit(repository: Path) -> None:
    for path in ("root.py", "pkg/yes.py", "pkg/deep/no.py", "large.py"):
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n" if path != "large.py" else "x" * 200, encoding="utf-8")
    commit(repository)
    policy = DiscoveryPolicy(
        include_globs=("**/*.py",), exclude_globs=("pkg/deep/**",), max_file_bytes=50
    )
    assert [source.path for source in discover_files(repository, policy)] == [
        "pkg/yes.py",
        "root.py",
    ]
    root_only = DiscoveryPolicy(include_globs=("*.py",), max_file_bytes=50)
    assert [source.path for source in discover_files(repository, root_only)] == ["root.py"]


def test_source_read_refuses_symlinks_directories_missing_and_unsafe_paths(
    repository: Path,
) -> None:
    (repository / "pkg").mkdir()
    (repository / "pkg" / "code.py").write_text("x = 1\n", encoding="utf-8")
    (repository / "link.py").symlink_to("README.md")
    sha = commit(repository)
    for path in ("../README.md", "/README.md", "link.py", "pkg", "missing.py"):
        with pytest.raises((ValueError, IngestionError)):
            read_source_file(repository, path, sha)


def test_source_read_preserves_literal_git_paths(repository: Path) -> None:
    paths = (":name.py", "[abc].py", "*name.py", " leading.py", "trailing.py ")
    for path in paths:
        (repository / path).write_text(f"# {path}\n", encoding="utf-8")
    sha = commit(repository)
    records = {source.path for source in discover_files(repository, expected_commit=sha)}
    for path in paths:
        assert path in records
        assert read_source_file(repository, path, sha) == f"# {path}\n"


def test_git_environment_cannot_redirect_snapshot(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_DIR", "/missing-repository")
    monkeypatch.setenv("GIT_WORK_TREE", "/missing-worktree")
    assert create_snapshot(repository).url == repository.as_uri()


@pytest.mark.parametrize(
    "path",
    [
        "/abs.py",
        "../bad.py",
        "a/../bad.py",
        "./a.py",
        "a//b.py",
        "a\\b.py",
        "C:/bad.py",
        "a/",
        "bad\nname.py",
    ],
)
def test_source_file_requires_safe_normalized_relative_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        SourceFile(path=path, sha256="a" * 64, size_bytes=0, line_count=0)


def test_records_are_frozen_strict_and_json_round_trip(repository: Path) -> None:
    snapshot = create_snapshot(repository)
    with pytest.raises(ValidationError):
        snapshot.commit_sha = "b" * 40
    with pytest.raises(ValidationError):
        RepositorySnapshot(url="x", commit_sha="a" * 40, captured_at=datetime.now())
    with pytest.raises(ValidationError):
        RepositorySnapshot(
            url="x", commit_sha="a" * 40, captured_at=datetime.now(UTC), unexpected=True
        )
    with pytest.raises(ValidationError):
        DiscoveryPolicy(max_file_bytes=0)
    with pytest.raises(ValidationError):
        DiscoveryPolicy(include_globs=("../*",))
    manifest = SnapshotManifest(snapshot=snapshot, files=tuple(discover_files(repository)))
    assert SnapshotManifest.model_validate_json(manifest.model_dump_json()) == manifest
    with pytest.raises(ValidationError, match="unique paths"):
        SnapshotManifest(snapshot=snapshot, files=manifest.files * 2)

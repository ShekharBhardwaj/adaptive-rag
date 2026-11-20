"""New-only run directories, durable append-only records, and explicit partial loads."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from adaptive_rag import __version__
from adaptive_rag.ingestion.git import IngestionError, _git
from adaptive_rag.ingestion.models import validate_source_path

if TYPE_CHECKING:
    from .experiment_models import ExperimentRecord


@dataclass(frozen=True)
class LoadedRun:
    manifest: dict[str, Any]
    records: tuple[ExperimentRecord, ...]
    events: tuple[dict[str, Any], ...]
    status: dict[str, Any] | None
    issues: tuple[str, ...]
    partial: bool


def _serialize(data: dict[str, Any], *, pretty: bool = False) -> bytes:
    if not isinstance(data, dict):
        raise TypeError("run artifacts must contain a JSON object")
    return (
        json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exclusive_write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


class RunStore:
    """Create exactly one new run, without resuming or overwriting prior artifacts.

    A successful append is flushed and fsynced before returning. A hard process
    interruption may leave an unterminated tail; load_run reports that explicitly.
    """

    def __init__(self, output: Path, manifest: dict[str, Any]) -> None:
        self.output = Path(output)
        self._manifest_bytes = _serialize(manifest, pretty=True)
        self._events: TextIO | None = None
        self._results: TextIO | None = None
        self._entered = False
        self._finished = False
        self._events_written = 0
        self._records_written = 0

    def __enter__(self) -> RunStore:
        if self._entered:
            raise RuntimeError("a run store cannot be entered more than once")
        # mkdir's exclusive creation protects every artifact in an existing run.
        self.output.mkdir(parents=True, exist_ok=False)
        self._entered = True
        try:
            _exclusive_write(self.output / "manifest.json", self._manifest_bytes)
            self._events = (self.output / "events.jsonl").open("x", encoding="utf-8")
            self._results = (self.output / "results.jsonl").open("x", encoding="utf-8")
            for stream in (self._events, self._results):
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(self.output)
        except BaseException as exc:
            try:
                self.finish(
                    "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed",
                    error=str(exc),
                    exception_type=type(exc).__name__,
                )
            except (OSError, ValueError):
                pass  # Preserve the original initialization failure and any created artifacts.
            self._close()
            raise
        return self

    def _active(self) -> None:
        if not self._entered or self._events is None or self._results is None:
            raise RuntimeError("run store must be active inside its context manager")
        if self._finished:
            raise RuntimeError("run store is already finalized")

    def event(self, data: dict[str, Any]) -> None:
        self._active()
        encoded = _serialize(data).decode("utf-8")
        assert self._events is not None
        self._events.write(encoded)
        self._events.flush()
        os.fsync(self._events.fileno())
        self._events_written += 1

    def record(self, record: ExperimentRecord | dict[str, Any]) -> None:
        self._active()
        data = record if isinstance(record, dict) else record.model_dump(mode="json")
        encoded = _serialize(data).decode("utf-8")
        assert self._results is not None
        self._results.write(encoded)
        self._results.flush()
        os.fsync(self._results.fileno())
        self._records_written += 1

    def write_artifact(self, name: str, data: bytes | dict[str, Any]) -> None:
        self._active()
        validate_source_path(name)
        if not isinstance(data, (bytes, dict)):
            raise TypeError("artifact data must be bytes or a JSON object")
        parent = self.output
        for component in Path(name).parts[:-1]:
            parent = parent / component
            if parent.is_symlink():
                raise ValueError("artifact parent directories must not be symlinks")
            if not parent.exists():
                parent.mkdir()
                _sync_directory(parent.parent)
            if not parent.is_dir():
                raise ValueError("artifact parent is not a directory")
        target = self.output / name
        if target.is_symlink():
            raise ValueError("artifact paths must not be symlinks")
        if not parent.resolve().is_relative_to(self.output.resolve()):
            raise ValueError("artifact path must stay inside the run directory")
        _exclusive_write(target, data if isinstance(data, bytes) else _serialize(data, pretty=True))

    def finish(self, status: str, **metadata: Any) -> None:
        if not self._entered or self._finished:
            raise RuntimeError("run store must be opened and not already finalized")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("final run status must be a nonblank string")
        reserved = {"status", "finished_at", "records_written", "events_written"}
        if reserved.intersection(metadata):
            raise ValueError("final status metadata cannot replace storage accounting fields")
        final = {
            **metadata,
            "status": status,
            "finished_at": datetime.now(UTC).isoformat(),
            "records_written": self._records_written,
            "events_written": self._events_written,
        }
        _exclusive_write(self.output / "status.json", _serialize(final, pretty=True))
        self._finished = True

    def _close(self) -> None:
        for stream in (self._events, self._results):
            if stream is not None:
                stream.close()
        self._events = self._results = None

    def __exit__(self, exception_type, exception, _traceback) -> None:
        try:
            if not self._finished:
                status = "failed" if exception is not None else "interrupted"
                if isinstance(exception, (KeyboardInterrupt, SystemExit)):
                    status = "interrupted"
                metadata = (
                    {"error": str(exception), "exception_type": exception_type.__name__}
                    if exception is not None
                    else {"error": "run exited without explicit finalization"}
                )
                try:
                    self.finish(status, **metadata)
                except (OSError, ValueError):
                    if exception is None:
                        raise
                    # Retain the triggering failure. Missing/malformed status is explicit on load.
        finally:
            self._close()


def _strict_object(raw: bytes) -> dict[str, Any]:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("nonstandard JSON numeric constant")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON number exceeds finite float representation")
        return parsed

    value = json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=constant,
        parse_float=finite_float,
    )
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _read_object(path: Path, issues: list[str], *, required: bool = True) -> dict | None:
    if path.is_symlink() or not path.is_file():
        if required or path.exists() or path.is_symlink():
            issues.append(f"{path.name}: missing artifact, non-file, or symlink")
        return None
    try:
        return _strict_object(path.read_bytes())
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        issues.append(f"{path.name}: invalid artifact: {exc}")
        return None


def _read_jsonl(path: Path, issues: list[str], *, records: bool) -> tuple[Any, ...]:
    from .experiment_models import ExperimentRecord

    if path.is_symlink() or not path.is_file():
        issues.append(f"{path.name}: missing artifact, non-file, or symlink")
        return ()
    output = []
    number = 0
    try:
        with path.open("rb") as stream:
            for number, raw in enumerate(stream, 1):
                try:
                    value = _strict_object(raw)
                    parsed = ExperimentRecord.model_validate(value) if records else value
                except (ValueError, UnicodeError, RecursionError) as exc:
                    issues.append(
                        f"{path.name}:{number}: invalid JSONL record; retained valid prefix: {exc}"
                    )
                    break
                output.append(parsed)
                if not raw.endswith(b"\n"):
                    issues.append(
                        f"{path.name}:{number}: unterminated final line retained as partial"
                    )
    except OSError as exc:
        issues.append(f"{path.name}:{number + 1}: could not read artifact: {exc}")
    return tuple(output)


def load_run(directory: Path | str) -> LoadedRun:
    """Load explicit valid prefixes, preserving raw duplicates and reporting all ambiguity."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("run must be a real existing directory")
    issues: list[str] = []
    manifest = _read_object(directory / "manifest.json", issues) or {}
    records = _read_jsonl(directory / "results.jsonl", issues, records=True)
    events = _read_jsonl(directory / "events.jsonl", issues, records=False)
    status = _read_object(directory / "status.json", issues, required=False)
    if status is None:
        issues.append("status.json: final status is missing or unreadable; run may be interrupted")
    elif status.get("status") != "completed":
        issues.append(f"status.json: run status is {status.get('status')!r}; results are partial")
    if status is not None:
        for field, actual in (("records_written", len(records)), ("events_written", len(events))):
            if field in status and (type(status[field]) is not int or status[field] != actual):
                issues.append(f"status.json: {field} contradicts the valid JSONL record count")
    seen: dict[str, Any] = {}
    for record in records:
        if record.job_id in seen:
            kind = "duplicate" if seen[record.job_id] == record else "conflicting duplicate"
            issues.append(f"results.jsonl: {kind} job_id {record.job_id!r}; raw records retained")
        else:
            seen[record.job_id] = record
        if manifest.get("run_id") is not None and record.run_id != manifest["run_id"]:
            issues.append(
                f"results.jsonl: job {record.job_id!r} has a different run_id from manifest"
            )
    if "planned_jobs" in manifest:
        planned = manifest["planned_jobs"]
        if not isinstance(planned, list) or any(
            not isinstance(job, dict) or not isinstance(job.get("job_id"), str) for job in planned
        ):
            issues.append(
                "manifest.json: planned_jobs must be a list of objects with string job_id"
            )
        else:
            identifiers = [job["job_id"] for job in planned]
            if len(identifiers) != len(set(identifiers)):
                issues.append("manifest.json: duplicate planned job_id values")
            unknown = sorted(set(seen) - set(identifiers))
            if unknown:
                issues.append(
                    f"results.jsonl: {len(unknown)} unknown job_id values: {unknown[:5]!r}"
                )
            missing = sorted(set(identifiers) - set(seen))
            if missing:
                issues.append(f"results.jsonl: {len(missing)} planned jobs have no valid record")
    return LoadedRun(manifest, records, events, status, tuple(issues), bool(issues))


def capture_environment() -> dict[str, Any]:
    """Capture framework/dependency provenance without credentials or repository imports."""
    source_root = Path(__file__).resolve().parents[1]
    project_root = source_root.parents[1]
    digest = hashlib.sha256()
    for source in sorted(source_root.rglob("*.py")):
        digest.update(source.relative_to(source_root).as_posix().encode() + b"\0")
        digest.update(source.read_bytes() + b"\0")
    sha = dirty = None
    try:
        sha = _git(project_root, ["rev-parse", "HEAD"]).decode().strip()
        dirty = bool(_git(project_root, ["status", "--porcelain", "--untracked-files=normal"]))
    except IngestionError:
        pass
    dependencies = {}
    for package in (
        "pydantic",
        "PyYAML",
        "httpx",
        "numpy",
        "faiss-cpu",
        "tree-sitter",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
    ):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    lock = project_root / "uv.lock"
    return {
        "framework_version": __version__,
        "framework_git_sha": sha,
        "framework_worktree_dirty": dirty,
        "framework_source_sha256": digest.hexdigest(),
        "lockfile_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()
        if lock.is_file()
        else None,
        "python": sys.version,
        "platform": platform.platform(),
        "dependencies": dependencies,
    }

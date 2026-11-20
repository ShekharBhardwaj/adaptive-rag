"""Local JSONL traces behind an interface that can support external adapters."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO
from uuid import uuid4

from pydantic import AwareDatetime, Field

from adaptive_rag import __version__
from adaptive_rag.ingestion.git import IngestionError, _git
from adaptive_rag.models import ResearchModel
from adaptive_rag.retrieval.models import RetrievalRequest, RetrievalResult


class RetrievalTrace(ResearchModel):
    schema_version: Literal["1"] = "1"
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    framework_version: str = __version__
    framework_source_sha256: str
    framework_git_sha: str | None = None
    framework_worktree_dirty: bool | None = None
    configuration: dict[str, Any]
    configuration_sha256: str
    request: RetrievalRequest
    result: RetrievalResult
    final_answer: str | None = None


class TraceSink(Protocol):
    def record(self, trace: RetrievalTrace) -> None: ...


class JsonlTraceSink:
    """One new output file per run; append multiple records within its context."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._stream: TextIO | None = None

    def __enter__(self) -> "JsonlTraceSink":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("x", encoding="utf-8")
        return self

    def record(self, trace: RetrievalTrace) -> None:
        if self._stream is None:
            raise ValueError("trace sink must be opened with a context manager")
        self._stream.write(trace.model_dump_json() + "\n")
        self._stream.flush()

    def __exit__(self, *args) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


def make_trace(
    configuration: dict, request: RetrievalRequest, result: RetrievalResult
) -> RetrievalTrace:
    encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    source_root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for source in sorted(source_root.rglob("*.py")):
        digest.update(source.relative_to(source_root).as_posix().encode() + b"\0")
        digest.update(source.read_bytes() + b"\0")
    framework_sha = None
    dirty = None
    try:
        project_root = source_root.parents[1]
        framework_sha = _git(project_root, ["rev-parse", "HEAD"]).decode().strip()
        dirty = bool(_git(project_root, ["status", "--porcelain", "--untracked-files=normal"]))
    except IngestionError:
        pass  # Installed wheels may have no Git working tree; retain unknown metadata.
    return RetrievalTrace(
        framework_source_sha256=digest.hexdigest(),
        framework_git_sha=framework_sha,
        framework_worktree_dirty=dirty,
        configuration=configuration,
        configuration_sha256=hashlib.sha256(encoded).hexdigest(),
        request=request,
        result=result,
    )

"""Immutable in-memory source corpus identified by an exact snapshot and policy."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from adaptive_rag.ingestion import (
    DiscoveryPolicy,
    RepositorySnapshot,
    SourceFile,
    discover_files,
    read_source_files,
    verify_snapshot,
)
from adaptive_rag.ingestion.models import validate_source_path

from .models import EvidenceChunk


@dataclass(frozen=True)
class RepositoryCorpus:
    repository: Path
    snapshot: RepositorySnapshot
    policy: DiscoveryPolicy
    files: tuple[SourceFile, ...]
    fingerprint: str
    _texts: Mapping[str, str]

    @classmethod
    def from_repository(
        cls, repository: Path | str, expected_commit: str, policy: DiscoveryPolicy | None = None
    ) -> "RepositoryCorpus":
        root = Path(repository).resolve()
        effective_policy = policy if policy is not None else DiscoveryPolicy()
        snapshot = verify_snapshot(root, expected_commit)
        files = tuple(discover_files(root, effective_policy, expected_commit=expected_commit))
        texts = read_source_files(root, files, expected_commit)
        identity = {
            "version": "corpus-v1",
            "url": snapshot.url,
            "commit": expected_commit,
            "policy": effective_policy.model_dump(mode="json"),
            "files": [source.model_dump(mode="json") for source in files],
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(root, snapshot, effective_policy, files, digest, MappingProxyType(texts))

    @property
    def commit_sha(self) -> str:
        return self.snapshot.commit_sha

    def verify(self) -> None:
        current = verify_snapshot(self.repository, self.commit_sha)
        if current.url != self.snapshot.url:
            raise ValueError("repository origin changed after corpus construction")

    def text(self, path: str) -> str:
        validate_source_path(path)
        try:
            return self._texts[path]
        except KeyError as exc:
            raise ValueError(f"path is outside the included corpus: {path!r}") from exc

    def evidence(
        self,
        path: str,
        start_line: int,
        end_line: int,
        score: float | None = None,
        reason: str = "",
    ) -> EvidenceChunk:
        lines = self.text(path).splitlines()
        if (
            isinstance(start_line, bool)
            or isinstance(end_line, bool)
            or not isinstance(start_line, int)
            or not isinstance(end_line, int)
            or not 1 <= start_line <= end_line <= len(lines)
        ):
            raise ValueError(f"invalid source range for {path!r}: {start_line}-{end_line}")
        text = "\n".join(lines[start_line - 1 : end_line])
        excerpt_hash = hashlib.sha256(text.encode()).hexdigest()
        identity = f"{self.commit_sha}\0{path}\0{start_line}\0{end_line}\0{excerpt_hash}"
        return EvidenceChunk(
            id=hashlib.sha256(identity.encode()).hexdigest(),
            repo_commit=self.commit_sha,
            path=path,
            start_line=start_line,
            end_line=end_line,
            text=text,
            excerpt_sha256=excerpt_hash,
            score=score,
            reason=reason,
        )

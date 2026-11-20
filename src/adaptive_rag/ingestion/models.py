"""Immutable, versioned records describing repository evidence."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    "**/.git/**",
    "**/.env",
    "**/.env.*",
    "**/.aws/**",
    "**/.ssh/**",
    "**/secrets.*",
    "**/credentials.*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/id_ed25519",
    "**/node_modules/**",
    "**/vendor/**",
    "**/vendors/**",
    "**/vendored/**",
    "**/third_party/**",
    "**/third-party/**",
    "**/.venv/**",
    "**/venv/**",
    "**/env/**",
    "**/build/**",
    "**/dist/**",
    "**/target/**",
    "**/out/**",
    "**/coverage/**",
    "**/htmlcov/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/.cache/**",
    "**/.tox/**",
    "**/.nox/**",
    "**/.next/**",
    "**/.nuxt/**",
    "**/.output/**",
    "**/.eggs/**",
    "**/*.egg-info/**",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/*.generated.*",
    "**/*.gen.*",
    "**/package-lock.json",
    "**/pnpm-lock.yaml",
    "**/yarn.lock",
    "**/poetry.lock",
    "**/uv.lock",
    "**/Pipfile.lock",
    "**/Cargo.lock",
    "**/composer.lock",
)


def validate_commit_sha(value: str) -> str:
    """Require a complete SHA-1 commit ID; branch names are never pins."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("commit_sha must be exactly 40 lowercase hexadecimal characters")
    return value


def validate_source_path(value: str) -> str:
    """Accept a canonical POSIX path that cannot escape a repository."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("path must be a nonempty normalized POSIX relative path")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("path must not contain control characters")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or PureWindowsPath(value).drive
        or any(part in ("", ".", "..") for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise ValueError("path must be a normalized POSIX relative path without traversal")
    return value


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RepositorySnapshot(_Record):
    schema_version: Literal["1"] = "1"
    url: Annotated[str, Field(min_length=1)]
    commit_sha: str
    captured_at: datetime

    _commit = field_validator("commit_sha")(validate_commit_sha)

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return value


class SourceFile(_Record):
    path: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    size_bytes: Annotated[int, Field(ge=0)]
    line_count: Annotated[int, Field(ge=0)]
    language: str | None = None

    _path = field_validator("path")(validate_source_path)


class DiscoveryPolicy(_Record):
    """POSIX segment globs; ** matches zero or more directory segments.

    Explicit exclude_globs replace the defaults. Binary, generated-header,
    symlink, submodule, and Git LFS pointer exclusions always apply.
    """

    include_globs: Annotated[tuple[str, ...], Field(min_length=1)] = ("**/*",)
    exclude_globs: tuple[str, ...] = DEFAULT_EXCLUDE_GLOBS
    max_file_bytes: Annotated[int, Field(gt=0)] = 1_000_000

    @field_validator("include_globs", "exclude_globs")
    @classmethod
    def validate_globs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if (
                not value
                or value.startswith("/")
                or "\\" in value
                or any(part in ("", ".", "..") for part in value.split("/"))
                or any(ord(character) < 32 for character in value)
            ):
                raise ValueError("globs must be normalized POSIX relative patterns")
        return values


class SnapshotManifest(_Record):
    schema_version: Literal["1"] = "1"
    snapshot: RepositorySnapshot
    policy: DiscoveryPolicy = Field(default_factory=DiscoveryPolicy)
    files: tuple[SourceFile, ...]

    @model_validator(mode="after")
    def require_unique_sorted_paths(self) -> SnapshotManifest:
        paths = [source.path for source in self.files]
        if paths != sorted(set(paths)):
            raise ValueError("manifest files must have unique paths in sorted order")
        return self

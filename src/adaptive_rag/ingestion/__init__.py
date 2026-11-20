"""Reproducible Git snapshots and source-file discovery."""

from .git import (
    IngestionError,
    SnapshotVerificationError,
    clone_snapshot,
    create_snapshot,
    discover_files,
    read_source_file,
    read_source_files,
    verify_snapshot,
)
from .models import DiscoveryPolicy, RepositorySnapshot, SnapshotManifest, SourceFile

__all__ = [
    "DiscoveryPolicy",
    "IngestionError",
    "RepositorySnapshot",
    "SnapshotManifest",
    "SnapshotVerificationError",
    "SourceFile",
    "clone_snapshot",
    "create_snapshot",
    "discover_files",
    "read_source_file",
    "read_source_files",
    "verify_snapshot",
]

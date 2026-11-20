"""Deterministic source-line chunks with optional language-aware boundaries.

Line ranges are inclusive and refer to complete original source lines. A line
longer than max_chars is kept intact: splitting it would invalidate line-based
citations. The bound is therefore soft for exactly one oversized line.
"""

from __future__ import annotations

import ast
import importlib
import platform
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Literal

from pydantic import Field, model_validator

from adaptive_rag.models import ResearchModel
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import EvidenceChunk

CHUNKING_VERSION = "line-preserving-v1"


class ChunkingConfig(ResearchModel):
    max_lines: Annotated[int, Field(strict=True, ge=1)] = 80
    max_chars: Annotated[int, Field(strict=True, ge=1)] = 12_000
    overlap_lines: Annotated[int, Field(strict=True, ge=0)] = 8
    parser: Literal["auto", "line_windows"] = "auto"
    oversized_line_policy: Literal["keep_complete_line"] = "keep_complete_line"

    @model_validator(mode="after")
    def overlap_is_smaller_than_window(self) -> ChunkingConfig:
        if self.overlap_lines >= self.max_lines:
            raise ValueError("overlap_lines must be smaller than max_lines")
        return self


def parser_versions() -> dict[str, str]:
    """Record installed parser versions, including the deterministic fallback."""
    result = {"chunking": CHUNKING_VERSION, "python_ast": f"stdlib-ast:{platform.python_version()}"}
    for package in (
        "tree-sitter",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
    ):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "unavailable"
    return result


def _tree_sitter_boundaries(text: str, suffix: str) -> tuple[set[int], str] | None:
    grammars = {
        ".py": ("tree_sitter_python", "language"),
        ".js": ("tree_sitter_javascript", "language"),
        ".jsx": ("tree_sitter_javascript", "language"),
        ".mjs": ("tree_sitter_javascript", "language"),
        ".cjs": ("tree_sitter_javascript", "language"),
        ".ts": ("tree_sitter_typescript", "language_typescript"),
        ".tsx": ("tree_sitter_typescript", "language_tsx"),
    }
    if suffix not in grammars:
        return None
    package, factory = grammars[suffix]
    try:
        from tree_sitter import Language, Parser

        grammar = importlib.import_module(package)
    except ImportError:
        return None
    try:
        parser = Parser(Language(getattr(grammar, factory)()))
        root = parser.parse(text.encode("utf-8")).root_node
    except (AttributeError, TypeError, ValueError):
        return {1}, f"line_windows:tree_sitter_incompatible:{package}"
    # Error recovery may invent misleading boundaries; fall back explicitly.
    if root.has_error:
        return {1}, f"line_windows:tree_sitter_parse_error:{package}"
    starts = {child.start_point.row + 1 for child in root.named_children}
    return starts | {1}, f"tree_sitter:{package}"


def _boundaries(text: str, path: str, config: ChunkingConfig) -> tuple[set[int], str]:
    if config.parser == "line_windows":
        return {1}, "line_windows:configured"
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    parsed = _tree_sitter_boundaries(text, suffix)
    if parsed is not None:
        return parsed
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            return {1}, "line_windows:python_ast_parse_error"
        starts = {1}
        for node in tree.body:
            start = getattr(node, "lineno", 1)
            for decorator in getattr(node, "decorator_list", ()):
                start = min(start, decorator.lineno)
            starts.add(start)
        return starts, "python_ast:tree_sitter_unavailable"
    return {1}, "line_windows:unsupported_or_parser_unavailable"


def chunk_corpus(
    corpus: RepositoryCorpus, config: ChunkingConfig | None = None
) -> tuple[EvidenceChunk, ...]:
    """Cover every nonempty file without dropping comments or decorators.

    Preferred cuts precede top-level syntax nodes. Larger nodes use bounded line
    windows. Overlap applies only after a cut inside a node/window; complete
    language-aware blocks do not need artificial overlap.
    """
    config = config or ChunkingConfig()
    chunks: list[EvidenceChunk] = []
    for source in corpus.files:
        text = corpus.text(source.path)
        lines = text.splitlines()
        if not lines:
            continue
        starts, backend = _boundaries(text, source.path, config)
        preferred_ends = {start - 1 for start in starts if start > 1} | {len(lines)}
        start = 1
        while start <= len(lines):
            end_limit = min(len(lines), start + config.max_lines - 1)
            chars = 0
            end = start
            for candidate in range(start, end_limit + 1):
                candidate_chars = len(lines[candidate - 1]) + (1 if candidate > start else 0)
                if chars + candidate_chars > config.max_chars and candidate > start:
                    break
                chars += candidate_chars
                end = candidate
                if chars > config.max_chars:
                    break
            cuts = [boundary for boundary in preferred_ends if start <= boundary <= end]
            natural_cut = bool(cuts)
            if natural_cut:
                end = max(cuts)
            oversized = len(lines[start - 1]) > config.max_chars and end == start
            reason = f"chunking={CHUNKING_VERSION};parser={backend}"
            if oversized:
                reason += ";oversized_line=kept_complete"
            chunks.append(corpus.evidence(source.path, start, end, reason=reason))
            if end == len(lines):
                break
            # Always advance even when a very long line reduces a window to one.
            start = end + 1 if natural_cut else max(start + 1, end + 1 - config.overlap_lines)
    return tuple(chunks)

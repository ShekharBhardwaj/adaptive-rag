"""Bounded deterministic navigation of the included, pinned repository corpus.

Search scores are explicit heuristics, never probabilities. Symbol declarations outside
valid Python are approximate; references are literal identifier occurrences, not a call graph.
"""

from __future__ import annotations

import fnmatch
import heapq
import re
import time
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from adaptive_rag.ingestion.models import validate_source_path

from .symbols import SymbolLocation, extract_symbols, identifier_terms

if TYPE_CHECKING:
    from .corpus import RepositoryCorpus
    from .models import EvidenceChunk

_MAX_RESULTS = 100
_MAX_SEARCH_EVIDENCE_CHARS = 12_000
_MAX_EXCERPT_CHARS = 1_200
_MAX_READ_CHARS = 24_000


@dataclass(frozen=True)
class ToolResult:
    data: dict[str, Any]
    evidence: tuple[EvidenceChunk, ...] = ()


class ToolDeadlineExceeded(ValueError):
    """A cooperative scan deadline elapsed; no further source scan is performed."""


def _limit(value: int, *, maximum: int = _MAX_RESULTS, name: str = "limit") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _query(value: str, name: str = "query") -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8_000:
        raise ValueError(f"{name} must contain between 1 and 8000 characters")
    if any(
        (ord(character) < 32 or ord(character) == 127)
        and not (name == "query" and character in "\n\r\t")
        for character in value
    ):
        raise ValueError(f"{name} must not contain control characters")
    return value.strip()


class RepositoryTools:
    """Read only corpus-owned source text; never touch arbitrary working-tree paths."""

    def __init__(self, corpus: RepositoryCorpus) -> None:
        self.corpus = corpus
        self._paths = tuple(sorted(source.path for source in corpus.files))
        self._path_set = frozenset(self._paths)
        self._symbol_cache: dict[str, tuple[SymbolLocation, ...]] = {}
        self.deadline: float | None = None

    def _check_deadline(self) -> None:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ToolDeadlineExceeded("repository tool execution deadline exceeded")

    def _symbols(self, path: str) -> tuple[SymbolLocation, ...]:
        if path not in self._symbol_cache:
            self._symbol_cache[path] = extract_symbols(path, self.corpus.text(path))
        return self._symbol_cache[path]

    def _excerpt(self, path: str, line: int, *, reason: str) -> EvidenceChunk | None:
        lines = self.corpus.text(path).splitlines()
        if not lines or line < 1 or line > len(lines):
            return None
        start = max(1, line - 2)
        end = min(len(lines), line + 5)
        while len("\n".join(lines[start - 1 : end])) > _MAX_EXCERPT_CHARS:
            if end > line:
                end -= 1
            elif start < line:
                start += 1
            else:
                return None
        return self.corpus.evidence(path, start, end, reason=reason)

    def _search_result(self, matches: list[dict[str, Any]], *, kind: str) -> ToolResult:
        evidence: list[EvidenceChunk] = []
        evidence_ids: set[str] = set()
        chars = 0
        for match in matches:
            chunk = self._excerpt(match["path"], match["start_line"], reason=kind)
            if chunk is None:
                match["omission_reason"] = "source line is empty or exceeds excerpt character limit"
            elif chars + len(chunk.text) > _MAX_SEARCH_EVIDENCE_CHARS:
                match["omission_reason"] = "search evidence character limit reached"
            else:
                match["evidence_id"] = chunk.id
                if chunk.id not in evidence_ids:
                    chars += len(chunk.text)
                    evidence.append(chunk)
                    evidence_ids.add(chunk.id)
        return ToolResult(
            {"matches": matches, "score_kind": "heuristic", "kind": kind}, tuple(evidence)
        )

    def list_directory(self, path: str = ".", limit: int = 50) -> ToolResult:
        limit = _limit(limit)
        if path != ".":
            validate_source_path(path)
        prefix = "" if path == "." else path + "/"
        entries: dict[str, str] = {}
        for source in self._paths:
            self._check_deadline()
            if not source.startswith(prefix):
                continue
            remainder = source[len(prefix) :]
            name, separator, _ = remainder.partition("/")
            entries[prefix + name] = "directory" if separator else "file"
        if not entries and path != ".":
            raise ValueError(f"directory is not in the included corpus: {path}")
        ordered = sorted(entries.items())
        return ToolResult(
            {
                "path": path,
                "entries": [{"path": entry, "kind": kind} for entry, kind in ordered[:limit]],
                "truncated": len(ordered) > limit,
            }
        )

    def search_files(self, pattern: str, limit: int = 20) -> ToolResult:
        """Case-insensitive POSIX glob, or substring when no glob characters occur."""
        limit = _limit(limit)
        pattern = _query(pattern, "pattern")
        validate_source_path(pattern)
        needle = pattern.casefold()
        glob = any(character in needle for character in "*?[")
        matches = []
        for path in self._paths:
            self._check_deadline()
            folded = path.casefold()
            basename = PurePosixPath(path).name.casefold()
            if glob:
                matched = fnmatch.fnmatchcase(folded, needle) or (
                    "/" not in needle and fnmatch.fnmatchcase(basename, needle)
                )
            else:
                matched = needle in folded
            if matched:
                score = 10.0 if needle in (folded, basename) else 5.0 if needle in basename else 2.0
                matches.append({"path": path, "start_line": 1, "score": score})
        matches.sort(key=lambda item: (-item["score"], item["path"]))
        return self._search_result(matches[:limit], kind="filename")

    def search_symbols(self, query: str, limit: int = 20) -> ToolResult:
        limit = _limit(limit)
        query = _query(query)
        terms = set(identifier_terms(query, drop_stop_words=True))
        needle = query.casefold()

        def candidates():
            for path in self._paths:
                self._check_deadline()
                for symbol in self._symbols(path):
                    common = terms.intersection(identifier_terms(symbol.name))
                    exact = needle in (symbol.name.casefold(), symbol.qualified_name.casefold())
                    if exact or common:
                        score = 10.0 if exact else 2.0 * len(common)
                        yield {**asdict(symbol), "score": score}

        matches = heapq.nsmallest(
            limit, candidates(), key=lambda item: (-item["score"], item["path"], item["start_line"])
        )
        return self._search_result(matches, kind="symbol")

    def search_keywords(self, query: str, limit: int = 20) -> ToolResult:
        """Rank literal source lines by query identifier overlap; no semantic matching."""
        limit = _limit(limit)
        terms = set(identifier_terms(_query(query), drop_stop_words=True))
        if not terms:
            return self._search_result([], kind="keyword")

        def candidates():
            for path in self._paths:
                self._check_deadline()
                for number, line in enumerate(self.corpus.text(path).splitlines(), 1):
                    if number % 100 == 0:
                        self._check_deadline()
                    common = terms.intersection(identifier_terms(line))
                    if common:
                        yield {"path": path, "start_line": number, "score": float(len(common))}

        matches = heapq.nsmallest(
            limit, candidates(), key=lambda item: (-item["score"], item["path"], item["start_line"])
        )
        return self._search_result(matches, kind="keyword")

    def read_file(
        self, path: str, start_line: int = 1, end_line: int | None = None, max_lines: int = 120
    ) -> ToolResult:
        validate_source_path(path)
        self._check_deadline()
        max_lines = _limit(max_lines, maximum=200, name="max_lines")
        if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
            raise ValueError("start_line must be a positive integer")
        if path not in self._path_set:
            raise ValueError(f"file is not in the included corpus: {path}")
        lines = self.corpus.text(path).splitlines()
        if not lines:
            if start_line != 1 or end_line not in (None, 1):
                raise ValueError("line range is outside an empty source file")
            return ToolResult({"path": path, "empty": True, "line_count": 0})
        if start_line > len(lines):
            raise ValueError("start_line is outside the source file")
        if end_line is None:
            end_line = min(len(lines), start_line + max_lines - 1)
        if (
            isinstance(end_line, bool)
            or not isinstance(end_line, int)
            or end_line < start_line
            or end_line > len(lines)
        ):
            raise ValueError("end_line must be within the file and at or after start_line")
        if end_line - start_line + 1 > max_lines:
            raise ValueError("requested line range exceeds max_lines")
        if len("\n".join(lines[start_line - 1 : end_line])) > _MAX_READ_CHARS:
            raise ValueError("requested line range exceeds 24000 evidence characters")
        chunk = self.corpus.evidence(path, start_line, end_line, reason="targeted inspection")
        return ToolResult(
            {
                "path": path,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": len(lines),
                "evidence_id": chunk.id,
            },
            (chunk,),
        )

    def inspect_references(self, symbol: str, limit: int = 20) -> ToolResult:
        limit = _limit(limit)
        symbol = _query(symbol, "symbol")
        if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", symbol) is None:
            raise ValueError("symbol must be an identifier or dotted qualified identifier")
        pattern = re.compile(r"(?<![\w$])" + re.escape(symbol) + r"(?![\w$])")
        matches = []
        for path in self._paths:
            self._check_deadline()
            for number, line in enumerate(self.corpus.text(path).splitlines(), 1):
                if pattern.search(line):
                    matches.append({"path": path, "start_line": number, "score": 1.0})
                    if len(matches) == limit:
                        result = self._search_result(matches, kind="textual_identifier_reference")
                        result.data["semantics"] = (
                            "Literal occurrences including definitions/comments"
                        )
                        return result
        result = self._search_result(matches, kind="textual_identifier_reference")
        result.data["semantics"] = "Literal occurrences including definitions/comments"
        return result

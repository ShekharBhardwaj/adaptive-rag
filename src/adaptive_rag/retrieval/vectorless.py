"""Deterministic hierarchy, filename, symbol, keyword, and inspection baseline.

Scores only express the rules below; they are not calibrated probabilities and make
no claim about the best strategy for any benchmark category. The API takes query
content and an included repository corpus, never benchmark answers or labels.
Source parsing is cached only within a request; every query starts with fresh
navigation tools so earlier questions cannot warm its symbol cache.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from .corpus import RepositoryCorpus
from .models import EvidenceChunk, RetrievalOperation, RetrievalRequest, RetrievalResult
from .symbols import identifier_terms
from .tools import RepositoryTools, ToolDeadlineExceeded, ToolResult

_PATH_FEATURE = re.compile(
    r"(?<![\w/])(?:[A-Za-z_][\w.-]*/)+[\w.*?-]+|[\w-]+\.(?:pyi?|js|ts|tsx|jsx|md|rs|go|java|yaml|yml)"
)


@dataclass
class _Candidate:
    path: str
    line: int
    score: float
    reasons: set[str]
    evidence: EvidenceChunk | None = None


class VectorlessRetriever:
    def __init__(self, corpus: RepositoryCorpus) -> None:
        self.corpus = corpus

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.monotonic()
        tools = RepositoryTools(self.corpus)
        operations: list[RetrievalOperation] = []
        errors: list[str] = []
        exhausted: set[str] = set()
        tool_calls = 0
        candidates: dict[tuple[str, int], _Candidate] = {}
        features = identifier_terms(request.query, drop_stop_words=True)
        paths = tuple(
            sorted({path.rstrip(".,;:!?") for path in _PATH_FEATURE.findall(request.query)})
        )
        directories = tuple(sorted({path.rsplit("/", 1)[0] for path in paths if "/" in path}))
        budget = request.budget
        tools.deadline = started + budget.max_seconds

        def timed_out() -> bool:
            if time.monotonic() - started >= budget.max_seconds:
                exhausted.add("max_seconds")
                return True
            return False

        def verify() -> bool:
            before = time.monotonic()
            try:
                self.corpus.verify()
            except ValueError as error:
                errors.append(str(error))
                operations.append(
                    RetrievalOperation(
                        name="verify_snapshot",
                        elapsed_seconds=time.monotonic() - before,
                        error=str(error),
                    )
                )
                return False
            operations.append(
                RetrievalOperation(
                    name="verify_snapshot", elapsed_seconds=time.monotonic() - before
                )
            )
            return True

        def call(name: str, arguments: dict[str, Any]) -> ToolResult | None:
            nonlocal tool_calls
            if timed_out():
                return None
            if tool_calls >= budget.max_tool_calls:
                exhausted.add("max_tool_calls")
                return None
            tool_calls += 1
            before = time.monotonic()
            try:
                result: ToolResult = getattr(tools, name)(**arguments)
            except ToolDeadlineExceeded as error:
                exhausted.add("max_seconds")
                operations.append(
                    RetrievalOperation(
                        name=name,
                        arguments=arguments,
                        elapsed_seconds=time.monotonic() - before,
                        error=str(error),
                    )
                )
                return None
            except ValueError as error:
                errors.append(f"{name}: {error}")
                operations.append(
                    RetrievalOperation(
                        name=name,
                        arguments=arguments,
                        elapsed_seconds=time.monotonic() - before,
                        error=str(error),
                    )
                )
                timed_out()
                return None
            operations.append(
                RetrievalOperation(
                    name=name,
                    arguments=arguments,
                    elapsed_seconds=time.monotonic() - before,
                    returned_ids=tuple(chunk.id for chunk in result.evidence),
                    details=result.data,
                )
            )
            timed_out()
            return result

        def add(result: ToolResult | None, rule: str, multiplier: float) -> None:
            if result is None:
                return
            evidence = {chunk.id: chunk for chunk in result.evidence}
            for match in result.data.get("matches", []):
                path, line = match["path"], match["start_line"]
                key = (path, line)
                hierarchy = 2.0 if any(path.startswith(d + "/") for d in directories) else 0.0
                candidate = candidates.setdefault(key, _Candidate(path, line, hierarchy, set()))
                candidate.score += multiplier * float(match["score"])
                candidate.reasons.add(rule)
                if hierarchy:
                    candidate.reasons.add("query directory prefix")
                chunk = evidence.get(match.get("evidence_id"))
                if chunk is not None:
                    candidate.evidence = chunk

        valid = verify()
        if valid:
            call("list_directory", {"path": ".", "limit": 50})
            for directory in directories[:2]:
                if exhausted:
                    break
                call("list_directory", {"path": directory, "limit": 30})
            file_queries = list(paths[:2])
            if not file_queries:
                # Longest terms tend to retain explicit names over generic query language.
                file_queries = sorted(features, key=lambda value: (-len(value), value))[:2]
            for pattern in file_queries:
                if exhausted:
                    break
                add(call("search_files", {"pattern": pattern, "limit": 20}), "filename", 1.0)
            if not exhausted:
                add(call("search_symbols", {"query": request.query, "limit": 30}), "symbol", 2.0)
            if not exhausted:
                add(call("search_keywords", {"query": request.query, "limit": 30}), "keyword", 1.0)

        chosen: list[EvidenceChunk] = []
        chars = 0
        ranked = sorted(candidates.values(), key=lambda item: (-item.score, item.path, item.line))
        for candidate in ranked:
            if len(chosen) >= request.top_k or not valid:
                break
            if any(
                chunk.path == candidate.path
                and chunk.start_line <= candidate.line <= chunk.end_line
                for chunk in chosen
            ):
                continue
            chunk = candidate.evidence
            if not exhausted:
                source_lines = self.corpus.text(candidate.path).splitlines()
                start = max(1, candidate.line - 3)
                end = min(len(source_lines), candidate.line + 26)
                if end >= start:
                    inspected = call(
                        "read_file",
                        {
                            "path": candidate.path,
                            "start_line": start,
                            "end_line": end,
                            "max_lines": 30,
                        },
                    )
                    if inspected is not None and inspected.evidence:
                        inspected_chunk = inspected.evidence[0]
                        if len(inspected_chunk.text) <= budget.max_evidence_chars - chars:
                            chunk = inspected_chunk
            if chunk is None:
                continue
            remaining = budget.max_evidence_chars - chars
            if len(chunk.text) > remaining:
                # Reduce only at source-line boundaries, keeping the ranked anchor in range.
                lines = self.corpus.text(chunk.path).splitlines()
                start, end = chunk.start_line, chunk.end_line
                while (
                    start <= candidate.line <= end
                    and len("\n".join(lines[start - 1 : end])) > remaining
                ):
                    if end > candidate.line:
                        end -= 1
                    elif start < candidate.line:
                        start += 1
                    else:
                        break
                if start <= candidate.line <= end:
                    chunk = self.corpus.evidence(chunk.path, start, end)
                if len(chunk.text) > remaining:
                    exhausted.add("max_evidence_chars")
                    continue
            chosen.append(
                chunk.model_copy(
                    update={
                        "score": candidate.score,
                        "reason": "; ".join(sorted(candidate.reasons)),
                    }
                )
            )
            chars += len(chunk.text)

        # A changed snapshot invalidates all retained evidence, including partial results.
        if valid and not verify():
            chosen = []
            valid = False
        timed_out()
        return RetrievalResult(
            strategy="vectorless",
            query=request.query,
            repo_commit=self.corpus.commit_sha,
            corpus_fingerprint=self.corpus.fingerprint,
            status="error" if not valid else "budget_exhausted" if exhausted else "completed",
            evidence=tuple(chosen),
            operations=tuple(operations),
            tool_call_count=tool_calls,
            elapsed_seconds=time.monotonic() - started,
            errors=tuple(errors),
            metadata={
                "score_kind": "heuristic",
                "rules": (
                    "filename score + 2 * symbol score + keyword overlap + 2 for query directory"
                ),
                "query_features": {"identifiers": list(features), "paths": list(paths)},
                "exhausted_limits": sorted(exhausted),
                "symbol_fallback": "regex declarations are approximate; no semantic call graph",
                "cache_policy": "source parsing cached within each request; tools reset per query",
            },
        )

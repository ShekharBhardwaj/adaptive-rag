"""Pinned, persistent FAISS cosine retrieval using real embedding providers.

Index directories are immutable. A completed manifest is written last; failed
builds retain their calls and costs in build-failure.json and cannot be loaded.
Each embedding batch has a durable intent and observation in build-events.jsonl.
An unmatched intent means usage is unknown. Explicit recovery can reuse verified
successful batches in a fresh directory; it never modifies or resumes the source.
Only load indexes from trusted local sources: checksums detect corruption, not
malicious replacement of both a manifest and its binary payload.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, TextIO

from pydantic import AwareDatetime, Field, model_validator

from adaptive_rag.generation.client import (
    EmbeddingClient,
    ModelCallNotStarted,
)
from adaptive_rag.generation.client import (
    _usage as _provider_usage,
)
from adaptive_rag.models import CommitSHA, ContentSHA256, ResearchModel
from adaptive_rag.retrieval.chunking import ChunkingConfig, chunk_corpus, parser_versions
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import (
    EvidenceChunk,
    ModelCallRecord,
    RetrievalBudget,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalResult,
    TokenUsage,
)

INDEX_VERSION = "faiss-flat-cosine-v1"


class VectorIndexError(ValueError):
    """An index could not be built or is incompatible with this experiment."""


class IndexBudgetError(VectorIndexError):
    """Index construction exhausted its explicitly separate indexing budget."""


class IndexManifest(ResearchModel):
    schema_version: Literal["1"] = "1"
    index_version: Literal["faiss-flat-cosine-v1"] = INDEX_VERSION
    created_at: AwareDatetime
    repo_commit: CommitSHA
    corpus_fingerprint: ContentSHA256
    embedding_identity: dict[str, Any]
    chunking: ChunkingConfig
    parsers: dict[str, str]
    dimensions: Annotated[int, Field(strict=True, ge=1)]
    chunk_count: Annotated[int, Field(strict=True, ge=1)]
    metric: Literal["normalized_inner_product"] = "normalized_inner_product"
    chunks_sha256: ContentSHA256
    index_sha256: ContentSHA256
    model_calls: tuple[ModelCallRecord, ...]
    model_attempts: Annotated[int, Field(strict=True, ge=1)]
    usage: TokenUsage
    elapsed_seconds: Annotated[float, Field(ge=0)]
    input_token_byte_estimate: Annotated[int, Field(strict=True, ge=0)]
    runtime_versions: dict[str, str]
    reuse_provenance: dict[str, Any] | None = None

    @model_validator(mode="after")
    def complete_accounting(self) -> IndexManifest:
        if not self.model_calls or any(
            call.operation != "embedding"
            or call.error is not None
            or call.model != self.embedding_identity.get("model")
            or call.base_url != self.embedding_identity.get("base_url")
            for call in self.model_calls
        ):
            raise ValueError("A completed index requires successful embedding call records")
        if self.model_attempts != len(self.model_calls):
            raise ValueError("A completed index must account for every model attempt")
        if self.usage.total_tokens is None or self.usage != _usage(list(self.model_calls)):
            raise ValueError("Index usage must match complete provider call accounting")
        if self.reuse_provenance is not None:
            reused = self.reuse_provenance.get("reused_successful_calls")
            new = self.reuse_provenance.get("new_model_attempts")
            if (
                type(reused) is not int
                or type(new) is not int
                or reused < 1
                or new < 0
                or reused + new != self.model_attempts
            ):
                raise ValueError("Index reuse accounting must identify every successful call once")
            if self.reuse_provenance.get("reused_usage") != _usage(
                list(self.model_calls[:reused])
            ).model_dump(mode="json") or self.reuse_provenance.get("new_usage") != _usage(
                list(self.model_calls[reused:])
            ).model_dump(mode="json"):
                raise ValueError("Index reuse token accounting contradicts successful calls")
            if not isinstance(self.reuse_provenance.get("parent_failure_accounting"), dict):
                raise ValueError("Index reuse must retain parent failure accounting separately")
            _validate_reuse_lineage(self, reused)
        return self


def _dependencies() -> tuple[Any, Any]:
    try:
        import faiss
        import numpy as np
    except ImportError as error:
        raise VectorIndexError("Vector retrieval requires the 'vector' dependency extra") from error
    return faiss, np


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_decoder() -> json.JSONDecoder:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON object key in index recovery artifact")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("nonstandard JSON numeric constant in index recovery artifact")

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number in index recovery artifact")
        return parsed

    return json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant, parse_float=finite)


class _RecoveryJSON:
    """Read one failure field/call at a time, without materializing its huge call array."""

    def __init__(self, stream: TextIO):
        self.stream, self.buffer, self.position, self.eof = stream, "", 0, False
        self.decoder = _strict_decoder()

    def _more(self):
        self.buffer = self.buffer[self.position :]
        self.position = 0
        block = self.stream.read(1024 * 1024)
        self.eof = not block
        self.buffer += block

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self._more()

    def take(self, expected):
        if self.peek() != expected:
            raise ValueError("invalid index recovery JSON structure")
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                # A number ending at a read boundary might continue in the next block.
                if end < len(self.buffer) or self.eof:
                    self.position = end
                    return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
            if len(self.buffer) - self.position > 64 * 1024 * 1024:
                raise ValueError("index recovery JSON value exceeds 64 MiB")
            self._more()


def _call_hash(call: ModelCallRecord) -> str:
    return _hash(
        json.dumps(
            call.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )


def _failure_accounting(path: Path) -> tuple[dict[str, Any], list[str], ModelCallRecord | None]:
    metadata: dict[str, Any] = {}
    digests: list[str] = []
    last_call = None
    usage = TokenUsage()
    known_input = known_output = unknown_calls = 0
    with path.open(encoding="utf-8") as stream:
        reader = _RecoveryJSON(stream)
        reader.take("{")
        first = True
        seen: set[str] = set()
        while reader.peek() != "}":
            if not first:
                reader.take(",")
            first = False
            key = reader.value()
            if not isinstance(key, str) or key in seen:
                raise ValueError("duplicate or invalid failure metadata key")
            seen.add(key)
            reader.take(":")
            if key != "model_calls":
                metadata[key] = reader.value()
                continue
            reader.take("[")
            first_call = True
            while reader.peek() != "]":
                if not first_call:
                    reader.take(",")
                first_call = False
                call = ModelCallRecord.model_validate(reader.value())
                digests.append(_call_hash(call))
                usage = usage.add(call.usage)
                if call.usage.input_tokens is not None:
                    known_input += call.usage.input_tokens
                if call.usage.output_tokens is not None:
                    known_output += call.usage.output_tokens
                unknown_calls += call.usage.total_tokens is None
                last_call = call
            reader.take("]")
        reader.take("}")
        if reader.peek():
            raise ValueError("trailing content in failure metadata")
    if "model_calls" not in seen:
        raise ValueError("failure artifact has no call accounting")
    unknown_attempts = metadata.get("unknown_model_attempts")
    attempts = metadata.get("model_attempts")
    if (
        type(unknown_attempts) is not int
        or unknown_attempts not in (0, 1)
        or type(attempts) is not int
        or attempts != len(digests) + unknown_attempts
    ):
        raise ValueError("failure attempt accounting is incomplete or contradictory")
    if unknown_attempts:
        usage = usage.add(TokenUsage(input_tokens=None, output_tokens=None))
    if metadata.get("usage") != usage.model_dump(mode="json"):
        raise ValueError("failure token usage contradicts its provider records")
    metadata["recorded_call_count"] = len(digests)
    metadata["known_input_tokens_subtotal"] = known_input
    metadata["known_output_tokens_subtotal"] = known_output
    metadata["unknown_usage_calls"] = unknown_calls + unknown_attempts
    return metadata, digests, last_call


def _validate_reuse_lineage(manifest: IndexManifest, reused: int) -> None:
    provenance = manifest.reuse_provenance
    source = provenance.get("source_directory")
    if not isinstance(source, str) or not source.strip() or not Path(source).is_absolute():
        raise ValueError("reuse lineage requires an absolute source directory")
    for name in ("source_journal_sha256", "source_failure_sha256"):
        digest = provenance.get(name)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("reuse lineage requires source artifact SHA256 identities")
    parent = provenance["parent_failure_accounting"]
    if (
        parent.get("repo_commit") != manifest.repo_commit
        or parent.get("corpus_fingerprint") != manifest.corpus_fingerprint
        or parent.get("embedding_identity") != manifest.embedding_identity
        or parent.get("chunking") != manifest.chunking.model_dump(mode="json")
        or parent.get("reuse_provenance") is not None
        or parent.get("status") not in {"error", "interrupted", "budget_exhausted"}
    ):
        raise ValueError("reuse lineage parent corpus, model or failure status differs")
    excluded = parent.get("excluded_call_records")
    if not isinstance(excluded, list) or len(excluded) > 1:
        raise ValueError("reuse lineage requires explicit excluded parent call records")
    excluded = [ModelCallRecord.model_validate(call) for call in excluded]
    if any(
        call.operation != "embedding"
        or call.model != manifest.embedding_identity["model"]
        or call.base_url != manifest.embedding_identity["base_url"]
        or call.usage != _provider_usage(call.response, "embedding")
        for call in excluded
    ):
        raise ValueError("reuse lineage excluded call identity or usage differs")
    old_calls = list(manifest.model_calls[:reused]) + excluded
    unknown = parent.get("unknown_model_attempts")
    count = parent.get("recorded_call_count")
    attempts = parent.get("model_attempts")
    if (
        type(unknown) is not int
        or unknown not in (0, 1)
        or type(count) is not int
        or count != len(old_calls)
        or type(attempts) is not int
        or attempts != count + unknown
    ):
        raise ValueError("reuse lineage parent call/attempt counts are inconsistent")
    if parent.get("usage") != _usage(old_calls, unrecorded_attempt=bool(unknown)).model_dump(
        mode="json"
    ):
        raise ValueError("reuse lineage must preserve parent unknown token usage")
    expected = {
        "known_input_tokens_subtotal": sum(
            call.usage.input_tokens for call in old_calls if call.usage.input_tokens is not None
        ),
        "known_output_tokens_subtotal": sum(
            call.usage.output_tokens for call in old_calls if call.usage.output_tokens is not None
        ),
        "unknown_usage_calls": sum(call.usage.total_tokens is None for call in old_calls) + unknown,
    }
    if any(
        type(parent.get(key)) is not int or parent[key] != value for key, value in expected.items()
    ):
        raise ValueError("reuse lineage parent known subtotals or unknown calls are inconsistent")
    elapsed = parent.get("elapsed_seconds")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("reuse lineage must retain finite parent elapsed time")
    inputs = [call.request.get("input") for call in manifest.model_calls[:reused]]
    if any(not isinstance(values, list) or not values for values in inputs) or (
        type(provenance.get("reused_chunks")) is not int
        or provenance["reused_chunks"] != sum(len(values) for values in inputs)
    ):
        raise ValueError("reuse lineage reused chunk count contradicts its call records")


@dataclass(frozen=True)
class _ReusableBatch:
    start: dict[str, Any]
    call: ModelCallRecord
    event_sha256: str


def _recovery_request(call, texts, identity):
    if (
        call.operation != "embedding"
        or call.model != identity.get("model")
        or call.base_url != identity.get("base_url")
    ):
        raise VectorIndexError("recovery call model identity differs")
    expected_request = {"model": identity["model"], "input": texts, "encoding_format": "float"}
    if identity.get("dimensions") is not None:
        expected_request["dimensions"] = identity["dimensions"]
    if call.request != expected_request:
        raise VectorIndexError("recovery call request differs from current embedding inputs")
    if call.usage != _provider_usage(call.response, "embedding"):
        raise VectorIndexError("recovery usage contradicts its provider response")


def _recovered_vectors(call, texts, identity, dimensions):
    _validate_call(call, identity)
    _recovery_request(call, texts, identity)
    if call.usage.total_tokens is None or call.usage.output_tokens != 0:
        raise VectorIndexError("recovery embedding usage is incomplete or contradicts its response")
    rows = call.response.get("data")
    if not isinstance(rows, list) or len(rows) != len(texts):
        raise VectorIndexError("recovery embedding response count differs from input count")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise VectorIndexError("recovery embedding row must be an object")
        index, values = row.get("index"), row.get("embedding")
        if (
            type(index) is not int
            or not 0 <= index < len(texts)
            or index in indexed
            or not isinstance(values, list)
            or any(type(value) not in (int, float) for value in values)
        ):
            raise VectorIndexError("invalid recovery embedding indices or values")
        indexed[index] = values
    return _vectors([indexed[index] for index in range(len(texts))], len(texts), dimensions)


def _reusable_batches(source, corpus, chunks, chunking, identity, batch_size):
    if source.is_symlink() or not source.is_dir():
        raise VectorIndexError("recovery source must be a real existing directory")
    paths = [source / name for name in ("build-events.jsonl", "build-failure.json")]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise VectorIndexError("recovery source requires regular journal and failure artifacts")
    if (source / "manifest.json").exists():
        raise VectorIndexError("recovery source must be an explicitly failed index build")
    journal_hash, failure_hash = (_file_hash(path) for path in paths)
    parent, failure_calls, last_call = _failure_accounting(paths[1])
    if parent.get("reuse_provenance") is not None:
        raise VectorIndexError("recursive recovery of an already recovered source is unsupported")
    if (
        parent.get("schema_version") != "1"
        or parent.get("status") not in {"error", "interrupted", "budget_exhausted"}
        or parent.get("repo_commit") != corpus.commit_sha
        or parent.get("corpus_fingerprint") != corpus.fingerprint
        or parent.get("chunking") != chunking.model_dump(mode="json")
        or parent.get("embedding_identity") != identity
    ):
        raise VectorIndexError("recovery source corpus, model identity or chunking differs")
    batches: list[_ReusableBatch] = []
    pending = terminal = None
    started_count = rejected_count = attempted_bytes = observed_count = 0
    dimensions = identity.get("dimensions")
    decoder = _strict_decoder()
    with paths[0].open("rb") as stream:
        for raw in stream:
            if not raw.endswith(b"\n"):
                raise VectorIndexError("recovery journal has an incomplete JSONL tail")
            event = decoder.decode(raw.decode("utf-8"))
            if not isinstance(event, dict) or terminal is not None:
                raise VectorIndexError("ambiguous recovery events after a terminal batch")
            name = event.get("event")
            if name == "batch_started":
                if pending is not None:
                    raise VectorIndexError("recovery journal contains overlapping batch intents")
                offset = started_count * batch_size
                texts = [chunk.text for chunk in chunks[offset : offset + batch_size]]
                expected = {
                    "batch_id": started_count,
                    "chunk_offset": offset,
                    "input_count": len(texts),
                    "input_token_byte_estimate": _token_estimate(texts),
                    "embedding_identity": identity,
                    "input": texts,
                }
                if not texts or any(event.get(key) != value for key, value in expected.items()):
                    raise VectorIndexError("recovery batch inputs, order or partition differ")
                if any(
                    type(event.get(key)) is not int
                    for key in (
                        "batch_id",
                        "chunk_offset",
                        "input_count",
                        "input_token_byte_estimate",
                    )
                ):
                    raise VectorIndexError("recovery batch counters must be strict integers")
                pending = event
                started_count += 1
                attempted_bytes += expected["input_token_byte_estimate"]
                continue
            if pending is None or name not in {
                "batch_result",
                "batch_error",
                "batch_admission_rejected",
            }:
                raise VectorIndexError("recovery journal result has no unique matching intent")
            if any(
                event.get(key) != pending[key]
                for key in (
                    "batch_id",
                    "chunk_offset",
                    "input_count",
                    "input_token_byte_estimate",
                    "embedding_identity",
                )
            ):
                raise VectorIndexError("recovery batch result contradicts its matching intent")
            if name == "batch_admission_rejected":
                if event.get("attempted") is not False:
                    raise VectorIndexError("recovery rejected admission claims provider delegation")
                rejected_count += 1
                attempted_bytes -= pending["input_token_byte_estimate"]
                terminal, pending = event, None
                continue
            if event.get("attempted") is not True:
                raise VectorIndexError("recovery observation has no delegated attempt")
            call = ModelCallRecord.model_validate(event["call"]) if event.get("call") else None
            if call is not None:
                _recovery_request(call, pending["input"], identity)
                if (
                    observed_count >= len(failure_calls)
                    or _call_hash(call) != failure_calls[observed_count]
                ):
                    raise VectorIndexError("recovery journal and failure call records disagree")
                observed_count += 1
            if name == "batch_error" or call is None:
                terminal, pending = event, None
                continue
            try:
                vectors = _recovered_vectors(call, pending["input"], identity, dimensions)
            except VectorIndexError:
                # A result is recorded before validation by the builder. Such a
                # final response may be accounted for, but is never reusable.
                terminal, pending = event, None
                continue
            dimensions = int(vectors.shape[1])
            batches.append(_ReusableBatch(pending, call, _hash(raw)))
            pending = None
    if (
        parent["model_attempts"] != started_count - rejected_count
        or parent.get("input_token_byte_estimate") != attempted_bytes
        or len(failure_calls) < len(batches)
        or len(failure_calls) > len(batches) + 1
        or (len(failure_calls) > observed_count and pending is None)
    ):
        raise VectorIndexError("recovery journal does not cover the parent failure accounting")
    if not batches:
        raise VectorIndexError("recovery source has no fully verified successful batches")
    if pending is not None and len(failure_calls) > observed_count:
        _recovery_request(last_call, pending["input"], identity)
    if any(
        _file_hash(path) != digest
        for path, digest in zip(paths, (journal_hash, failure_hash), strict=True)
    ):
        raise VectorIndexError("recovery source changed during verification")
    parent["excluded_call_records"] = (
        [last_call.model_dump(mode="json")] if len(failure_calls) > len(batches) else []
    )
    parent["construction_cost_accounting"] = (
        "Successful reused calls are included once in the new manifest; excluded parent calls "
        "and any unrecorded attempts remain additional construction cost. "
        "Unknown usage is not zero."
    )
    return batches, {
        "source_directory": str(source.resolve()),
        "source_journal_sha256": journal_hash,
        "source_failure_sha256": failure_hash,
        "reused_successful_calls": len(batches),
        "reused_chunks": sum(batch.start["input_count"] for batch in batches),
        "reused_usage": _usage([batch.call for batch in batches]).model_dump(mode="json"),
        "parent_failure_accounting": parent,
        "budget_scope": "new provider calls only; elapsed time includes validation/replay",
        "manifest_usage_scope": "successful reused and new embedding calls, counted once",
    }


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _build_event(stream: TextIO, event: dict[str, Any]) -> None:
    encoded = json.dumps(
        {"at": datetime.now(UTC).isoformat(), **event},
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    stream.write(encoded + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _build_failure(directory: Path, failure: dict[str, Any]) -> None:
    with (directory / "build-failure.json").open("xb") as stream:
        stream.write(_json_bytes(failure))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(directory)


def _usage(calls: list[ModelCallRecord], *, unrecorded_attempt: bool = False) -> TokenUsage:
    usage = TokenUsage()
    for call in calls:
        usage = usage.add(call.usage)
    if unrecorded_attempt:
        usage = usage.add(TokenUsage(input_tokens=None, output_tokens=None))
    return usage


def _validate_call(record: ModelCallRecord, identity: dict[str, Any]) -> None:
    if record.operation != "embedding" or record.error is not None:
        raise VectorIndexError("Provider returned an unsuccessful embedding call record")
    if record.model != identity.get("model") or record.base_url != identity.get("base_url"):
        raise VectorIndexError("Embedding call record contradicts configured model identity")


def _token_estimate(texts: list[str]) -> int:
    # This is a conservative preflight estimate, never a reported provider count.
    return sum(len(text.encode("utf-8")) for text in texts)


def _vectors(vectors: Any, expected_count: int, dimensions: int | None = None) -> Any:
    _, np = _dependencies()
    try:
        array = np.asarray(vectors, dtype="float32")
    except (TypeError, ValueError, OverflowError) as error:
        raise VectorIndexError("Embedding vectors must be a rectangular numeric matrix") from error
    if array.ndim != 2 or array.shape[0] != expected_count or array.shape[1] < 1:
        raise VectorIndexError("Embedding count or dimensions do not match the request")
    if dimensions is not None and array.shape[1] != dimensions:
        raise VectorIndexError("Embedding dimensions changed")
    if not np.isfinite(array).all():
        raise VectorIndexError("Embedding vectors contain nonfinite values")
    # Float64 accumulation avoids overflow while normalizing valid float32 values.
    norms = np.linalg.norm(array.astype("float64"), axis=1)
    if (norms == 0).any() or not np.isfinite(norms).all():
        raise VectorIndexError("Embedding vectors must have nonzero finite norms")
    return np.ascontiguousarray(array / norms[:, None], dtype="float32")


class VectorRetriever:
    """A flat cosine index with separate indexing and per-query accounting."""

    def __init__(
        self,
        corpus: RepositoryCorpus,
        client: EmbeddingClient,
        *,
        chunking: ChunkingConfig | None = None,
        batch_size: int = 64,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self.corpus = corpus
        self.client = client
        self.chunking = chunking or ChunkingConfig()
        self.batch_size = batch_size
        self._manifest: IndexManifest | None = None
        self._index: Any = None
        self._chunks: tuple[EvidenceChunk, ...] = ()

    def build_index(
        self,
        directory: Path,
        *,
        budget: RetrievalBudget | None = None,
        reuse_from: Path | None = None,
    ) -> IndexManifest:
        """Build once; leave a failure record if anything fails after creation.

        No provider call starts unless its UTF-8 byte estimate fits the remaining
        token budget. Missing provider usage prevents any subsequent call.
        Every delegated batch is journaled before and after the call. Interrupted
        builds retain accounting but cannot be resumed or loaded. Explicit reuse
        verifies a failed build's successful prefix before any new provider call.
        Reused calls retain their original usage; admission budgets charge only
        newly delegated calls, while the wall-clock budget includes verification.
        """
        budget = budget or RetrievalBudget()
        directory = Path(directory)
        if reuse_from is not None:
            reuse_from = Path(reuse_from)
            if directory.resolve().is_relative_to(reuse_from.resolve()):
                raise VectorIndexError("recovery output must be outside the immutable source")
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise VectorIndexError("Index directory must be new and writable") from error
        self._manifest, self._index, self._chunks = None, None, ()
        started = time.perf_counter()
        calls: list[ModelCallRecord] = []
        new_calls: list[ModelCallRecord] = []
        reuse_provenance = None
        byte_estimate = 0
        model_attempts = 0
        unrecorded_attempt = False
        identity: dict[str, Any] = {}
        journal: TextIO | None = None
        journal_errors: list[str] = []
        try:
            journal = (directory / "build-events.jsonl").open("x", encoding="utf-8")
            journal.flush()
            os.fsync(journal.fileno())
            _sync_directory(directory)
            identity = deepcopy(self.client.identity)
            faiss, np = _dependencies()
            self.corpus.verify()
            chunks = chunk_corpus(self.corpus, self.chunking)
            if not chunks:
                raise VectorIndexError("Cannot index a corpus with no nonempty source files")
            index = None
            dimensions = identity.get("dimensions")
            if dimensions is not None and (
                isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1
            ):
                raise VectorIndexError("Declared embedding dimensions must be a positive integer")
            reused_batches = []
            if reuse_from is not None:
                reused_batches, reuse_provenance = _reusable_batches(
                    reuse_from, self.corpus, chunks, self.chunking, identity, self.batch_size
                )
            for offset in range(0, len(chunks), self.batch_size):
                texts = [chunk.text for chunk in chunks[offset : offset + self.batch_size]]
                estimate = _token_estimate(texts)
                elapsed = time.perf_counter() - started
                if offset // self.batch_size < len(reused_batches):
                    batch = reused_batches[offset // self.batch_size]
                    if time.perf_counter() - started >= budget.max_seconds:
                        raise IndexBudgetError(
                            "Indexing time budget exhausted while replaying batches"
                        )
                    vectors = _recovered_vectors(batch.call, texts, identity, dimensions)
                    _build_event(
                        journal,
                        {
                            "event": "batch_reused",
                            "batch_id": offset // self.batch_size,
                            "source_directory": reuse_provenance["source_directory"],
                            "source_journal_sha256": reuse_provenance["source_journal_sha256"],
                            "source_result_event_sha256": batch.event_sha256,
                            "start": batch.start,
                            "call": batch.call.model_dump(mode="json"),
                            "attempted": False,
                            "provider_usage_scope": "original successful source call; not rebilled",
                        },
                    )
                    calls.append(batch.call)
                    byte_estimate += estimate
                    if index is None:
                        dimensions = int(vectors.shape[1])
                        index = faiss.IndexFlatIP(dimensions)
                    index.add(vectors)
                    continue
                usage = _usage(new_calls)
                if usage.total_tokens is None:
                    raise IndexBudgetError(
                        "Provider usage is unknown; no further calls are allowed"
                    )
                if (
                    model_attempts >= budget.max_model_calls
                    or usage.total_tokens + estimate > budget.max_tokens
                    or elapsed >= budget.max_seconds
                ):
                    raise IndexBudgetError("Indexing budget exhausted before embedding batch")
                if self.client.identity != identity:
                    raise VectorIndexError("Embedding client identity changed during index build")
                event = {
                    "batch_id": offset // self.batch_size,
                    "chunk_offset": offset,
                    "input_count": len(texts),
                    "input_token_byte_estimate": estimate,
                    "embedding_identity": identity,
                }
                _build_event(
                    journal,
                    {
                        "event": "batch_started",
                        **event,
                        "input": texts,
                        # Durable intent alone does not prove provider delegation or billing.
                        "attempted": None,
                    },
                )
                # Writing durable intent consumes time too; never delegate after the deadline.
                elapsed = time.perf_counter() - started
                if elapsed >= budget.max_seconds:
                    _build_event(
                        journal,
                        {
                            "event": "batch_admission_rejected",
                            **event,
                            "attempted": False,
                            "error": "Indexing deadline exhausted before provider delegation",
                        },
                    )
                    raise IndexBudgetError("Indexing deadline exhausted before provider delegation")
                model_attempts += 1
                byte_estimate += estimate
                try:
                    response = self.client.embed(texts, timeout=budget.max_seconds - elapsed)
                except ModelCallNotStarted as error:
                    model_attempts -= 1
                    byte_estimate -= estimate
                    _build_event(
                        journal,
                        {
                            "event": "batch_admission_rejected",
                            **event,
                            "attempted": False,
                            "error": str(error),
                        },
                    )
                    raise IndexBudgetError(f"Embedding admission rejected: {error}") from error
                except BaseException as error:
                    if (
                        isinstance(error, (KeyboardInterrupt, SystemExit))
                        and getattr(error, "_adaptive_rag_not_started", False) is True
                    ):
                        model_attempts -= 1
                        byte_estimate -= estimate
                        try:
                            _build_event(
                                journal,
                                {
                                    "event": "batch_admission_rejected",
                                    **event,
                                    "attempted": False,
                                    "exception_type": type(error).__name__,
                                    "error": str(error),
                                    "unknown_usage": False,
                                    "interrupted": True,
                                },
                            )
                        except (OSError, ValueError) as journal_error:
                            journal_errors.append(str(journal_error))
                        raise
                    record = getattr(error, "record", None)
                    if isinstance(record, ModelCallRecord):
                        calls.append(record.model_copy(deep=True))
                        new_calls.append(calls[-1])
                    else:
                        record = None
                        unrecorded_attempt = True
                    try:
                        _build_event(
                            journal,
                            {
                                "event": "batch_error",
                                **event,
                                "attempted": True,
                                "call": record.model_dump(mode="json") if record else None,
                                "exception_type": type(error).__name__,
                                "error": str(error),
                                "unknown_usage": record is None
                                or record.usage.total_tokens is None,
                                "interrupted": isinstance(error, (KeyboardInterrupt, SystemExit)),
                            },
                        )
                    except (OSError, ValueError) as journal_error:
                        # Preserve the provider exception, especially a soft interruption.
                        journal_errors.append(str(journal_error))
                    raise
                if not isinstance(getattr(response, "call", None), ModelCallRecord):
                    unrecorded_attempt = True
                    _build_event(
                        journal,
                        {
                            "event": "batch_error",
                            **event,
                            "attempted": True,
                            "call": None,
                            "error": "Embedding attempt returned no valid call record",
                            "unknown_usage": True,
                            "interrupted": False,
                        },
                    )
                    raise VectorIndexError("Embedding attempt returned no valid call record")
                calls.append(response.call.model_copy(deep=True))
                new_calls.append(calls[-1])
                _build_event(
                    journal,
                    {
                        "event": "batch_result",
                        **event,
                        "attempted": True,
                        "call": calls[-1].model_dump(mode="json"),
                        "unknown_usage": calls[-1].usage.total_tokens is None,
                    },
                )
                _validate_call(response.call, identity)
                vectors = _vectors(response.vectors, len(texts), dimensions)
                if index is None:
                    dimensions = int(vectors.shape[1])
                    index = faiss.IndexFlatIP(dimensions)
                index.add(vectors)
                usage = _usage(new_calls)
                if usage.total_tokens is None:
                    raise IndexBudgetError("Provider usage is unknown; index remains incomplete")
                if (
                    usage.total_tokens > budget.max_tokens
                    or time.perf_counter() - started > budget.max_seconds
                ):
                    raise IndexBudgetError("Indexing budget exceeded by provider response")
            assert index is not None and dimensions is not None
            chunks_bytes = _json_bytes([chunk.model_dump(mode="json") for chunk in chunks])
            index_bytes = faiss.serialize_index(index).tobytes()
            (directory / "chunks.json").write_bytes(chunks_bytes)
            (directory / "index.faiss").write_bytes(index_bytes)
            self.corpus.verify()
            if self.client.identity != identity:
                raise VectorIndexError("Embedding client identity changed during index build")
            if time.perf_counter() - started > budget.max_seconds:
                raise IndexBudgetError("Indexing time budget exhausted while saving artifacts")
            manifest = IndexManifest(
                created_at=datetime.now(UTC),
                repo_commit=self.corpus.commit_sha,
                corpus_fingerprint=self.corpus.fingerprint,
                embedding_identity=identity,
                chunking=self.chunking,
                parsers=parser_versions(),
                dimensions=dimensions,
                chunk_count=len(chunks),
                chunks_sha256=_hash(chunks_bytes),
                index_sha256=_hash(index_bytes),
                model_calls=tuple(calls),
                model_attempts=len(calls),
                usage=_usage(calls),
                elapsed_seconds=time.perf_counter() - started,
                input_token_byte_estimate=byte_estimate,
                runtime_versions={"faiss": faiss.__version__, "numpy": np.__version__},
                reuse_provenance={
                    **reuse_provenance,
                    "new_model_attempts": model_attempts,
                    "new_usage": _usage(new_calls).model_dump(mode="json"),
                }
                if reuse_provenance is not None
                else None,
            )
            (directory / "manifest.json").write_bytes(_json_bytes(manifest.model_dump(mode="json")))
            self._manifest, self._index, self._chunks = manifest, index, chunks
            return manifest
        except BaseException as error:
            interrupted = isinstance(error, (KeyboardInterrupt, SystemExit))
            failure = {
                "schema_version": "1",
                "status": "interrupted"
                if interrupted
                else "budget_exhausted"
                if isinstance(error, IndexBudgetError)
                else "error",
                "repo_commit": self.corpus.commit_sha,
                "corpus_fingerprint": self.corpus.fingerprint,
                "embedding_identity": identity,
                "chunking": self.chunking.model_dump(mode="json"),
                "model_calls": [call.model_dump(mode="json") for call in calls],
                "model_attempts": model_attempts + len(calls) - len(new_calls),
                "unknown_model_attempts": int(unrecorded_attempt),
                "usage": _usage(calls, unrecorded_attempt=unrecorded_attempt).model_dump(
                    mode="json"
                ),
                "elapsed_seconds": time.perf_counter() - started,
                "input_token_byte_estimate": byte_estimate,
                "errors": [str(error)],
                "exception_type": type(error).__name__,
                "journal_errors": journal_errors,
                "parsers": parser_versions(),
                "reuse_provenance": {
                    **reuse_provenance,
                    "new_model_attempts": model_attempts,
                    "new_usage": _usage(
                        new_calls, unrecorded_attempt=unrecorded_attempt
                    ).model_dump(mode="json"),
                    "replayed_successful_calls": len(calls) - len(new_calls),
                }
                if reuse_provenance is not None
                else None,
            }
            try:
                _build_failure(directory, failure)
            except (OSError, ValueError):
                # Retain the triggering exception; the journal still preserves prior calls.
                if not interrupted:
                    raise
            if not isinstance(error, Exception):
                raise
            if isinstance(error, VectorIndexError):
                raise
            raise VectorIndexError(f"Index build failed: {error}") from error
        finally:
            if journal is not None:
                journal.close()

    def load_index(self, directory: Path) -> IndexManifest:
        """Verify provenance and hashes before passing bytes to FAISS."""
        directory = Path(directory)
        self._manifest, self._index, self._chunks = None, None, ()
        try:
            faiss, np = _dependencies()
            self.corpus.verify()
            if directory.is_symlink() or not directory.is_dir():
                raise VectorIndexError("Index directory must be a real local directory")
            for name in ("manifest.json", "chunks.json", "index.faiss"):
                if (directory / name).is_symlink() or not (directory / name).is_file():
                    raise VectorIndexError(f"Index artifact is missing or a symlink: {name}")
            if (directory / "build-failure.json").exists():
                raise VectorIndexError("Incomplete or unsuccessful indexes cannot be loaded")
            manifest = IndexManifest.model_validate_json((directory / "manifest.json").read_bytes())
            if (
                manifest.repo_commit != self.corpus.commit_sha
                or manifest.corpus_fingerprint != self.corpus.fingerprint
            ):
                raise VectorIndexError("Index corpus or pinned commit mismatch")
            if manifest.embedding_identity != self.client.identity:
                raise VectorIndexError("Index embedding model identity mismatch")
            if manifest.runtime_versions != {"faiss": faiss.__version__, "numpy": np.__version__}:
                raise VectorIndexError("Index FAISS or NumPy runtime version mismatch")
            if manifest.chunking != self.chunking or manifest.parsers != parser_versions():
                raise VectorIndexError("Index chunking or parser version mismatch")
            chunks_bytes = (directory / "chunks.json").read_bytes()
            index_bytes = (directory / "index.faiss").read_bytes()
            if (
                _hash(chunks_bytes) != manifest.chunks_sha256
                or _hash(index_bytes) != manifest.index_sha256
            ):
                raise VectorIndexError("Index artifact checksum mismatch")
            raw_chunks = json.loads(chunks_bytes)
            if not isinstance(raw_chunks, list):
                raise VectorIndexError("Index chunks must be a JSON list")
            chunks = tuple(EvidenceChunk.model_validate(chunk) for chunk in raw_chunks)
            if len(chunks) != manifest.chunk_count or len({chunk.id for chunk in chunks}) != len(
                chunks
            ):
                raise VectorIndexError("Index chunk count or unique identifiers mismatch")
            expected = chunk_corpus(self.corpus, self.chunking)
            if chunks != expected:
                raise VectorIndexError("Index source chunks, provenance, or row order mismatch")
            index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype="uint8"))
            if (
                type(index).__name__ != "IndexFlatIP"
                or index.metric_type != faiss.METRIC_INNER_PRODUCT
                or index.d != manifest.dimensions
                or index.ntotal != manifest.chunk_count
            ):
                raise VectorIndexError("FAISS index type, dimensions, or row count mismatch")
            rows = index.reconstruct_n(0, index.ntotal)
            norms = np.linalg.norm(rows.astype("float64"), axis=1)
            if not np.isfinite(rows).all() or not np.allclose(norms, 1.0, atol=1e-5):
                raise VectorIndexError("FAISS rows must be finite unit vectors")
            self._manifest, self._index, self._chunks = manifest, index, chunks
            return manifest
        except VectorIndexError:
            raise
        except Exception as error:
            raise VectorIndexError(f"Could not load complete index: {error}") from error

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        calls: list[ModelCallRecord] = []
        operations: list[RetrievalOperation] = []
        evidence: tuple[EvidenceChunk, ...] = ()
        status = "completed"
        errors: tuple[str, ...] = ()
        estimate = _token_estimate([request.query])
        tool_calls = 0
        model_attempts = 0
        unrecorded_attempt = False
        try:
            if self._index is None or self._manifest is None:
                raise VectorIndexError("Build or load a compatible index before retrieval")
            if self.client.identity != self._manifest.embedding_identity:
                raise VectorIndexError("Embedding model identity changed after loading index")
            self.corpus.verify()
            elapsed = time.perf_counter() - started
            budget = request.budget
            if (
                budget.max_model_calls < 1
                or budget.max_tool_calls < 1
                or estimate > budget.max_tokens
                or elapsed >= budget.max_seconds
            ):
                raise IndexBudgetError("Retrieval budget exhausted before query embedding")
            model_attempts += 1
            try:
                response = self.client.embed([request.query], timeout=budget.max_seconds - elapsed)
            except ModelCallNotStarted as error:
                model_attempts -= 1
                raise IndexBudgetError(f"Embedding admission rejected: {error}") from error
            except Exception as error:
                record = getattr(error, "record", None)
                if isinstance(record, ModelCallRecord):
                    calls.append(record)
                else:
                    unrecorded_attempt = True
                raise
            if not isinstance(getattr(response, "call", None), ModelCallRecord):
                unrecorded_attempt = True
                raise VectorIndexError("Embedding attempt returned no valid call record")
            calls.append(response.call)
            _validate_call(response.call, self._manifest.embedding_identity)
            if self.client.identity != self._manifest.embedding_identity:
                raise VectorIndexError("Embedding client identity changed during retrieval")
            usage = _usage(calls)
            if usage.total_tokens is None:
                raise IndexBudgetError("Provider usage is unknown; no search was performed")
            if (
                usage.total_tokens > budget.max_tokens
                or time.perf_counter() - started > budget.max_seconds
            ):
                raise IndexBudgetError("Retrieval budget exceeded by embedding response")
            vector = _vectors(response.vectors, 1, self._manifest.dimensions)
            search_started = time.perf_counter()
            tool_calls = 1
            scores, indices = self._index.search(vector, len(self._chunks))
            # FAISS ties need a stable source-order tiebreak for reproducibility.
            ranked = sorted(
                (
                    (float(score), int(row))
                    for score, row in zip(scores[0], indices[0], strict=True)
                ),
                key=lambda match: (-match[0], match[1]),
            )
            chosen: list[EvidenceChunk] = []
            used_chars = 0
            for score, row in ranked:
                if row < 0 or row >= len(self._chunks) or not math.isfinite(score):
                    raise VectorIndexError("FAISS returned an invalid result")
                chunk = self._chunks[row]
                if used_chars + len(chunk.text) > budget.max_evidence_chars:
                    continue
                chosen.append(
                    chunk.model_copy(
                        update={"score": score, "reason": "normalized cosine similarity"}
                    )
                )
                used_chars += len(chunk.text)
                if len(chosen) == request.top_k:
                    break
            evidence = tuple(chosen)
            operations.append(
                RetrievalOperation(
                    name="faiss.search",
                    arguments={"top_k": request.top_k, "candidate_count": len(self._chunks)},
                    elapsed_seconds=time.perf_counter() - search_started,
                    returned_ids=tuple(chunk.id for chunk in evidence),
                )
            )
            if time.perf_counter() - started > budget.max_seconds:
                raise IndexBudgetError("Retrieval time budget exhausted during search")
            if len(evidence) < min(request.top_k, len(self._chunks)):
                status = "budget_exhausted"
                errors = ("Evidence character budget excluded candidate chunks",)
        except IndexBudgetError as error:
            status, errors = "budget_exhausted", (str(error),)
        except Exception as error:
            status, errors = "error", (str(error),)
        verification_started = time.perf_counter()
        try:
            self.corpus.verify()
        except Exception as error:
            evidence = ()
            status = "error"
            errors += (f"Final source integrity verification failed: {error}",)
            operations.append(
                RetrievalOperation(
                    name="verify_snapshot",
                    elapsed_seconds=time.perf_counter() - verification_started,
                    error=str(error),
                )
            )
        else:
            operations.append(
                RetrievalOperation(
                    name="verify_snapshot",
                    elapsed_seconds=time.perf_counter() - verification_started,
                )
            )
            if status == "completed" and time.perf_counter() - started > request.budget.max_seconds:
                status = "budget_exhausted"
                errors += ("Retrieval time budget exhausted during final source verification",)
        return RetrievalResult(
            strategy="vector",
            query=request.query,
            repo_commit=self.corpus.commit_sha,
            corpus_fingerprint=self.corpus.fingerprint,
            status=status,
            evidence=evidence,
            operations=tuple(operations),
            model_calls=tuple(calls),
            usage=_usage(calls, unrecorded_attempt=unrecorded_attempt),
            tool_call_count=tool_calls,
            elapsed_seconds=time.perf_counter() - started,
            errors=errors,
            metadata={
                "input_token_byte_estimate": estimate if model_attempts else 0,
                "model_attempts": model_attempts,
                "index_version": INDEX_VERSION,
                "indexing_costs_included": False,
            },
        )

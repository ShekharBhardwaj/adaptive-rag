"""FAISS integration uses deterministic embeddings only as test fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from adaptive_rag.generation.client import EmbeddingResponse, ModelClientError
from adaptive_rag.retrieval.chunking import ChunkingConfig
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import (
    ModelCallRecord,
    RetrievalBudget,
    RetrievalRequest,
    TokenUsage,
)
from adaptive_rag.retrieval.vector import IndexBudgetError, VectorIndexError, VectorRetriever

pytest.importorskip("faiss")
pytest.importorskip("numpy")


@pytest.fixture
def corpus(tmp_path: Path) -> RepositoryCorpus:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "apple.py").write_text("def apple():\n    return 'apple fruit'\n", encoding="utf-8")
    (root / "banana.py").write_text("def banana():\n    return 'banana fruit'\n", encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=environment,
        ).stdout.strip()

    git("init", "--quiet", "--template=")
    git("add", "--all")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return RepositoryCorpus.from_repository(root, git("rev-parse", "HEAD"))


class FixtureEmbeddings:
    """Explicitly synthetic vectors; this class never ships in framework code."""

    def __init__(self, *, identity: str = "fixture-v1", malformed: str | None = None):
        self.name = identity
        self.malformed = malformed
        self.requests: list[list[str]] = []
        self.unknown_usage = False
        self.fail = False

    @property
    def identity(self) -> dict:
        return {"base_url": "https://example.invalid/v1", "model": self.name, "dimensions": 2}

    def embed(self, texts: list[str], *, timeout: float) -> EmbeddingResponse:
        assert timeout > 0
        self.requests.append(texts)
        call = ModelCallRecord(
            operation="embedding",
            model=self.name,
            base_url="https://example.invalid/v1",
            request={"input": texts},
            response={"fixture": True},
            usage=TokenUsage(
                input_tokens=None if self.unknown_usage else len(texts), output_tokens=0
            ),
            elapsed_seconds=0.001,
        )
        if self.fail:
            raise ModelClientError(
                "fixture provider failure", call.model_copy(update={"error": "fixture"})
            )
        vectors = tuple((1.0, 0.0) if "apple" in text else (0.0, 1.0) for text in texts)
        if self.malformed == "count":
            vectors = vectors[:-1]
        elif self.malformed == "zero":
            vectors = tuple((0.0, 0.0) for _ in texts)
        elif self.malformed == "nan":
            vectors = tuple((float("nan"), 1.0) for _ in texts)
        elif self.malformed == "dimension":
            vectors = tuple((1.0, 2.0, 3.0) for _ in texts)
        # Bypass response validation solely to test a misbehaving custom client.
        return EmbeddingResponse.model_construct(vectors=vectors, call=call)


def test_real_faiss_index_roundtrip_preserves_refs_and_separates_indexing_costs(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    client = FixtureEmbeddings()
    index = tmp_path / "index"
    builder = VectorRetriever(corpus, client, batch_size=1)
    manifest = builder.build_index(index)
    assert manifest.chunk_count == 2
    assert manifest.dimensions == 2
    assert len(manifest.model_calls) == 2
    assert manifest.usage.input_tokens == 2
    assert manifest.corpus_fingerprint == corpus.fingerprint
    retriever = VectorRetriever(corpus, client)
    assert retriever.load_index(index) == manifest
    result = retriever.retrieve(RetrievalRequest(query="apple", top_k=1))
    assert result.status == "completed"
    assert result.evidence[0].path == "apple.py"
    assert result.evidence[0].score == pytest.approx(1.0)
    assert result.evidence[0].start_line == 1
    assert result.evidence[0].end_line == 2
    assert len(result.model_calls) == 1
    assert result.usage.input_tokens == 1
    assert result.tool_call_count == 1
    assert result.metadata["indexing_costs_included"] is False
    assert result.operations[0].returned_ids == (result.evidence[0].id,)
    with pytest.raises(VectorIndexError, match="new and writable"):
        builder.build_index(index)


def test_queries_require_an_index(corpus: RepositoryCorpus) -> None:
    result = VectorRetriever(corpus, FixtureEmbeddings()).retrieve(RetrievalRequest(query="apple"))
    assert result.status == "error"
    assert result.model_calls == ()


@pytest.mark.parametrize("artifact", ["index.faiss", "chunks.json"])
def test_load_refuses_corruption_before_deserializing(
    corpus: RepositoryCorpus, tmp_path: Path, artifact: str
) -> None:
    retriever = VectorRetriever(corpus, FixtureEmbeddings())
    index = tmp_path / "index"
    retriever.build_index(index)
    (index / artifact).write_bytes(b"damaged payload")
    with pytest.raises(VectorIndexError, match="checksum"):
        retriever.load_index(index)
    assert retriever.retrieve(RetrievalRequest(query="apple")).status == "error"


def test_load_refuses_model_chunking_and_corpus_mismatches(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    index = tmp_path / "index"
    VectorRetriever(corpus, FixtureEmbeddings()).build_index(index)
    with pytest.raises(VectorIndexError, match="model identity"):
        VectorRetriever(corpus, FixtureEmbeddings(identity="different")).load_index(index)
    with pytest.raises(VectorIndexError, match="chunking"):
        VectorRetriever(
            corpus, FixtureEmbeddings(), chunking=ChunkingConfig(max_lines=60)
        ).load_index(index)
    manifest_path = index / "manifest.json"
    body = json.loads(manifest_path.read_text())
    body["corpus_fingerprint"] = "a" * 64
    manifest_path.write_text(json.dumps(body))
    with pytest.raises(VectorIndexError, match="corpus"):
        VectorRetriever(corpus, FixtureEmbeddings()).load_index(index)


def test_load_rejects_reordered_chunks_even_with_updated_checksum(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    index = tmp_path / "index"
    retriever = VectorRetriever(corpus, FixtureEmbeddings())
    retriever.build_index(index)
    chunks_path = index / "chunks.json"
    chunks = json.loads(chunks_path.read_text())
    chunks.reverse()
    chunks_path.write_text(json.dumps(chunks))
    manifest_path = index / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chunks_sha256"] = hashlib.sha256(chunks_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(VectorIndexError, match="row order"):
        retriever.load_index(index)


@pytest.mark.parametrize("malformed", ["count", "zero", "nan", "dimension"])
def test_failed_build_preserves_calls_and_never_becomes_loadable(
    corpus: RepositoryCorpus, tmp_path: Path, malformed: str
) -> None:
    index = tmp_path / "index"
    retriever = VectorRetriever(corpus, FixtureEmbeddings(malformed=malformed))
    with pytest.raises(VectorIndexError):
        retriever.build_index(index)
    failure = json.loads((index / "build-failure.json").read_text())
    assert len(failure["model_calls"]) == 1
    assert failure["usage"]["input_tokens"] == 2
    assert not (index / "manifest.json").exists()
    with pytest.raises(VectorIndexError):
        retriever.load_index(index)


def test_build_token_budget_is_checked_before_call_and_keeps_failure(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    index = tmp_path / "index"
    client = FixtureEmbeddings()
    with pytest.raises(IndexBudgetError):
        VectorRetriever(corpus, client).build_index(index, budget=RetrievalBudget(max_tokens=1))
    assert client.requests == []
    failure = json.loads((index / "build-failure.json").read_text())
    assert failure["status"] == "budget_exhausted"
    assert failure["usage"]["input_tokens"] == 0


def test_build_model_call_budget_preserves_partial_calls(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    index = tmp_path / "index"
    client = FixtureEmbeddings()
    with pytest.raises(IndexBudgetError):
        VectorRetriever(corpus, client, batch_size=1).build_index(
            index, budget=RetrievalBudget(max_model_calls=1)
        )
    assert len(client.requests) == 1
    assert len(json.loads((index / "build-failure.json").read_text())["model_calls"]) == 1


def test_build_unknown_usage_is_preserved_and_stops_further_calls(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    index = tmp_path / "index"
    client = FixtureEmbeddings()
    client.unknown_usage = True
    with pytest.raises(IndexBudgetError, match="unknown"):
        VectorRetriever(corpus, client, batch_size=1).build_index(index)
    assert len(client.requests) == 1
    assert json.loads((index / "build-failure.json").read_text())["usage"]["input_tokens"] is None


def test_provider_failure_preserves_its_record(corpus: RepositoryCorpus, tmp_path: Path) -> None:
    index = tmp_path / "index"
    client = FixtureEmbeddings()
    retriever = VectorRetriever(corpus, client)
    retriever.build_index(index)
    client.fail = True
    result = retriever.retrieve(RetrievalRequest(query="apple"))
    assert result.status == "error"
    assert len(result.model_calls) == 1
    assert result.model_calls[0].error == "fixture"


@pytest.mark.parametrize(
    "budget",
    [
        RetrievalBudget(max_model_calls=0),
        RetrievalBudget(max_tool_calls=0),
        RetrievalBudget(max_tokens=1),
    ],
)
def test_query_budget_prevents_provider_call(
    corpus: RepositoryCorpus, tmp_path: Path, budget: RetrievalBudget
) -> None:
    client = FixtureEmbeddings()
    retriever = VectorRetriever(corpus, client)
    retriever.build_index(tmp_path / "index")
    before = len(client.requests)
    result = retriever.retrieve(RetrievalRequest(query="apple", budget=budget))
    assert result.status == "budget_exhausted"
    assert len(client.requests) == before
    assert result.usage.total_tokens == 0


def test_evidence_budget_does_not_truncate_source_lines(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    retriever = VectorRetriever(corpus, FixtureEmbeddings())
    retriever.build_index(tmp_path / "index")
    result = retriever.retrieve(
        RetrievalRequest(query="apple", top_k=2, budget=RetrievalBudget(max_evidence_chars=1))
    )
    assert result.status == "budget_exhausted"
    assert result.evidence == ()
    assert result.tool_call_count == 1


def test_query_rejects_dimensions_unknown_usage_and_changed_identity(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    client = FixtureEmbeddings()
    retriever = VectorRetriever(corpus, client)
    retriever.build_index(tmp_path / "index")
    client.malformed = "dimension"
    assert retriever.retrieve(RetrievalRequest(query="apple")).status == "error"
    client.malformed = None
    client.unknown_usage = True
    result = retriever.retrieve(RetrievalRequest(query="apple"))
    assert result.status == "budget_exhausted"
    assert result.usage.input_tokens is None
    assert result.tool_call_count == 0
    client.name = "different"
    result = retriever.retrieve(RetrievalRequest(query="apple"))
    assert result.status == "error"
    assert result.model_calls == ()


def test_equal_similarity_ties_use_source_order(corpus: RepositoryCorpus, tmp_path: Path) -> None:
    retriever = VectorRetriever(corpus, FixtureEmbeddings())
    retriever.build_index(tmp_path / "index")
    result = retriever.retrieve(RetrievalRequest(query="apple", top_k=2))
    assert [item.path for item in result.evidence] == ["apple.py", "banana.py"]
    # Both documents have equal dot products against the diagonal query vector.
    original = retriever.client.embed

    def diagonal(texts: list[str], *, timeout: float) -> EmbeddingResponse:
        response = original(texts, timeout=timeout)
        return response.model_copy(update={"vectors": ((1.0, 1.0),)})

    retriever.client.embed = diagonal
    result = retriever.retrieve(RetrievalRequest(query="tie", top_k=2))
    assert [item.path for item in result.evidence] == ["apple.py", "banana.py"]


def test_query_final_verification_rejects_provider_side_source_changes(
    corpus: RepositoryCorpus, tmp_path: Path
) -> None:
    client = FixtureEmbeddings()
    retriever = VectorRetriever(corpus, client)
    retriever.build_index(tmp_path / "index")
    original = client.embed

    def mutate(texts: list[str], *, timeout: float) -> EmbeddingResponse:
        response = original(texts, timeout=timeout)
        (corpus.repository / "injected.txt").write_text("changed during request")
        return response

    client.embed = mutate
    result = retriever.retrieve(RetrievalRequest(query="apple", top_k=1))
    assert result.status == "error"
    assert result.evidence == ()
    assert len(result.model_calls) == 1
    assert result.usage.input_tokens == 1
    assert result.operations[-1].name == "verify_snapshot"
    assert result.operations[-1].error is not None


@pytest.mark.parametrize(
    "field,value", [("model", "other-provider-model"), ("base_url", "https://other.invalid/v1")]
)
@pytest.mark.parametrize("mode", ["build", "query"])
def test_vector_rejects_contradictory_embedding_call_identity(
    corpus: RepositoryCorpus, tmp_path: Path, field: str, value: str, mode: str
) -> None:
    client = FixtureEmbeddings()
    retriever = VectorRetriever(corpus, client)
    index = tmp_path / "index"
    if mode == "query":
        retriever.build_index(index)
    original = client.embed

    def wrong_identity(texts: list[str], *, timeout: float) -> EmbeddingResponse:
        response = original(texts, timeout=timeout)
        return response.model_copy(update={"call": response.call.model_copy(update={field: value})})

    client.embed = wrong_identity
    if mode == "build":
        with pytest.raises(VectorIndexError, match="identity"):
            retriever.build_index(index)
        failure = json.loads((index / "build-failure.json").read_text())
        assert failure["model_attempts"] == 1
        assert len(failure["model_calls"]) == 1
        assert failure["model_calls"][0][field] == value
        assert not (index / "manifest.json").exists()
    else:
        result = retriever.retrieve(RetrievalRequest(query="apple"))
        assert result.status == "error"
        assert result.evidence == ()
        assert result.metadata["model_attempts"] == 1
        assert result.model_calls[0].model_dump()[field] == value
        assert result.usage.input_tokens == 1


@pytest.mark.parametrize("mode", ["build", "query"])
def test_unrecorded_embedding_attempt_has_unknown_usage(
    corpus: RepositoryCorpus, tmp_path: Path, mode: str
) -> None:
    client = FixtureEmbeddings()
    retriever = VectorRetriever(corpus, client)
    index = tmp_path / "index"
    if mode == "query":
        retriever.build_index(index)

    def fail_without_record(texts: list[str], *, timeout: float) -> EmbeddingResponse:
        raise RuntimeError("no provider accounting available")

    client.embed = fail_without_record
    if mode == "build":
        with pytest.raises(VectorIndexError, match="accounting"):
            retriever.build_index(index)
        failure = json.loads((index / "build-failure.json").read_text())
        assert failure["usage"] == {"input_tokens": None, "output_tokens": None}
        assert failure["model_attempts"] == 1
        assert failure["model_calls"] == []
        assert failure["input_token_byte_estimate"] > 0
    else:
        result = retriever.retrieve(RetrievalRequest(query="apple"))
        assert result.status == "error"
        assert result.usage.total_tokens is None
        assert result.model_calls == ()
        assert result.metadata["model_attempts"] == 1
        assert result.metadata["input_token_byte_estimate"] == len("apple")

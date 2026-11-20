"""Explicit immutable recovery with synthetic provider responses and no network."""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from adaptive_rag.generation.client import EmbeddingResponse, ModelClientError
from adaptive_rag.retrieval import vector
from adaptive_rag.retrieval.models import (
    EvidenceChunk,
    ModelCallRecord,
    RetrievalBudget,
    TokenUsage,
)
from adaptive_rag.retrieval.vector import (
    IndexBudgetError,
    IndexManifest,
    VectorIndexError,
    VectorRetriever,
)

pytest.importorskip("faiss")
pytest.importorskip("numpy")


class Corpus:
    commit_sha = "a" * 40
    fingerprint = "b" * 64

    def verify(self):
        pass


@pytest.fixture
def corpus(monkeypatch):
    chunks = tuple(
        EvidenceChunk(
            id=str(number) * 64,
            path=f"source{number}.py",
            start_line=1,
            end_line=1,
            excerpt_sha256="f" * 64,
            repo_commit=Corpus.commit_sha,
            text=f"value = {number}",
        )
        for number in range(4)
    )
    monkeypatch.setattr(vector, "chunk_corpus", lambda *_: chunks)
    return Corpus()


class Client:
    identity = {"base_url": "https://fixture.invalid/v1", "model": "synthetic", "dimensions": 2}

    def __init__(self, fail_at=None):
        self.requests = []
        self.fail_at = fail_at

    def embed(self, texts, *, timeout):
        self.requests.append(texts)
        incoming = len(texts) * 10
        response = {
            "data": [{"index": index, "embedding": [1.0, 0.5]} for index in range(len(texts))],
            "usage": {"prompt_tokens": incoming, "total_tokens": incoming},
        }
        failed = len(self.requests) == self.fail_at
        if failed:
            response = {"error": {"message": "Synthetic HTTP 429", "code": 429}}
        call = ModelCallRecord(
            operation="embedding",
            model=self.identity["model"],
            base_url=self.identity["base_url"],
            request={
                "model": self.identity["model"],
                "input": texts,
                "encoding_format": "float",
                "dimensions": 2,
            },
            response=response,
            usage=TokenUsage(
                input_tokens=None if failed else incoming, output_tokens=None if failed else 0
            ),
            error="HTTP 429" if failed else None,
        )
        if failed:
            raise ModelClientError("Synthetic HTTP 429", call)
        return EmbeddingResponse(vectors=tuple((1.0, 0.5) for _ in texts), call=call)


def artifact(path):
    return json.loads(path.read_text())


def hashes(directory):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()
    }


@pytest.fixture
def failed(corpus, tmp_path):
    directory = tmp_path / "failed"
    with pytest.raises(VectorIndexError, match="HTTP 429"):
        VectorRetriever(corpus, Client(fail_at=3), batch_size=1).build_index(directory)
    return directory


def test_reuse_verifies_successful_prefix_and_charges_only_new_calls(corpus, failed, tmp_path):
    before = hashes(failed)
    client = Client()
    output = tmp_path / "recovered"
    manifest = VectorRetriever(corpus, client, batch_size=1).build_index(
        output, reuse_from=failed, budget=RetrievalBudget(max_model_calls=2, max_tokens=50)
    )

    assert client.requests == [["value = 2"], ["value = 3"]]
    assert manifest.model_attempts == len(manifest.model_calls) == 4
    assert manifest.usage == TokenUsage(input_tokens=40, output_tokens=0)
    provenance = manifest.reuse_provenance
    assert provenance["reused_successful_calls"] == provenance["reused_chunks"] == 2
    assert (
        provenance["reused_usage"]
        == provenance["new_usage"]
        == {"input_tokens": 20, "output_tokens": 0}
    )
    assert provenance["new_model_attempts"] == 2
    parent = provenance["parent_failure_accounting"]
    assert parent["model_attempts"] == 3 and parent["recorded_call_count"] == 3
    assert parent["usage"] == {"input_tokens": None, "output_tokens": None}
    assert parent["known_input_tokens_subtotal"] == 20 and parent["unknown_usage_calls"] == 1
    assert parent["excluded_call_records"][0]["error"] == "HTTP 429"
    assert parent["elapsed_seconds"] >= 0
    assert provenance["source_journal_sha256"] == before["build-events.jsonl"]
    assert provenance["source_failure_sha256"] == before["build-failure.json"]
    assert hashes(failed) == before
    events = [json.loads(line) for line in (output / "build-events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "batch_reused",
        "batch_reused",
        "batch_started",
        "batch_result",
        "batch_started",
        "batch_result",
    ]
    assert all(event["attempted"] is False for event in events[:2])
    assert all(call.error is None for call in manifest.model_calls)
    assert VectorRetriever(corpus, client, batch_size=1).load_index(output) == manifest


@pytest.mark.parametrize("mutation", ["identity", "corpus", "chunking", "partition"])
def test_mismatched_sources_reject_before_any_new_call(corpus, failed, tmp_path, mutation):
    client = Client()
    retriever = VectorRetriever(corpus, client, batch_size=1)
    if mutation == "partition":
        retriever.batch_size = 2
    else:
        path = failed / "build-failure.json"
        data = artifact(path)
        if mutation == "identity":
            data["embedding_identity"]["model"] = "different"
        elif mutation == "corpus":
            data["corpus_fingerprint"] = "e" * 64
        else:
            data["chunking"]["max_lines"] += 1
        path.write_text(json.dumps(data))
    with pytest.raises(VectorIndexError):
        retriever.build_index(tmp_path / "rejected", reuse_from=failed)
    assert client.requests == []


@pytest.mark.parametrize("mutation", ["input", "duplicate_result", "failure_call", "nonfinite"])
def test_tampered_or_ambiguous_records_reject_before_calls(corpus, failed, tmp_path, mutation):
    path = failed / "build-events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if mutation == "input":
        events[0]["input"] = ["other source"]
    elif mutation == "duplicate_result":
        events.insert(2, events[1])
    elif mutation == "failure_call":
        data = artifact(failed / "build-failure.json")
        data["model_calls"][0]["response"]["data"][0]["embedding"] = [0.2, 0.4]
        (failed / "build-failure.json").write_text(json.dumps(data))
    else:
        events[1]["call"]["response"]["data"][0]["embedding"][0] = float("inf")
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    client = Client()
    with pytest.raises(VectorIndexError):
        VectorRetriever(corpus, client, batch_size=1).build_index(
            tmp_path / "rejected", reuse_from=failed
        )
    assert client.requests == []


def test_incremental_budget_denial_keeps_parent_unknown_usage(corpus, failed, tmp_path):
    client = Client()
    output = tmp_path / "recovered"
    with pytest.raises(IndexBudgetError):
        VectorRetriever(corpus, client, batch_size=1).build_index(
            output, reuse_from=failed, budget=RetrievalBudget(max_model_calls=0, max_tokens=0)
        )
    assert client.requests == []
    result = artifact(output / "build-failure.json")
    assert result["model_attempts"] == 2 and len(result["model_calls"]) == 2
    assert result["reuse_provenance"]["new_model_attempts"] == 0
    assert result["reuse_provenance"]["new_usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert result["reuse_provenance"]["parent_failure_accounting"]["usage"]["input_tokens"] is None
    with pytest.raises(VectorIndexError, match="recursive"):
        VectorRetriever(corpus, Client(), batch_size=1).build_index(
            tmp_path / "recursive", reuse_from=output
        )


def test_output_inside_failed_source_is_rejected_without_mutation(corpus, failed):
    before = hashes(failed)
    with pytest.raises(VectorIndexError, match="outside"):
        VectorRetriever(corpus, Client(), batch_size=1).build_index(
            failed / "child", reuse_from=failed
        )
    assert hashes(failed) == before


def test_complete_embedding_prefix_can_recover_with_zero_new_call_budget(
    corpus, tmp_path, monkeypatch
):
    source = tmp_path / "failed-saving"
    real_json_bytes = vector._json_bytes

    def fail_save(value):
        if isinstance(value, list):
            raise OSError("Synthetic save failure after every provider call")
        return real_json_bytes(value)

    monkeypatch.setattr(vector, "_json_bytes", fail_save)
    with pytest.raises(VectorIndexError, match="save failure"):
        VectorRetriever(corpus, Client(), batch_size=1).build_index(source)
    monkeypatch.setattr(vector, "_json_bytes", real_json_bytes)
    client = Client()
    result = VectorRetriever(corpus, client, batch_size=1).build_index(
        tmp_path / "recovered-saving",
        reuse_from=source,
        budget=RetrievalBudget(max_model_calls=0, max_tokens=0),
    )
    assert result.reuse_provenance["reused_successful_calls"] == 4
    assert result.reuse_provenance["new_model_attempts"] == 0 and client.requests == []


@pytest.mark.parametrize("mutation", ["empty_parent", "drop_unknown", "zero_usage", "source_hash"])
def test_saved_lineage_cannot_erase_parent_failure_uncertainty(corpus, failed, tmp_path, mutation):
    manifest = (
        VectorRetriever(corpus, Client(), batch_size=1)
        .build_index(tmp_path / "recovered", reuse_from=failed)
        .model_dump(mode="json")
    )
    provenance = manifest["reuse_provenance"]
    parent = provenance["parent_failure_accounting"]
    if mutation == "empty_parent":
        provenance["parent_failure_accounting"] = {}
    elif mutation == "drop_unknown":
        parent["excluded_call_records"] = []
    elif mutation == "zero_usage":
        parent["usage"] = {"input_tokens": 20, "output_tokens": 0}
    else:
        provenance["source_failure_sha256"] = "missing"
    with pytest.raises(ValidationError):
        IndexManifest.model_validate(manifest)


def test_unrecorded_soft_interruption_is_retained_outside_successful_reuse(corpus, tmp_path):
    class Interrupted(Client):
        def embed(self, texts, *, timeout):
            if len(self.requests) == 2:
                raise KeyboardInterrupt("Synthetic interrupted attempt")
            return super().embed(texts, timeout=timeout)

    source = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        VectorRetriever(corpus, Interrupted(), batch_size=1).build_index(source)
    client = Client()
    manifest = VectorRetriever(corpus, client, batch_size=1).build_index(
        tmp_path / "recovered-interruption", reuse_from=source
    )
    parent = manifest.reuse_provenance["parent_failure_accounting"]
    assert parent["unknown_model_attempts"] == parent["unknown_usage_calls"] == 1
    assert parent["excluded_call_records"] == []
    assert parent["usage"] == {"input_tokens": None, "output_tokens": None}
    assert manifest.reuse_provenance["new_model_attempts"] == len(client.requests) == 2

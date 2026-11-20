"""Index accounting survives provider failures and soft interruptions without API calls."""

from __future__ import annotations

import json

import pytest

from adaptive_rag.generation.client import (
    EmbeddingResponse,
    ModelCallNotStarted,
    ModelClientError,
)
from adaptive_rag.retrieval import vector
from adaptive_rag.retrieval.models import (
    EvidenceChunk,
    ModelCallRecord,
    RetrievalBudget,
    TokenUsage,
)
from adaptive_rag.retrieval.vector import IndexBudgetError, VectorIndexError, VectorRetriever

pytest.importorskip("faiss")
pytest.importorskip("numpy")


class SyntheticCorpus:
    commit_sha = "a" * 40
    fingerprint = "b" * 64

    def verify(self):
        pass


@pytest.fixture
def corpus(monkeypatch):
    chunks = tuple(
        EvidenceChunk(
            id=character * 64,
            path=f"{character}.py",
            start_line=1,
            end_line=1,
            excerpt_sha256="f" * 64,
            repo_commit=SyntheticCorpus.commit_sha,
            text=f"value = '{character}'",
        )
        for character in ("c", "d")
    )
    monkeypatch.setattr(vector, "chunk_corpus", lambda *_: chunks)
    return SyntheticCorpus()


def events(directory):
    return [
        json.loads(line) for line in (directory / "build-events.jsonl").read_text().splitlines()
    ]


def failure(directory):
    return json.loads((directory / "build-failure.json").read_text())


class SyntheticClient:
    identity = {"base_url": "https://fixture.invalid/v1", "model": "synthetic", "dimensions": 2}

    def __init__(self, directory, *, fail_at=None, exception=None):
        self.directory = directory
        self.fail_at = fail_at
        self.exception = exception
        self.requests = 0

    def embed(self, texts, *, timeout):
        assert timeout > 0
        self.requests += 1
        observed = events(self.directory)
        # Intent has reached the filesystem before any provider delegation. Every
        # previous observation must be durable before the following batch starts.
        assert observed[-1]["event"] == "batch_started"
        assert observed[-1]["batch_id"] == self.requests - 1
        assert observed[-1]["input"] == texts
        if self.requests > 1:
            assert observed[-2]["event"] == "batch_result"
        call = ModelCallRecord(
            operation="embedding",
            model=self.identity["model"],
            base_url=self.identity["base_url"],
            request={"input": texts},
            usage=TokenUsage(input_tokens=3, output_tokens=0),
        )
        if self.requests == self.fail_at:
            if self.exception == "known":
                raise ModelClientError("Synthetic provider failure", call)
            raise self.exception
        return EmbeddingResponse(vectors=tuple((1.0, 0.0) for _ in texts), call=call)


def test_batch_intents_and_observations_are_flushed_and_fsynced(corpus, tmp_path, monkeypatch):
    directory = tmp_path / "index"
    synced_events = []
    real_fsync = vector.os.fsync

    def fsync(descriptor):
        real_fsync(descriptor)
        if (directory / "build-events.jsonl").exists():
            synced_events.append(events(directory))

    monkeypatch.setattr(vector.os, "fsync", fsync)
    client = SyntheticClient(directory)
    manifest = VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    recorded = events(directory)
    assert [event["event"] for event in recorded] == [
        "batch_started",
        "batch_result",
        "batch_started",
        "batch_result",
    ]
    assert [len(snapshot) for snapshot in synced_events] == [0, 0, 1, 2, 3, 4]
    assert recorded[0]["attempted"] is None
    assert recorded[1]["attempted"] is True
    assert recorded[1]["call"] == manifest.model_calls[0].model_dump(mode="json")
    assert manifest.model_attempts == client.requests == 2


def test_known_provider_failure_preserves_previous_and_failed_call(corpus, tmp_path):
    directory = tmp_path / "index"
    client = SyntheticClient(directory, fail_at=2, exception="known")
    with pytest.raises(VectorIndexError, match="Synthetic provider failure"):
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    recorded = events(directory)
    assert recorded[-1]["event"] == "batch_error"
    assert recorded[-1]["unknown_usage"] is False
    assert recorded[-1]["call"]["usage"] == {"input_tokens": 3, "output_tokens": 0}
    failed = failure(directory)
    assert failed["model_attempts"] == 2
    assert len(failed["model_calls"]) == 2
    assert failed["usage"] == {"input_tokens": 6, "output_tokens": 0}
    assert failed["unknown_model_attempts"] == 0
    assert not (directory / "manifest.json").exists()


@pytest.mark.parametrize("exception", [KeyboardInterrupt("stop"), SystemExit(130)])
def test_soft_interrupt_retains_known_calls_and_explicit_unknown_attempt(
    corpus, tmp_path, exception
):
    directory = tmp_path / "index"
    client = SyntheticClient(directory, fail_at=2, exception=exception)
    with pytest.raises(type(exception)) as raised:
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    assert raised.value is exception
    recorded = events(directory)
    assert recorded[-1]["event"] == "batch_error"
    assert recorded[-1]["interrupted"] is True
    assert recorded[-1]["call"] is None and recorded[-1]["unknown_usage"] is True
    failed = failure(directory)
    assert failed["status"] == "interrupted"
    assert failed["exception_type"] == type(exception).__name__
    assert failed["model_attempts"] == 2 and len(failed["model_calls"]) == 1
    assert failed["unknown_model_attempts"] == 1
    assert failed["usage"] == {"input_tokens": None, "output_tokens": None}
    assert not (directory / "manifest.json").exists()
    with pytest.raises(VectorIndexError):
        VectorRetriever(corpus, client).load_index(directory)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("fail_at", [1, 2])
def test_pre_slot_pacing_interruption_retains_only_actual_successful_accounting(
    corpus, tmp_path, interruption, fail_at
):
    directory = tmp_path / "index"
    cancelled = interruption("Synthetic cancellation before a pacing slot")
    cancelled._adaptive_rag_not_started = True
    client = SyntheticClient(directory, fail_at=fail_at, exception=cancelled)
    with pytest.raises(interruption) as raised:
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    assert raised.value is cancelled
    recorded = events(directory)
    rejected = recorded[-1]
    assert rejected["event"] == "batch_admission_rejected"
    assert rejected["attempted"] is False
    assert rejected["unknown_usage"] is False
    assert rejected["interrupted"] is True
    assert rejected["exception_type"] == interruption.__name__
    assert not any(event["event"] == "batch_error" for event in recorded)
    saved = failure(directory)
    successful = fail_at - 1
    assert saved["status"] == "interrupted"
    assert saved["exception_type"] == interruption.__name__
    assert saved["model_attempts"] == len(saved["model_calls"]) == successful
    assert saved["unknown_model_attempts"] == 0
    assert saved["usage"] == {"input_tokens": 3 * successful, "output_tokens": 0}
    assert saved["input_token_byte_estimate"] == sum(
        event["input_token_byte_estimate"] for event in recorded if event["event"] == "batch_result"
    )
    assert not (directory / "manifest.json").exists()


def test_rejected_adapter_admission_is_not_counted_as_a_paid_attempt(corpus, tmp_path):
    directory = tmp_path / "index"
    client = SyntheticClient(directory, fail_at=1, exception=ModelCallNotStarted("No admission"))
    with pytest.raises(IndexBudgetError, match="No admission"):
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    recorded = events(directory)
    assert [event["event"] for event in recorded] == ["batch_started", "batch_admission_rejected"]
    assert recorded[-1]["attempted"] is False
    failed = failure(directory)
    assert failed["model_attempts"] == failed["unknown_model_attempts"] == 0
    assert failed["input_token_byte_estimate"] == 0 and failed["model_calls"] == []
    assert failed["usage"] == {"input_tokens": 0, "output_tokens": 0}


def test_local_admission_denial_never_writes_provider_intent(corpus, tmp_path):
    directory = tmp_path / "index"
    client = SyntheticClient(directory)
    with pytest.raises(IndexBudgetError):
        VectorRetriever(corpus, client, batch_size=1).build_index(
            directory, budget=RetrievalBudget(max_model_calls=0)
        )

    assert client.requests == 0 and events(directory) == []
    assert failure(directory)["model_attempts"] == 0


def test_failed_intent_write_never_delegates(corpus, tmp_path, monkeypatch):
    directory = tmp_path / "index"
    client = SyntheticClient(directory)

    def fail_write(*_):
        raise OSError("Synthetic journal failure")

    monkeypatch.setattr(vector, "_build_event", fail_write)
    with pytest.raises(VectorIndexError, match="Synthetic journal failure"):
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    assert client.requests == 0
    failed = failure(directory)
    assert failed["model_attempts"] == failed["unknown_model_attempts"] == 0
    assert failed["usage"] == {"input_tokens": 0, "output_tokens": 0}


def test_failed_result_write_retains_known_call_and_prevents_next_batch(
    corpus, tmp_path, monkeypatch
):
    directory = tmp_path / "index"
    client = SyntheticClient(directory)
    real_event = vector._build_event

    def fail_result(stream, event):
        if event["event"] == "batch_result":
            raise OSError("Synthetic result journal failure")
        real_event(stream, event)

    monkeypatch.setattr(vector, "_build_event", fail_result)
    with pytest.raises(VectorIndexError, match="Synthetic result journal failure"):
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    assert client.requests == 1
    failed = failure(directory)
    assert failed["model_attempts"] == 1 and len(failed["model_calls"]) == 1
    assert failed["unknown_model_attempts"] == 0
    assert failed["usage"] == {"input_tokens": 3, "output_tokens": 0}


def test_interruption_is_preserved_even_if_error_journaling_fails(corpus, tmp_path, monkeypatch):
    directory = tmp_path / "index"
    interruption = KeyboardInterrupt("Synthetic interruption")
    client = SyntheticClient(directory, fail_at=1, exception=interruption)
    real_event = vector._build_event

    def fail_error(stream, event):
        if event["event"] == "batch_error":
            raise OSError("Synthetic error journal failure")
        real_event(stream, event)

    monkeypatch.setattr(vector, "_build_event", fail_error)
    with pytest.raises(KeyboardInterrupt) as raised:
        VectorRetriever(corpus, client, batch_size=1).build_index(directory)

    assert raised.value is interruption
    failed = failure(directory)
    assert failed["status"] == "interrupted" and failed["unknown_model_attempts"] == 1
    assert failed["journal_errors"] == ["Synthetic error journal failure"]


def test_intent_write_time_cannot_push_provider_delegation_past_deadline(
    corpus, tmp_path, monkeypatch
):
    directory = tmp_path / "index"
    client = SyntheticClient(directory)
    real_event = vector._build_event
    clock = [0.0]
    monkeypatch.setattr(vector.time, "perf_counter", lambda: clock[0])

    def slow_intent(stream, event):
        real_event(stream, event)
        if event["event"] == "batch_started":
            clock[0] = 10.0

    monkeypatch.setattr(vector, "_build_event", slow_intent)
    with pytest.raises(IndexBudgetError, match="deadline"):
        VectorRetriever(corpus, client, batch_size=1).build_index(
            directory, budget=RetrievalBudget(max_seconds=5)
        )

    assert client.requests == 0
    assert events(directory)[-1]["event"] == "batch_admission_rejected"
    failed = failure(directory)
    assert failed["model_attempts"] == failed["input_token_byte_estimate"] == 0

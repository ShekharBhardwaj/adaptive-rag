"""Independent execution-boundary audit; every response is a labeled fixture."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from adaptive_rag.config import FoundationConfig
from adaptive_rag.evaluation import runner
from adaptive_rag.evaluation.experiment_models import PlannedJob, question_sha256
from adaptive_rag.evaluation.runner import ExperimentClients, PreparedExperiment, run_experiment
from adaptive_rag.evaluation.storage import load_run
from adaptive_rag.generation.client import ChatResponse
from adaptive_rag.ingestion import DiscoveryPolicy, RepositorySnapshot
from adaptive_rag.models import BenchmarkQuestion
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import ModelCallRecord, RetrievalResult, TokenUsage


class FixtureChat:
    def __init__(self):
        self.model = "synthetic-answer"
        self.requests = []

    @property
    def identity(self):
        return {"model": self.model, "base_url": "https://fixture.invalid/v1"}

    def complete(self, messages, tools, **settings):
        self.requests.append({"messages": messages, "tools": tools, **settings})
        message = {
            "role": "assistant",
            "content": json.dumps({"answer": "Synthetic audit output", "citation_ids": []}),
        }
        return ChatResponse(
            message=message,
            call=ModelCallRecord(
                operation="chat",
                model=self.model,
                base_url=self.identity["base_url"],
                request={"messages": messages, "tools": tools},
                response={"message": message},
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            ),
        )


def prepared_fixture(tmp_path, monkeypatch, *, condition="vectorless", verify=None, retrieve=None):
    snapshot = RepositorySnapshot(
        url="https://fixture.invalid/source.git", commit_sha="a" * 40, captured_at=datetime.now(UTC)
    )
    # Only the preparation boundary is replaced. Generation, evidence checking,
    # record persistence, model invariants, and accounting execute normally.
    source = RepositoryCorpus(
        repository=tmp_path / "source",
        snapshot=snapshot,
        policy=DiscoveryPolicy(),
        files=(),
        fingerprint="b" * 64,
        _texts={"fixture.py": "value = 1"},
    )
    chunk = source.evidence("fixture.py", 1, 1)
    question = BenchmarkQuestion(
        id="synthetic-audit-question",
        question="Where is the synthetic fixture value?",
        category="structural",
        ground_truth_answer="Synthetic expected answer only.",
        evidence=[chunk.model_dump(exclude={"id", "repo_commit", "text", "score", "reason"})],
        repo_commit=snapshot.commit_sha,
        provenance=dict(
            author="Synthetic author",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            method="source_inspection",
            notes="Synthetic audit only.",
        ),
        difficulty="easy",
        split="development",
    )
    config = FoundationConfig.model_validate(
        {
            "repository": {
                "url": snapshot.url,
                "path": source.repository,
                "commit_sha": snapshot.commit_sha,
            },
            "experiment": {
                "dataset": tmp_path / "synthetic.jsonl",
                "conditions": [condition],
                "repetitions": 2,
                "require_pilot": False,
            },
        }
    )
    jobs = [
        PlannedJob(
            job_id=hashlib.sha256(f"synthetic:{i}".encode()).hexdigest(),
            question_id=question.id,
            condition=condition,
            repetition=i,
        )
        for i in range(2)
    ]
    answer_client = FixtureChat()
    agent_client = FixtureChat() if condition == "agentic" else None
    clients = ExperimentClients(answer=answer_client, agent=agent_client)
    corpus = SimpleNamespace(
        commit_sha=source.commit_sha,
        fingerprint=source.fingerprint,
        snapshot=snapshot,
        policy=source.policy,
        files=(),
        verify=verify or (lambda: None),
        evidence=source.evidence,
    )

    def fixture_retrieve(request):
        result = RetrievalResult(
            strategy=condition,
            query=request.query,
            repo_commit=source.commit_sha,
            corpus_fingerprint=source.fingerprint,
            status="completed",
            evidence=(chunk,),
        )
        return retrieve(result, agent_client) if retrieve else result

    identities = {"answer": dict(answer_client.identity)}
    if agent_client is not None:
        identities["agent"] = dict(agent_client.identity)
    prepared = PreparedExperiment(
        config=config,
        corpus=corpus,
        questions=(question,),
        all_questions=(question,),
        benchmark_raw=question.model_dump_json().encode() + b"\n",
        clients=clients,
        retrievers={condition: SimpleNamespace(retrieve=fixture_retrieve)},
        manifest={
            "run_id": "synthetic-audit-run",
            "planned_jobs": [job.model_dump() for job in jobs],
            "model_identities": identities,
            "question_hashes": {question.id: question_sha256(question)},
        },
        validation={"synthetic": True},
        price_schedule=None,
        index_manifest=None,
    )
    monkeypatch.setattr(runner, "prepare_experiment", lambda *args, **kwargs: prepared)
    return config, clients


def test_invalid_retrieval_provenance_never_receives_recall_credit(tmp_path, monkeypatch):
    config, clients = prepared_fixture(
        tmp_path,
        monkeypatch,
        retrieve=lambda result, _: result.model_copy(update={"query": "a different question"}),
    )
    path = tmp_path / "run"
    run_experiment(config, path, clients=clients)
    records = load_run(path).records
    assert records
    assert not clients.answer.requests
    assert all(record.status == "error" and record.retrieval is not None for record in records)
    assert all(record.metrics is None for record in records)


def test_failed_final_source_verification_never_receives_recall_credit(tmp_path, monkeypatch):
    calls = []

    def verify():
        calls.append(None)
        if len(calls) >= 2:
            raise ValueError("synthetic source changed during generation")

    config, clients = prepared_fixture(tmp_path, monkeypatch, verify=verify)
    path = tmp_path / "run"
    run_experiment(config, path, clients=clients)
    records = load_run(path).records
    assert records[0].answer is not None
    assert records[0].retrieval is not None
    assert records[0].status == "error"
    assert records[0].metrics is None


def test_navigation_model_identity_is_pinned_for_the_whole_run(tmp_path, monkeypatch):
    def mutate_identity(result, client):
        client.model = "changed-synthetic-model"
        return result

    config, clients = prepared_fixture(
        tmp_path, monkeypatch, condition="agentic", retrieve=mutate_identity
    )
    path = tmp_path / "run"
    run_experiment(config, path, clients=clients)
    records = load_run(path).records
    assert all(record.status == "error" for record in records)
    assert not clients.answer.requests

"""Offline integration fixtures exercise orchestration, never research accuracy."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from adaptive_rag.config import FoundationConfig, load_config
from adaptive_rag.evaluation.analysis import aggregate_results
from adaptive_rag.evaluation.experiment_models import RunBudget
from adaptive_rag.evaluation.runner import ExperimentClients, prepare_experiment, run_experiment
from adaptive_rag.evaluation.storage import load_run
from adaptive_rag.generation.client import ChatResponse, EmbeddingResponse, ModelClientError
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage


class FixtureChat:
    """Explicitly synthetic provider outputs; no external requests."""

    def __init__(self, *, mode="answer", failure=None):
        self.mode, self.failure = mode, failure
        self.requests = []

    @property
    def identity(self):
        return {"model": f"synthetic-{self.mode}", "base_url": "https://fixture.invalid/v1"}

    def complete(self, messages, tools, **settings):
        self.requests.append(deepcopy({"messages": messages, "tools": tools, **settings}))
        if self.failure == "interrupt":
            raise KeyboardInterrupt("synthetic interrupted provider")
        if self.failure == "unrecorded":
            raise ModelClientError("synthetic transport failure without accounting")
        if self.mode == "navigation":
            if messages[-1]["role"] == "tool":
                ids = json.loads(messages[-1]["content"])["available_evidence_ids"]
                message = {"role": "assistant", "content": json.dumps({"evidence_ids": ids[:1]})}
            else:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "synthetic-read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps(
                                    {
                                        "path": "answer.py",
                                        "start_line": 1,
                                        "end_line": 2,
                                    }
                                ),
                            },
                        }
                    ],
                }
        else:
            payload = json.loads(messages[-1]["content"])
            message = {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "answer": "Synthetic fixture answer only.",
                        "citation_ids": [c["id"] for c in payload["evidence"][:1]],
                    }
                ),
            }
            if self.failure == "malformed":
                message["content"] = "synthetic invalid output"
        usage = TokenUsage(input_tokens=10, output_tokens=5)
        if self.failure == "unknown":
            usage = TokenUsage(input_tokens=None, output_tokens=None)
        return ChatResponse(
            message=message,
            call=ModelCallRecord(
                operation="chat",
                **self.identity,
                request=deepcopy({"messages": messages, "tools": tools, **settings}),
                response={"message": message},
                usage=usage,
            ),
        )


class FixtureEmbedding:
    """Tiny deterministic vectors exist solely to verify real FAISS execution."""

    def __init__(self):
        self.requests = []

    @property
    def identity(self):
        return {
            "model": "synthetic-embedding",
            "base_url": "https://fixture.invalid/v1",
            "dimensions": 2,
        }

    def embed(self, texts, *, timeout):
        self.requests.append(list(texts))
        return EmbeddingResponse(
            vectors=tuple((1.0, 0.0) if "answer" in text else (0.0, 1.0) for text in texts),
            call=ModelCallRecord(
                operation="embedding",
                model=self.identity["model"],
                base_url=self.identity["base_url"],
                request={"input": list(texts)},
                response={"synthetic_fixture": True},
                usage=TokenUsage(input_tokens=len(texts), output_tokens=0),
            ),
        )


@pytest.fixture
def fixture_experiment(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "answer.py").write_text("def answer():\n    return 42\n")
    (source / "other.py").write_text("def other():\n    return 7\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(source), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    git("init", "--quiet", "--template=")
    git("remote", "add", "origin", "https://fixture.invalid/source.git")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "Synthetic test source",
    )
    sha = git("rev-parse", "HEAD")
    question = {
        "id": "synthetic-a",
        "question": "What does answer return?",
        "category": "conceptual",
        "ground_truth_answer": "GOLD_SENTINEL_DO_NOT_SEND",
        "evidence": [
            {
                "path": "answer.py",
                "start_line": 1,
                "end_line": 2,
                "excerpt_sha256": hashlib.sha256(b"def answer():\n    return 42").hexdigest(),
            }
        ],
        "repo_commit": sha,
        "difficulty": "easy",
        "split": "development",
        "provenance": {
            "author": "Synthetic fixture author",
            "created_at": "2026-01-01T00:00:00Z",
            "method": "source_inspection",
            "notes": "Synthetic test annotation only.",
            "review": {
                "reviewer": "Synthetic fixture reviewer",
                "reviewed_at": "2026-01-02T00:00:00Z",
                "method": "source_inspection",
                "notes": "Synthetic review metadata; no actual research claim.",
            },
        },
    }
    second = deepcopy(question)
    second.update(id="synthetic-b", question="Which file defines answer?", category="structural")
    held = deepcopy(question)
    held.update(
        id="synthetic-held", question="Where is the return of 42 implemented?", split="held_out"
    )
    dataset = tmp_path / "synthetic.jsonl"
    dataset.write_text("".join(json.dumps(q) + "\n" for q in (question, second, held)))
    config = FoundationConfig.model_validate(
        {
            "repository": {
                "url": "https://fixture.invalid/source.git",
                "path": source,
                "commit_sha": sha,
            },
            "retrieval": {"top_k": 1},
            "experiment": {
                "dataset": dataset,
                "conditions": ["vectorless", "no_retrieval"],
                "repetitions": 2,
                "require_pilot": False,
            },
        }
    )
    clients = ExperimentClients(
        answer=FixtureChat(), embedding=FixtureEmbedding(), agent=FixtureChat(mode="navigation")
    )
    return config, clients


def change(config, **updates):
    return config.model_copy(update={"experiment": config.experiment.model_copy(update=updates)})


def test_plan_freezes_split_schedule_and_never_calls_models(fixture_experiment):
    config, clients = fixture_experiment
    first = prepare_experiment(config, clients=clients, run_id="synthetic-fixed-run")
    second = prepare_experiment(config, clients=clients, run_id="synthetic-fixed-run")
    assert first.manifest["planned_jobs"] == second.manifest["planned_jobs"]
    assert len(first.manifest["planned_jobs"]) == 8
    assert {q.id for q in first.questions} == {"synthetic-a", "synthetic-b"}
    assert first.manifest["benchmark_sha256"] == hashlib.sha256(first.benchmark_raw).hexdigest()
    assert not clients.answer.requests and not clients.agent.requests
    assert not clients.embedding.requests


def test_all_conditions_execute_shared_generation_and_no_annotations_leak(
    fixture_experiment,
    tmp_path,
):
    pytest.importorskip("faiss")
    from adaptive_rag.retrieval.vector import VectorRetriever

    config, clients = fixture_experiment
    corpus = RepositoryCorpus.from_repository(config.repository.path, config.repository.commit_sha)
    index = tmp_path / "index"
    VectorRetriever(corpus, clients.embedding).build_index(index)
    build_calls = len(clients.embedding.requests)
    config = change(
        config, conditions=("vector", "vectorless", "agentic", "no_retrieval"), vector_index=index
    )
    output = tmp_path / "run"
    result = run_experiment(config, output, clients=clients)
    assert result["status"] == "completed", result
    loaded = load_run(output)
    assert not loaded.issues and not loaded.partial
    assert len(loaded.records) == 16
    assert len(clients.answer.requests) == 16
    assert len(clients.embedding.requests) - build_calls == 4
    assert len(clients.agent.requests) == 8
    assert {r.condition for r in loaded.records} == set(config.experiment.conditions)
    assert all(r.answer and r.answer.status == "completed" for r in loaded.records)
    assert all(r.metadata["provenance_verified"] for r in loaded.records)
    for record in loaded.records:
        assert record.usage.total_tokens == sum(c.usage.total_tokens for c in record.model_calls)
        if record.condition == "no_retrieval":
            assert record.retrieval is None and not record.answer.citations
            assert record.metrics.evidence_recall == 0
        else:
            assert record.retrieval and record.answer.citations
    prompts = clients.answer.requests + clients.agent.requests
    assert "GOLD_SENTINEL" not in json.dumps(prompts)
    assert all("ground_truth_answer" not in json.dumps(request) for request in prompts)
    answer_systems = {request["messages"][0]["content"] for request in clients.answer.requests}
    assert len(answer_systems) == 1
    assert all(request["max_output_tokens"] == 1024 for request in clients.answer.requests)
    assert all(request["temperature"] == 0.0 for request in clients.answer.requests)
    requests = [e for e in loaded.events if e["event"] == "model_request"]
    assert len(requests) == 28  # 16 answers, four query embeddings, eight navigation calls.
    assert loaded.status["model_attempts"] == 28
    summary = aggregate_results(
        loaded.records, loaded.manifest["planned_jobs"], bootstrap_samples=20
    )
    assert summary  # Analysis executes without treating fixture answers as human-scored truth.


def test_global_call_budget_keeps_unexecuted_planned_jobs(fixture_experiment, tmp_path):
    config, clients = fixture_experiment
    config = change(
        config,
        conditions=("no_retrieval",),
        budget=config.experiment.budget.model_copy(update={"max_model_calls": 1}),
    )
    result = run_experiment(config, tmp_path / "run", clients=clients)
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "budget_exhausted"
    assert result["planned_jobs"] == 4 and result["observed_jobs"] == 1
    assert len(clients.answer.requests) == 1
    assert loaded.records[0].status == "completed"
    assert loaded.status["model_attempts"] == 1


@pytest.mark.parametrize("failure", ["unknown", "unrecorded", "interrupt"])
def test_incomplete_accounting_or_interruption_stops_with_durable_evidence(
    fixture_experiment,
    tmp_path,
    failure,
):
    config, clients = fixture_experiment
    clients.answer.failure = failure
    config = change(config, conditions=("no_retrieval",))
    result = run_experiment(config, tmp_path / "run", clients=clients)
    loaded = load_run(tmp_path / "run")
    assert len(clients.answer.requests) == 1 and len(loaded.records) == 1
    assert loaded.status["model_attempts"] == 1
    assert loaded.records[0].usage.total_tokens is None
    assert loaded.records[0].estimated_cost_usd is None
    assert any(event["event"] == "model_request" for event in loaded.events)
    if failure == "interrupt":
        assert result["status"] == "interrupted"
        assert loaded.records[0].status == "interrupted"
        assert any(event["event"] == "model_interrupted" for event in loaded.events)
    else:
        assert result["status"] == "budget_exhausted"


def test_malformed_outputs_remain_observed_failures(fixture_experiment, tmp_path):
    config, clients = fixture_experiment
    clients.answer.failure = "malformed"
    config = change(config, conditions=("no_retrieval",))
    result = run_experiment(config, tmp_path / "run", clients=clients)
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "completed_with_errors"
    assert result["observed_jobs"] == result["planned_jobs"] == 4
    assert all(record.status == "error" and record.model_calls for record in loaded.records)
    assert all(record.usage.total_tokens == 15 for record in loaded.records)


def test_explicit_cost_overrun_stops_without_hiding_last_call(fixture_experiment, tmp_path):
    config, clients = fixture_experiment
    prices = tmp_path / "synthetic-prices.json"
    prices.write_text(
        json.dumps(
            {
                "currency": "USD",
                "as_of": "2026-01-01",
                "source": "Synthetic test rates only.",
                "entries": [
                    {
                        "base_url": clients.answer.identity["base_url"],
                        "model": clients.answer.identity["model"],
                        "operation": "chat",
                        "input_usd_per_million": 1,
                        "output_usd_per_million": 2,
                    }
                ],
            }
        )
    )
    config = change(
        config,
        conditions=("no_retrieval",),
        price_schedule=prices,
        budget=config.experiment.budget.model_copy(update={"max_cost_usd": 0.000005}),
    )
    result = run_experiment(config, tmp_path / "run", clients=clients)
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "budget_exhausted"
    assert len(clients.answer.requests) == 1
    assert loaded.records[0].estimated_cost_usd == pytest.approx(0.00002)
    assert loaded.records[0].status == "budget_exhausted"
    assert (tmp_path / "run" / "price-schedule.json").exists()


def _reserve_config(config, tmp_path, *, priced=True):
    schedule = None
    if priced:
        schedule = tmp_path / "reserve-test-prices.json"
        schedule.write_text(
            json.dumps(
                {
                    "currency": "USD",
                    "as_of": "2026-01-01",
                    "source": "Synthetic reservation rates only.",
                    "entries": [
                        {
                            "base_url": "https://fixture.invalid/v1",
                            "model": "synthetic-answer",
                            "operation": "chat",
                            "input_usd_per_million": 1,
                            "output_usd_per_million": 2,
                        }
                    ],
                }
            )
        )
    return change(
        config,
        conditions=("no_retrieval",),
        price_schedule=schedule,
        budget=config.experiment.budget.model_copy(
            update={
                "unknown_usage_policy": "reserve",
                "max_tokens": 100000,
                "max_cost_usd": 1.0 if priced else None,
            }
        ),
    )


class OnceFailedChat(FixtureChat):
    def complete(self, *args, **kwargs):
        try:
            return super().complete(*args, **kwargs)
        finally:
            self.failure = None


def test_unknown_usage_reservations_are_opt_in_with_a_closed_policy():
    assert RunBudget().unknown_usage_policy == "stop"
    assert RunBudget(unknown_usage_policy="reserve").unknown_usage_policy == "reserve"
    with pytest.raises(ValueError):
        RunBudget(unknown_usage_policy="ignore")


@pytest.mark.parametrize("failure", ["unknown", "unrecorded"])
def test_reserve_policy_continues_later_jobs_but_never_fills_actual_unknown_usage(
    fixture_experiment, tmp_path, failure, monkeypatch
):
    from adaptive_rag.evaluation import runner

    generator = runner.GroundedAnswerGenerator
    admitted_token_limits = []

    class CaptureGenerationBudget(generator):
        def __init__(self, client, *, settings):
            admitted_token_limits.append(settings.max_tokens)
            super().__init__(client, settings=settings)

    monkeypatch.setattr(runner, "GroundedAnswerGenerator", CaptureGenerationBudget)
    config, _ = fixture_experiment
    config = _reserve_config(config, tmp_path)
    config = change(
        config,
        generation=config.experiment.generation.model_copy(
            update={"max_tokens": config.experiment.budget.max_tokens}
        ),
    )
    answer = OnceFailedChat(failure=failure)
    clients = ExperimentClients(answer=answer)
    result = run_experiment(config, tmp_path / "run", clients=clients)
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "completed_with_errors"
    assert result["observed_jobs"] == result["planned_jobs"] == 4
    assert len(answer.requests) == 4
    assert loaded.records[0].status != "completed"
    assert loaded.records[0].usage.total_tokens is None
    assert loaded.records[0].estimated_cost_usd is None
    assert all(record.status == "completed" for record in loaded.records[1:])
    assert loaded.status["usage"]["input_tokens"] is None
    assert loaded.status["estimated_cost_usd"] is None
    assert loaded.status["unknown_cost_calls"] == 1
    assert loaded.status["model_attempts"] == 4
    first_budget = loaded.records[0].metadata["budget_accounting"]
    assert first_budget["reserved_unknown_calls"] == 1
    assert first_budget["unreserved_unknown_calls"] == 0
    assert first_budget["usage"]["input_tokens"] > 0
    assert first_budget["usage"]["output_tokens"] == config.experiment.generation.max_output_tokens
    assert first_budget["estimated_cost_usd"] > 0
    assert admitted_token_limits[0] == config.experiment.budget.max_tokens
    assert admitted_token_limits[1] == config.experiment.budget.max_tokens - sum(
        first_budget["usage"].values()
    )
    total_budget = loaded.status["budget_accounting"]
    assert total_budget["reserved_unknown_calls"] == 1
    assert total_budget["unreserved_unknown_calls"] == 0
    assert total_budget["usage"]["input_tokens"] == first_budget["usage"]["input_tokens"] + 30
    assert total_budget["usage"]["output_tokens"] == first_budget["usage"]["output_tokens"] + 15
    assert total_budget["estimated_cost_usd"] == pytest.approx(
        first_budget["estimated_cost_usd"] + 0.00006
    )
    assert len(total_budget["attempts"]) == 4
    assert "not actual billed usage" in total_budget["interpretation"]
    assert loaded.manifest["execution_policy"]["unknown_usage_policy"] == "reserve"
    assert loaded.manifest["configuration"]["experiment"]["budget"]["unknown_usage_policy"] == (
        "reserve"
    )


def test_reserve_policy_missing_rates_rejects_calls_before_unknown_usage(
    fixture_experiment, tmp_path
):
    config, _ = fixture_experiment
    config = _reserve_config(config, tmp_path, priced=False)
    answer = OnceFailedChat(failure="unrecorded")
    result = run_experiment(config, tmp_path / "run", clients=ExperimentClients(answer=answer))
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "completed_with_errors"
    assert result["observed_jobs"] == result["planned_jobs"] == 4
    assert answer.requests == []
    assert all(record.status == "budget_exhausted" for record in loaded.records)
    assert all(record.usage.total_tokens == 0 for record in loaded.records)
    assert loaded.status["estimated_cost_usd"] == 0
    assert loaded.status["budget_accounting"]["estimated_cost_usd"] == 0
    assert loaded.status["budget_accounting"]["attempts"] == []


def test_reserve_policy_unreservable_delegated_unknown_stops_later_jobs(
    fixture_experiment, tmp_path, monkeypatch
):
    from adaptive_rag.evaluation.journal import CallJournal

    original = CallJournal.budget_accounting.fget

    def unreservable_unknown(journal):
        accounting = original(journal)
        if journal.usage.total_tokens is None:
            accounting["estimated_cost_usd"] = None
            accounting["reserved_unknown_calls"] = 0
            accounting["unreserved_unknown_calls"] = 1
            for receipt in accounting["attempts"]:
                receipt["status"] = "unreserved_unknown"
                receipt["estimated_cost_usd"] = None
                receipt["reason"] = "Synthetic post-delegation reservation uncertainty"
        return accounting

    monkeypatch.setattr(CallJournal, "budget_accounting", property(unreservable_unknown))
    config, _ = fixture_experiment
    config = _reserve_config(config, tmp_path)
    answer = OnceFailedChat(failure="unrecorded")
    result = run_experiment(config, tmp_path / "run", clients=ExperimentClients(answer=answer))
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "budget_exhausted"
    assert len(answer.requests) == result["observed_jobs"] == 1
    assert loaded.records[0].usage.total_tokens is None
    assert loaded.status["estimated_cost_usd"] is None
    assert loaded.status["budget_accounting"]["estimated_cost_usd"] is None
    assert loaded.status["budget_accounting"]["unreserved_unknown_calls"] == 1
    assert "no finite token/cost reservation" in loaded.status["stop_reason"]


def test_reserve_policy_never_continues_an_interrupted_job(fixture_experiment, tmp_path):
    config, _ = fixture_experiment
    config = _reserve_config(config, tmp_path)
    answer = OnceFailedChat(failure="interrupt")
    result = run_experiment(config, tmp_path / "run", clients=ExperimentClients(answer=answer))
    loaded = load_run(tmp_path / "run")
    assert result["status"] == "interrupted"
    assert len(answer.requests) == result["observed_jobs"] == 1
    assert loaded.records[0].status == "interrupted"
    assert loaded.records[0].usage.total_tokens is None
    assert loaded.status["usage"]["input_tokens"] is None
    assert loaded.status["budget_accounting"]["reserved_unknown_calls"] == 1


def test_unreviewed_benchmark_fails_before_any_model_call(fixture_experiment, tmp_path):
    config, clients = fixture_experiment
    rows = [json.loads(line) for line in config.experiment.dataset.read_text().splitlines()]
    rows[0]["provenance"]["review"] = None
    config.experiment.dataset.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="missing_independent_review"):
        run_experiment(config, tmp_path / "run", clients=clients)
    assert not clients.answer.requests and not (tmp_path / "run").exists()


def test_api_admission_and_source_output_guards_are_preflight(
    fixture_experiment,
    tmp_path,
    monkeypatch,
):
    config, clients = fixture_experiment
    with pytest.raises(ValueError, match="allow-api"):
        run_experiment(config, tmp_path / "run")
    monkeypatch.chdir(tmp_path)
    relative = config.model_copy(
        update={
            "repository": config.repository.model_copy(update={"path": Path("source")}),
        }
    )
    with pytest.raises(ValueError, match="outside the pinned"):
        run_experiment(relative, Path("source/results"), clients=clients)
    assert not clients.answer.requests


def test_example_config_paths_resolve_without_contacts():
    config = load_config(Path(__file__).resolve().parents[1] / "configs/experiment.example.yaml")
    assert config.experiment.dataset.is_absolute()
    assert config.experiment.vector_index.is_absolute()
    assert config.experiment.require_pilot
    assert config.experiment.repetitions == 3

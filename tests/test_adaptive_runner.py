"""Adaptive execution uses synthetic annotations and local deterministic providers."""

import json
from copy import deepcopy

import pytest
from test_runner import fixture_experiment

from adaptive_rag.evaluation.analysis import aggregate_results
from adaptive_rag.evaluation.runner import ExperimentClients, prepare_experiment, run_experiment
from adaptive_rag.evaluation.storage import load_run
from adaptive_rag.generation.client import ChatResponse
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage
from adaptive_rag.retrieval.vector import VectorRetriever


class SyntheticRouterClient:
    def __init__(self, *, strategy="vectorless", failure=None):
        self.strategy, self.failure = strategy, failure
        self.requests = []

    @property
    def identity(self):
        return {"model": "synthetic-router", "base_url": "https://fixture.invalid/v1"}

    def complete(self, messages, tools, **settings):
        self.requests.append(deepcopy({"messages": messages, "tools": tools, **settings}))
        text = json.dumps({"strategy": self.strategy, "reason": "Synthetic selection only."})
        if self.failure == "malformed":
            text = "synthetic malformed selection"
        usage = TokenUsage(input_tokens=10, output_tokens=5)
        if self.failure == "unknown":
            usage = TokenUsage(input_tokens=None, output_tokens=None)
        message = {"role": "assistant", "content": text}
        return ChatResponse(
            message=message,
            call=ModelCallRecord(
                operation="chat",
                **self.identity,
                request={"messages": deepcopy(messages), "tools": tools, **settings},
                response={"message": message},
                usage=usage,
            ),
        )


@pytest.fixture
def adaptive_fixture(tmp_path):
    config, clients = fixture_experiment.__wrapped__(tmp_path)
    corpus = RepositoryCorpus.from_repository(
        config.repository.path, config.repository.commit_sha, config.files
    )
    index = tmp_path / "index"
    VectorRetriever(corpus, clients.embedding, chunking=config.retrieval.chunking).build_index(
        index
    )
    clients.embedding.requests.clear()
    router = SyntheticRouterClient()
    clients = ExperimentClients(
        answer=clients.answer,
        embedding=clients.embedding,
        agent=clients.agent,
        router=router,
    )
    config = config.model_copy(
        update={
            "experiment": config.experiment.model_copy(
                update={
                    "conditions": (
                        "vector",
                        "vectorless",
                        "agentic",
                        "no_retrieval",
                        "adaptive_rule",
                        "adaptive_llm",
                    ),
                    "vector_index": index,
                }
            )
        }
    )
    return config, clients


def test_six_conditions_keep_routing_costs_and_annotations_out_of_router(
    adaptive_fixture, tmp_path
):
    config, clients = adaptive_fixture
    plan = prepare_experiment(config, clients=clients, run_id="synthetic-adaptive")
    assert len(plan.manifest["planned_jobs"]) == 24
    assert not clients.router.requests and not clients.embedding.requests
    assert plan.manifest["model_identities"]["router"] == clients.router.identity
    result = run_experiment(config, tmp_path / "run", clients=clients)
    assert result["status"] == "completed"
    loaded = load_run(tmp_path / "run")
    assert len(loaded.records) == 24 and not loaded.partial
    assert not loaded.issues
    for record in loaded.records:
        if record.condition.startswith("adaptive_"):
            assert record.routing is not None and record.routing.status == "completed"
            assert record.retrieval.selected_strategy == record.routing.selected_strategy
            assert record.retrieval.strategy == record.condition
            assert (
                record.model_calls[: len(record.routing.model_calls)] == record.routing.model_calls
            )
        else:
            assert record.routing is None
    requests = json.dumps(clients.router.requests)
    assert "GOLD_SENTINEL_DO_NOT_SEND" not in requests
    assert "ground_truth_answer" not in requests and '"category"' not in requests
    assert "Where is the return of 42 implemented?" not in requests
    assert all(request["tools"] == [] for request in clients.router.requests)
    summary = aggregate_results(loaded.records, loaded.manifest["planned_jobs"])
    adaptive = summary["conditions"]["adaptive_llm"]
    assert adaptive["selected_strategies"] == {"vectorless": 4}
    assert adaptive["measurements_observed"]["routing_total_tokens"]["sum"] == 60
    assert adaptive["measurements_observed"]["routing_model_calls"]["sum"] == 4


@pytest.mark.parametrize("strategy", ["vector", "vectorless", "agentic"])
def test_every_route_uses_one_concrete_baseline(adaptive_fixture, tmp_path, strategy):
    config, clients = adaptive_fixture
    clients.router.strategy = strategy
    config = config.model_copy(
        update={
            "experiment": config.experiment.model_copy(
                update={
                    "conditions": ("adaptive_llm",),
                }
            )
        }
    )
    result = run_experiment(config, tmp_path / "run", clients=clients)
    assert result["status"] == "completed"
    records = load_run(tmp_path / "run").records
    assert len(records) == 4
    assert all(r.routing.selected_strategy == strategy for r in records)
    assert all(r.retrieval.selected_strategy == strategy for r in records)


@pytest.mark.parametrize("failure,observed", [("malformed", 4), ("unknown", 1)])
def test_failed_router_never_generates_or_falls_back(adaptive_fixture, tmp_path, failure, observed):
    config, clients = adaptive_fixture
    clients.router.failure = failure
    config = config.model_copy(
        update={
            "experiment": config.experiment.model_copy(
                update={
                    "conditions": ("adaptive_llm",),
                }
            )
        }
    )
    run_experiment(config, tmp_path / "run", clients=clients)
    records = load_run(tmp_path / "run").records
    assert len(records) == observed
    assert (
        not clients.answer.requests
        and not clients.embedding.requests
        and not clients.agent.requests
    )
    assert all(r.status != "completed" and r.routing.selected_strategy is None for r in records)
    assert all(r.answer is None for r in records)
    if failure == "unknown":
        assert records[0].usage.total_tokens is None


def test_shared_call_budget_accounts_for_router_before_vector(adaptive_fixture, tmp_path):
    config, clients = adaptive_fixture
    clients.router.strategy = "vector"
    config = config.model_copy(
        update={
            "retrieval": config.retrieval.model_copy(
                update={"budget": config.retrieval.budget.model_copy(update={"max_model_calls": 1})}
            ),
            "experiment": config.experiment.model_copy(update={"conditions": ("adaptive_llm",)}),
        }
    )
    run_experiment(config, tmp_path / "run", clients=clients)
    records = load_run(tmp_path / "run").records
    assert len(records) == 4
    assert all(r.status == "budget_exhausted" for r in records)
    assert len(clients.router.requests) == 4
    assert not clients.embedding.requests and not clients.answer.requests


def test_interrupt_after_route_preserves_decision_and_call_journal(adaptive_fixture, tmp_path):
    config, clients = adaptive_fixture
    clients.router.strategy = "agentic"
    clients.agent.failure = "interrupt"
    config = config.model_copy(
        update={
            "experiment": config.experiment.model_copy(
                update={
                    "conditions": ("adaptive_llm",),
                }
            )
        }
    )
    outcome = run_experiment(config, tmp_path / "run", clients=clients)
    assert outcome["status"] == "interrupted"
    loaded = load_run(tmp_path / "run")
    assert len(loaded.records) == 1
    record = loaded.records[0]
    assert record.routing.selected_strategy == "agentic"
    assert record.status == "interrupted" and record.answer is None
    assert record.usage.total_tokens is None and record.metadata["model_attempts"] == 2
    assert len(record.routing.model_calls) == 1

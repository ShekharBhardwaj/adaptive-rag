"""Cascade orchestration with synthetic annotations and local deterministic providers.

These checks exercise accounting and control flow only; they measure no answer quality.
"""

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_runner import FixtureChat, fixture_experiment

from adaptive_rag.evaluation import cascade
from adaptive_rag.evaluation.analysis import aggregate_results
from adaptive_rag.evaluation.experiment_models import ExperimentSettings, RunBudget
from adaptive_rag.evaluation.runner import ExperimentClients, prepare_experiment, run_experiment
from adaptive_rag.evaluation.storage import load_run
from adaptive_rag.generation.client import ChatResponse
from adaptive_rag.retrieval import agentic, agentic_wrapup
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage
from adaptive_rag.retrieval.vector import VectorRetriever

pytest.importorskip("faiss")


class SufficiencyChat:
    """Synthetic answers that also report evidence sufficiency; no external requests."""

    def __init__(self, sufficient=True, malformed=None):
        self.sufficient, self.malformed = sufficient, malformed
        self.requests = []

    @property
    def identity(self):
        return {"model": "synthetic-answer", "base_url": "https://fixture.invalid/v1"}

    def complete(self, messages, tools, **settings):
        self.requests.append(deepcopy({"messages": messages, "tools": tools, **settings}))
        number = len(self.requests)
        payload = json.loads(messages[-1]["content"])
        reported = self.sufficient(number) if callable(self.sufficient) else self.sufficient
        content = json.dumps(
            {
                "answer": f"Synthetic fixture answer {number}.",
                "citation_ids": [chunk["id"] for chunk in payload["evidence"][:1]],
                "evidence_sufficient": reported,
            }
        )
        if self.malformed is not None and self.malformed(number):
            content = "synthetic invalid output"
        message = {"role": "assistant", "content": content}
        return ChatResponse(
            message=message,
            call=ModelCallRecord(
                operation="chat",
                **self.identity,
                request=deepcopy({"messages": messages, "tools": tools, **settings}),
                response={"message": message},
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            ),
        )


class ProseNavigator(FixtureChat):
    """A navigator that answers in prose and never selects evidence."""

    def __init__(self):
        super().__init__(mode="navigation")

    def complete(self, messages, tools, **settings):
        self.requests.append(deepcopy({"messages": messages, "tools": tools, **settings}))
        message = {"role": "assistant", "content": "Synthetic prose instead of a selection."}
        return ChatResponse(
            message=message,
            call=ModelCallRecord(
                operation="chat",
                **self.identity,
                request=deepcopy({"messages": messages, "tools": tools, **settings}),
                response={"message": message},
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            ),
        )


def odd_calls(number):
    return number % 2 == 1


def even_calls(number):
    return number % 2 == 0


@pytest.fixture
def cascade_fixture(tmp_path):
    config, clients = fixture_experiment.__wrapped__(tmp_path)
    corpus = RepositoryCorpus.from_repository(
        config.repository.path, config.repository.commit_sha, config.files
    )
    index = tmp_path / "index"
    VectorRetriever(corpus, clients.embedding, chunking=config.retrieval.chunking).build_index(
        index
    )
    clients.embedding.requests.clear()
    clients = ExperimentClients(
        answer=SufficiencyChat(), embedding=clients.embedding, agent=clients.agent
    )
    config = config.model_copy(
        update={
            "retrieval": config.retrieval.model_copy(
                update={
                    "budget": config.retrieval.budget.model_copy(update={"max_tokens": 200_000})
                }
            ),
            "experiment": config.experiment.model_copy(
                update={
                    "conditions": ("adaptive_cascade",),
                    "vector_index": index,
                    "generation": config.experiment.generation.model_copy(
                        update={"report_evidence_sufficiency": True}
                    ),
                }
            ),
        }
    )
    return config, clients


def with_experiment(config, **updates):
    return config.model_copy(update={"experiment": config.experiment.model_copy(update=updates)})


def test_policy_escalates_only_on_failure_or_a_report_that_is_not_true():
    reason = cascade.escalation_reason
    assert (
        reason(retrieval_status="completed", answer_status="completed", evidence_sufficient=True)
        is None
    )
    assert (
        reason(retrieval_status="completed", answer_status="completed", evidence_sufficient=False)
        == "evidence_reported_insufficient"
    )
    assert (
        reason(retrieval_status="completed", answer_status="completed", evidence_sufficient=None)
        == "evidence_reported_insufficient"
    )
    assert (
        reason(retrieval_status="completed", answer_status="error", evidence_sufficient=True)
        == "first_stage_answer_failed"
    )
    assert (
        reason(retrieval_status="budget_exhausted", answer_status=None, evidence_sufficient=None)
        == "first_stage_retrieval_failed"
    )
    final = cascade.final_stage
    assert (
        final(first_answer_completed=True, second_attempted=True, second_answer_completed=True) == 2
    )
    assert (
        final(first_answer_completed=True, second_attempted=True, second_answer_completed=False)
        == 1
    )
    assert (
        final(first_answer_completed=False, second_attempted=True, second_answer_completed=False)
        == 2
    )
    assert (
        final(first_answer_completed=False, second_attempted=False, second_answer_completed=False)
        == 1
    )


def test_cascade_requires_the_shared_sufficiency_report(cascade_fixture, tmp_path):
    with pytest.raises(ValidationError, match="report_evidence_sufficiency"):
        ExperimentSettings.model_validate(
            {"dataset": tmp_path / "synthetic.jsonl", "conditions": ["adaptive_cascade"]}
        )
    config, clients = cascade_fixture
    without = with_experiment(
        config,
        generation=config.experiment.generation.model_copy(
            update={"report_evidence_sufficiency": False}
        ),
    )
    with pytest.raises(ValueError, match="report_evidence_sufficiency"):
        prepare_experiment(without, clients=clients)


def test_sufficient_first_stage_answers_without_any_navigation(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    plan = prepare_experiment(config, clients=clients, run_id="synthetic-cascade")
    assert plan.manifest["cascade_settings"]["policy_version"] == "vector-first-cascade-v1"
    assert plan.manifest["agentic_wrapup_settings"]["policy_version"] == "agentic-wrapup-v1"
    assert not clients.answer.requests and not clients.agent.requests
    result = run_experiment(config, tmp_path / "run", clients=clients)
    assert result["status"] == "completed"
    loaded = load_run(tmp_path / "run")
    assert len(loaded.records) == 4 and not loaded.issues
    assert not clients.agent.requests
    for record in loaded.records:
        assert record.status == "completed" and record.routing is None
        assert record.retrieval.strategy == "adaptive_cascade"
        assert record.retrieval.selected_strategy == "vector"
        details = record.metadata["cascade"]
        assert details["escalated"] is False and details["escalation_reason"] is None
        assert details["final_stage"] == 1 and details["fell_back_to_first_stage"] is False
        assert details["first_stage_evidence_sufficient"] is True
        assert [stage["strategy"] for stage in details["stages"]] == ["vector"]
        assert [call.operation for call in record.model_calls] == ["embedding", "chat"]
        assert record.metadata["model_attempts"] == 2
        assert record.usage.total_tokens == 16
        assert record.answer.metadata["prompt_version"] == "grounded-answer-v4-sufficiency"


def test_insufficient_report_escalates_and_charges_both_stages(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    clients.answer.sufficient = even_calls
    assert run_experiment(config, tmp_path / "run", clients=clients)["status"] == "completed"
    loaded = load_run(tmp_path / "run")
    assert len(loaded.records) == 4
    for record in loaded.records:
        assert record.status == "completed"
        assert record.retrieval.selected_strategy == "agentic_wrapup"
        details = record.metadata["cascade"]
        assert details["escalated"] is True
        assert details["escalation_reason"] == "evidence_reported_insufficient"
        assert details["final_stage"] == 2 and details["final_strategy"] == "agentic_wrapup"
        first, second = details["stages"]
        assert (first["strategy"], second["strategy"]) == ("vector", "agentic_wrapup")
        assert first["answer"]["status"] == "completed"
        assert first["answer"]["metadata"]["evidence_sufficient"] is False
        assert first["answer"]["answer"] != record.answer.answer
        assert second["answer"]["answer"] == record.answer.answer
        assert second["retrieval"]["metadata"]["prompt_version"] == agentic_wrapup.PROMPT_VERSION
        # One embedding, the first answer, two navigation requests, the second answer.
        assert [call.operation for call in record.model_calls] == ["embedding"] + ["chat"] * 4
        assert record.metadata["model_attempts"] == 5
        assert record.usage.total_tokens == 1 + 4 * 15
        # The vector search and the navigator's read are both counted.
        assert record.tool_call_count == record.retrieval.tool_call_count == 2
        assert record.tool_call_count == sum(
            stage["retrieval"]["tool_call_count"] for stage in details["stages"]
        )
        names = [operation.name for operation in record.retrieval.operations]
        assert names.index("cascade_decision") < names.index("read_file")
        assert record.retrieval.usage.total_tokens == 1 + 2 * 15
        assert record.metrics.evidence_recall == 1.0
    sent = json.dumps(clients.answer.requests) + json.dumps(clients.agent.requests)
    assert "GOLD_SENTINEL_DO_NOT_SEND" not in sent and "ground_truth_answer" not in sent
    assert '"category"' not in sent and "Where is the return of 42 implemented?" not in sent
    summary = aggregate_results(loaded.records, loaded.manifest["planned_jobs"])
    assert summary["conditions"]["adaptive_cascade"]["cascade"] == {
        "observed": 4,
        "escalated": 4,
        "escalation_reasons": {"evidence_reported_insufficient": 4},
        "escalations_not_admitted": 0,
        "final_strategies": {"agentic_wrapup": 4},
        "fell_back_to_first_stage": 0,
    }


def test_failed_second_stage_keeps_the_completed_first_answer(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    navigator = ProseNavigator()
    clients = ExperimentClients(
        answer=SufficiencyChat(sufficient=False), embedding=clients.embedding, agent=navigator
    )
    result = run_experiment(config, tmp_path / "run", clients=clients)
    assert result["status"] == "completed"
    records = load_run(tmp_path / "run").records
    assert len(records) == 4 and len(navigator.requests) == 8
    for record in records:
        assert record.status == "completed"
        assert record.retrieval.selected_strategy == "vector"
        assert record.retrieval.status == "completed"
        details = record.metadata["cascade"]
        assert details["escalated"] is True and details["final_stage"] == 1
        assert details["fell_back_to_first_stage"] is True
        first, second = details["stages"]
        assert second["status"] == "error" and second["answer"] is None
        assert first["answer"]["answer"] == record.answer.answer
        assert agentic_wrapup.SELECTION_FAILURE in record.errors
        # The failed navigation is still charged: embedding, answer, two navigation requests.
        assert record.metadata["model_attempts"] == 4
        assert record.usage.total_tokens == 1 + 3 * 15
        assert len(clients.answer.requests) == 4


def test_failed_first_answer_escalates_and_its_failure_is_preserved(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    clients.answer.malformed = odd_calls
    assert run_experiment(config, tmp_path / "run", clients=clients)["status"] == "completed"
    for record in load_run(tmp_path / "run").records:
        assert record.status == "completed"
        details = record.metadata["cascade"]
        assert details["escalation_reason"] == "first_stage_answer_failed"
        assert details["first_stage_evidence_sufficient"] is None
        assert details["final_stage"] == 2 and details["fell_back_to_first_stage"] is False
        first = details["stages"][0]
        assert first["status"] == "error" and first["answer"]["answer"] is None
        assert any("invalid answer response" in error for error in record.errors)


def test_both_stages_failing_is_a_failure_with_no_invented_answer(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    clients = ExperimentClients(
        answer=SufficiencyChat(malformed=lambda number: True),
        embedding=clients.embedding,
        agent=clients.agent,
    )
    result = run_experiment(config, tmp_path / "run", clients=clients)
    assert result["status"] == "completed_with_errors"
    for record in load_run(tmp_path / "run").records:
        assert record.status == "error"
        assert record.answer is not None and record.answer.answer is None
        details = record.metadata["cascade"]
        assert details["escalated"] is True and details["final_stage"] == 2
        assert [stage["status"] for stage in details["stages"]] == ["error", "error"]


def test_escalation_is_not_started_when_the_run_budget_cannot_cover_it(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    clients.answer.sufficient = False
    config = with_experiment(config, budget=RunBudget(max_model_calls=3))
    run_experiment(config, tmp_path / "run", clients=clients)
    first = load_run(tmp_path / "run").records[0]
    assert first.status == "completed"
    details = first.metadata["cascade"]
    assert details["escalated"] is False and details["fell_back_to_first_stage"] is True
    assert details["escalation_not_admitted"] == (
        "run model-call budget leaves no escalation and answer"
    )
    assert len(details["stages"]) == 1 and not clients.agent.requests
    assert first.retrieval.selected_strategy == "vector"


def test_new_conditions_run_beside_unchanged_fixed_controls(cascade_fixture, tmp_path):
    config, clients = cascade_fixture
    clients.answer.sufficient = False
    config = with_experiment(
        config,
        conditions=("vector", "agentic", "agentic_wrapup", "adaptive_cascade", "no_retrieval"),
    )
    result = run_experiment(config, tmp_path / "run", clients=clients)
    assert result["status"] == "completed" and result["observed_jobs"] == 20
    loaded = load_run(tmp_path / "run")
    by_condition = {}
    for record in loaded.records:
        by_condition.setdefault(record.condition, []).append(record)
    for record in by_condition["agentic"]:
        assert record.retrieval.strategy == "agentic"
        assert record.retrieval.metadata["prompt_version"] == agentic.PROMPT_VERSION
        assert "wrap_up" not in record.retrieval.metadata and "cascade" not in record.metadata
    for record in by_condition["agentic_wrapup"]:
        assert record.retrieval.strategy == "agentic_wrapup" and record.routing is None
        assert record.retrieval.metadata["wrap_up"]["policy_version"] == "agentic-wrapup-v1"
        assert "cascade" not in record.metadata
    for record in by_condition["vector"] + by_condition["no_retrieval"]:
        assert record.answer.metadata["prompt_version"] == "grounded-answer-v4-sufficiency"
        assert record.answer.metadata["evidence_sufficient"] is False
        assert "cascade" not in record.metadata
    summary = aggregate_results(loaded.records, loaded.manifest["planned_jobs"])
    assert "cascade" not in summary["conditions"]["vector"]
    assert summary["conditions"]["adaptive_cascade"]["cascade"]["escalated"] == 4
    assert all(item["completed"] == 4 for item in summary["conditions"].values())

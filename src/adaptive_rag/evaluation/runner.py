"""Reproducible fixed and adaptive execution, without judging or hidden retries."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from adaptive_rag.config import FoundationConfig
from adaptive_rag.generation.answers import GroundedAnswerGenerator
from adaptive_rag.generation.client import (
    ChatClient,
    EmbeddingClient,
    OpenAIChatClient,
    OpenAIEmbeddingClient,
)
from adaptive_rag.generation.connections import request_pacers
from adaptive_rag.generation.models import AnswerResult
from adaptive_rag.ingestion import SnapshotManifest, verify_snapshot
from adaptive_rag.models import BenchmarkQuestion
from adaptive_rag.retrieval.base import Retriever
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import (
    RetrievalOperation,
    RetrievalRequest,
    RetrievalResult,
    TokenUsage,
)
from adaptive_rag.routing import LLMRouter, RoutingResult, RuleBasedRouter

from . import cascade as cascade_policy
from .benchmark import (
    _parse_benchmark,
    _reject_json_constant,
    _unique_json_object,
    validate_benchmark,
)
from .experiment_models import ExperimentRecord, PlannedJob, question_sha256
from .journal import CallJournal
from .metrics import compute_mechanical_metrics
from .pricing import CostEstimate, PriceSchedule, estimate_cost, schedule_sha256
from .storage import RunStore, capture_environment


@dataclass(frozen=True)
class ExperimentClients:
    answer: ChatClient
    embedding: EmbeddingClient | None = None
    agent: ChatClient | None = None
    router: ChatClient | None = None


@dataclass(frozen=True)
class PreparedExperiment:
    config: FoundationConfig
    corpus: RepositoryCorpus
    questions: tuple[BenchmarkQuestion, ...]
    all_questions: tuple[BenchmarkQuestion, ...]
    benchmark_raw: bytes
    clients: ExperimentClients
    retrievers: dict[str, Retriever]
    manifest: dict[str, Any]
    validation: dict[str, Any]
    price_schedule: PriceSchedule | None
    index_manifest: dict[str, Any] | None


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _clients(config: FoundationConfig) -> ExperimentClients:
    settings, experiment = config.models, config.experiment
    if settings is None or experiment is None:
        raise ValueError("an experiment and explicitly configured models are required")

    def require(model: str | None, label: str) -> str:
        if model is None or model.startswith("REPLACE_"):
            raise ValueError(f"configure an actual {label} model identifier")
        return model

    embedding_pacer, chat_pacer = request_pacers(settings)
    common = dict(
        base_url=settings.base_url,
        api_key=os.environ.get(settings.api_key_env),
        pacer=embedding_pacer,
    )
    chat_common = dict(
        base_url=settings.chat_base_url or settings.base_url,
        api_key=os.environ.get(settings.chat_api_key_env or settings.api_key_env),
        pacer=chat_pacer,
    )
    answer = OpenAIChatClient(
        model=require(experiment.answer_model or settings.chat_model, "answer"),
        token_parameter=settings.token_parameter,
        **chat_common,
    )
    embedding = None
    agent = None
    adaptive = bool(set(experiment.conditions) & {"adaptive_rule", "adaptive_llm"})
    cascade = "adaptive_cascade" in experiment.conditions
    if "vector" in experiment.conditions or adaptive or cascade:
        embedding = OpenAIEmbeddingClient(
            model=require(settings.embedding_model, "embedding"),
            dimensions=settings.embedding_dimensions,
            **common,
        )
    if {"agentic", "agentic_wrapup"} & set(experiment.conditions) or adaptive or cascade:
        agent = OpenAIChatClient(
            model=require(settings.chat_model, "agent navigation"),
            token_parameter=settings.token_parameter,
            **chat_common,
        )
    router = None
    if "adaptive_llm" in experiment.conditions:
        router = OpenAIChatClient(
            model=require(config.routing.chat_model or settings.chat_model, "routing"),
            token_parameter=settings.token_parameter,
            **chat_common,
        )
    return ExperimentClients(answer=answer, embedding=embedding, agent=agent, router=router)


def prepare_experiment(
    config: FoundationConfig,
    *,
    clients: ExperimentClients | None = None,
    run_id: str | None = None,
) -> PreparedExperiment:
    """Validate and freeze inputs and the randomized job order without model requests."""
    started = time.perf_counter()
    experiment = config.experiment
    if experiment is None:
        raise ValueError("configure an experiment section; see configs/experiment.example.yaml")
    clients = clients if clients is not None else _clients(config)
    if experiment.dataset.resolve().is_relative_to(config.repository.path.resolve()):
        raise ValueError("benchmark annotations must be outside the retrieval corpus checkout")
    snapshot = verify_snapshot(config.repository.path, config.repository.commit_sha)
    canonical = lambda value: value.rstrip("/").removesuffix(".git")  # noqa: E731
    if canonical(snapshot.url) != canonical(config.repository.url):
        raise ValueError("repository origin does not match configured URL")
    raw = experiment.dataset.read_bytes()
    benchmark_digest = hashlib.sha256(raw).hexdigest()
    validation = validate_benchmark(
        experiment.dataset,
        config.repository.path,
        config.repository.commit_sha,
        require_reviewed=True,
        pilot=experiment.require_pilot,
        policy=config.files,
    )
    if not validation.valid:
        raise ValueError(
            "benchmark validation failed: "
            + "; ".join(f"{issue.code}: {issue.message}" for issue in validation.errors)
        )
    if validation.dataset_sha256 != benchmark_digest:
        raise ValueError("benchmark changed while preparing the experiment")
    parsed, errors = _parse_benchmark(raw)
    if errors:
        raise ValueError("frozen benchmark cannot be parsed")
    all_questions = tuple(question for _, question in parsed)
    questions = tuple(q for q in all_questions if q.split == experiment.split)
    if not questions:
        raise ValueError("the selected experiment split has no questions")
    corpus = RepositoryCorpus.from_repository(
        config.repository.path,
        config.repository.commit_sha,
        config.files,
    )
    retrievers: dict[str, Retriever] = {}
    index_manifest = None
    adaptive = bool(set(experiment.conditions) & {"adaptive_rule", "adaptive_llm"})
    cascade = "adaptive_cascade" in experiment.conditions
    required_baselines = set(experiment.conditions) & {
        "vector",
        "vectorless",
        "agentic",
        "agentic_wrapup",
    }
    if adaptive:
        required_baselines.update(("vector", "vectorless", "agentic"))
    if cascade:
        # Checked here as well because copied settings bypass model validation.
        if not experiment.generation.report_evidence_sufficiency:
            raise ValueError(
                "adaptive_cascade requires generation.report_evidence_sufficiency for every "
                "condition, because its escalation reads the shared answer's report"
            )
        required_baselines.update((cascade_policy.FIRST_STAGE, cascade_policy.SECOND_STAGE))
    if "vectorless" in required_baselines:
        from adaptive_rag.retrieval.vectorless import VectorlessRetriever

        retrievers["vectorless"] = VectorlessRetriever(corpus)
    if "agentic" in required_baselines:
        from adaptive_rag.retrieval.agentic import AgenticRetriever

        if clients.agent is None:
            raise ValueError("agentic condition requires a navigation chat client")
        retrievers["agentic"] = AgenticRetriever(
            corpus,
            clients.agent,
            temperature=config.models.temperature if config.models else 0.0,
            max_output_tokens=config.models.max_output_tokens if config.models else 512,
        )
    if "agentic_wrapup" in required_baselines:
        from adaptive_rag.retrieval.agentic_wrapup import AgenticWrapUpRetriever

        if clients.agent is None:
            raise ValueError("agentic_wrapup condition requires a navigation chat client")
        retrievers["agentic_wrapup"] = AgenticWrapUpRetriever(
            corpus,
            clients.agent,
            temperature=config.models.temperature if config.models else 0.0,
            max_output_tokens=config.models.max_output_tokens if config.models else 512,
        )
    if "vector" in required_baselines:
        from adaptive_rag.retrieval.vector import VectorRetriever

        if clients.embedding is None or experiment.vector_index is None:
            raise ValueError("vector condition requires a configured, completed vector_index")
        retriever = VectorRetriever(
            corpus,
            clients.embedding,
            chunking=config.retrieval.chunking,
            batch_size=config.retrieval.embedding_batch_size,
        )
        index_manifest = retriever.load_index(experiment.vector_index).model_dump(mode="json")
        retrievers["vector"] = retriever
    if adaptive:
        from adaptive_rag.retrieval.adaptive import AdaptiveRetriever

        candidates = {name: retrievers[name] for name in ("vector", "vectorless", "agentic")}
        if "adaptive_rule" in experiment.conditions:
            retrievers["adaptive_rule"] = AdaptiveRetriever(
                corpus,
                RuleBasedRouter(),
                candidates,
                policy="adaptive_rule",
                routing_budget=config.routing.budget,
            )
        if "adaptive_llm" in experiment.conditions:
            if clients.router is None:
                raise ValueError("LLM adaptive condition requires a routing chat client")
            retrievers["adaptive_llm"] = AdaptiveRetriever(
                corpus,
                LLMRouter(
                    clients.router,
                    temperature=config.routing.temperature,
                    max_output_tokens=config.routing.max_output_tokens,
                ),
                candidates,
                policy="adaptive_llm",
                routing_budget=config.routing.budget,
            )
    prices = None
    if experiment.price_schedule is not None:
        prices = PriceSchedule.model_validate(
            json.loads(
                experiment.price_schedule.read_bytes(),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        )
    identities = {"answer": deepcopy(clients.answer.identity)}
    if clients.embedding is not None:
        identities["embedding"] = deepcopy(clients.embedding.identity)
    if clients.agent is not None:
        identities["agent"] = deepcopy(clients.agent.identity)
    if clients.router is not None:
        identities["router"] = deepcopy(clients.router.identity)
    if experiment.budget.max_cost_usd is not None:
        if prices is None:
            raise ValueError("a run cost budget requires an explicit dated price schedule")
        required = [(identities["answer"], "chat")]
        if "vector" in required_baselines:
            required.append((identities["embedding"], "embedding"))
        if {"agentic", "agentic_wrapup"} & required_baselines:
            required.append((identities["agent"], "chat"))
        if "adaptive_llm" in experiment.conditions:
            required.append((identities["router"], "chat"))
        available = {(p.base_url, p.model, p.operation) for p in prices.entries}
        if any(
            (identity["base_url"].rstrip("/"), identity["model"], operation) not in available
            for identity, operation in required
        ):
            raise ValueError("cost budget cannot admit models missing from the price schedule")
    run_id = run_id or str(uuid4())
    jobs = []
    for question in questions:
        for condition in experiment.conditions:
            for repetition in range(experiment.repetitions):
                identity = f"{run_id}\0{question.id}\0{condition}\0{repetition}"
                jobs.append(
                    PlannedJob(
                        job_id=hashlib.sha256(identity.encode()).hexdigest(),
                        question_id=question.id,
                        condition=condition,
                        repetition=repetition,
                    )
                )
    random.Random(experiment.order_seed).shuffle(jobs)
    configuration = config.model_dump(mode="json")
    manifest = {
        "schema_version": "1",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_sha256": benchmark_digest,
        "configuration_sha256": hashlib.sha256(_canonical(configuration)).hexdigest(),
        "configuration": configuration,
        "snapshot": corpus.snapshot.model_dump(mode="json"),
        "corpus_fingerprint": corpus.fingerprint,
        "question_hashes": {q.id: question_sha256(q) for q in questions},
        "split": experiment.split,
        "question_count": len(questions),
        "planned_jobs": [job.model_dump(mode="json") for job in jobs],
        "order_seed": experiment.order_seed,
        "model_identities": identities,
        "generation_settings": experiment.generation.model_dump(mode="json"),
        "retrieval_settings": config.retrieval.model_dump(mode="json"),
        "routing_settings": config.routing.model_dump(mode="json") if adaptive else None,
        "price_schedule_sha256": schedule_sha256(prices) if prices else None,
        "index_manifest_sha256": hashlib.sha256(_canonical(index_manifest)).hexdigest()
        if index_manifest
        else None,
        "framework": capture_environment(),
        "preparation_seconds": time.perf_counter() - started,
        "execution_policy": {
            "retrieval_failure": (
                "stop before generation; preserve failed retrieval and partial evidence"
            ),
            "retries": "none",
            "indexing_costs_in_queries": False,
            "provider_seed": None,
            "order_seed_is_provider_seed": False,
            "held_out_labels_in_model_inputs": False,
            "cache_policy": (
                "shared immutable corpus and loaded vector index; "
                "navigation/symbol tools fresh per query"
            ),
            "global_budget": "tighten stage admission/deadlines as remaining run budget decreases",
            "unknown_usage_policy": experiment.budget.unknown_usage_policy,
            "budget_accounting": (
                "Actual usage/cost remain unknown when provider accounting is missing. "
                "Reserve policy uses recorded request-byte/output reservations only for "
                "future-job admission; reservations are not actual billed usage."
            ),
            "routing": (
                "one pre-retrieval selection; all overhead charged; no fallback or escalation"
            ),
        },
    }
    # Added only when the newer conditions are planned, so earlier plans keep their shape.
    if "agentic_wrapup" in required_baselines:
        from adaptive_rag.retrieval import agentic_wrapup

        manifest["agentic_wrapup_settings"] = {
            "policy_version": agentic_wrapup.POLICY_VERSION,
            "prompt_version": agentic_wrapup.PROMPT_VERSION,
            "min_turn_growth_bytes": agentic_wrapup.MIN_TURN_GROWTH_BYTES,
            "final_instruction_bytes": agentic_wrapup.FINAL_NOTE_BYTES,
        }
        manifest["execution_policy"]["agentic_wrapup"] = (
            "one selection request and one tool call are held in reserve; one rejected "
            "selection may be repeated inside the same retrieval budget; no limit is raised"
        )
        manifest["execution_policy"]["retries"] = (
            "none for jobs, requests or answers; agentic_wrapup alone may repeat one rejected "
            "selection inside its own retrieval budget"
        )
    if cascade:
        manifest["cascade_settings"] = dict(cascade_policy.DESCRIPTION)
        manifest["execution_policy"]["cascade"] = (
            "vector first; escalate once to agentic_wrapup on a failed or self-reported "
            "insufficient first stage; keep the completed first-stage answer if the second "
            "stage fails; both stages charged to the job"
        )
        manifest["execution_policy"]["routing"] = (
            "pre-retrieval routers make one selection with no fallback or escalation; "
            "adaptive_cascade is not a router and is described under cascade"
        )
    return PreparedExperiment(
        config,
        corpus,
        questions,
        all_questions,
        raw,
        clients,
        retrievers,
        manifest,
        validation.model_dump(mode="json"),
        prices,
        index_manifest,
    )


def _cost(calls, prices, unrecorded_attempts: int) -> CostEstimate:
    cost = estimate_cost(calls, prices)
    if unrecorded_attempts:
        return CostEstimate(
            estimated_usd=None,
            known_subtotal_usd=cost.known_subtotal_usd,
            unknown_calls=cost.unknown_calls + unrecorded_attempts,
            priced_calls=cost.priced_calls,
            schedule_sha256=cost.schedule_sha256,
        )
    return cost


def _verify_retrieval(
    result: RetrievalResult, job: PlannedJob, question, corpus, *, strategy: str | None = None
) -> None:
    """Check one retrieval output; a cascade stage names the strategy it must report."""
    if (
        result.strategy != (strategy or job.condition)
        or result.query != question.question
        or result.repo_commit != corpus.commit_sha
        or result.corpus_fingerprint != corpus.fingerprint
    ):
        raise ValueError("retrieval output does not match its condition/query/corpus")
    if job.condition in {"adaptive_rule", "adaptive_llm"}:
        route = RoutingResult.model_validate(result.metadata.get("routing"))
        expected_router = "rule_based" if job.condition == "adaptive_rule" else "llm"
        if (
            route.query != question.question
            or route.router != expected_router
            or route.repository.repo_commit != corpus.commit_sha
            or route.repository.corpus_fingerprint != corpus.fingerprint
            or result.selected_strategy != route.selected_strategy
            or (result.status == "completed" and route.status != "completed")
        ):
            raise ValueError("adaptive routing output contradicts its query/corpus/condition")
    for chunk in result.evidence:
        actual = corpus.evidence(chunk.path, chunk.start_line, chunk.end_line)
        if any(
            getattr(chunk, field) != getattr(actual, field)
            for field in (
                "id",
                "path",
                "start_line",
                "end_line",
                "text",
                "excerpt_sha256",
                "repo_commit",
            )
        ):
            raise ValueError("retrieval evidence contradicts the pinned source corpus")


def run_experiment(
    config: FoundationConfig,
    output: Path | str,
    *,
    allow_api: bool = False,
    clients: ExperimentClients | None = None,
) -> dict[str, Any]:
    """Execute one fresh frozen plan; injected clients are for adapters and labeled tests."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"run output already exists: {output}")
    if output.is_relative_to(config.repository.path.resolve()):
        raise ValueError("run output must be outside the pinned source checkout")
    if clients is None and not allow_api:
        raise ValueError("experiment execution requires --allow-api and configured models")
    run_started = time.perf_counter()
    prepared = prepare_experiment(config, clients=clients)
    experiment = config.experiment
    assert experiment is not None
    jobs = [PlannedJob.model_validate(job) for job in prepared.manifest["planned_jobs"]]
    questions = {q.id: q for q in prepared.questions}
    total_usage = TokenUsage()
    total_attempts = observed = 0
    known_cost = 0.0
    unknown_costs = 0
    reserve_unknown = experiment.budget.unknown_usage_policy == "reserve"
    total_budget_usage = TokenUsage()
    budget_known_cost = 0.0
    budget_unknown_cost_jobs = 0
    reserved_unknown_calls = unreserved_unknown_calls = 0
    budget_attempts: list[dict[str, Any]] = []
    result_counts: dict[str, int] = {}
    final_status = "completed"
    stop_reason = None

    def remaining_seconds() -> float:
        return experiment.budget.max_seconds - (time.perf_counter() - run_started)

    def admission_usage() -> TokenUsage:
        return total_budget_usage if reserve_unknown else total_usage

    def admission_known_cost() -> float:
        return budget_known_cost if reserve_unknown else known_cost

    def admission_unknown_costs() -> int:
        return unreserved_unknown_calls if reserve_unknown else unknown_costs

    def budget_snapshot() -> dict[str, Any]:
        return {
            "policy": experiment.budget.unknown_usage_policy,
            "interpretation": "Used-or-reserved admission estimates; not actual billed usage.",
            "usage": total_budget_usage.model_dump(mode="json"),
            "estimated_cost_usd": None if budget_unknown_cost_jobs else budget_known_cost,
            "known_cost_subtotal_usd": budget_known_cost,
            "unknown_cost_jobs": budget_unknown_cost_jobs,
            "reserved_unknown_calls": reserved_unknown_calls,
            "unreserved_unknown_calls": unreserved_unknown_calls,
            "attempts": deepcopy(budget_attempts),
        }

    def limit_reason() -> str | None:
        if remaining_seconds() <= 0:
            return "run wall-clock budget exhausted"
        if total_attempts >= experiment.budget.max_model_calls:
            return "run model-call budget exhausted"
        used = admission_usage()
        if used.total_tokens is None:
            return "run token usage is unknown; further requests disabled"
        if used.total_tokens >= experiment.budget.max_tokens:
            return "run token budget exhausted"
        cap = experiment.budget.max_cost_usd
        if cap is not None and (admission_unknown_costs() or admission_known_cost() >= cap):
            return "run estimated-cost budget exhausted or incomplete"
        return None

    with RunStore(output, prepared.manifest) as store:
        journal = CallJournal(
            store,
            budget=experiment.budget,
            base_usage=admission_usage,
            base_attempts=lambda: total_attempts,
            base_known_cost=admission_known_cost,
            base_unknown_costs=admission_unknown_costs,
            remaining_seconds=remaining_seconds,
            price_schedule=prepared.price_schedule,
        )
        wrapped_clients = ExperimentClients(
            answer=journal.wrap_chat(prepared.clients.answer),
            embedding=journal.wrap_embedding(prepared.clients.embedding)
            if prepared.clients.embedding is not None
            else None,
            agent=journal.wrap_chat(prepared.clients.agent)
            if prepared.clients.agent is not None
            else None,
            router=journal.wrap_chat(prepared.clients.router)
            if prepared.clients.router is not None
            else None,
        )
        for condition, client in (
            ("vector", wrapped_clients.embedding),
            ("agentic", wrapped_clients.agent),
            ("agentic_wrapup", wrapped_clients.agent),
        ):
            if condition in prepared.retrievers and client is not None:
                prepared.retrievers[condition].client = client
        if "adaptive_llm" in prepared.retrievers and wrapped_clients.router is not None:
            prepared.retrievers["adaptive_llm"].router.client = wrapped_clients.router

        def verify_identities() -> None:
            for name in ("answer", "embedding", "agent", "router"):
                client = getattr(wrapped_clients, name)
                if (
                    client is not None
                    and client.identity != prepared.manifest["model_identities"][name]
                ):
                    raise ValueError(f"{name} model identity changed within the experiment")

        def stage_retrieval(job: PlannedJob, question, strategy: str) -> RetrievalResult:
            """One cascade stage under the per-retrieval limits of the fixed conditions."""
            nonlocal phase
            phase = "retrieval"
            spent = journal.usage.total_tokens or 0
            budget = config.retrieval.budget.model_copy(
                update={
                    "max_model_calls": min(
                        config.retrieval.budget.max_model_calls,
                        max(
                            0,
                            experiment.budget.max_model_calls
                            - total_attempts
                            - journal.attempts
                            - 1,
                        ),
                    ),
                    "max_tokens": min(
                        config.retrieval.budget.max_tokens,
                        max(
                            0,
                            experiment.budget.max_tokens - admission_usage().total_tokens - spent,
                        ),
                    ),
                    "max_seconds": max(
                        0.000001,
                        min(config.retrieval.budget.max_seconds, remaining_seconds()),
                    ),
                }
            )
            result = prepared.retrievers[strategy].retrieve(
                RetrievalRequest(
                    query=question.question,
                    top_k=config.retrieval.top_k,
                    budget=budget,
                )
            )
            phase = "retrieval_verification"
            _verify_retrieval(result, job, question, prepared.corpus, strategy=strategy)
            phase = "identity_verification"
            verify_identities()
            return result

        def stage_answer(question, evidence) -> tuple[AnswerResult | None, str, list[str]]:
            """The shared answer request, admitted exactly as for a single-stage job."""
            nonlocal phase
            used = journal.usage
            if used.total_tokens is None:
                return None, "budget_exhausted", ["retrieval usage is unknown; generation disabled"]
            left = experiment.budget.max_tokens - admission_usage().total_tokens - used.total_tokens
            if total_attempts + journal.attempts >= experiment.budget.max_model_calls:
                return None, "budget_exhausted", ["run model-call budget leaves no answer call"]
            if remaining_seconds() <= 0 or left <= 0:
                return None, "budget_exhausted", ["run time/token budget leaves no answer call"]
            phase = "generation"
            settings = experiment.generation.model_copy(
                update={
                    "max_tokens": min(experiment.generation.max_tokens, left),
                    "max_seconds": min(experiment.generation.max_seconds, remaining_seconds()),
                }
            )
            result = GroundedAnswerGenerator(wrapped_clients.answer, settings=settings).generate(
                question.question, evidence
            )
            return result, result.status, list(result.errors)

        def run_cascade(job: PlannedJob, question):
            """Vector first; the reserved-selection navigator only when that does not suffice."""
            nonlocal phase
            first = stage_retrieval(job, question, cascade_policy.FIRST_STAGE)
            first_answer: AnswerResult | None = None
            first_status: str = first.status
            first_errors = list(first.errors)
            if first.status == "completed":
                first_answer, first_status, more = stage_answer(question, first.evidence)
                first_errors.extend(more)
            reported = (
                first_answer.metadata.get("evidence_sufficient")
                if first_answer is not None
                else None
            )
            sufficient = reported if type(reported) is bool else None
            reason = cascade_policy.escalation_reason(
                retrieval_status=first.status,
                answer_status=first_status if first.status == "completed" else None,
                evidence_sufficient=sufficient,
            )
            second: RetrievalResult | None = None
            second_answer: AnswerResult | None = None
            second_status: str | None = None
            second_errors: list[str] = []
            second_attempted = False
            not_admitted: str | None = None
            if reason is not None:
                used = journal.usage
                if used.total_tokens is None:
                    not_admitted = "first-stage usage is unknown; escalation disabled"
                elif total_attempts + journal.attempts + 1 >= experiment.budget.max_model_calls:
                    not_admitted = "run model-call budget leaves no escalation and answer"
                elif (
                    remaining_seconds() <= 0
                    or experiment.budget.max_tokens
                    - admission_usage().total_tokens
                    - used.total_tokens
                    <= 0
                ):
                    not_admitted = "run time/token budget leaves no escalation"
                else:
                    second_attempted = True
                    try:
                        second = stage_retrieval(job, question, cascade_policy.SECOND_STAGE)
                        second_status = second.status
                        second_errors = list(second.errors)
                        if second.status == "completed":
                            second_answer, second_status, more = stage_answer(
                                question, second.evidence
                            )
                            second_errors.extend(more)
                    except Exception as exc:
                        # Provenance and identity failures stay fatal for the whole run.
                        if phase not in {"retrieval", "generation"}:
                            raise
                        second_errors.append(f"second stage {phase}: {exc}")
                        second_status = "error"
            final = cascade_policy.final_stage(
                first_answer_completed=first_answer is not None and first_status == "completed",
                second_attempted=second_attempted,
                second_answer_completed=second_answer is not None and second_status == "completed",
            )
            chosen = second if final == 2 and second is not None else first
            chosen_answer = second_answer if final == 2 else first_answer
            chosen_status = (second_status or "error") if final == 2 else first_status
            summary = {
                "policy_version": cascade_policy.POLICY_VERSION,
                "first_stage": cascade_policy.FIRST_STAGE,
                "second_stage": cascade_policy.SECOND_STAGE,
                "first_stage_evidence_sufficient": sufficient,
                "escalation_reason": reason,
                "escalated": second_attempted,
                "escalation_not_admitted": not_admitted,
                "final_stage": final,
                "final_strategy": chosen.strategy,
                "fell_back_to_first_stage": (
                    reason is not None and final == 1 and chosen_status == "completed"
                ),
            }

            def attempts_of(result: RetrievalResult | None) -> int:
                if result is None:
                    return 0
                return result.metadata.get("model_attempts", len(result.model_calls))

            def stage_record(number, result, stage_result, stage_status, stage_errors):
                return {
                    "stage": number,
                    "strategy": result.strategy if result is not None else None,
                    "status": stage_status,
                    "errors": list(stage_errors),
                    # Calls and operations of both stages are kept once, in order, on the
                    # job's retrieval record and call journal.
                    "retrieval": result.model_dump(
                        mode="json", exclude={"model_calls", "operations"}
                    )
                    if result is not None
                    else None,
                    "answer": stage_result.model_dump(mode="json")
                    if stage_result is not None
                    else None,
                }

            stages = [stage_record(1, first, first_answer, first_status, first_errors)]
            if second_attempted:
                stages.append(stage_record(2, second, second_answer, second_status, second_errors))
            combined = RetrievalResult(
                strategy="adaptive_cascade",
                selected_strategy=chosen.strategy,
                query=question.question,
                repo_commit=prepared.corpus.commit_sha,
                corpus_fingerprint=prepared.corpus.fingerprint,
                status=chosen.status,
                evidence=chosen.evidence,
                operations=first.operations
                + (
                    RetrievalOperation(
                        name="cascade_decision",
                        arguments={"policy": cascade_policy.POLICY_VERSION},
                        details=dict(summary),
                    ),
                )
                + (second.operations if second is not None else ()),
                model_calls=first.model_calls + (second.model_calls if second is not None else ()),
                usage=first.usage.add(second.usage) if second is not None else first.usage,
                tool_call_count=first.tool_call_count
                + (second.tool_call_count if second is not None else 0),
                elapsed_seconds=first.elapsed_seconds
                + (second.elapsed_seconds if second is not None else 0.0),
                errors=first.errors + (second.errors if second is not None else ()),
                metadata={
                    "cascade": summary,
                    "model_attempts": attempts_of(first) + attempts_of(second),
                },
            )
            return (
                combined,
                chosen_answer,
                chosen_status,
                first_errors + second_errors,
                {**summary, "stages": stages},
            )

        store.write_artifact("benchmark.jsonl", prepared.benchmark_raw)
        store.write_artifact("configuration.json", config.model_dump(mode="json"))
        store.write_artifact("validation.json", prepared.validation)
        store.write_artifact(
            "corpus-manifest.json",
            SnapshotManifest(
                snapshot=prepared.corpus.snapshot,
                policy=prepared.corpus.policy,
                files=prepared.corpus.files,
            ).model_dump(mode="json"),
        )
        if prepared.price_schedule is not None:
            store.write_artifact(
                "price-schedule.json", prepared.price_schedule.model_dump(mode="json")
            )
        if prepared.index_manifest is not None:
            store.write_artifact("index-manifest.json", prepared.index_manifest)
        for job in jobs:
            stop_reason = limit_reason()
            if stop_reason:
                final_status = "budget_exhausted"
                store.event(
                    {
                        "event": "run_stopped",
                        "reason": stop_reason,
                        "at": datetime.now(UTC).isoformat(),
                    }
                )
                break
            question = questions[job.question_id]
            started = time.perf_counter()
            journal.begin_job(job.job_id)
            store.event(
                {"event": "job_started", "job_id": job.job_id, "at": datetime.now(UTC).isoformat()}
            )
            retrieval = answer = routing = None
            cascade_details: dict[str, Any] | None = None
            adaptive_retriever = (
                prepared.retrievers[job.condition]
                if job.condition in {"adaptive_rule", "adaptive_llm"}
                else None
            )
            if adaptive_retriever is not None:
                adaptive_retriever.last_routing_result = None
            errors: list[str] = []
            status = "completed"
            provenance_valid = False
            fatal = interrupted = False
            phase = "source_verification"
            try:
                prepared.corpus.verify()
                phase = "identity_verification"
                verify_identities()
                provenance_valid = True
                remaining_tokens = experiment.budget.max_tokens - admission_usage().total_tokens
                if job.condition == "adaptive_cascade":
                    retrieval, answer, status, stage_errors, cascade_details = run_cascade(
                        job, question
                    )
                    errors.extend(stage_errors)
                elif job.condition != "no_retrieval":
                    phase = "retrieval"
                    budget = config.retrieval.budget.model_copy(
                        update={
                            "max_model_calls": min(
                                config.retrieval.budget.max_model_calls,
                                max(0, experiment.budget.max_model_calls - total_attempts - 1),
                            ),
                            "max_tokens": min(config.retrieval.budget.max_tokens, remaining_tokens),
                            "max_seconds": max(
                                0.000001,
                                min(config.retrieval.budget.max_seconds, remaining_seconds()),
                            ),
                        }
                    )
                    retrieval = prepared.retrievers[job.condition].retrieve(
                        RetrievalRequest(
                            query=question.question,
                            top_k=config.retrieval.top_k,
                            budget=budget,
                        )
                    )
                    phase = "retrieval_verification"
                    _verify_retrieval(retrieval, job, question, prepared.corpus)
                    if adaptive_retriever is not None:
                        routing = RoutingResult.model_validate(retrieval.metadata["routing"])
                    phase = "identity_verification"
                    verify_identities()
                    status = retrieval.status
                    errors.extend(retrieval.errors)
                if status == "completed" and job.condition != "adaptive_cascade":
                    stage_attempts = journal.attempts
                    stage_usage = journal.usage
                    remaining_tokens -= stage_usage.total_tokens or 0
                    if stage_usage.total_tokens is None:
                        status = "budget_exhausted"
                        errors.append("retrieval usage is unknown; generation disabled")
                    elif total_attempts + stage_attempts >= experiment.budget.max_model_calls:
                        status = "budget_exhausted"
                        errors.append("run model-call budget leaves no answer call")
                    elif remaining_seconds() <= 0 or remaining_tokens <= 0:
                        status = "budget_exhausted"
                        errors.append("run time/token budget leaves no answer call")
                    else:
                        phase = "generation"
                        settings = experiment.generation.model_copy(
                            update={
                                "max_tokens": min(
                                    experiment.generation.max_tokens, remaining_tokens
                                ),
                                "max_seconds": min(
                                    experiment.generation.max_seconds, remaining_seconds()
                                ),
                            }
                        )
                        answer = GroundedAnswerGenerator(
                            wrapped_clients.answer,
                            settings=settings,
                        ).generate(question.question, retrieval.evidence if retrieval else ())
                        status = answer.status
                        errors.extend(answer.errors)
                phase = "final_verification"
                prepared.corpus.verify()
                verify_identities()
            except (KeyboardInterrupt, SystemExit) as exc:
                interrupted = True
                status = "interrupted"
                errors.append(f"{phase}: soft interruption ({type(exc).__name__})")
                try:
                    prepared.corpus.verify()
                    verify_identities()
                except Exception:
                    provenance_valid = False
            except Exception as exc:
                status = "error"
                errors.append(f"{phase}: {exc}")
                if phase in {
                    "source_verification",
                    "identity_verification",
                    "retrieval_verification",
                    "final_verification",
                } or (adaptive_retriever is not None and phase == "retrieval"):
                    provenance_valid = False
                    fatal = True
            if adaptive_retriever is not None and routing is None:
                routing = adaptive_retriever.last_routing_result
            calls = journal.calls
            attempts = journal.attempts
            usage = journal.usage
            cost = _cost(calls, prepared.price_schedule, journal.unknown_attempts)
            combined_usage = total_usage.add(usage)
            job_budget = deepcopy(journal.budget_accounting)
            job_budget_usage = TokenUsage.model_validate(job_budget["usage"])
            job_budget_cost = job_budget["estimated_cost_usd"]
            finite_budget_cost = (
                type(job_budget_cost) in (int, float)
                and math.isfinite(job_budget_cost)
                and job_budget_cost >= 0
            )
            actual_unknown_calls = journal.unknown_attempts + sum(
                call.usage.total_tokens is None for call in calls
            )
            reservable = (
                job_budget_usage.total_tokens is not None
                and job_budget["unreserved_unknown_calls"] == 0
                and job_budget["reserved_unknown_calls"] >= actual_unknown_calls
                and finite_budget_cost
            )
            unreservable = reserve_unknown and (
                job_budget_usage.total_tokens is None
                or not finite_budget_cost
                or job_budget["unreserved_unknown_calls"] > 0
                or (usage.total_tokens is None and not reservable)
            )
            combined_budget_usage = total_budget_usage.add(job_budget_usage)
            compared_usage = combined_budget_usage if reserve_unknown else combined_usage
            compared_cost = (
                budget_known_cost + (job_budget_cost if finite_budget_cost else 0.0)
                if reserve_unknown
                else known_cost + cost.known_subtotal_usd
            )
            compared_unknown_cost = (
                budget_unknown_cost_jobs + int(not finite_budget_cost)
                if reserve_unknown
                else unknown_costs + cost.unknown_calls
            )
            cap = experiment.budget.max_cost_usd
            overshoot = (
                remaining_seconds() < 0
                or (
                    compared_usage.total_tokens is not None
                    and compared_usage.total_tokens > experiment.budget.max_tokens
                )
                or total_attempts + attempts > experiment.budget.max_model_calls
                or (cap is not None and (compared_unknown_cost > 0 or compared_cost > cap))
            )
            if overshoot and not interrupted and not fatal:
                status = "budget_exhausted"
                errors.append(
                    "an in-flight operation exceeded or invalidated the global run budget"
                )
            record = ExperimentRecord(
                run_id=prepared.manifest["run_id"],
                job_id=job.job_id,
                question_id=question.id,
                question_sha256=question_sha256(question),
                category=question.category,
                split=question.split,
                condition=job.condition,
                repetition=job.repetition,
                status=status,
                retrieval=retrieval,
                routing=routing,
                answer=answer,
                model_calls=calls,
                usage=usage,
                tool_call_count=retrieval.tool_call_count if retrieval else 0,
                elapsed_seconds=time.perf_counter() - started,
                errors=tuple(errors),
                metrics=compute_mechanical_metrics(
                    question,
                    retrieval.evidence if retrieval else (),
                    answer,
                )
                if provenance_valid
                else None,
                estimated_cost_usd=cost.estimated_usd,
                metadata={
                    "model_attempts": attempts,
                    "cost": cost.model_dump(mode="json"),
                    "indexing_costs_included": False,
                    "provenance_verified": provenance_valid,
                    "admission_rejection": journal.blocked_reason,
                    "budget_accounting": {
                        **job_budget,
                        "policy": experiment.budget.unknown_usage_policy,
                        "interpretation": (
                            "Used-or-reserved admission estimates; not actual billed usage."
                        ),
                    },
                    **({"cascade": cascade_details} if cascade_details is not None else {}),
                },
            )
            store.record(record)
            store.event(
                {
                    "event": "job_finished",
                    "job_id": job.job_id,
                    "status": status,
                    "at": datetime.now(UTC).isoformat(),
                }
            )
            observed += 1
            total_attempts += attempts
            total_usage = total_usage.add(usage)
            known_cost += cost.known_subtotal_usd
            unknown_costs += cost.unknown_calls
            total_budget_usage = combined_budget_usage
            if finite_budget_cost:
                budget_known_cost += job_budget_cost
            else:
                budget_unknown_cost_jobs += 1
            reserved_unknown_calls += job_budget["reserved_unknown_calls"]
            unreserved_unknown_calls += job_budget["unreserved_unknown_calls"]
            budget_attempts.extend(deepcopy(job_budget["attempts"]))
            result_counts[status] = result_counts.get(status, 0) + 1
            if (
                interrupted
                or fatal
                or overshoot
                or unreservable
                or (usage.total_tokens is None and not reserve_unknown)
            ):
                final_status = (
                    "interrupted" if interrupted else "failed" if fatal else "budget_exhausted"
                )
                stop_reason = (
                    "model accounting has no finite token/cost reservation; further jobs disabled"
                    if unreservable
                    else errors[-1]
                    if errors
                    else "run accounting is incomplete"
                )
                store.event(
                    {
                        "event": "run_stopped",
                        "reason": stop_reason,
                        "at": datetime.now(UTC).isoformat(),
                    }
                )
                break
        if (
            final_status == "completed"
            and observed == len(jobs)
            and any(status != "completed" for status in result_counts)
        ):
            final_status = "completed_with_errors"
        store.finish(
            final_status,
            planned_jobs=len(jobs),
            observed_jobs=observed,
            result_counts=result_counts,
            stop_reason=stop_reason,
            model_attempts=total_attempts,
            usage=total_usage.model_dump(mode="json"),
            estimated_cost_usd=None if unknown_costs else known_cost,
            known_cost_subtotal_usd=known_cost,
            unknown_cost_calls=unknown_costs,
            elapsed_seconds=time.perf_counter() - run_started,
            budget_accounting=budget_snapshot(),
        )
    return {
        "run_id": prepared.manifest["run_id"],
        "output": str(output),
        "status": final_status,
        "planned_jobs": len(jobs),
        "observed_jobs": observed,
        "result_counts": result_counts,
    }

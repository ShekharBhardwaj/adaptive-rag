"""Pinned source inspection, retrieval, adaptive routing, and reproducible experiments."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from adaptive_rag.config import FoundationConfig, load_config
from adaptive_rag.evaluation import validate_benchmark
from adaptive_rag.ingestion import (
    DiscoveryPolicy,
    IngestionError,
    RepositorySnapshot,
    SnapshotManifest,
    clone_snapshot,
    discover_files,
    verify_snapshot,
)
from adaptive_rag.models import BenchmarkQuestion
from adaptive_rag.observability import JsonlTraceSink, make_trace
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import RetrievalRequest


def _write_json(data: dict, output: Path | None) -> None:
    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    # Inspection and validation artifacts are immutable: give a fresh output path.
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    print(json.dumps({"output": str(output.resolve()), "status": "written"}))


def _configured_snapshot(config: FoundationConfig, *, clone: bool = False) -> RepositorySnapshot:
    repo = config.repository
    if clone and (not repo.path.exists() or (repo.path.is_dir() and not any(repo.path.iterdir()))):
        snapshot = clone_snapshot(repo.url, repo.path, repo.commit_sha)
    else:
        snapshot = verify_snapshot(repo.path, repo.commit_sha)
    if snapshot.url.rstrip("/").removesuffix(".git") != repo.url.rstrip("/").removesuffix(".git"):
        raise ValueError("repository origin does not match the configured URL")
    return snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    groups = parser.add_subparsers(dest="group", required=True)
    repo = groups.add_parser("repo", help="Create or inspect a pinned clean Git snapshot")
    repo_commands = repo.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "inspect"):
        command = repo_commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument(
            "--output", type=Path, help="Write a new JSON artifact; never overwrite"
        )
    config = groups.add_parser("config", help="Validate inert YAML settings")
    config_commands = config.add_subparsers(dest="command", required=True)
    config_commands.add_parser("validate").add_argument("--config", type=Path, required=True)
    benchmark = groups.add_parser("benchmark", help="Validate independently authored annotations")
    benchmark_commands = benchmark.add_subparsers(dest="command", required=True)
    schema = benchmark_commands.add_parser("schema")
    schema.add_argument("--output", type=Path)
    validate = benchmark_commands.add_parser("validate")
    validate.add_argument("dataset", type=Path)
    validate.add_argument("--config", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    validate.add_argument("--pilot", action="store_true", help="Require balanced 30-question pilot")
    validate.add_argument(
        "--allow-unreviewed", action="store_true", help="Audit draft evidence; emit review warnings"
    )
    retrieve = groups.add_parser(
        "retrieve", help="Return source evidence using a fixed or adaptive strategy"
    )
    retrieve.add_argument("--config", type=Path, required=True)
    retrieve.add_argument(
        "--strategy",
        choices=("vector", "vectorless", "agentic", "adaptive_rule", "adaptive_llm"),
        required=True,
    )
    retrieve.add_argument("--query", required=True)
    retrieve.add_argument("--top-k", type=int)
    retrieve.add_argument("--index", type=Path, help="Previously built index for vector retrieval")
    retrieve.add_argument("--output", type=Path)
    retrieve.add_argument("--trace", type=Path, help="New JSONL trace artifact")
    retrieve.add_argument(
        "--allow-api", action="store_true", help="Permit configured model requests"
    )
    route = groups.add_parser("route", help="Inspect a pre-retrieval decision without retrieving")
    route.add_argument("--config", type=Path, required=True)
    route.add_argument("--router", choices=("rule", "llm"), required=True)
    route.add_argument("--query", required=True)
    route.add_argument("--output", type=Path, help="Write a new JSON decision artifact")
    route.add_argument(
        "--allow-api", action="store_true", help="Permit configured routing model requests"
    )
    index = groups.add_parser("index", help="Plan or build an immutable FAISS vector index")
    index_commands = index.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        command = index_commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--output", type=Path, required=name == "build")
        if name == "build":
            command.add_argument("--allow-api", action="store_true")
            command.add_argument(
                "--reuse-from",
                type=Path,
                help="Explicitly reuse verified successful batches into a new index directory",
            )
    experiment = groups.add_parser(
        "experiment", help="Plan, execute, review, and summarize retrieval conditions"
    )
    experiments = experiment.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        command = experiments.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--output", type=Path, required=name == "run")
        if name == "run":
            command.add_argument("--allow-api", action="store_true")
    for name in ("summarize", "review-template"):
        command = experiments.add_parser(name)
        command.add_argument("run", type=Path)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--seed", type=int, default=0)
        if name == "summarize":
            command.add_argument("--reviews", type=Path)
            command.add_argument("--bootstrap-samples", type=int, default=2000)
    return parser


def _model_client(
    config: FoundationConfig,
    operation: str,
    allow_api: bool,
    *,
    model_override: str | None = None,
    pacers=None,
):
    from adaptive_rag.generation.client import OpenAIChatClient, OpenAIEmbeddingClient
    from adaptive_rag.generation.connections import request_pacers

    if not allow_api:
        raise ValueError("model requests require --allow-api and explicitly configured model IDs")
    settings = config.models
    if settings is None:
        raise ValueError("add a models section to your YAML; see configs/retrieval.example.yaml")
    model = model_override or (
        settings.embedding_model if operation == "embedding" else settings.chat_model
    )
    if model is None or model.startswith("REPLACE_"):
        raise ValueError(f"configure a real {operation} model ID served by your endpoint")
    embedding = operation == "embedding"
    base_url = settings.base_url if embedding else (settings.chat_base_url or settings.base_url)
    key_env = (
        settings.api_key_env if embedding else (settings.chat_api_key_env or settings.api_key_env)
    )
    kwargs = dict(base_url=base_url, model=model, api_key=os.environ.get(key_env))
    embedding_pacer, chat_pacer = pacers if pacers is not None else request_pacers(settings)
    kwargs["pacer"] = embedding_pacer if embedding else chat_pacer
    if operation == "embedding":
        return OpenAIEmbeddingClient(dimensions=settings.embedding_dimensions, **kwargs)
    return OpenAIChatClient(token_parameter=settings.token_parameter, **kwargs)


def _router(config: FoundationConfig, name: str, allow_api: bool, *, pacers=None):
    from adaptive_rag.routing import LLMRouter, RuleBasedRouter

    if name == "rule":
        return RuleBasedRouter()
    client = _model_client(
        config, "chat", allow_api, model_override=config.routing.chat_model, pacers=pacers
    )
    return LLMRouter(
        client,
        temperature=config.routing.temperature,
        max_output_tokens=config.routing.max_output_tokens,
    )


def _route(args, config: FoundationConfig) -> int:
    import hashlib

    from adaptive_rag.routing import RepositoryMetadata, RoutingRequest

    started = time.monotonic()
    if args.output is not None:
        if args.output.exists():
            raise FileExistsError(f"output already exists: {args.output}")
        if args.output.resolve().is_relative_to(config.repository.path):
            raise ValueError("routing artifacts must be outside the pinned repository checkout")
    # Reject invalid queries and API settings before source preparation or calls.
    validated = RetrievalRequest(query=args.query, budget=config.routing.budget)
    router = _router(config, args.router, args.allow_api)
    _configured_snapshot(config)
    corpus = RepositoryCorpus.from_repository(
        config.repository.path, config.repository.commit_sha, config.files
    )
    request = RoutingRequest(
        query=validated.query,
        repository=RepositoryMetadata.from_corpus(corpus),
        budget=config.routing.budget,
    )
    preparation_seconds = time.monotonic() - started
    result = router.route(request)
    configuration = config.model_dump(mode="json")
    encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    report = result.model_dump(mode="json")
    report.update(
        request=request.model_dump(mode="json"),
        configuration=configuration,
        configuration_sha256=hashlib.sha256(encoded).hexdigest(),
        preparation_seconds=preparation_seconds,
        end_to_end_seconds=time.monotonic() - started,
    )
    _write_json(report, args.output)
    return 0 if result.status == "completed" else 2


def _phase2(args, config: FoundationConfig) -> int:
    from adaptive_rag.retrieval.chunking import chunk_corpus

    started = time.monotonic()
    request = None
    client = None
    adaptive = args.group == "retrieve" and args.strategy in {"adaptive_rule", "adaptive_llm"}
    adaptive_clients = None
    router = None
    outputs = [
        output.resolve()
        for output in (getattr(args, "output", None), getattr(args, "trace", None))
        if output is not None
    ]
    if len(set(outputs)) != len(outputs):
        raise ValueError("result and trace artifacts require different output paths")
    if any(output.is_relative_to(config.repository.path) for output in outputs):
        raise ValueError("artifacts must be saved outside the pinned repository checkout")
    # Reject invalid model settings, existing output artifacts, and invalid queries
    # before loading the corpus or making any potentially billable call.
    for output in (getattr(args, "output", None), getattr(args, "trace", None)):
        if output is not None and output.exists():
            raise FileExistsError(f"output already exists: {output}")
    if args.group == "retrieve":
        request = RetrievalRequest(
            query=args.query,
            top_k=args.top_k if args.top_k is not None else config.retrieval.top_k,
            budget=config.retrieval.budget,
        )
        if adaptive:
            if args.index is None:
                raise ValueError("adaptive retrieval requires --index for its vector candidate")
            from adaptive_rag.generation.connections import request_pacers

            pacers = request_pacers(config.models) if config.models is not None else None
            adaptive_clients = (
                _model_client(config, "embedding", args.allow_api, pacers=pacers),
                _model_client(config, "chat", args.allow_api, pacers=pacers),
            )
            router = _router(
                config,
                "rule" if args.strategy == "adaptive_rule" else "llm",
                args.allow_api,
                pacers=pacers,
            )
        elif args.strategy in ("vector", "agentic"):
            client = _model_client(
                config, "embedding" if args.strategy == "vector" else "chat", args.allow_api
            )
        if args.strategy == "vector" and args.index is None:
            raise ValueError("vector retrieval requires --index pointing to a completed index")
    elif args.command == "build":
        client = _model_client(config, "embedding", args.allow_api)
    _configured_snapshot(config)
    corpus = RepositoryCorpus.from_repository(
        config.repository.path, config.repository.commit_sha, config.files
    )
    if args.group == "index":
        if args.command == "plan":
            chunks = chunk_corpus(corpus, config.retrieval.chunking)
            _write_json(
                {
                    "repo_commit": corpus.commit_sha,
                    "corpus_fingerprint": corpus.fingerprint,
                    "source_files": len(corpus.files),
                    "chunks": len(chunks),
                    "embedding_input_utf8_bytes": sum(len(chunk.text.encode()) for chunk in chunks),
                    "embedding_batch_size": config.retrieval.embedding_batch_size,
                    "planned_embedding_calls": (
                        len(chunks) + config.retrieval.embedding_batch_size - 1
                    )
                    // config.retrieval.embedding_batch_size,
                    "indexing_budget": config.retrieval.indexing_budget.model_dump(mode="json"),
                    "note": (
                        "Byte counts are conservative admission estimates, "
                        "not provider token usage."
                    ),
                },
                args.output,
            )
            return 0
        from adaptive_rag.retrieval.vector import VectorRetriever

        retriever = VectorRetriever(
            corpus,
            client,
            chunking=config.retrieval.chunking,
            batch_size=config.retrieval.embedding_batch_size,
        )
        build_options = {"budget": config.retrieval.indexing_budget}
        if args.reuse_from is not None:
            build_options["reuse_from"] = args.reuse_from
        manifest = retriever.build_index(args.output, **build_options)
        # Raw calls include every embedding vector. Keep them in the immutable
        # manifest without serializing that potentially large payload to stdout.
        directory = args.output.resolve()
        summary = {
            "status": "completed",
            "index_directory": str(directory),
            "manifest_path": str(directory / "manifest.json"),
            "index_version": manifest.index_version,
            "repo_commit": manifest.repo_commit,
            "corpus_fingerprint": manifest.corpus_fingerprint,
            "embedding_identity": manifest.embedding_identity,
            "chunk_count": manifest.chunk_count,
            "dimensions": manifest.dimensions,
            "model_attempts": manifest.model_attempts,
            "usage": manifest.usage.model_dump(mode="json"),
            "elapsed_seconds": manifest.elapsed_seconds,
            "input_token_byte_estimate": manifest.input_token_byte_estimate,
        }
        reuse = getattr(manifest, "reuse_provenance", None)
        if reuse is not None:
            # Parent failure provenance can include raw calls; print only counters.
            summary["reuse"] = {
                key: reuse[key]
                for key in (
                    "source_directory",
                    "reused_successful_calls",
                    "reused_chunks",
                    "reused_usage",
                    "new_model_attempts",
                    "new_usage",
                    "budget_scope",
                )
                if key in reuse
            }
        _write_json(summary, None)
        return 0
    if adaptive:
        from adaptive_rag.retrieval.adaptive import AdaptiveRetriever
        from adaptive_rag.retrieval.agentic import AgenticRetriever
        from adaptive_rag.retrieval.vector import VectorRetriever
        from adaptive_rag.retrieval.vectorless import VectorlessRetriever

        vector = VectorRetriever(
            corpus,
            adaptive_clients[0],
            chunking=config.retrieval.chunking,
            batch_size=config.retrieval.embedding_batch_size,
        )
        # Index integrity/compatibility fails before any routing request is paid for.
        vector.load_index(args.index)
        retriever = AdaptiveRetriever(
            corpus,
            router,
            {
                "vector": vector,
                "vectorless": VectorlessRetriever(corpus),
                "agentic": AgenticRetriever(
                    corpus,
                    adaptive_clients[1],
                    temperature=config.models.temperature,
                    max_output_tokens=config.models.max_output_tokens,
                ),
            },
            policy=args.strategy,
            routing_budget=config.routing.budget,
        )
    elif args.strategy == "vectorless":
        from adaptive_rag.retrieval.vectorless import VectorlessRetriever

        retriever = VectorlessRetriever(corpus)
    elif args.strategy == "vector":
        from adaptive_rag.retrieval.vector import VectorRetriever

        retriever = VectorRetriever(
            corpus,
            client,
            chunking=config.retrieval.chunking,
            batch_size=config.retrieval.embedding_batch_size,
        )
        retriever.load_index(args.index)
    else:
        from adaptive_rag.retrieval.agentic import AgenticRetriever

        retriever = AgenticRetriever(
            corpus,
            client,
            temperature=config.models.temperature,
            max_output_tokens=config.models.max_output_tokens,
        )
    preparation_seconds = time.monotonic() - started
    result = retriever.retrieve(request)
    result = result.model_copy(
        update={
            "metadata": {
                **result.metadata,
                "preparation_seconds": preparation_seconds,
                "end_to_end_seconds": time.monotonic() - started,
            }
        }
    )
    if args.trace:
        with JsonlTraceSink(args.trace) as sink:
            sink.record(make_trace(config.model_dump(mode="json"), request, result))
    _write_json(result.model_dump(mode="json"), args.output)
    return 0 if result.status == "completed" else 2


def _phase3(args) -> int:
    from adaptive_rag.evaluation.runner import prepare_experiment, run_experiment

    if args.command in {"plan", "run"}:
        config = load_config(args.config)
        if args.command == "run":
            result = run_experiment(config, args.output, allow_api=args.allow_api)
            _write_json(result, None)
            return (
                130
                if result["status"] == "interrupted"
                else 0
                if result["status"] == "completed"
                else 2
            )
        if args.output is not None:
            if args.output.exists():
                raise FileExistsError(f"output already exists: {args.output}")
            if args.output.resolve().is_relative_to(config.repository.path):
                raise ValueError("planning artifacts must be outside the pinned corpus checkout")
        prepared = prepare_experiment(config)
        _write_json(prepared.manifest, args.output)
        return 0
    from adaptive_rag.evaluation.analysis import aggregate_results
    from adaptive_rag.evaluation.reviews import (
        export_review_template,
        load_reviews,
        validate_reviews,
    )
    from adaptive_rag.evaluation.storage import load_run

    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    if args.output.resolve().is_relative_to(args.run.resolve()):
        raise ValueError("derived artifacts must be saved outside the immutable raw run directory")
    loaded = load_run(args.run)
    questions, planned_jobs = _validate_frozen_run_inputs(args.run, loaded)
    if args.command == "review-template":
        items = export_review_template(loaded.records, questions, seed=args.seed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            for item in items:
                stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
        print(
            json.dumps(
                {
                    "output": str(args.output.resolve()),
                    "review_items": len(items),
                    "run_partial": loaded.partial,
                    "load_issues": loaded.issues,
                }
            )
        )
        return 0
    scores = load_reviews(args.reviews) if args.reviews else ()
    validate_reviews(loaded.records, scores, questions=questions)
    summary = aggregate_results(
        loaded.records,
        planned_jobs,
        scores=scores,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    summary.update(
        run_id=loaded.manifest["run_id"],
        raw_run_status=loaded.status,
        raw_load_issues=list(loaded.issues),
        raw_run_partial=loaded.partial,
        benchmark_sha256=loaded.manifest["benchmark_sha256"],
        configuration_sha256=loaded.manifest["configuration_sha256"],
    )
    _write_json(summary, args.output)
    return 0


def _validate_frozen_run_inputs(run: Path, loaded):
    """Bind both derived workflows to the same frozen Cartesian execution plan.

    Valid prefixes of interrupted/corrupt JSONL remain usable; absent outputs
    stay in the full original planned denominator. Contradictory valid rows or
    mutated plans are rejected before exporting reviews or reporting metrics.
    """
    import hashlib
    import itertools

    from adaptive_rag.evaluation.benchmark import load_benchmark
    from adaptive_rag.evaluation.experiment_models import PlannedJob, question_sha256
    from adaptive_rag.evaluation.runner import _canonical

    manifest = loaded.manifest
    benchmark = run / "benchmark.jsonl"
    if hashlib.sha256(benchmark.read_bytes()).hexdigest() != manifest.get("benchmark_sha256"):
        raise ValueError("frozen benchmark checksum differs from the run manifest")
    configuration = json.loads((run / "configuration.json").read_bytes())
    if hashlib.sha256(_canonical(configuration)).hexdigest() != manifest.get(
        "configuration_sha256"
    ):
        raise ValueError("frozen configuration checksum differs from the run manifest")
    config = FoundationConfig.model_validate(configuration)
    settings = config.experiment
    if settings is None:
        raise ValueError("frozen configuration must declare the experiment")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run manifest requires a nonblank run_id")
    questions = load_benchmark(benchmark)
    selected = {q.id: q for q in questions if q.split == settings.split}
    if manifest.get("split") != settings.split or manifest.get("question_count") != len(selected):
        raise ValueError("run manifest contradicts the frozen experiment split/questions")
    hashes = {identifier: question_sha256(q) for identifier, q in selected.items()}
    if manifest.get("question_hashes") != hashes:
        raise ValueError("run manifest question hashes differ from the frozen benchmark")
    raw_jobs = manifest.get("planned_jobs")
    if not isinstance(raw_jobs, list):
        raise ValueError("run manifest requires a planned_jobs list")
    jobs = tuple(PlannedJob.model_validate(job) for job in raw_jobs)
    by_job = {job.job_id: job for job in jobs}
    identities = {(job.question_id, job.condition, job.repetition) for job in jobs}
    if len(by_job) != len(jobs) or len(identities) != len(jobs):
        raise ValueError("run manifest contains duplicate planned jobs")
    expected = set(itertools.product(selected, settings.conditions, range(settings.repetitions)))
    if not expected or identities != expected:
        raise ValueError(
            "planned jobs do not cover the frozen questions, conditions, and repetitions"
        )
    observed = set()
    for record in loaded.records:
        job = by_job.get(record.job_id)
        if record.run_id != run_id or job is None:
            raise ValueError("raw output is outside the frozen run/plan")
        if record.job_id in observed:
            raise ValueError("raw output contains duplicate planned jobs")
        observed.add(record.job_id)
        if any(
            getattr(record, field) != getattr(job, field)
            for field in ("question_id", "condition", "repetition")
        ):
            raise ValueError("raw output contradicts its frozen planned job")
        question = selected.get(record.question_id)
        if question is None or hashes[record.question_id] != record.question_sha256:
            raise ValueError("raw output is bound to a different benchmark annotation")
        if record.category != question.category or record.split != question.split:
            raise ValueError(
                "raw output category/split differs from its frozen benchmark annotation"
            )
    return questions, jobs


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.group == "experiment":
            return _phase3(args)
        if args.group == "benchmark" and args.command == "schema":
            _write_json(BenchmarkQuestion.model_json_schema(), args.output)
            return 0
        config = load_config(args.config)
        if args.group == "route":
            return _route(args, config)
        if args.group in {"retrieve", "index"}:
            return _phase2(args, config)
        if args.group == "config":
            _write_json(config.model_dump(mode="json"), None)
            return 0
        if args.group == "repo":
            snapshot = _configured_snapshot(config, clone=args.command == "snapshot")
            if args.command == "snapshot":
                data = snapshot.model_dump(mode="json")
            else:
                policy: DiscoveryPolicy = config.files
                manifest = SnapshotManifest(
                    snapshot=snapshot,
                    policy=policy,
                    files=discover_files(
                        config.repository.path, policy, expected_commit=config.repository.commit_sha
                    ),
                )
                data = manifest.model_dump(mode="json")
            _write_json(data, args.output)
            return 0
        _configured_snapshot(config)
        report = validate_benchmark(
            args.dataset,
            config.repository.path,
            config.repository.commit_sha,
            require_reviewed=not args.allow_unreviewed,
            pilot=args.pilot,
            policy=config.files,
        )
        _write_json(report.model_dump(mode="json"), args.output)
        return 0 if report.valid else 2
    except (IngestionError, ValidationError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 2

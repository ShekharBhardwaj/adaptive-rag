"""Bounded provider compatibility check using synthetic source, never benchmark items."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.config import load_config
from adaptive_rag.evaluation.pricing import PriceSchedule, estimate_cost
from adaptive_rag.evaluation.runner import _clients
from adaptive_rag.generation.answers import GroundedAnswerGenerator
from adaptive_rag.generation.models import GenerationSettings
from adaptive_rag.retrieval.agentic import AgenticRetriever
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import RetrievalBudget, RetrievalRequest
from adaptive_rag.routing import LLMRouter, RepositoryMetadata, RoutingRequest

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--allow-api", action="store_true", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
config = load_config(args.config)
assert config.models.chat_base_url == "https://api.anthropic.com/v1"
for variable in (config.models.api_key_env, config.models.chat_api_key_env):
    if not variable or not os.environ.get(variable):
        raise ValueError(f"Required credential is absent: {variable}; no requests made")
prices = PriceSchedule.model_validate_json(config.experiment.price_schedule.read_text())
clients = _clients(config)
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
deadline = time.monotonic() + 180
calls = []
results = {}
stage = "not_started"


def save(name, value):
    with (output / name).open("x") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def admit():
    cost = estimate_cost(calls, prices)
    remaining = deadline - time.monotonic()
    if len(calls) >= 8 or remaining <= 0 or cost.estimated_usd is None:
        raise ValueError("Compatibility call/time/accounting limit reached")
    if cost.estimated_usd >= 0.10:
        raise ValueError("Compatibility estimated-cost limit reached")
    return remaining


def record(call):
    calls.append(call)
    with (output / "model-calls.jsonl").open("a") as stream:
        stream.write(json.dumps({"stage": stage, "call": call.model_dump(mode="json")}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class TrackedClient:
    def __init__(self, delegate):
        self.delegate = delegate

    @property
    def identity(self):
        return self.delegate.identity

    def invoke(self, method, *values, timeout, **kwargs):
        remaining = admit()
        try:
            response = getattr(self.delegate, method)(
                *values, timeout=min(timeout, remaining), **kwargs
            )
        except Exception as exc:
            if getattr(exc, "record", None) is not None:
                record(exc.record)
            raise
        record(response.call)
        return response

    def complete(self, messages, tools, **kwargs):
        return self.invoke("complete", messages, tools, **kwargs)

    def embed(self, texts, **kwargs):
        return self.invoke("embed", texts, **kwargs)


try:
    source = root / "experiments/preflight/phase4-2026-11-16/live-compatibility-008/synthetic-source"
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    corpus = RepositoryCorpus.from_repository(source, commit, config.files)
    stage = "qwen_query_embedding"
    embedding = TrackedClient(clients.embedding).embed(
        ["Where is SyntheticWidget defined?"], timeout=30
    )
    assert len(embedding.vectors) == 1 and len(embedding.vectors[0]) == 4096
    assert embedding.call.usage.total_tokens is not None
    results[stage] = {"status": "passed", "dimensions": 4096}

    stage = "anthropic_routing"
    route = LLMRouter(TrackedClient(clients.router), max_output_tokens=256).route(
        RoutingRequest(
            query="Where is SyntheticWidget defined in synthetic.py?",
            repository=RepositoryMetadata.from_corpus(corpus),
            budget=config.routing.budget,
        )
    )
    save("synthetic-routing.json", route.model_dump(mode="json"))
    assert route.status == "completed", route.errors
    results[stage] = {"status": "passed", "selection": route.selected_strategy}

    stage = "anthropic_grounded_answer"
    answer = GroundedAnswerGenerator(
        TrackedClient(clients.answer),
        settings=GenerationSettings(max_output_tokens=256, max_tokens=16000, max_seconds=30),
    ).generate(
        "What is the value of SyntheticWidget.value?",
        (corpus.evidence("synthetic.py", 1, 2),),
    )
    save("synthetic-answer.json", answer.model_dump(mode="json"))
    assert answer.status == "completed" and answer.citations, answer.errors
    results[stage] = {"status": "passed", "citations": len(answer.citations)}

    stage = "anthropic_native_tools"
    navigation = AgenticRetriever(corpus, TrackedClient(clients.agent)).retrieve(
        RetrievalRequest(
            query=("Use read_file to read synthetic.py lines 1-2, then call select_evidence "
                   "with the returned evidence ID."),
            budget=RetrievalBudget(
                max_model_calls=4, max_tool_calls=5, max_tokens=32000, max_seconds=60
            ),
        )
    )
    save("synthetic-navigation.json", navigation.model_dump(mode="json"))
    assert navigation.status == "completed" and navigation.evidence, navigation.errors
    assert navigation.metadata.get("selection_method") == "tool_call"
    results[stage] = {"status": "passed", "model_calls": len(navigation.model_calls)}
    status = "passed"
except Exception as exc:
    status = "failed"
    results[stage] = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}

summary = {
    "status": status,
    "kind": "synthetic_compatibility_check_not_benchmark_results",
    "recorded_at": datetime.now(UTC).isoformat(),
    "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
    "model_identities": {name: getattr(clients, name).identity for name in ("embedding", "answer", "agent", "router")},
    "limits": {"model_calls": 8, "seconds": 180, "estimated_cost_usd": 0.10},
    "results": results,
    "model_calls": len(calls),
    "cost": estimate_cost(calls, prices).model_dump(mode="json"),
}
save("summary.json", summary)
print(json.dumps(summary, indent=2))
raise SystemExit(0 if status == "passed" else 2)

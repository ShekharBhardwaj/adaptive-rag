"""Bounded provider compatibility check of the phase 6 request shapes.

Synthetic source and synthetic questions only; never benchmark items. It checks
that the provider accepts the new requests before a study is run:

* the shared answer with the evidence-sufficiency report;
* the reserved selection of ``agentic_wrapup``, a user instruction after tool results;
* its two retry shapes, after an ignored instruction and after prose.

The model cannot be made to misbehave on demand, so for the two retry shapes one
assistant message is simulated locally and the follow-up request is real. Simulated
messages are written to ``simulated-responses.jsonl``, are never sent as provider
output, and cost nothing. These are not benchmark results.
"""

import argparse
import hashlib
import json
import os
import subprocess
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.config import load_config
from adaptive_rag.evaluation.pricing import PriceSchedule, estimate_cost
from adaptive_rag.evaluation.runner import _clients
from adaptive_rag.generation.answers import SUFFICIENCY_PROMPT_VERSION, GroundedAnswerGenerator
from adaptive_rag.generation.client import ChatResponse
from adaptive_rag.generation.models import GenerationSettings
from adaptive_rag.retrieval import agentic_wrapup
from adaptive_rag.retrieval.agentic_wrapup import AgenticWrapUpRetriever
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import (
    ModelCallRecord,
    RetrievalBudget,
    RetrievalRequest,
    TokenUsage,
)

MAX_CALLS, MAX_SECONDS, MAX_COST_USD = 12, 300, 0.10

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--allow-api", action="store_true", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
config = load_config(args.config)
assert config.models.chat_base_url == "https://api.anthropic.com/v1"
assert config.experiment.generation.report_evidence_sufficiency is True
for variable in (config.models.api_key_env, config.models.chat_api_key_env):
    if not variable or not os.environ.get(variable):
        raise ValueError(f"Required credential is absent: {variable}; no requests made")
prices = PriceSchedule.model_validate_json(config.experiment.price_schedule.read_text())
clients = _clients(config)
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
deadline = time.monotonic() + MAX_SECONDS
calls = []
results = {}
stage = "not_started"


def save(name, value):
    with (output / name).open("x") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def append(name, value):
    with (output / name).open("a") as stream:
        stream.write(json.dumps(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def admit():
    cost = estimate_cost(calls, prices)
    remaining = deadline - time.monotonic()
    if len(calls) >= MAX_CALLS or remaining <= 0 or cost.estimated_usd is None:
        raise ValueError("Compatibility call/time/accounting limit reached")
    if cost.estimated_usd >= MAX_COST_USD:
        raise ValueError("Compatibility estimated-cost limit reached")
    return remaining


def record(call):
    calls.append(call)
    append("model-calls.jsonl", {"stage": stage, "call": call.model_dump(mode="json")})


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


class SimulateOnce(TrackedClient):
    """Answer one chosen request locally with a fixed assistant message."""

    def __init__(self, delegate, when, message):
        super().__init__(delegate)
        self.when, self.message = when, message
        self.seen, self.used = 0, False

    def complete(self, messages, tools, **kwargs):
        self.seen += 1
        if not self.used and self.when(self.seen, messages):
            self.used = True
            message = deepcopy(self.message)
            append(
                "simulated-responses.jsonl",
                {"stage": stage, "request_number": self.seen, "message": message},
            )
            return ChatResponse(
                message=message,
                call=ModelCallRecord(
                    operation="chat",
                    model=self.identity["model"],
                    base_url=self.identity["base_url"],
                    request={"simulated_locally": True, "sent_to_provider": False},
                    response={"simulated_locally": True, "message": message},
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                ),
            )
        return super().complete(messages, tools, **kwargs)


def selection_required(_number, messages):
    return json.loads(messages[1]["content"])["remaining_budget"]["selection_required_now"]


def navigate(client, **budget):
    return AgenticWrapUpRetriever(corpus, client).retrieve(
        RetrievalRequest(
            query="Use read_file to read synthetic.py lines 1-2.",
            budget=RetrievalBudget(max_tokens=64000, max_seconds=120, **budget),
        )
    )


try:
    source = root / "experiments/preflight/phase4-2026-11-16/live-compatibility-008/synthetic-source"
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    corpus = RepositoryCorpus.from_repository(source, commit, config.files)

    stage = "qwen_query_embedding"
    embedding = TrackedClient(clients.embedding).embed(
        ["Where is SyntheticWidget defined?"], timeout=30
    )
    assert len(embedding.vectors) == 1 and len(embedding.vectors[0]) == 4096
    assert embedding.call.usage.total_tokens is not None
    results[stage] = {"status": "passed", "dimensions": 4096}

    settings = GenerationSettings(
        max_output_tokens=256, max_tokens=16000, max_seconds=30, report_evidence_sufficiency=True
    )
    stage = "anthropic_sufficiency_answer_with_evidence"
    answer = GroundedAnswerGenerator(TrackedClient(clients.answer), settings=settings).generate(
        "What is the value of SyntheticWidget.value?",
        (corpus.evidence("synthetic.py", 1, 2),),
    )
    save("synthetic-answer-with-evidence.json", answer.model_dump(mode="json"))
    assert answer.status == "completed" and answer.citations, answer.errors
    assert answer.metadata["prompt_version"] == SUFFICIENCY_PROMPT_VERSION
    assert type(answer.metadata["evidence_sufficient"]) is bool
    results[stage] = {
        "status": "passed",
        "citations": len(answer.citations),
        "evidence_sufficient": answer.metadata["evidence_sufficient"],
    }

    stage = "anthropic_sufficiency_answer_without_evidence"
    bare = GroundedAnswerGenerator(TrackedClient(clients.answer), settings=settings).generate(
        "What is the value of SyntheticWidget.value?", ()
    )
    save("synthetic-answer-without-evidence.json", bare.model_dump(mode="json"))
    assert bare.status == "completed", bare.errors
    assert type(bare.metadata["evidence_sufficient"]) is bool
    results[stage] = {
        "status": "passed",
        "evidence_sufficient": bare.metadata["evidence_sufficient"],
    }

    stage = "anthropic_wrapup_reserved_selection"
    reserved = navigate(TrackedClient(clients.agent), max_model_calls=2, max_tool_calls=5)
    save("synthetic-navigation-reserved-selection.json", reserved.model_dump(mode="json"))
    assert reserved.status == "completed" and reserved.evidence, reserved.errors
    assert reserved.metadata["prompt_version"] == agentic_wrapup.PROMPT_VERSION
    assert reserved.metadata["wrap_up"]["trigger"] == "last_model_call"
    results[stage] = {
        "status": "passed",
        "model_calls": len(reserved.model_calls),
        "selection_method": reserved.metadata.get("selection_method"),
    }

    stage = "anthropic_wrapup_retry_after_ignored_instruction"
    ignored = navigate(
        SimulateOnce(
            clients.agent,
            selection_required,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "simulated-ignored-instruction",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "synthetic.py"}),
                        },
                    }
                ],
            },
        ),
        max_model_calls=4,
        max_tool_calls=2,
    )
    save("synthetic-navigation-ignored-instruction.json", ignored.model_dump(mode="json"))
    assert ignored.status == "completed" and ignored.evidence, ignored.errors
    assert ignored.metadata["wrap_up"]["selection_retries"] == 1
    assert ignored.metadata["wrap_up"]["unexecuted_tool_calls"] == 1
    results[stage] = {
        "status": "passed",
        "model_calls_including_one_simulated": len(ignored.model_calls),
        "selection_method": ignored.metadata.get("selection_method"),
    }

    stage = "anthropic_wrapup_retry_after_prose"
    prose = navigate(
        SimulateOnce(
            clients.agent,
            lambda number, _messages: number == 2,
            {
                "role": "assistant",
                "content": "Based on my reading, SyntheticWidget.value is defined in synthetic.py.",
            },
        ),
        max_model_calls=4,
        max_tool_calls=5,
    )
    save("synthetic-navigation-prose.json", prose.model_dump(mode="json"))
    assert prose.status == "completed" and prose.evidence, prose.errors
    assert prose.metadata["wrap_up"]["selection_retries"] == 1
    assert prose.errors == (agentic_wrapup.SELECTION_FAILURE,)
    results[stage] = {
        "status": "passed",
        "model_calls_including_one_simulated": len(prose.model_calls),
        "selection_method": prose.metadata.get("selection_method"),
    }
    status = "passed"
except Exception as exc:
    status = "failed"
    results[stage] = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}

chat_starts = sorted(call.started_at for call in calls if call.operation == "chat")
summary = {
    "status": status,
    "kind": "synthetic_compatibility_check_not_benchmark_results",
    "recorded_at": datetime.now(UTC).isoformat(),
    "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
    "model_identities": {
        name: getattr(clients, name).identity for name in ("embedding", "answer", "agent")
    },
    "limits": {
        "model_calls": MAX_CALLS,
        "seconds": MAX_SECONDS,
        "estimated_cost_usd": MAX_COST_USD,
    },
    "results": results,
    "provider_model_calls": len(calls),
    "locally_simulated_responses": 2 if status == "passed" else None,
    "chat_start_gaps_seconds": [
        round((later - earlier).total_seconds(), 6)
        for earlier, later in zip(chat_starts, chat_starts[1:], strict=False)
    ],
    "cost": estimate_cost(calls, prices).model_dump(mode="json"),
}
save("summary.json", summary)
print(json.dumps(summary, indent=2))
raise SystemExit(0 if status == "passed" else 2)

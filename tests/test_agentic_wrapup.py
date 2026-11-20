"""Scripted clients exercise the reserved-selection navigator; not benchmark measurements."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from adaptive_rag.retrieval import agentic, agentic_wrapup
from adaptive_rag.retrieval.agentic import AgenticRetriever
from adaptive_rag.retrieval.agentic_wrapup import AgenticWrapUpRetriever
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import (
    ModelCallRecord,
    RetrievalBudget,
    RetrievalRequest,
    TokenUsage,
)

OUT = 512


def _git(root: Path, *args: str) -> str:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return subprocess.run(
        ["git", "-C", str(root), *args],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("wrapup-source")
    _git(root, "init", "--quiet", "--template=")
    _git(root, "config", "user.name", "Synthetic Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "logic.py").write_text("def process(value):\n    return value + 1\n")
    (root / "caller.py").write_text("from logic import process\nresult = process(1)\n")
    (root / "long.py").write_text(
        "".join(f"value_{number:03d} = {'x' * 110!r}\n" for number in range(1, 201))
    )
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "-m", "Synthetic navigation fixture")
    return RepositoryCorpus.from_repository(root, _git(root, "rev-parse", "HEAD"))


def tool(name="read_file", arguments=None, identifier="read-1"):
    return {
        "id": identifier,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments or {"path": "logic.py"})},
    }


def tools_message(*calls):
    return {"role": "assistant", "content": "Inspect the source.", "tool_calls": list(calls)}


def shown_ids(messages):
    identifiers = []
    for message in messages:
        if message["role"] == "tool":
            identifiers.extend(json.loads(message["content"]).get("available_evidence_ids", []))
    return identifiers


def select_shown(identifier="select-1", limit=1):
    def respond(messages, _tools):
        return tools_message(
            tool("select_evidence", {"evidence_ids": shown_ids(messages)[:limit]}, identifier)
        )

    return respond


PROSE = {"role": "assistant", "content": "Based on my investigation, the answer is that ..."}


class ScriptedClient:
    identity = {"base_url": "https://fixture.invalid/v1", "model": "scripted-fixture"}

    def __init__(self, responses, usage=None):
        self.responses = list(responses)
        self.requests = []
        self.usage = usage or TokenUsage(input_tokens=10, output_tokens=5)

    def complete(self, messages, tools, **kwargs):
        self.requests.append(copy.deepcopy({"messages": messages, "tools": tools, **kwargs}))
        response = self.responses.pop(0)
        message = response(messages, tools) if callable(response) else response
        return SimpleNamespace(
            message=message,
            call=ModelCallRecord(
                operation="chat",
                model="scripted-fixture",
                base_url="https://fixture.invalid/v1",
                request=copy.deepcopy(self.requests[-1]),
                response={"message": message},
                usage=self.usage,
            ),
        )


def request(**budget):
    budget.setdefault("max_tokens", 1_000_000)
    return RetrievalRequest(query="Where is process defined?", budget=RetrievalBudget(**budget))


def prompt_size(sent):
    body = {"messages": sent["messages"], "tools": sent["tools"]}
    return len(agentic._json(body).encode("utf-8"))


def budget_message(sent):
    return json.loads(sent["messages"][1]["content"])["remaining_budget"]


def first_prompt_size(corpus):
    probe = ScriptedClient([select_shown()])
    result = AgenticWrapUpRetriever(corpus, probe).retrieve(request())
    return result.metadata["admissions"][0]["prompt_utf8_bytes"]


def test_original_navigator_prompt_is_unchanged():
    # The hash recorded by every agentic job of run 04ebe642-5ec1-4301-98b2-2a17859c8ece.
    assert agentic.PROMPT_VERSION == "repository-navigation-v6"
    assert (
        hashlib.sha256(agentic.SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        == "4ee8ec16a0e00a2d1eae306ee33b3a79b209ee72b016970f75b5c7067a054c72"
    )
    assert agentic_wrapup.SYSTEM_PROMPT != agentic.SYSTEM_PROMPT


def test_selection_by_the_model_completes_and_is_labelled_as_this_variant(corpus):
    client = ScriptedClient([tools_message(tool()), select_shown()])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.strategy == "agentic_wrapup"
    assert result.evidence == (corpus.evidence("logic.py", 1, 2, reason="targeted inspection"),)
    assert result.metadata["prompt_version"] == agentic_wrapup.PROMPT_VERSION
    assert result.metadata["system_prompt"] == agentic_wrapup.SYSTEM_PROMPT
    assert result.metadata["selection_method"] == "tool_call"
    wrap_up = result.metadata["wrap_up"]
    assert wrap_up["policy_version"] == "agentic-wrapup-v1"
    assert wrap_up["selection_required"] is False and wrap_up["trigger"] is None
    assert wrap_up["selection_retries"] == 0
    assert result.errors == ()
    assert [message["role"] for message in client.requests[1]["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]


def test_the_charge_reported_to_the_model_is_the_charge_enforced(corpus):
    client = ScriptedClient(
        [tools_message(tool()), tools_message(tool(identifier="read-2")), select_shown()]
    )
    budget = request(max_tokens=200_000)
    result = AgenticWrapUpRetriever(corpus, client).retrieve(budget)
    assert result.status == "completed"
    spent = 0
    for sent, admission in zip(client.requests, result.metadata["admissions"], strict=True):
        reported = budget_message(sent)
        assert reported["request_charge"] == prompt_size(sent) == admission["prompt_utf8_bytes"]
        assert reported["tokens"] == 200_000 - spent
        assert reported["selection_required_now"] is False
        spent += 15


def test_last_model_request_is_reserved_for_selection(corpus):
    client = ScriptedClient([tools_message(tool()), select_shown()])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request(max_model_calls=2))
    assert result.status == "completed"
    assert result.metadata["wrap_up"]["trigger"] == "last_model_call"
    first, second = client.requests
    assert budget_message(first)["navigation_may_end_after_this_request"] is True
    assert budget_message(second)["selection_required_now"] is True
    final = second["messages"][-1]
    assert final["role"] == "user"
    assert json.loads(final["content"]) == {
        "selection_required_now": True,
        "instruction": agentic_wrapup.SELECTION_REQUIRED_INSTRUCTION,
    }
    assert result.metadata["admissions"][-1]["selection_required"] is True


def test_original_navigator_spends_its_last_request_on_navigation(corpus):
    script = [tools_message(tool()), tools_message(tool(identifier="read-2"))]
    result = AgenticRetriever(corpus, ScriptedClient(script)).retrieve(request(max_model_calls=2))
    assert result.status == "budget_exhausted"
    assert result.errors[-1] == "model-call budget exhausted"


def test_navigation_requested_after_selection_is_required_is_never_executed(corpus):
    script = [tools_message(tool()), tools_message(tool(identifier="read-2"))]
    client = ScriptedClient(script)
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request(max_model_calls=2))
    assert result.status == "budget_exhausted"
    assert result.errors[-2:] == (
        "navigation tools were requested after selection became required",
        "selection was not made before navigation ended",
    )
    assert result.tool_call_count == 1
    assert result.metadata["wrap_up"]["unexecuted_tool_calls"] == 1
    assert result.operations[-1].error == agentic_wrapup.NOT_EXECUTED_NOTICE
    assert result.operations[-1].details["executed"] is False


def test_last_tool_call_is_reserved_and_an_ignored_instruction_gets_one_retry(corpus):
    client = ScriptedClient(
        [tools_message(tool()), tools_message(tool(identifier="read-2")), select_shown()]
    )
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request(max_tool_calls=2))
    assert result.status == "completed"
    wrap_up = result.metadata["wrap_up"]
    assert wrap_up["trigger"] == "last_tool_call"
    assert wrap_up["selection_retries"] == 1 and wrap_up["unexecuted_tool_calls"] == 1
    assert result.tool_call_count == 2
    retry = client.requests[2]["messages"]
    assert [message["role"] for message in retry[-3:]] == ["user", "assistant", "tool"]
    assert json.loads(retry[-1]["content"]) == {
        "error": agentic_wrapup.NOT_EXECUTED_NOTICE,
        "instruction": agentic_wrapup.RETRY_INSTRUCTION,
    }
    assert len(shown_ids(retry)) == 1


def test_token_reserve_ends_navigation_while_a_full_selection_still_fits(corpus):
    first = first_prompt_size(corpus)
    need = (
        2 * first + 2 * OUT + agentic_wrapup.FINAL_NOTE_BYTES + agentic_wrapup.MIN_TURN_GROWTH_BYTES
    )
    client = ScriptedClient([tools_message(tool()), select_shown()])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request(max_tokens=need + 40))
    assert result.status == "completed"
    assert result.metadata["wrap_up"]["trigger"] == "token_reserve"
    assert len(client.requests) == 2
    assert budget_message(client.requests[1])["selection_required_now"] is True
    assert result.metadata["admissions"][-1]["reserved_output_tokens"] == OUT
    assert not any("token budget cannot admit" in error for error in result.errors)


def test_a_budget_too_small_for_navigation_goes_straight_to_selection(corpus):
    first = first_prompt_size(corpus)
    client = ScriptedClient([{"role": "assistant", "content": '{"evidence_ids":[]}'}])
    limit = first + agentic_wrapup.FINAL_NOTE_BYTES + OUT + 200
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request(max_tokens=limit))
    assert result.status == "completed" and result.evidence == ()
    assert result.metadata["wrap_up"]["trigger"] == "token_reserve"
    assert result.tool_call_count == 0


def test_prose_instead_of_a_selection_gets_exactly_one_retry(corpus):
    client = ScriptedClient([tools_message(tool()), PROSE, select_shown()])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.errors == (agentic_wrapup.SELECTION_FAILURE,)
    wrap_up = result.metadata["wrap_up"]
    assert wrap_up["selection_retries"] == 1 and wrap_up["trigger"] == "selection_retry"
    retry = client.requests[2]["messages"]
    assert retry[-2] == {"role": "assistant", "content": PROSE["content"]}
    assert json.loads(retry[-1]["content"]) == {
        "selection_rejected": agentic_wrapup.SELECTION_FAILURE,
        "instruction": agentic_wrapup.RETRY_INSTRUCTION,
    }


def test_a_second_prose_response_fails_like_the_original(corpus):
    client = ScriptedClient([tools_message(tool()), PROSE, PROSE])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.errors == (agentic_wrapup.SELECTION_FAILURE,) * 2
    assert len(client.requests) == 3
    original = AgenticRetriever(corpus, ScriptedClient([tools_message(tool()), PROSE])).retrieve(
        request()
    )
    assert original.status == "error"
    assert original.errors == (agentic_wrapup.SELECTION_FAILURE,)


def test_invalid_evidence_ids_are_rejected_by_the_original_validator_then_retried(corpus):
    invalid = tools_message(tool("select_evidence", {"evidence_ids": ["0" * 64]}, "select-1"))
    client = ScriptedClient([tools_message(tool()), invalid, select_shown("select-2")])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    failed = [op for op in result.operations if op.name == "select_evidence" and op.error]
    assert len(failed) == 1
    assert failed[0].error == "selection must contain unique available evidence_ids within top_k"
    assert result.metadata["wrap_up"]["selection_retries"] == 1
    assert result.tool_call_count == 3

    again = ScriptedClient([tools_message(tool()), invalid, copy.deepcopy(invalid)])
    again.responses[2]["tool_calls"][0]["id"] = "select-2"
    rejected = AgenticWrapUpRetriever(corpus, again).retrieve(request())
    assert rejected.status == "error"
    assert rejected.evidence != ()
    assert sum("tool select_evidence failed" in error for error in rejected.errors) == 2


def test_an_oversized_read_is_shortened_instead_of_rejected(corpus):
    oversized = {"path": "long.py", "start_line": 11, "end_line": 150, "max_lines": 40}
    client = ScriptedClient([tools_message(tool(arguments=oversized)), select_shown()])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request())
    assert result.status == "completed" and result.errors == ()
    assert (result.evidence[0].start_line, result.evidence[0].end_line) == (11, 50)
    read = result.operations[0]
    assert read.arguments["end_line"] is None
    assert read.details["requested_end_line"] == 150 and read.details["range_shortened"] is True
    assert result.metadata["wrap_up"]["shortened_reads"] == 1
    shown = json.loads(client.requests[1]["messages"][-1]["content"])
    assert shown["notice"] == agentic_wrapup.SHORTENED_NOTICE

    original = AgenticRetriever(
        corpus,
        ScriptedClient(
            [tools_message(tool(arguments=oversized)), {"role": "assistant", "content": "{}"}]
        ),
    ).retrieve(request())
    assert "tool read_file failed: requested line range exceeds max_lines" in original.errors


def test_tool_output_that_would_spend_the_selection_reserve_is_withheld(corpus):
    first = first_prompt_size(corpus)
    need = (
        2 * first + 2 * OUT + agentic_wrapup.FINAL_NOTE_BYTES + agentic_wrapup.MIN_TURN_GROWTH_BYTES
    )
    reads = [
        tool(
            arguments={"path": "long.py", "start_line": start, "max_lines": 40},
            identifier=f"read-{start}",
        )
        for start in (1, 41, 81, 121, 161)
    ]
    client = ScriptedClient([tools_message(*reads), select_shown(limit=5)])
    result = AgenticWrapUpRetriever(corpus, client).retrieve(request(max_tokens=need + 40))
    assert result.status == "completed"
    wrap_up = result.metadata["wrap_up"]
    assert 1 <= wrap_up["withheld_tool_outputs"] < 5
    withheld = [op for op in result.operations if op.details.get("withheld")]
    assert len(withheld) == wrap_up["withheld_tool_outputs"]
    assert all(op.error == agentic_wrapup.WITHHELD_NOTICE for op in withheld)
    assert not any(op.returned_ids for op in withheld)
    shown = 5 - len(withheld)
    assert result.metadata["candidate_evidence_count"] == shown == len(result.evidence)
    # Every requested call was answered, and the reserved selection kept its full allowance.
    selection = client.requests[1]
    assert sum(message["role"] == "tool" for message in selection["messages"]) == 5
    assert result.metadata["admissions"][-1]["reserved_output_tokens"] == OUT
    assert prompt_size(selection) + OUT <= need + 40 - 15

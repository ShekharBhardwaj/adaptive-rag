"""Scripted clients exercise orchestration; these are not benchmark measurements."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from adaptive_rag.generation.client import ModelClientError
from adaptive_rag.retrieval import agentic
from adaptive_rag.retrieval.agentic import AgenticRetriever
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import (
    ModelCallRecord,
    RetrievalBudget,
    RetrievalRequest,
    TokenUsage,
)
from adaptive_rag.retrieval.tools import RepositoryTools


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
    root = tmp_path_factory.mktemp("agentic-source")
    _git(root, "init", "--quiet", "--template=")
    _git(root, "config", "user.name", "Synthetic Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "logic.py").write_text("def process(value):\n    return value + 1\n")
    (root / "caller.py").write_text("from logic import process\nresult = process(1)\n")
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
    return {
        "role": "assistant",
        "content": "Inspect the matching source file.",
        "tool_calls": list(calls),
    }


def final_selection(messages, _tools):
    payload = json.loads(messages[-1]["content"])
    return {
        "role": "assistant",
        "content": json.dumps({"evidence_ids": payload["available_evidence_ids"][:1]}),
    }


class ScriptedClient:
    identity = {"base_url": "https://fixture.invalid/v1", "model": "scripted-fixture"}

    def __init__(self, responses, usage=None):
        self.responses = list(responses)
        self.requests = []
        self.usage = usage or TokenUsage(input_tokens=10, output_tokens=5)

    def complete(self, messages, tools, **kwargs):
        self.requests.append(copy.deepcopy({"messages": messages, "tools": tools, **kwargs}))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
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
    return RetrievalRequest(query="Where is process defined?", budget=RetrievalBudget(**budget))


def test_navigation_records_real_tools_evidence_history_and_model_identity(corpus):
    client = ScriptedClient([tools_message(tool()), final_selection])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.evidence[0].text == "def process(value):\n    return value + 1"
    assert result.evidence[0] == corpus.evidence("logic.py", 1, 2, reason="targeted inspection")
    assert result.tool_call_count == 1
    assert result.usage.total_tokens == 30
    assert len(result.model_calls) == 2
    assert result.operations[0].returned_ids == (result.evidence[0].id,)
    assert result.metadata["client"] == client.identity
    assert result.metadata["prompt_version"] == agentic.PROMPT_VERSION
    assert result.metadata["response_encoding"] == "json"
    assert result.metadata["system_prompt"] == agentic.SYSTEM_PROMPT
    exposed = {schema["function"]["name"] for schema in client.requests[0]["tools"]}
    assert exposed == {
        "list_directory",
        "search_files",
        "search_symbols",
        "read_file",
        "inspect_references",
        "select_evidence",
    }
    history = client.requests[1]["messages"]
    assert [message["role"] for message in history] == ["system", "user", "assistant", "tool"]
    assert history[-1]["tool_call_id"] == "read-1"
    assert 0 < client.requests[0]["timeout"] <= request().budget.max_seconds


def test_no_evidence_is_valid_and_does_not_invent_an_answer(corpus):
    client = ScriptedClient([{"role": "assistant", "content": '{"evidence_ids":[]}'}])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.evidence == ()
    assert result.tool_call_count == 0
    assert "warning" in result.metadata
    assert "answer" not in result.model_dump()
    assert result.metadata["selection_method"] == "text_json"


@pytest.mark.parametrize(
    "content", ["An invented answer", "{}", "[]", '{"evidence_ids":["invented"]}']
)
def test_malformed_or_invented_final_selection_is_an_error(corpus, content):
    client = ScriptedClient([{"role": "assistant", "content": content}])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()
    assert "available evidence_ids" in result.errors[-1]


def test_invalid_and_unknown_calls_are_recorded_counted_and_recoverable(corpus):
    invalid_json = tool(arguments={"path": "logic.py"}, identifier="invalid")
    invalid_json["function"]["arguments"] = "{oops"
    client = ScriptedClient(
        [
            tools_message(tool("execute_source", {"command": "danger"}, "unknown"), invalid_json),
            tools_message(tool(identifier="valid")),
            final_selection,
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.tool_call_count == 3
    assert len(result.operations) == 3
    assert result.operations[0].error.startswith("unknown tool")
    assert "not valid JSON" in result.operations[1].error
    assert result.operations[2].error is None
    assert len(result.evidence) == 1
    assert len(client.requests[1]["messages"]) == 5


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": "logic.py", "start_line": True},
        {"path": "../outside"},
        {"path": "logic.py", "max_lines": 201},
        {"path": "logic.py", "undeclared": "argument"},
    ],
)
def test_unsafe_or_invalid_tool_arguments_cannot_read_source(corpus, arguments):
    client = ScriptedClient(
        [
            tools_message(tool(arguments=arguments)),
            {"role": "assistant", "content": '{"evidence_ids":[]}'},
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.evidence == ()
    assert result.operations[0].error
    assert result.tool_call_count == 1


def test_parallel_calls_cannot_bypass_tool_call_budget(corpus):
    client = ScriptedClient(
        [
            tools_message(
                tool(identifier="one"),
                tool(arguments={"path": "caller.py"}, identifier="two"),
                tool(identifier="three"),
            )
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request(max_tool_calls=2))
    assert result.status == "budget_exhausted"
    assert result.tool_call_count == 2
    assert len(result.operations) == 2
    assert len(result.evidence) == 2
    assert len(result.model_calls) == 1


def test_model_call_budget_preserves_partial_evidence(corpus):
    client = ScriptedClient([tools_message(tool())])
    result = AgenticRetriever(corpus, client).retrieve(request(max_model_calls=1))
    assert result.status == "budget_exhausted"
    assert len(result.model_calls) == 1
    assert len(result.evidence) == 1


@pytest.mark.parametrize("budget", [{"max_model_calls": 0}, {"max_tokens": 1}])
def test_exhausted_admission_does_not_contact_provider(corpus, budget):
    client = ScriptedClient([])
    result = AgenticRetriever(corpus, client).retrieve(request(**budget))
    assert result.status == "budget_exhausted"
    assert client.requests == []
    assert result.usage.total_tokens == 0


def test_output_token_reservation_is_capped_to_remaining_admission(corpus):
    probe = ScriptedClient([{"role": "assistant", "content": '{"evidence_ids":[]}'}])
    first = AgenticRetriever(corpus, probe).retrieve(request())
    prompt_bytes = first.metadata["admissions"][0]["prompt_utf8_bytes"]
    client = ScriptedClient([{"role": "assistant", "content": '{"evidence_ids":[]}'}])
    limit = prompt_bytes + 20
    result = AgenticRetriever(corpus, client).retrieve(request(max_tokens=limit))
    assert result.status == "completed"
    actual_prompt = result.metadata["admissions"][0]["prompt_utf8_bytes"]
    assert client.requests[0]["max_output_tokens"] == limit - actual_prompt
    assert 0 < client.requests[0]["max_output_tokens"] < 512


def test_missing_usage_stops_before_any_tool_execution(corpus):
    client = ScriptedClient([tools_message(tool())], TokenUsage(input_tokens=None, output_tokens=5))
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "budget_exhausted"
    assert result.usage.input_tokens is None
    assert result.usage.total_tokens is None
    assert result.tool_call_count == 0
    assert "complete token usage" in result.errors[-1]


def test_provider_reported_excess_stops_before_tools(corpus):
    client = ScriptedClient(
        [tools_message(tool())], TokenUsage(input_tokens=16_001, output_tokens=5)
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens == 16_006
    assert result.tool_call_count == 0


def test_time_budget_passes_timeout_and_rejects_late_model_response(corpus, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(agentic.time, "monotonic", lambda: clock[0])

    def late(_messages, _tools):
        clock[0] = 3.0
        return {"role": "assistant", "content": '{"evidence_ids":[]}'}

    client = ScriptedClient([late])
    result = AgenticRetriever(corpus, client).retrieve(request(max_seconds=2))
    assert client.requests[0]["timeout"] == 2.0
    assert result.status == "budget_exhausted"
    assert len(result.model_calls) == 1
    assert result.elapsed_seconds == 3.0


def test_late_tool_retains_actual_partial_evidence_and_stops(corpus, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(agentic.time, "monotonic", lambda: clock[0])
    original = RepositoryTools.read_file

    def late_read(self, **arguments):
        result = original(self, **arguments)
        clock[0] = 3.0
        return result

    monkeypatch.setattr(RepositoryTools, "read_file", late_read)
    client = ScriptedClient([tools_message(tool())])
    result = AgenticRetriever(corpus, client).retrieve(request(max_seconds=2))
    assert result.status == "budget_exhausted"
    assert len(result.evidence) == 1
    assert result.tool_call_count == 1
    assert len(client.requests) == 1


def test_source_verification_failure_prevents_model_contact(corpus, monkeypatch):
    def invalid(_self):
        raise ValueError("source pin drift")

    monkeypatch.setattr(RepositoryCorpus, "verify", invalid)
    client = ScriptedClient([])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()
    assert client.requests == []
    assert any("source pin drift" in error for error in result.errors)


def test_source_drift_after_model_cannot_return_evidence(corpus, monkeypatch):
    checks = [0]

    def check(_self):
        checks[0] += 1
        if checks[0] > 1:
            raise ValueError("source pin drift")

    monkeypatch.setattr(RepositoryCorpus, "verify", check)
    client = ScriptedClient([tools_message(tool()), final_selection])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()
    assert result.operations[0].returned_ids


def test_tool_payloads_are_bounded_valid_json_and_explicitly_truncated(corpus, monkeypatch):
    original = RepositoryTools.read_file

    def large_metadata(self, **kwargs):
        result = original(self, **kwargs)
        result.data["large_metadata"] = ["x" * 10_000] * 100
        return result

    monkeypatch.setattr(RepositoryTools, "read_file", large_metadata)
    client = ScriptedClient([tools_message(tool()), final_selection])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    content = client.requests[1]["messages"][-1]["content"]
    assert len(content.encode()) <= agentic.MAX_TOOL_OUTPUT_BYTES
    assert json.loads(content)["output_truncated"] is True
    assert len(result.evidence) == 1


def test_small_evidence_budget_omits_whole_source_ranges(corpus):
    client = ScriptedClient([tools_message(tool()), final_selection])
    result = AgenticRetriever(corpus, client).retrieve(request(max_evidence_chars=1))
    assert result.status == "completed"
    assert result.evidence == ()
    assert result.operations[0].returned_ids == ()
    assert result.operations[0].details["output"]["output_truncated"]


def test_failed_model_record_retains_reported_usage_and_elapsed(corpus):
    record = ModelCallRecord(
        operation="chat",
        model="scripted-fixture",
        base_url="https://fixture.invalid/v1",
        request={"synthetic": True},
        response={"error": "synthetic failure"},
        usage=TokenUsage(input_tokens=17, output_tokens=3),
        elapsed_seconds=0.4,
        error="synthetic provider failure",
    )
    client = ScriptedClient([ModelClientError("synthetic provider failure", record)])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.model_calls == (record,)
    assert result.usage.total_tokens == 20
    assert result.model_calls[0].elapsed_seconds == 0.4
    assert result.tool_call_count == 0


def test_failure_without_usage_record_does_not_claim_zero_tokens(corpus):
    client = ScriptedClient([ModelClientError("connection interrupted")])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "budget_exhausted"
    assert result.usage.total_tokens is None
    assert result.metadata["model_attempts"] == 1


@pytest.mark.parametrize(
    "message",
    [
        {"role": "user", "content": "unexpected"},
        {"role": "assistant", "content": []},
        {"role": "assistant", "tool_calls": "invalid"},
        tools_message(tool(identifier="duplicate"), tool(identifier="duplicate")),
        tools_message({"type": "function", "function": {"name": "read_file"}}),
    ],
)
def test_malformed_model_messages_are_returned_as_errors(corpus, message):
    client = ScriptedClient([message])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()
    assert result.tool_call_count == 0


def test_malformed_tool_name_is_a_counted_tool_error(corpus):
    call = tool()
    call["function"]["name"] = ["read_file"]
    client = ScriptedClient(
        [
            tools_message(call),
            {"role": "assistant", "content": '{"evidence_ids":[]}'},
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.tool_call_count == 1
    assert result.operations[0].name == "invalid_tool_call"
    assert result.operations[0].error


def test_final_cannot_select_more_than_top_k(corpus):
    def too_many(messages, _tools):
        ids = []
        for message in messages:
            if message["role"] == "tool":
                ids.extend(json.loads(message["content"])["available_evidence_ids"])
        return {"role": "assistant", "content": json.dumps({"evidence_ids": ids})}

    client = ScriptedClient(
        [
            tools_message(
                tool(identifier="one"), tool(arguments={"path": "caller.py"}, identifier="two")
            ),
            too_many,
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(
        RetrievalRequest(query="Find process", top_k=1)
    )
    assert result.status == "error"
    assert len(result.evidence) == 1
    assert result.evidence[0].path == "logic.py"


def test_contradictory_model_identity_is_preserved_and_rejected(corpus):
    client = ScriptedClient([tools_message(tool())])
    client.identity = {"base_url": "https://fixture.invalid/v1", "model": "different-model"}
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.model_calls[0].model == "scripted-fixture"
    assert result.tool_call_count == 0
    assert "client identity" in result.errors[-1]


def test_blank_tool_name_cannot_escape_structured_error_result(corpus):
    call = tool()
    call["function"]["name"] = "   "
    client = ScriptedClient(
        [
            tools_message(call),
            {"role": "assistant", "content": '{"evidence_ids":[]}'},
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.operations[0].name == "invalid_tool_call"
    assert result.operations[0].error


def test_duplicate_json_tool_keys_are_not_silently_accepted(corpus):
    call = tool()
    call["function"]["arguments"] = '{"path":"outside","path":"logic.py"}'
    client = ScriptedClient(
        [
            tools_message(call),
            {"role": "assistant", "content": '{"evidence_ids":[]}'},
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.operations[0].error == "tool arguments are not valid JSON"
    assert result.evidence == ()


def test_duplicate_json_final_keys_are_invalid(corpus):
    client = ScriptedClient(
        [
            {"role": "assistant", "content": '{"evidence_ids":["invented"],"evidence_ids":[]}'},
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()


def test_fenced_tool_arguments_remain_invalid(corpus):
    call = tool()
    call["function"]["arguments"] = '```json\n{"path":"logic.py"}\n```'
    client = ScriptedClient(
        [tools_message(call), {"role": "assistant", "content": '{"evidence_ids":[]}'}]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.operations[0].error == "tool arguments are not valid JSON"
    assert result.evidence == ()
    assert result.tool_call_count == 1


@pytest.mark.parametrize("native_control", [False, True])
def test_real_adapter_accepts_fenced_or_native_selection_without_extra_request(
    corpus, native_control
):
    import httpx

    from adaptive_rag.generation.client import OpenAIChatClient

    requests = []
    outputs = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            output = tools_message(tool())
        else:
            available = json.loads(body["messages"][-1]["content"])["available_evidence_ids"]
            if native_control:
                output = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        tool("select_evidence", {"evidence_ids": available[:1]}, "finish")
                    ],
                }
            else:
                output = {
                    "role": "assistant",
                    "content": "```json\n" + json.dumps({"evidence_ids": available[:1]}) + "\n```",
                }
        outputs.append(output)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": output}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = OpenAIChatClient(
        base_url="https://fixture.invalid/v1",
        model="fixture-navigation",
        transport=httpx.MockTransport(handler),
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.evidence[0].path == "logic.py"
    assert len(requests) == len(result.model_calls) == 2
    assert result.tool_call_count == (2 if native_control else 1)
    assert result.usage.total_tokens == 30
    assert result.metadata["model_attempts"] == 2
    if not native_control:
        assert result.metadata["response_encoding"] == "json_fence"
    assert result.metadata["prompt_version"] == "repository-navigation-v6"
    assert result.metadata["selection_method"] == ("tool_call" if native_control else "text_json")
    assert result.model_calls[-1].response["choices"][0]["message"] == outputs[-1]


def select_observed_evidence(messages, _tools):
    available = json.loads(messages[-1]["content"])["available_evidence_ids"]
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool("select_evidence", {"evidence_ids": available[:1]}, "select-1")],
    }


def test_selection_control_completes_with_observed_evidence_and_no_extra_request(corpus):
    client = ScriptedClient([tools_message(tool()), select_observed_evidence])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert len(client.requests) == len(result.model_calls) == 2
    assert result.tool_call_count == 2
    assert result.evidence[0].path == "logic.py"
    assert result.usage.total_tokens == 30
    assert result.metadata["selection_method"] == "tool_call"
    operation = result.operations[-1]
    assert operation.name == "select_evidence"
    assert operation.arguments == {"evidence_ids": [result.evidence[0].id]}
    assert operation.returned_ids == (result.evidence[0].id,)
    assert operation.error is None
    assert operation.details["control"] is True
    assert operation.details["tool_call_id"] == "select-1"
    assert result.model_calls[-1].response["message"]["tool_calls"][0]["function"]["name"] == (
        "select_evidence"
    )


def test_navigation_budget_is_refreshed_and_reserves_the_last_selection_turn(corpus):
    client = ScriptedClient([tools_message(tool()), select_observed_evidence])
    result = AgenticRetriever(corpus, client).retrieve(
        request(max_model_calls=2, max_tool_calls=2, max_tokens=64000)
    )
    assert result.status == "completed"
    first, last = [json.loads(item["messages"][1]["content"]) for item in client.requests]
    assert first["remaining_budget"]["model_calls"] == 2
    assert first["remaining_budget"]["tool_calls"] == 2
    assert first["remaining_budget"]["tokens"] == 64000
    assert last["remaining_budget"]["model_calls"] == 1
    assert last["remaining_budget"]["tool_calls"] == 1
    assert last["remaining_budget"]["tokens"] == 63985
    assert last["remaining_budget"]["evidence_chars"] == 24000 - len(result.evidence[0].text)
    assert 0 < last["remaining_budget"]["seconds"] <= first["remaining_budget"]["seconds"]
    assert "Reserve one model request and one tool call for selection" in agentic.SYSTEM_PROMPT
    assert len(result.model_calls) == 2


def test_navigator_payload_is_compact_but_operation_and_result_keep_full_evidence(corpus):
    client = ScriptedClient([tools_message(tool()), select_observed_evidence])
    result = AgenticRetriever(corpus, client).retrieve(request())
    payload = json.loads(client.requests[1]["messages"][-1]["content"])
    supplied = payload["evidence"][0]
    assert set(supplied) == {"id", "path", "start_line", "end_line", "text"}
    full = result.evidence[0].model_dump(mode="json")
    assert supplied == {key: full[key] for key in supplied}
    assert result.operations[0].details["output"]["evidence"] == [full]
    assert {"repo_commit", "excerpt_sha256", "reason", "score"} <= set(full)
    assert len(json.dumps(supplied)) < len(json.dumps(full))


def test_tool_turn_narration_is_not_replayed_but_raw_response_and_usage_are_preserved(corpus):
    narration = "Repeated navigation narration. " * 250
    first = tools_message(tool())
    first["content"] = narration
    client = ScriptedClient([first, select_observed_evidence])
    result = AgenticRetriever(corpus, client).retrieve(request(max_tokens=12000))
    assert result.status == "completed"
    assert client.requests[1]["messages"][-2]["content"] is None
    assert client.requests[1]["messages"][-2]["tool_calls"] == first["tool_calls"]
    assert result.model_calls[0].response["message"]["content"] == narration
    assert result.model_calls[0].usage == client.usage
    assert result.usage.total_tokens == 30
    assert narration not in json.dumps(client.requests[1]["messages"])
    assert result.metadata["admissions"][1]["prompt_utf8_bytes"] + len(narration) > 12000


def test_read_schema_promotes_bounded_reads_without_guessing_file_length():
    schema = next(
        item["function"]
        for item in agentic.tool_schemas()
        if item["function"]["name"] == "read_file"
    )
    assert schema["parameters"]["properties"]["max_lines"]["default"] == 40
    assert "Omit end_line or use null" in schema["description"]
    arguments = agentic._arguments("read_file", '{"path":"logic.py"}')
    assert arguments["start_line"] == 1
    assert arguments["end_line"] is None
    assert arguments["max_lines"] == 40


def test_selection_control_can_select_no_evidence_without_reading_source(corpus, monkeypatch):
    monkeypatch.setattr(
        RepositoryTools,
        "read_file",
        lambda *_args, **_kwargs: pytest.fail("selection must not read source"),
    )
    client = ScriptedClient(
        [tools_message(tool("select_evidence", {"evidence_ids": []}, "finish"))]
    )
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "completed"
    assert result.evidence == ()
    assert result.tool_call_count == 1
    assert len(client.requests) == 1
    assert result.metadata["selection_method"] == "tool_call"
    assert result.operations[0].details["control"] is True


@pytest.mark.parametrize("after_read", [False, True])
def test_selection_control_cannot_exceed_tool_budget(corpus, after_read):
    responses = (
        [tools_message(tool()), select_observed_evidence]
        if after_read
        else [tools_message(tool("select_evidence", {"evidence_ids": []}, "finish"))]
    )
    client = ScriptedClient(responses)
    result = AgenticRetriever(corpus, client).retrieve(request(max_tool_calls=int(after_read)))
    assert result.status == "budget_exhausted"
    assert result.tool_call_count == int(after_read)
    assert len(result.operations) == int(after_read)
    assert len(result.evidence) == int(after_read)
    assert all(operation.name != "select_evidence" for operation in result.operations)
    assert "selection_method" not in result.metadata


@pytest.mark.parametrize(
    "raw",
    [
        '{"evidence_ids":["invented"]}',
        '{"evidence_ids":[],"extra":true}',
        '{"evidence_ids":"not an array"}',
        '{"evidence_ids":[1]}',
        '{"evidence_ids":null}',
        '{"evidence_ids":[],"evidence_ids":[]}',
        '{"evidence_ids":[],"extra":NaN}',
        '```json\n{"evidence_ids":[]}\n```',
        "[]",
        None,
    ],
)
def test_invalid_selection_control_is_recorded_and_fails_without_retry(corpus, raw):
    control = tool("select_evidence", {"evidence_ids": []}, "finish")
    control["function"]["arguments"] = raw
    client = ScriptedClient([tools_message(control)])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()
    assert len(client.requests) == len(result.model_calls) == 1
    assert result.tool_call_count == 1
    assert len(result.operations) == 1
    assert result.operations[0].name == "select_evidence"
    assert result.operations[0].error is not None
    assert result.operations[0].details["control"] is True
    assert result.operations[0].returned_ids == ()
    assert (
        result.model_calls[0].response["message"]["tool_calls"][0]["function"]["arguments"] == raw
    )


@pytest.mark.parametrize("read_first", [False, True])
def test_mixed_selection_control_batch_never_executes_read_tools(corpus, monkeypatch, read_first):
    monkeypatch.setattr(
        RepositoryTools,
        "read_file",
        lambda *_args, **_kwargs: pytest.fail("mixed finalization batch must not read source"),
    )
    control = tool("select_evidence", {"evidence_ids": []}, "finish")
    read = tool(identifier="read")
    calls = [read, control] if read_first else [control, read]
    client = ScriptedClient([tools_message(*calls)])
    result = AgenticRetriever(corpus, client).retrieve(request())
    assert result.status == "error"
    assert result.evidence == ()
    assert result.tool_call_count == 1
    assert len(result.operations) == 1
    assert result.operations[0].name == "select_evidence"
    assert "sole tool call" in result.operations[0].error
    assert result.operations[0].details["requested_tools"] == [
        call["function"]["name"] for call in calls
    ]
    assert len(client.requests) == 1


@pytest.mark.parametrize("duplicate", [False, True])
def test_selection_control_validates_top_k_and_unique_observed_ids(corpus, duplicate):
    def invalid_selection(messages, _tools):
        observed = []
        for message in messages:
            if message["role"] == "tool":
                observed.extend(json.loads(message["content"])["available_evidence_ids"])
        ids = [observed[0], observed[0]] if duplicate else observed
        return tools_message(tool("select_evidence", {"evidence_ids": ids}, "finish"))

    client = ScriptedClient(
        [
            tools_message(
                tool(identifier="read-a"),
                tool(arguments={"path": "caller.py"}, identifier="read-b"),
            ),
            invalid_selection,
        ]
    )
    result = AgenticRetriever(corpus, client).retrieve(request().model_copy(update={"top_k": 1}))
    assert result.status == "error"
    assert result.tool_call_count == 3
    assert result.operations[-1].error is not None
    assert result.operations[-1].details["control"] is True
    assert len(client.requests) == 2


@pytest.mark.parametrize("failure", ["late", "missing_usage", "excess_usage"])
def test_selection_control_cannot_bypass_time_or_usage_admission(corpus, monkeypatch, failure):
    clock = [0.0]
    monkeypatch.setattr(agentic.time, "monotonic", lambda: clock[0])

    def control_response(_messages, _tools):
        if failure == "late":
            clock[0] = 3.0
        return tools_message(tool("select_evidence", {"evidence_ids": []}, "finish"))

    usage = {
        "late": TokenUsage(input_tokens=10, output_tokens=5),
        "missing_usage": TokenUsage(input_tokens=None, output_tokens=5),
        "excess_usage": TokenUsage(input_tokens=16001, output_tokens=5),
    }[failure]
    client = ScriptedClient([control_response], usage)
    result = AgenticRetriever(corpus, client).retrieve(request(max_seconds=2))
    assert result.status == "budget_exhausted"
    assert result.tool_call_count == 0
    assert result.operations == ()
    assert len(client.requests) == len(result.model_calls) == 1
    assert result.usage == usage
    assert "selection_method" not in result.metadata

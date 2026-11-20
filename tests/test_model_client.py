"""Protocol fixtures exercise the HTTP boundary without contacting a provider."""

import json

import httpx
import pytest

from adaptive_rag.generation.client import ModelClientError, OpenAIChatClient, OpenAIEmbeddingClient
from adaptive_rag.retrieval.models import TokenUsage


def embed_client(handler, **kwargs):
    return OpenAIEmbeddingClient(
        base_url="http://fixture.invalid/v1",
        model="fixture-embedding",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def chat_client(handler, **kwargs):
    return OpenAIChatClient(
        base_url="http://fixture.invalid/v1",
        model="fixture-chat",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def completion(message=None):
    return {
        "choices": [{"message": message or {"role": "assistant", "content": "fixture"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }


def test_embeddings_restore_provider_order_and_usage():
    def handler(request):
        assert request.url.path == "/v1/embeddings"
        assert json.loads(request.content)["encoding_format"] == "float"
        return httpx.Response(
            200,
            json={
                "data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}],
                "usage": {"prompt_tokens": 7},
            },
        )

    result = embed_client(handler).embed(["first", "second"], timeout=1)
    assert result.vectors == ((1.0, 0.0), (0.0, 1.0))
    assert result.call.usage == TokenUsage(input_tokens=7, output_tokens=0)


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 1, "embedding": [1]}],
        [{"index": 0, "embedding": []}],
        [{"index": True, "embedding": [1]}],
        [{"index": 0, "embedding": ["1"]}],
        [{"index": 0, "embedding": [True]}],
        [{"index": 0, "embedding": [10**1000]}],
    ],
)
def test_invalid_embeddings_preserve_failure_record(data):
    client = embed_client(lambda request: httpx.Response(200, json={"data": data}))
    with pytest.raises(ModelClientError) as error:
        client.embed(["query"], timeout=1)
    assert error.value.record.error
    assert error.value.record.response == {"data": data}


def test_embedding_dimension_mismatch_and_unknown_usage():
    body = {"data": [{"index": 0, "embedding": [1, 2]}]}
    with pytest.raises(ModelClientError, match="dimensions"):
        embed_client(lambda r: httpx.Response(200, json=body), dimensions=3).embed(["q"], timeout=1)
    response = embed_client(lambda r: httpx.Response(200, json=body)).embed(["q"], timeout=1)
    assert response.call.usage.total_tokens is None


def test_chat_snapshots_messages_and_excludes_auth_from_trace():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer fixture-secret"
        return httpx.Response(200, json=completion())

    messages = [{"role": "user", "content": "fixture query"}]
    result = chat_client(
        handler, api_key="fixture-secret", token_parameter="max_completion_tokens"
    ).complete(
        messages,
        [],
        max_output_tokens=10,
        temperature=None,
        timeout=1,
    )
    messages[0]["content"] = "mutated"
    assert result.call.request["messages"][0]["content"] == "fixture query"
    assert result.call.usage.total_tokens == 7
    assert "fixture-secret" not in result.call.model_dump_json()
    assert seen[0]["max_completion_tokens"] == 10
    assert "temperature" not in seen[0]


def test_tools_and_assistant_response_are_preserved():
    tools = [{"type": "function", "function": {"name": "list_directory", "parameters": {}}}]
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "list_directory", "arguments": "{}"},
            }
        ],
    }

    def handler(request):
        assert json.loads(request.content)["tools"] == tools
        return httpx.Response(200, json=completion(message))

    assert (
        chat_client(handler)
        .complete([], tools, max_output_tokens=10, temperature=0, timeout=1)
        .message
        == message
    )


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b'{"x":NaN}',
        b'{"usage":{},"usage":{}}',
        b'{"choices":[]}',
        b'{"choices":[{"message":{"role":"user"}}]}',
    ],
)
def test_malformed_response_is_traceable(body):
    with pytest.raises(ModelClientError) as error:
        chat_client(lambda r: httpx.Response(200, content=body)).complete(
            [],
            [],
            max_output_tokens=10,
            temperature=0,
            timeout=1,
        )
    assert error.value.record is not None
    assert error.value.record.error


def test_http_failure_has_no_retry_and_unknown_usage():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "fixture rate limit"}})

    with pytest.raises(ModelClientError, match="429") as error:
        chat_client(handler).complete([], [], max_output_tokens=10, temperature=0, timeout=1)
    assert len(calls) == 1
    assert error.value.record.usage.total_tokens is None


def test_transport_timeout_is_recorded():
    def handler(request):
        raise httpx.ReadTimeout("fixture timeout", request=request)

    with pytest.raises(ModelClientError, match="ReadTimeout") as error:
        embed_client(handler).embed(["query"], timeout=0.1)
    assert error.value.record.elapsed_seconds >= 0


def test_usage_addition_preserves_unknown():
    assert TokenUsage().total_tokens == 0
    combined = TokenUsage(input_tokens=2, output_tokens=1).add(TokenUsage(input_tokens=None))
    assert combined.input_tokens is None
    assert combined.output_tokens == 1
    assert combined.total_tokens is None


@pytest.mark.parametrize(
    "url", ["file:///tmp/model", "https://key:secret@example.org/v1", "https://e/v1?key=s"]
)
def test_invalid_endpoint_is_rejected(url):
    with pytest.raises(ValueError):
        OpenAIChatClient(base_url=url, model="fixture")

"""Chat credentials can change without changing persistent embedding identity."""

import pytest
from pydantic import ValidationError

from adaptive_rag.config import FoundationConfig, ModelSettings
from adaptive_rag.evaluation import runner
from adaptive_rag.generation.client import OpenAIEmbeddingClient


def config(**models):
    return FoundationConfig.model_validate(
        {
            "repository": {
                "url": "https://fixture.invalid/repo.git",
                "path": "/unused/synthetic-repository",
                "commit_sha": "a" * 40,
            },
            "models": {
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "SYNTHETIC_EMBEDDING_KEY",
                "embedding_model": "qwen/qwen3-embedding-8b",
                "chat_model": "claude-haiku-4-5-20251001",
                **models,
            },
            "experiment": {
                "dataset": "/unused/synthetic-dataset.jsonl",
                "conditions": ["adaptive_llm"],
            },
        }
    )


@pytest.fixture
def chat_constructors(monkeypatch):
    captured = []

    def capture(**kwargs):
        captured.append(kwargs)
        return kwargs

    monkeypatch.setattr(runner, "OpenAIChatClient", capture)
    monkeypatch.setenv("SYNTHETIC_EMBEDDING_KEY", "synthetic-embedding-secret")
    monkeypatch.setenv("SYNTHETIC_ANTHROPIC_KEY", "synthetic-anthropic-secret")
    return captured


def test_direct_anthropic_chat_keeps_qwen_embedding_identity(chat_constructors, monkeypatch):
    embedding_arguments = {}

    def embedding_client(**kwargs):
        embedding_arguments.update(kwargs)
        return OpenAIEmbeddingClient(**kwargs)

    monkeypatch.setattr(runner, "OpenAIEmbeddingClient", embedding_client)
    settings = config(
        chat_base_url="https://api.anthropic.com/v1",
        chat_api_key_env="SYNTHETIC_ANTHROPIC_KEY",
    )
    clients = runner._clients(settings)
    assert len(chat_constructors) == 3
    assert clients.answer is chat_constructors[0]
    assert clients.agent is chat_constructors[1]
    assert clients.router is chat_constructors[2]
    assert all(call["base_url"] == "https://api.anthropic.com/v1" for call in chat_constructors)
    assert all(call["api_key"] == "synthetic-anthropic-secret" for call in chat_constructors)
    assert all(call["model"] == "claude-haiku-4-5-20251001" for call in chat_constructors)
    assert all(call["token_parameter"] == "max_tokens" for call in chat_constructors)
    expected_embedding = OpenAIEmbeddingClient(
        base_url="https://openrouter.ai/api/v1", model="qwen/qwen3-embedding-8b"
    )
    assert clients.embedding.identity == expected_embedding.identity
    assert embedding_arguments["api_key"] == "synthetic-embedding-secret"
    serialized = settings.model_dump_json()
    assert "synthetic-embedding-secret" not in serialized
    assert "synthetic-anthropic-secret" not in serialized
    assert "SYNTHETIC_ANTHROPIC_KEY" in serialized


def test_chat_overrides_default_to_original_shared_connection(chat_constructors):
    clients = runner._clients(config())
    assert all(call["base_url"] == "https://openrouter.ai/api/v1" for call in chat_constructors)
    assert all(call["api_key"] == "synthetic-embedding-secret" for call in chat_constructors)
    assert clients.embedding.identity["base_url"] == "https://openrouter.ai/api/v1"


@pytest.mark.parametrize("field", ["chat_base_url", "chat_api_key_env"])
def test_optional_chat_connection_names_reject_blank_values(field):
    with pytest.raises(ValidationError):
        ModelSettings(base_url="https://fixture.invalid/v1", **{field: " "})

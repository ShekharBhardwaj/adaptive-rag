"""Adaptive CLI contracts use isolated source and synthetic provider fixtures only."""

import json
import subprocess

import pytest

from adaptive_rag.cli import _model_client, _router, main
from adaptive_rag.config import FoundationConfig
from adaptive_rag.observability import RetrievalTrace


@pytest.mark.parametrize(
    "overrides,chat_base,chat_key",
    [
        ({}, "https://embedding.example.invalid/v1", "synthetic-embedding-key"),
        (
            {"chat_base_url": "https://chat.example.invalid/v1"},
            "https://chat.example.invalid/v1",
            "synthetic-embedding-key",
        ),
        (
            {"chat_api_key_env": "SYNTHETIC_CHAT_KEY"},
            "https://embedding.example.invalid/v1",
            "synthetic-chat-key",
        ),
        (
            {
                "chat_base_url": "https://chat.example.invalid/v1",
                "chat_api_key_env": "SYNTHETIC_CHAT_KEY",
            },
            "https://chat.example.invalid/v1",
            "synthetic-chat-key",
        ),
    ],
)
def test_cli_chat_overrides_do_not_change_embedding_endpoint_or_credentials(
    tmp_path, monkeypatch, overrides, chat_base, chat_key
):
    from types import SimpleNamespace

    settings = {
        "base_url": "https://embedding.example.invalid/v1",
        "api_key_env": "SYNTHETIC_EMBEDDING_KEY",
        "embedding_model": "synthetic-embedding",
        "chat_model": "synthetic-chat",
        **overrides,
    }
    config = FoundationConfig.model_validate(
        {
            "repository": {
                "url": "https://source.invalid/repo.git",
                "path": tmp_path,
                "commit_sha": "a" * 40,
            },
            "models": settings,
            "routing": {"chat_model": "synthetic-router"},
        }
    )
    monkeypatch.setenv("SYNTHETIC_EMBEDDING_KEY", "synthetic-embedding-key")
    monkeypatch.setenv("SYNTHETIC_CHAT_KEY", "synthetic-chat-key")
    created = []

    def client(kind, **kwargs):
        created.append((kind, kwargs))
        return SimpleNamespace(identity={"model": kwargs["model"], "base_url": kwargs["base_url"]})

    monkeypatch.setattr(
        "adaptive_rag.generation.client.OpenAIEmbeddingClient",
        lambda **kwargs: client("embedding", **kwargs),
    )
    monkeypatch.setattr(
        "adaptive_rag.generation.client.OpenAIChatClient", lambda **kwargs: client("chat", **kwargs)
    )
    _model_client(config, "embedding", True)
    _model_client(config, "chat", True)
    _router(config, "llm", True)
    assert created[0][0] == "embedding"
    assert created[0][1]["base_url"] == "https://embedding.example.invalid/v1"
    assert created[0][1]["api_key"] == "synthetic-embedding-key"
    assert created[0][1]["model"] == "synthetic-embedding"
    for kind, kwargs in created[1:]:
        assert kind == "chat"
        assert kwargs["base_url"] == chat_base
        assert kwargs["api_key"] == chat_key
        assert kwargs["token_parameter"] == "max_tokens"
    assert [kwargs["model"] for _, kwargs in created] == [
        "synthetic-embedding",
        "synthetic-chat",
        "synthetic-router",
    ]


@pytest.fixture
def routing_source(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Synthetic Routing Fixture")
    git("config", "user.email", "routing@example.invalid")
    (repo / "source.py").write_text("class SyntheticTarget:\n    value = 1\n")
    git("add", ".")
    git("commit", "-m", "synthetic routing source")
    commit = git("rev-parse", "HEAD")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"repository:\n  url: {repo.as_uri()}\n  path: source\n  commit_sha: {commit}\n"
    )
    return repo, config


def test_rule_route_has_no_model_requests_and_preserves_provenance(routing_source, capsys):
    _, config = routing_source
    assert (
        main(
            [
                "route",
                "--config",
                str(config),
                "--router",
                "rule",
                "--query",
                "Where is SyntheticTarget defined?",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "completed"
    assert report["selected_strategy"] in {"vector", "vectorless", "agentic"}
    assert report["router"] == "rule_based"
    assert report["model_calls"] == []
    assert report["request"]["query"] == "Where is SyntheticTarget defined?"
    assert report["request"]["budget"]["max_model_calls"] == 1
    assert len(report["configuration_sha256"]) == 64
    assert report["end_to_end_seconds"] >= report["elapsed_seconds"]


def test_route_output_is_immutable_and_outside_corpus(
    routing_source, tmp_path, capsys, monkeypatch
):
    repo, config = routing_source
    args = ["route", "--config", str(config), "--router", "rule", "--query", "fixture"]
    target = tmp_path / "decision.json"
    assert main([*args, "--output", str(target)]) == 0
    capsys.readouterr()
    original = target.read_bytes()
    monkeypatch.setattr(
        "adaptive_rag.cli._configured_snapshot",
        lambda *_args, **_kwargs: pytest.fail("invalid output must fail before source access"),
    )
    assert main([*args, "--output", str(target)]) == 2
    assert "exists" in json.loads(capsys.readouterr().err)["error"]
    assert target.read_bytes() == original
    inside = repo / "decision.json"
    assert main([*args, "--output", str(inside)]) == 2
    assert "outside" in json.loads(capsys.readouterr().err)["error"]
    assert not inside.exists()


def test_llm_route_requires_explicit_api_opt_in_before_source_access(
    routing_source, capsys, monkeypatch
):
    _, config = routing_source
    monkeypatch.setattr(
        "adaptive_rag.cli._configured_snapshot",
        lambda *_args, **_kwargs: pytest.fail("denied routing must not read source"),
    )
    args = ["route", "--config", str(config), "--router", "llm", "--query", "fixture"]
    assert main(args) == 2
    assert "--allow-api" in json.loads(capsys.readouterr().err)["error"]
    assert main([*args, "--allow-api"]) == 2
    assert "models section" in json.loads(capsys.readouterr().err)["error"]


def test_route_invalid_query_fails_before_source_access(routing_source, capsys, monkeypatch):
    _, config = routing_source
    monkeypatch.setattr(
        "adaptive_rag.cli._configured_snapshot",
        lambda *_args, **_kwargs: pytest.fail("invalid query must not read source"),
    )
    assert main(["route", "--config", str(config), "--router", "rule", "--query", "   "]) == 2
    assert "query" in json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize("strategy", ["adaptive_rule", "adaptive_llm"])
def test_adaptive_retrieval_preflights_all_candidates_before_source_access(
    routing_source, tmp_path, capsys, monkeypatch, strategy
):
    _, config = routing_source
    monkeypatch.setattr(
        "adaptive_rag.cli._configured_snapshot",
        lambda *_args, **_kwargs: pytest.fail("invalid candidates must not read source"),
    )
    args = ["retrieve", "--config", str(config), "--strategy", strategy, "--query", "fixture"]
    assert main(args) == 2
    assert "--index" in json.loads(capsys.readouterr().err)["error"]
    args.extend(["--index", str(tmp_path / "not-built")])
    assert main(args) == 2
    assert "--allow-api" in json.loads(capsys.readouterr().err)["error"]
    assert main([*args, "--allow-api"]) == 2
    assert "models section" in json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize(
    "selection,status,code",
    [
        (
            {"strategy": "vectorless", "reason": "Synthetic exact identifier lookup."},
            "completed",
            0,
        ),
        ({"strategy": "unsupported", "reason": "Synthetic invalid choice."}, "error", 2),
    ],
)
def test_llm_route_uses_configured_model_and_preserves_raw_failure(
    routing_source, tmp_path, capsys, monkeypatch, selection, status, code
):
    import httpx

    from adaptive_rag.generation.client import OpenAIChatClient

    _, config = routing_source
    with config.open("a") as stream:
        stream.write(
            "models:\n  base_url: http://fixture.invalid/v1\n  chat_model: fixture-navigation\n"
            "routing:\n  chat_model: fixture-router\n  temperature: 0.0\n  max_output_tokens: 64\n"
        )
    requests = []

    def handler(request):
        data = json.loads(request.content)
        requests.append(data)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": json.dumps(selection)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(
        "adaptive_rag.generation.client.OpenAIChatClient",
        lambda **kwargs: OpenAIChatClient(**kwargs, transport=httpx.MockTransport(handler)),
    )
    target = tmp_path / "llm-decision.json"
    assert (
        main(
            [
                "route",
                "--config",
                str(config),
                "--router",
                "llm",
                "--query",
                "Where is SyntheticTarget defined?",
                "--output",
                str(target),
                "--allow-api",
            ]
        )
        == code
    )
    capsys.readouterr()
    report = json.loads(target.read_text())
    assert report["status"] == status
    assert report["selected_strategy"] == ("vectorless" if code == 0 else None)
    assert report["metadata"]["model_attempts"] == 1
    assert report["usage"] == {"input_tokens": 20, "output_tokens": 10}
    assert len(report["model_calls"]) == len(requests) == 1
    assert requests[0]["model"] == "fixture-router"
    assert requests[0]["max_tokens"] == 64
    assert "source.py" not in json.dumps(requests[0]["messages"])


@pytest.mark.parametrize("strategy", ["adaptive_rule", "adaptive_llm"])
def test_adaptive_retrieval_uses_shared_index_and_records_routing_in_trace(
    routing_source, tmp_path, capsys, monkeypatch, strategy
):
    import httpx

    from adaptive_rag.generation.client import OpenAIChatClient, OpenAIEmbeddingClient

    _, config = routing_source
    with config.open("a") as stream:
        stream.write(
            "models:\n  base_url: http://fixture.invalid/v1\n"
            "  embedding_model: fixture-embedding\n  chat_model: fixture-chat\n"
        )
    requests = []

    def handler(request):
        data = json.loads(request.content)
        requests.append(data)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": i, "embedding": [1.0, 0.5]} for i in range(len(data["input"]))
                    ],
                    "usage": {"prompt_tokens": 10},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"strategy": "vectorless", "reason": "Synthetic lookup."}
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    transport = httpx.MockTransport(handler)
    clients = {
        "embedding": OpenAIEmbeddingClient(
            base_url="http://fixture.invalid/v1", model="fixture-embedding", transport=transport
        ),
        "chat": OpenAIChatClient(
            base_url="http://fixture.invalid/v1", model="fixture-chat", transport=transport
        ),
    }
    monkeypatch.setattr(
        "adaptive_rag.cli._model_client",
        lambda config, operation, allow_api, **kwargs: clients[operation],
    )
    index = tmp_path / "synthetic-index"
    assert (
        main(["index", "build", "--config", str(config), "--output", str(index), "--allow-api"])
        == 0
    )
    capsys.readouterr()
    trace = tmp_path / "adaptive-trace.jsonl"
    assert (
        main(
            [
                "retrieve",
                "--config",
                str(config),
                "--strategy",
                strategy,
                "--index",
                str(index),
                "--query",
                "Where is SyntheticTarget defined?",
                "--trace",
                str(trace),
                "--allow-api",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["strategy"] == strategy
    assert report["selected_strategy"] == "vectorless"
    assert report["evidence"][0]["path"] == "source.py"
    assert report["metadata"]["routing"]["selected_strategy"] == "vectorless"
    assert len(report["model_calls"]) == (1 if strategy == "adaptive_llm" else 0)
    record = RetrievalTrace.model_validate_json(trace.read_text())
    assert record.result.strategy == strategy
    assert record.result.metadata["end_to_end_seconds"] >= record.result.elapsed_seconds
    assert len(requests) == (2 if strategy == "adaptive_llm" else 1)


def test_adaptive_index_failure_precedes_paid_routing(
    routing_source, tmp_path, capsys, monkeypatch
):
    from types import SimpleNamespace

    _, config = routing_source
    with config.open("a") as stream:
        stream.write(
            "models:\n  base_url: http://fixture.invalid/v1\n"
            "  embedding_model: fixture-embedding\n  chat_model: fixture-chat\n"
        )
    monkeypatch.setattr(
        "adaptive_rag.cli._router",
        lambda *_args, **_kwargs: SimpleNamespace(
            route=lambda *_args: pytest.fail("invalid index must fail before routing")
        ),
    )
    assert (
        main(
            [
                "retrieve",
                "--config",
                str(config),
                "--strategy",
                "adaptive_llm",
                "--index",
                str(tmp_path / "not-built"),
                "--query",
                "fixture",
                "--allow-api",
            ]
        )
        == 2
    )
    assert "error" in json.loads(capsys.readouterr().err)

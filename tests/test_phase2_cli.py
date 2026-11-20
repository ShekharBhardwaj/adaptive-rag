"""Public CLI and corpus integration, using only an isolated source repository."""

import hashlib
import json
import subprocess

import pytest

from adaptive_rag.cli import main
from adaptive_rag.ingestion import discover_files, read_source_files
from adaptive_rag.observability import RetrievalTrace
from adaptive_rag.retrieval.corpus import RepositoryCorpus


@pytest.fixture
def source_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Fixture Author")
    git("config", "user.email", "fixture@example.invalid")
    (repo / "source.py").write_text(
        "class BaseRetriever:\n    def invoke(self):\n        return []\n"
    )
    git("add", ".")
    git("commit", "-m", "isolated source fixture")
    commit = git("rev-parse", "HEAD")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"repository:\n  url: {repo.as_uri()}\n  path: repo\n  commit_sha: {commit}\n"
    )
    return repo, commit, config


def test_bulk_corpus_hashes_and_fingerprint(source_repo):
    repo, commit, _ = source_repo
    first = RepositoryCorpus.from_repository(repo, commit)
    second = RepositoryCorpus.from_repository(repo, commit)
    assert first.fingerprint == second.fingerprint
    evidence = first.evidence("source.py", 1, 2)
    assert evidence.excerpt_sha256 == hashlib.sha256(evidence.text.encode()).hexdigest()
    assert evidence.id == second.evidence("source.py", 1, 2).id
    with pytest.raises(TypeError):
        first._texts["source.py"] = "mutated"
    with pytest.raises(ValueError):
        first.text("../outside.py")
    with pytest.raises(ValueError):
        first.evidence("source.py", 0, 1)


def test_bulk_source_read_rejects_forged_manifest(source_repo):
    repo, commit, _ = source_repo
    sources = discover_files(repo, expected_commit=commit)
    forged = sources[0].model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError, match="manifest"):
        read_source_files(repo, [forged], commit)
    with pytest.raises(ValueError, match="duplicate"):
        read_source_files(repo, sources + sources, commit)


def test_vectorless_cli_returns_evidence_and_roundtrippable_jsonl(source_repo, tmp_path, capsys):
    _, commit, config = source_repo
    trace = tmp_path / "trace.jsonl"
    assert (
        main(
            [
                "retrieve",
                "--strategy",
                "vectorless",
                "--config",
                str(config),
                "--query",
                "Where is BaseRetriever defined?",
                "--trace",
                str(trace),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["repo_commit"] == commit
    assert result["evidence"][0]["path"] == "source.py"
    assert result["model_calls"] == []
    record = RetrievalTrace.model_validate_json(trace.read_text())
    assert record.result.status == "completed"
    assert record.final_answer is None
    assert len(record.framework_source_sha256) == 64
    assert record.result.metadata["end_to_end_seconds"] >= record.result.elapsed_seconds


@pytest.mark.parametrize("strategy", ["vector", "agentic"])
def test_model_requests_require_explicit_settings_and_opt_in(source_repo, capsys, strategy):
    _, _, config = source_repo
    args = ["retrieve", "--strategy", strategy, "--config", str(config), "--query", "fixture"]
    assert main(args) == 2
    assert "--allow-api" in json.loads(capsys.readouterr().err)["error"]
    assert main([*args, "--allow-api"]) == 2
    assert "models section" in json.loads(capsys.readouterr().err)["error"]


def test_index_plan_uses_no_model_and_reports_estimates(source_repo, capsys):
    _, commit, config = source_repo
    assert main(["index", "plan", "--config", str(config)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["repo_commit"] == commit
    assert report["chunks"] > 0
    assert report["embedding_input_utf8_bytes"] > 0
    assert "provider token usage" in report["note"]


@pytest.mark.parametrize("with_reuse", [False, True])
def test_index_reuse_is_forwarded_only_when_explicit(
    source_repo, tmp_path, capsys, monkeypatch, with_reuse
):
    from types import SimpleNamespace

    _, _, config = source_repo
    source = tmp_path / "failed-build"
    destination = tmp_path / "new-index"
    calls = []

    if with_reuse:

        def build(_self, directory, *, budget, reuse_from):
            calls.append((directory, budget, reuse_from))
            raise ValueError("synthetic build delegation reached")

    else:

        def build(_self, directory, *, budget):
            calls.append((directory, budget))
            raise ValueError("synthetic build delegation reached")

    monkeypatch.setattr("adaptive_rag.retrieval.vector.VectorRetriever.build_index", build)
    monkeypatch.setattr(
        "adaptive_rag.cli._model_client",
        lambda *_args: SimpleNamespace(identity={"model": "synthetic-embedding"}),
    )
    args = [
        "index",
        "build",
        "--config",
        str(config),
        "--output",
        str(destination),
        "--allow-api",
    ]
    if with_reuse:
        args.extend(["--reuse-from", str(source)])
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "synthetic build delegation reached"
    assert len(calls) == 1
    assert calls[0][0] == destination
    assert calls[0][1].max_model_calls == 1000
    assert len(calls[0]) == (3 if with_reuse else 2)
    if with_reuse:
        assert calls[0][2] == source


def test_index_reuse_does_not_bypass_explicit_api_admission(
    source_repo, tmp_path, capsys, monkeypatch
):
    _, _, config = source_repo
    monkeypatch.setattr(
        "adaptive_rag.cli._configured_snapshot",
        lambda *_args, **_kwargs: pytest.fail("denied build must not read source or reuse inputs"),
    )
    assert (
        main(
            [
                "index",
                "build",
                "--config",
                str(config),
                "--output",
                str(tmp_path / "new-index"),
                "--reuse-from",
                str(tmp_path / "failed-build"),
            ]
        )
        == 2
    )
    assert "--allow-api" in json.loads(capsys.readouterr().err)["error"]


def test_index_reuse_stdout_omits_parent_raw_calls(source_repo, tmp_path, capsys, monkeypatch):
    from types import SimpleNamespace

    from adaptive_rag.retrieval.models import TokenUsage

    _, _, config = source_repo
    source = tmp_path / "failed-build"
    provenance = {
        "source_directory": str(source),
        "source_journal_sha256": "a" * 64,
        "source_failure_sha256": "b" * 64,
        "reused_successful_calls": 1,
        "reused_chunks": 2,
        "reused_usage": {"input_tokens": 20, "output_tokens": 0},
        "new_model_attempts": 1,
        "new_usage": {"input_tokens": 10, "output_tokens": 0},
        "budget_scope": "new provider calls only; elapsed time includes validation/replay",
        "parent_failure_accounting": {
            "model_calls": [{"response": {"embedding": ["raw-provider-data-must-stay-on-disk"]}}],
            "usage": {"input_tokens": None, "output_tokens": None},
        },
    }

    def build(retriever, directory, *, budget, reuse_from):
        assert reuse_from == source
        return SimpleNamespace(
            index_version="synthetic-summary-fixture",
            repo_commit=retriever.corpus.commit_sha,
            corpus_fingerprint=retriever.corpus.fingerprint,
            embedding_identity={"model": "synthetic-embedding"},
            chunk_count=3,
            dimensions=2,
            model_attempts=2,
            usage=TokenUsage(input_tokens=30, output_tokens=0),
            elapsed_seconds=0.5,
            input_token_byte_estimate=100,
            reuse_provenance=provenance,
        )

    monkeypatch.setattr("adaptive_rag.retrieval.vector.VectorRetriever.build_index", build)
    monkeypatch.setattr(
        "adaptive_rag.cli._model_client",
        lambda *_args: SimpleNamespace(identity={"model": "synthetic-embedding"}),
    )
    assert (
        main(
            [
                "index",
                "build",
                "--config",
                str(config),
                "--output",
                str(tmp_path / "new-index"),
                "--reuse-from",
                str(source),
                "--allow-api",
            ]
        )
        == 0
    )
    stdout = capsys.readouterr().out
    summary = json.loads(stdout)
    assert set(summary["reuse"]) == {
        "source_directory",
        "reused_successful_calls",
        "reused_chunks",
        "reused_usage",
        "new_model_attempts",
        "new_usage",
        "budget_scope",
    }
    assert summary["model_attempts"] == 2
    assert summary["reuse"]["new_model_attempts"] == 1
    assert summary["reuse"]["new_usage"] == {"input_tokens": 10, "output_tokens": 0}
    assert "parent_failure_accounting" not in stdout
    assert "raw-provider-data-must-stay-on-disk" not in stdout


def test_colliding_and_corpus_contained_outputs_fail_before_retrieval(
    source_repo, tmp_path, capsys
):
    repo, _, config = source_repo
    args = ["retrieve", "--strategy", "vectorless", "--config", str(config), "--query", "fixture"]
    same = tmp_path / "same.json"
    assert main([*args, "--output", str(same), "--trace", str(same)]) == 2
    assert "different output paths" in json.loads(capsys.readouterr().err)["error"]
    assert not same.exists()
    target = repo / "trace.jsonl"
    assert main([*args, "--trace", str(target)]) == 2
    assert "outside" in json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


def test_failed_budget_still_writes_raw_trace(source_repo, capsys, tmp_path):
    _, _, config = source_repo
    with config.open("a") as stream:
        stream.write("retrieval:\n  budget:\n    max_tool_calls: 0\n")
    target = tmp_path / "exhausted.jsonl"
    assert (
        main(
            [
                "retrieve",
                "--strategy",
                "vectorless",
                "--config",
                str(config),
                "--query",
                "BaseRetriever",
                "--trace",
                str(target),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "budget_exhausted"
    assert RetrievalTrace.model_validate_json(target.read_text()).result.tool_call_count == 0


def test_vector_cli_build_load_query_through_http_fixture(
    source_repo, capsys, tmp_path, monkeypatch
):
    import httpx

    from adaptive_rag.generation.client import OpenAIEmbeddingClient

    _, _, config = source_repo

    def handler(request):
        inputs = json.loads(request.content)["input"]
        return httpx.Response(
            200,
            json={
                "data": [{"index": i, "embedding": [1.0, 0.5]} for i in range(len(inputs))],
                "usage": {"prompt_tokens": len(inputs) * 10},
            },
        )

    client = OpenAIEmbeddingClient(
        base_url="http://fixture.invalid/v1",
        model="fixture-embedding",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("adaptive_rag.cli._model_client", lambda *args: client)
    index = tmp_path / "fixture-index"
    assert (
        main(["index", "build", "--config", str(config), "--output", str(index), "--allow-api"])
        == 0
    )
    stdout = capsys.readouterr().out
    summary = json.loads(stdout)
    assert set(summary) == {
        "status",
        "index_directory",
        "manifest_path",
        "index_version",
        "repo_commit",
        "corpus_fingerprint",
        "embedding_identity",
        "chunk_count",
        "dimensions",
        "model_attempts",
        "usage",
        "elapsed_seconds",
        "input_token_byte_estimate",
    }
    assert summary["status"] == "completed"
    assert summary["index_directory"] == str(index.resolve())
    assert summary["manifest_path"] == str(index.resolve() / "manifest.json")
    assert summary["chunk_count"] > 0
    assert summary["dimensions"] == 2
    assert summary["model_attempts"] == 1
    assert summary["elapsed_seconds"] >= 0
    assert summary["usage"]["input_tokens"] > 0
    assert "model_calls" not in summary
    assert '"embedding":' not in stdout
    saved_manifest = json.loads((index / "manifest.json").read_text())
    assert saved_manifest["model_calls"][0]["response"]["data"][0]["embedding"] == [1.0, 0.5]
    for field in (
        "index_version",
        "repo_commit",
        "corpus_fingerprint",
        "embedding_identity",
        "chunk_count",
        "dimensions",
        "model_attempts",
        "usage",
        "elapsed_seconds",
        "input_token_byte_estimate",
    ):
        assert summary[field] == saved_manifest[field]
    assert (
        main(
            [
                "retrieve",
                "--strategy",
                "vector",
                "--config",
                str(config),
                "--index",
                str(index),
                "--query",
                "BaseRetriever",
                "--allow-api",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["evidence"][0]["path"] == "source.py"
    assert len(result["model_calls"]) == 1
    assert result["usage"]["input_tokens"] == 10


def test_agentic_cli_through_http_fixture(source_repo, capsys, tmp_path, monkeypatch):
    import httpx

    from adaptive_rag.generation.client import OpenAIChatClient

    _, _, config = source_repo
    with config.open("a") as stream:
        stream.write("models:\n  base_url: http://fixture.invalid/v1\n  chat_model: fixture-chat\n")
    requests = []

    def handler(request):
        data = json.loads(request.content)
        requests.append(data)
        if len(requests) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "fixture-call",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "source.py"}),
                        },
                    }
                ],
            }
        else:
            shown = json.loads(data["messages"][-1]["content"])["available_evidence_ids"]
            message = {"role": "assistant", "content": json.dumps({"evidence_ids": shown[:1]})}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = OpenAIChatClient(
        base_url="http://fixture.invalid/v1",
        model="fixture-chat",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("adaptive_rag.cli._model_client", lambda *args: client)
    trace = tmp_path / "agentic-fixture.jsonl"
    assert (
        main(
            [
                "retrieve",
                "--strategy",
                "agentic",
                "--config",
                str(config),
                "--query",
                "BaseRetriever",
                "--allow-api",
                "--trace",
                str(trace),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["evidence"][0]["path"] == "source.py"
    assert result["tool_call_count"] == 1
    assert len(result["model_calls"]) == 2
    assert RetrievalTrace.model_validate_json(trace.read_text()).result.usage.total_tokens == 30

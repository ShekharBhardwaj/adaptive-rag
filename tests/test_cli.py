import json
import subprocess

import pytest

from adaptive_rag.cli import main


@pytest.fixture
def configured_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Test Author")
    git("config", "user.email", "test@example.invalid")
    (repo / "module.py").write_text("def example():\n    return 1\n", encoding="utf-8")
    git("add", "module.py")
    git("commit", "-m", "Synthetic test fixture")
    sha = git("rev-parse", "HEAD")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"repository:\n  url: {repo.as_uri()}\n  path: repo\n  commit_sha: {sha}\n",
        encoding="utf-8",
    )
    return repo, config


def test_cli_config_and_existing_snapshot(configured_repo, capsys):
    repo, config = configured_repo
    assert main(["config", "validate", "--config", str(config)]) == 0
    assert json.loads(capsys.readouterr().out)["repository"]["path"] == str(repo)
    assert main(["repo", "snapshot", "--config", str(config)]) == 0
    assert len(json.loads(capsys.readouterr().out)["commit_sha"]) == 40


def test_cli_inspection_and_immutable_outputs(configured_repo, capsys, tmp_path):
    _, config = configured_repo
    output = tmp_path / "artifacts" / "manifest.json"
    args = ["repo", "inspect", "--config", str(config), "--output", str(output)]
    assert main(args) == 0
    before = output.read_bytes()
    assert json.loads(before)["files"][0]["path"] == "module.py"
    capsys.readouterr()
    assert main(args) == 2
    assert output.read_bytes() == before
    assert json.loads(capsys.readouterr().err)["type"] == "FileExistsError"


def test_cli_rejects_dirty_checkout_and_origin_mismatch(configured_repo, capsys):
    repo, config = configured_repo
    text = config.read_text()
    config.write_text(text.replace(repo.as_uri(), "https://example.invalid/different.git"))
    assert main(["repo", "inspect", "--config", str(config)]) == 2
    assert "origin" in json.loads(capsys.readouterr().err)["error"]
    config.write_text(text)
    (repo / "module.py").write_text("changed\n")
    assert main(["repo", "snapshot", "--config", str(config)]) == 2
    assert json.loads(capsys.readouterr().err)["error"]


def test_cli_schema_and_invalid_benchmark(configured_repo, capsys, tmp_path):
    _, config = configured_repo
    assert main(["benchmark", "schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "ground_truth_answer" in schema["properties"]
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert main(["benchmark", "validate", str(empty), "--config", str(config)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert not report["valid"]
    assert report["errors"]


@pytest.mark.parametrize("precreate", [False, True])
def test_cli_clones_exact_commit_into_new_or_empty_destination(
    configured_repo, capsys, tmp_path, precreate
):
    repo, config = configured_repo
    destination = tmp_path / "cloned"
    if precreate:
        destination.mkdir()
    config.write_text(config.read_text().replace("path: repo", "path: cloned"))
    assert main(["repo", "snapshot", "--config", str(config)]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot["url"] == repo.as_uri()
    assert (destination / "module.py").read_bytes() == (repo / "module.py").read_bytes()
    head = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == snapshot["commit_sha"]


def test_python_module_entrypoint():
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "adaptive_rag", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "route" in result.stdout and "experiment" in result.stdout

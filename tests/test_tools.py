from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

import pytest

from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.symbols import extract_symbols, identifier_terms
from adaptive_rag.retrieval.tools import RepositoryTools, ToolDeadlineExceeded


def make_corpus(root: Path, files: dict[str, str]) -> RepositoryCorpus:
    root.mkdir()
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            env=env,
            check=True,
            text=True,
            capture_output=True,
            timeout=30,
        ).stdout.strip()

    git("init", "--quiet", "--template=")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgsign", "false")
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git("add", "--all")
    git("commit", "--quiet", "-m", "fixture")
    return RepositoryCorpus.from_repository(root, git("rev-parse", "HEAD"))


@pytest.fixture
def corpus(tmp_path: Path) -> RepositoryCorpus:
    return make_corpus(
        tmp_path / "repo",
        {
            "README.md": "# Fixture\nRetriever implementation lives under src.\n",
            "src/retriever.py": (
                "class BaseRetriever:\n"
                "    async def retrieve_documents(self, query):\n"
                "        return query\n\n"
                "def use_retriever(query):\n"
                "    return BaseRetriever().retrieve_documents(query)\n"
            ),
            "src/nested/worker.ts": "export class Worker {}\nconst retriever = 'BaseRetriever';\n",
            "src/references.txt": (
                "BaseRetrieverX\n_BaseRetriever\nBaseRetriever()\n# BaseRetriever\n"
            ),
            ".env": "BaseRetriever=secret\n",
            "empty.txt": "",
        },
    )


def test_directory_navigation_is_one_level_and_included_only(corpus):
    tools = RepositoryTools(corpus)
    entries = tools.list_directory().data["entries"]
    assert {entry["path"] for entry in entries} == {"README.md", "empty.txt", "src"}
    assert {entry["path"] for entry in tools.list_directory("src").data["entries"]} == {
        "src/nested",
        "src/references.txt",
        "src/retriever.py",
    }
    assert tools.list_directory(limit=1).data["truncated"] is True
    with pytest.raises(ValueError, match="not in the included corpus"):
        tools.list_directory("missing")


@pytest.mark.parametrize("path", ["../README.md", "/tmp/file", "src/../README.md", "a\\b", "a//b"])
def test_tools_refuse_escaping_or_noncanonical_paths(corpus, path):
    tools = RepositoryTools(corpus)
    for method in (tools.read_file, tools.list_directory, tools.search_files):
        with pytest.raises(ValueError):
            method(path)


def test_filename_glob_substring_and_stable_order(corpus):
    tools = RepositoryTools(corpus)
    assert [item["path"] for item in tools.search_files("*.py").data["matches"]] == [
        "src/retriever.py"
    ]
    assert tools.search_files("RETRIEVER").data["matches"][0]["path"] == "src/retriever.py"
    assert tools.search_files(".env").data["matches"] == []
    assert tools.search_files("**/*.ts").data["matches"][0]["path"] == "src/nested/worker.ts"


def test_python_symbols_have_real_scope_and_generic_fallback_is_marked(corpus):
    tools = RepositoryTools(corpus)
    matches = tools.search_symbols("retrieve_documents").data["matches"]
    exact = next(item for item in matches if item["name"] == "retrieve_documents")
    assert exact["qualified_name"] == "BaseRetriever.retrieve_documents"
    assert exact["start_line"] == 2 and exact["end_line"] == 3
    assert exact["extraction"] == "python_ast"
    worker = tools.search_symbols("Worker").data["matches"][0]
    assert worker["extraction"] == "regex_approximate"
    assert worker["start_line"] == 1
    assert {"retrieve", "documents", "retrieve_documents"} <= set(
        identifier_terms("retrieve_documents")
    )
    assert {"base", "retriever", "baseretriever"} <= set(identifier_terms("BaseRetriever"))
    broken = extract_symbols("broken.py", "def broken(:\n")
    assert broken[0].extraction == "regex_approximate"


def test_every_search_excerpt_matches_source_and_hash(corpus):
    tools = RepositoryTools(corpus)
    for result in (
        tools.search_files("retriever"),
        tools.search_symbols("BaseRetriever"),
        tools.search_keywords("retriever documents"),
        tools.inspect_references("BaseRetriever"),
    ):
        assert result.evidence
        for chunk in result.evidence:
            expected = "\n".join(
                corpus.text(chunk.path).splitlines()[chunk.start_line - 1 : chunk.end_line]
            )
            assert chunk.text == expected
            assert chunk.repo_commit == corpus.commit_sha
            assert chunk.excerpt_sha256 == hashlib.sha256(expected.encode()).hexdigest()


def test_references_are_exact_textual_occurrences_not_a_call_graph(corpus):
    result = RepositoryTools(corpus).inspect_references("BaseRetriever")
    lines = [
        item["start_line"]
        for item in result.data["matches"]
        if item["path"] == "src/references.txt"
    ]
    assert lines == [3, 4]
    assert "definitions/comments" in result.data["semantics"]
    with pytest.raises(ValueError, match="identifier"):
        RepositoryTools(corpus).inspect_references("BaseRetriever.*")


def test_read_bounds_empty_file_and_limits(corpus):
    tools = RepositoryTools(corpus)
    result = tools.read_file("src/retriever.py", start_line=2, end_line=3)
    assert result.evidence[0].text.startswith("    async def retrieve_documents")
    assert result.data["line_count"] == 6
    assert tools.read_file("empty.txt").data["empty"] is True
    for kwargs in (
        {"start_line": 0},
        {"start_line": 7},
        {"end_line": 7},
        {"start_line": 3, "end_line": 2},
        {"end_line": 3, "max_lines": 2},
        {"max_lines": 201},
        {"start_line": True},
    ):
        with pytest.raises(ValueError):
            tools.read_file("src/retriever.py", **kwargs)
    with pytest.raises(ValueError, match="not in the included corpus"):
        tools.read_file(".env")
    for limit in (0, 101, True, 2.0):
        with pytest.raises(ValueError):
            tools.search_symbols("Retriever", limit=limit)


def test_oversized_lines_do_not_create_false_truncated_evidence(tmp_path):
    corpus = make_corpus(tmp_path / "repo", {"large.py": "# Retriever " + "x" * 25_000 + "\n"})
    tools = RepositoryTools(corpus)
    result = tools.search_keywords("Retriever")
    assert not result.evidence
    assert "omission_reason" in result.data["matches"][0]
    with pytest.raises(ValueError, match="24000 evidence characters"):
        tools.read_file("large.py")


def test_tools_stop_source_scans_at_cooperative_deadline(corpus):
    tools = RepositoryTools(corpus)
    tools.deadline = time.monotonic() - 1
    for method, argument in (
        (tools.list_directory, "."),
        (tools.search_files, "retriever"),
        (tools.search_symbols, "Retriever"),
        (tools.search_keywords, "Retriever"),
        (tools.read_file, "README.md"),
        (tools.inspect_references, "Retriever"),
    ):
        with pytest.raises(ToolDeadlineExceeded):
            method(argument)

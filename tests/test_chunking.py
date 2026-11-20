"""Chunk boundaries retain source provenance under parser and size fallbacks."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptive_rag.retrieval import chunking
from adaptive_rag.retrieval.chunking import ChunkingConfig, chunk_corpus
from adaptive_rag.retrieval.corpus import RepositoryCorpus


def make_corpus(tmp_path: Path, files: dict[str, str]) -> RepositoryCorpus:
    root = tmp_path / "repository"
    root.mkdir()
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=environment,
        ).stdout.strip()

    git("init", "--quiet", "--template=")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "--all")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return RepositoryCorpus.from_repository(root, git("rev-parse", "HEAD"))


def test_python_boundaries_preserve_decorators_comments_and_last_line(tmp_path: Path) -> None:
    text = (
        "# leading comment\nimport os\n\n"
        "@decorate\ndef first():\n    return 1\n\n"
        "# second comment\ndef second():\n    return 2"
    )
    corpus = make_corpus(tmp_path, {"code.py": text})
    chunks = chunk_corpus(corpus, ChunkingConfig(max_lines=6, overlap_lines=1))
    covered = {line for chunk in chunks for line in range(chunk.start_line, chunk.end_line + 1)}
    assert covered == set(range(1, 11))
    decorated = next(chunk for chunk in chunks if "def first" in chunk.text)
    assert "@decorate" in decorated.text
    assert all("parser=" in chunk.reason for chunk in chunks)
    for chunk in chunks:
        assert chunk.text == "\n".join(text.splitlines()[chunk.start_line - 1 : chunk.end_line])
        assert chunk.excerpt_sha256 == hashlib.sha256(chunk.text.encode()).hexdigest()
    assert chunk_corpus(corpus, ChunkingConfig(max_lines=6, overlap_lines=1)) == chunks


def test_windows_cover_all_lines_with_overlap_and_bounded_size(tmp_path: Path) -> None:
    text = "\n".join(f"line {number}" for number in range(20))
    corpus = make_corpus(tmp_path, {"notes.txt": text})
    config = ChunkingConfig(max_lines=5, max_chars=30, overlap_lines=2, parser="line_windows")
    chunks = chunk_corpus(corpus, config)
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 20
    assert all(len(chunk.text) <= 30 for chunk in chunks)
    assert all(chunk.end_line - chunk.start_line < 5 for chunk in chunks)
    assert {line for c in chunks for line in range(c.start_line, c.end_line + 1)} == set(
        range(1, 21)
    )
    assert any(
        right.start_line <= left.end_line for left, right in zip(chunks, chunks[1:], strict=False)
    )


def test_one_oversized_line_is_kept_intact_and_explicit(tmp_path: Path) -> None:
    corpus = make_corpus(tmp_path, {"one.txt": "x" * 100 + "\nnext"})
    chunks = chunk_corpus(corpus, ChunkingConfig(max_lines=5, max_chars=10, overlap_lines=0))
    assert chunks[0].text == "x" * 100
    assert chunks[0].start_line == chunks[0].end_line == 1
    assert "oversized_line=kept_complete" in chunks[0].reason
    assert chunks[1].text == "next"


def test_parse_error_and_empty_file_fallbacks(tmp_path: Path) -> None:
    corpus = make_corpus(tmp_path, {"bad.py": "def broken(:\n  pass\n", "empty.py": ""})
    chunks = chunk_corpus(corpus)
    assert len(chunks) == 1
    assert "parse_error" in chunks[0].reason
    assert chunks[0].path == "bad.py"
    assert chunks[0].end_line == 2


def test_typescript_parser_backend_is_recorded_and_covers_crlf_source(tmp_path: Path) -> None:
    text = "// comment\r\nexport function x() { return 1; }\r\nconst y = 2;"
    corpus = make_corpus(tmp_path, {"code.ts": text})
    chunks = chunk_corpus(corpus, ChunkingConfig(max_lines=2, overlap_lines=0))
    assert {line for c in chunks for line in range(c.start_line, c.end_line + 1)} == {1, 2, 3}
    assert all("parser=" in chunk.reason for chunk in chunks)
    assert all("\r" not in chunk.text for chunk in chunks)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_lines": 0},
        {"max_chars": 0},
        {"max_lines": 4, "overlap_lines": 4},
        {"max_lines": True},
        {"oversized_line_policy": "truncate"},
    ],
)
def test_chunking_rejects_invalid_or_silently_truncating_configuration(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(**kwargs)


def test_python_ast_fallback_retains_decorator_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chunking, "_tree_sitter_boundaries", lambda text, suffix: None)
    corpus = make_corpus(
        tmp_path, {"code.py": "import os\n\n@decorate\ndef example():\n    return 1\n"}
    )
    chunks = chunk_corpus(corpus, ChunkingConfig(max_lines=3, overlap_lines=0))
    decorated = next(chunk for chunk in chunks if "def example" in chunk.text)
    assert decorated.start_line == 3
    assert "@decorate" in decorated.text
    assert "python_ast:tree_sitter_unavailable" in decorated.reason

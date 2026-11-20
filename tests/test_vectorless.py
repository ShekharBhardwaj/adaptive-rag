from __future__ import annotations

import hashlib

from test_tools import make_corpus

from adaptive_rag.retrieval import tools as repository_tools
from adaptive_rag.retrieval.models import RetrievalBudget, RetrievalRequest
from adaptive_rag.retrieval.vectorless import VectorlessRetriever


def fixture_corpus(tmp_path):
    return make_corpus(
        tmp_path / "repo",
        {
            "README.md": "# Fixture\nGeneral package docs.\n",
            "src/retrievers/base.py": (
                "class BaseRetriever:\n"
                "    def retrieve_documents(self, query):\n"
                "        return self._search(query)\n\n"
                "    def _search(self, query):\n"
                "        return ['matching document']\n"
            ),
            "src/unrelated.py": "def other():\n    return 42\n",
            "docs/retrieval.md": "Retrieval uses a configured retriever.\n",
        },
    )


def test_vectorless_inspects_explicit_path_symbol_and_preserves_source(tmp_path):
    corpus = fixture_corpus(tmp_path)
    result = VectorlessRetriever(corpus).retrieve(
        RetrievalRequest(
            query="How does BaseRetriever retrieve_documents in src/retrievers/base.py?",
            top_k=2,
        )
    )
    assert result.status == "completed"
    assert result.evidence[0].path == "src/retrievers/base.py"
    assert "retrieve_documents" in result.evidence[0].text
    names = {operation.name for operation in result.operations}
    assert {
        "list_directory",
        "search_files",
        "search_symbols",
        "search_keywords",
        "read_file",
    } <= names
    assert result.tool_call_count == sum(op.name != "verify_snapshot" for op in result.operations)
    assert result.usage.total_tokens == 0 and result.model_calls == ()
    assert result.metadata["score_kind"] == "heuristic"
    assert result.corpus_fingerprint == corpus.fingerprint
    for chunk in result.evidence:
        expected = "\n".join(
            corpus.text(chunk.path).splitlines()[chunk.start_line - 1 : chunk.end_line]
        )
        assert chunk.text == expected
        assert chunk.excerpt_sha256 == hashlib.sha256(expected.encode()).hexdigest()


def test_vectorless_is_deterministic_without_benchmark_labels(tmp_path):
    corpus = fixture_corpus(tmp_path)
    request = RetrievalRequest(query="retrieve documents BaseRetriever", top_k=3)
    retriever = VectorlessRetriever(corpus)
    first, second = retriever.retrieve(request), retriever.retrieve(request)
    assert first.evidence == second.evidence
    assert [(op.name, op.arguments, op.returned_ids) for op in first.operations] == [
        (op.name, op.arguments, op.returned_ids) for op in second.operations
    ]
    assert first.metadata == second.metadata


def test_vectorless_no_matches_and_no_implicit_model_calls(tmp_path):
    corpus = fixture_corpus(tmp_path)
    result = VectorlessRetriever(corpus).retrieve(RetrievalRequest(query="zzznonexistent"))
    assert result.status == "completed" and result.evidence == ()
    assert result.model_calls == ()


def test_symbol_extraction_cache_is_reset_for_each_query(tmp_path, monkeypatch):
    corpus = fixture_corpus(tmp_path)
    extracted = []
    original = repository_tools.extract_symbols

    def tracked(path, text):
        extracted.append(path)
        return original(path, text)

    monkeypatch.setattr(repository_tools, "extract_symbols", tracked)
    retriever = VectorlessRetriever(corpus)
    request = RetrievalRequest(query="BaseRetriever retrieve_documents", top_k=2)
    first = retriever.retrieve(request)
    first_extractions = tuple(extracted)
    assert len(first_extractions) == len(corpus.files)
    second = retriever.retrieve(request)
    assert tuple(extracted) == first_extractions + first_extractions
    assert first.status == second.status == "completed"
    assert first.evidence == second.evidence


def test_tool_budget_counts_all_attempts_and_stops(tmp_path):
    corpus = fixture_corpus(tmp_path)
    result = VectorlessRetriever(corpus).retrieve(
        RetrievalRequest(
            query="BaseRetriever",
            budget=RetrievalBudget(max_tool_calls=0),
        )
    )
    assert result.status == "budget_exhausted"
    assert result.tool_call_count == 0 and result.evidence == ()
    assert result.metadata["exhausted_limits"] == ["max_tool_calls"]
    result = VectorlessRetriever(corpus).retrieve(
        RetrievalRequest(
            query="BaseRetriever",
            budget=RetrievalBudget(max_tool_calls=2),
        )
    )
    assert result.status == "budget_exhausted"
    assert result.tool_call_count == 2


def test_partial_evidence_obeys_character_budget_with_true_line_ranges(tmp_path):
    corpus = fixture_corpus(tmp_path)
    result = VectorlessRetriever(corpus).retrieve(
        RetrievalRequest(
            query="BaseRetriever",
            top_k=4,
            budget=RetrievalBudget(max_evidence_chars=25),
        )
    )
    assert sum(len(chunk.text) for chunk in result.evidence) <= 25
    assert result.status == "budget_exhausted"
    assert "max_evidence_chars" in result.metadata["exhausted_limits"]
    for chunk in result.evidence:
        assert chunk.text == "\n".join(
            corpus.text(chunk.path).splitlines()[chunk.start_line - 1 : chunk.end_line]
        )


def test_time_limit_records_observed_work_and_stops(tmp_path):
    corpus = fixture_corpus(tmp_path)
    result = VectorlessRetriever(corpus).retrieve(
        RetrievalRequest(
            query="BaseRetriever",
            budget=RetrievalBudget(max_seconds=0.000001),
        )
    )
    assert result.status == "budget_exhausted"
    assert result.tool_call_count == 0
    assert "max_seconds" in result.metadata["exhausted_limits"]


def test_snapshot_mutation_fails_closed(tmp_path):
    corpus = fixture_corpus(tmp_path)
    (corpus.repository / "src/retrievers/base.py").write_text("changed\n")
    result = VectorlessRetriever(corpus).retrieve(RetrievalRequest(query="BaseRetriever"))
    assert result.status == "error" and result.evidence == ()
    assert result.errors and result.operations[0].error


def test_failed_navigation_is_traced_and_counts_toward_budget(tmp_path):
    corpus = fixture_corpus(tmp_path)
    result = VectorlessRetriever(corpus).retrieve(RetrievalRequest(query="missing/file.py"))
    failed = [operation for operation in result.operations if operation.error]
    assert any(operation.name == "list_directory" for operation in failed)
    assert result.tool_call_count == sum(op.name != "verify_snapshot" for op in result.operations)
    assert result.errors

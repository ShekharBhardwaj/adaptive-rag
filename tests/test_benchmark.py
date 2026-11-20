"""Benchmarks must fail closed when source evidence or provenance is invalid."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from adaptive_rag.evaluation import (
    BenchmarkLoadError,
    export_benchmark_schema,
    load_benchmark,
    validate_benchmark,
)
from adaptive_rag.ingestion import DiscoveryPolicy


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


@pytest.fixture
def benchmark_repo(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "--quiet")
    git(repository, "config", "user.name", "Fixture Author")
    git(repository, "config", "user.email", "author@example.invalid")
    git(repository, "config", "core.autocrlf", "false")
    (repository / "src").mkdir()
    (repository / "src" / "example.py").write_bytes(
        b'def answer():\r\n    """Return the documented value."""\r\n    return 42\r\n'
    )
    (repository / "excluded.py").write_text("generated = True\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", "Fixture source snapshot")
    return repository, git(repository, "rev-parse", "HEAD")


def record(commit: str, *, identifier: str = "concept-01") -> dict:
    excerpt = 'def answer():\n    """Return the documented value."""\n    return 42'
    return {
        "id": identifier,
        "question": "What value does answer return?",
        "category": "conceptual",
        "ground_truth_answer": "The answer function returns the integer 42.",
        "evidence": [
            {
                "path": "src/example.py",
                "start_line": 1,
                "end_line": 3,
                "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
            }
        ],
        "repo_commit": commit,
        "provenance": {
            "author": "Fixture Author",
            "created_at": "2026-01-01T12:00:00Z",
            "method": "source_inspection",
            "notes": "Read the complete implementation at the recorded commit.",
            "review": {
                "reviewer": "Independent Reviewer",
                "reviewed_at": "2026-01-02T12:00:00Z",
                "method": "source_inspection",
                "notes": "Verified the answer against the cited source range.",
            },
        },
        "difficulty": "easy",
        "split": "development",
    }


def write_dataset(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "questions.jsonl"
    path.write_text("".join(json.dumps(value) + "\n" for value in records), encoding="utf-8")
    return path


def codes(report) -> set[str]:
    return {issue.code for issue in report.errors}


def test_valid_benchmark_records_raw_hash_and_counts(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    path = write_dataset(tmp_path, [record(commit)])
    report = validate_benchmark(path, repository, commit)
    assert report.valid, report.model_dump_json(indent=2)
    assert report.dataset_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report.expected_commit == commit
    assert report.question_count == 1
    assert report.category_counts == {"conceptual": 1, "structural": 0, "cross_file": 0}
    assert report.split_counts == {"development": 1, "held_out": 0}
    assert report.validated_at.tzinfo is not None
    assert report.model_dump(mode="json")["valid"] is True
    assert load_benchmark(path)[0].id == "concept-01"


@pytest.mark.parametrize("contents", [b"", b"\n", b"  \n", b"not json\n", b"[]\n"])
def test_empty_or_invalid_benchmarks_never_pass(benchmark_repo, tmp_path, contents):
    repository, commit = benchmark_repo
    path = tmp_path / "bad.jsonl"
    path.write_bytes(contents)
    report = validate_benchmark(path, repository, commit)
    assert not report.valid
    assert "empty_benchmark" in codes(report)
    with pytest.raises(BenchmarkLoadError):
        load_benchmark(path)


def test_per_line_errors_preserve_valid_records_for_audit(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    path = write_dataset(tmp_path, [record(commit)])
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"id":"broken", "question":true}\n{bad json}\n\n')
    report = validate_benchmark(path, repository, commit)
    assert report.question_count == 1
    assert {error.line for error in report.errors} == {2, 3, 4}
    assert {error.code for error in report.errors} == {
        "invalid_question",
        "invalid_json",
        "blank_line",
    }
    invalid = next(error for error in report.errors if error.code == "invalid_question")
    assert invalid.question_id == "broken"
    assert "question" in invalid.message


def test_invalid_utf8_is_a_structured_error(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    path = tmp_path / "bad.jsonl"
    path.write_bytes(b"\xff")
    report = validate_benchmark(path, repository, commit)
    assert not report.valid
    assert "invalid_encoding" in codes(report)


@pytest.mark.parametrize(
    "contents",
    [
        '{"id":"first","id":"second"}\n',
        '{"provenance":{"author":"one","author":"two"}}\n',
        '{"id":NaN}\n',
    ],
)
def test_ambiguous_or_nonstandard_json_is_rejected(benchmark_repo, tmp_path, contents):
    repository, commit = benchmark_repo
    path = tmp_path / "bad.jsonl"
    path.write_text(contents, encoding="utf-8")
    report = validate_benchmark(path, repository, commit)
    assert "invalid_json" in codes(report)
    assert report.errors[0].line == 1


@pytest.mark.parametrize(
    "split, expected", [("development", "duplicate_question"), ("held_out", "split_leakage")]
)
def test_normalized_duplicate_questions_and_split_leakage(
    benchmark_repo, tmp_path, split, expected
):
    repository, commit = benchmark_repo
    first = record(commit)
    second = record(commit, identifier="concept-02")
    second["question"] = "  WHAT\tvalue does answer return?  "
    second["split"] = split
    path = write_dataset(tmp_path, [first, second])
    report = validate_benchmark(path, repository, commit)
    assert expected in codes(report)
    with pytest.raises(BenchmarkLoadError) as exc:
        load_benchmark(path)
    assert any(error.line == 2 and error.question_id == "concept-02" for error in exc.value.errors)


def test_duplicate_ids_fail_even_when_questions_differ(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    first = record(commit)
    second = record(commit)
    second["question"] = "Which implementation defines answer?"
    path = write_dataset(tmp_path, [first, second])
    assert "duplicate_id" in codes(validate_benchmark(path, repository, commit))


def test_unreviewed_records_require_explicit_authoring_audit(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    question = record(commit)
    question["provenance"]["review"] = None
    path = write_dataset(tmp_path, [question])
    assert "missing_independent_review" in codes(validate_benchmark(path, repository, commit))
    audit = validate_benchmark(path, repository, commit, require_reviewed=False)
    assert audit.valid
    assert {warning.code for warning in audit.warnings} == {"review_not_required"}
    assert audit.require_reviewed is False


@pytest.mark.parametrize("change", ["same_author", "review_before_authoring", "naive_timestamp"])
def test_invalid_review_provenance_is_rejected(benchmark_repo, tmp_path, change):
    repository, commit = benchmark_repo
    question = record(commit)
    review = question["provenance"]["review"]
    if change == "same_author":
        review["reviewer"] = " fixture AUTHOR "
    elif change == "review_before_authoring":
        review["reviewed_at"] = "2025-12-31T12:00:00Z"
    else:
        review["reviewed_at"] = "2026-01-02T12:00:00"
    report = validate_benchmark(write_dataset(tmp_path, [question]), repository, commit)
    assert not report.valid
    assert codes(report) & {"invalid_question", "non_independent_review", "review_before_authoring"}


def test_expected_commit_and_question_commit_are_both_verified(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    wrong_commit = "0" * 40
    path = write_dataset(tmp_path, [record(wrong_commit)])
    assert "question_commit_mismatch" in codes(validate_benchmark(path, repository, commit))
    report = validate_benchmark(path, repository, wrong_commit)
    assert "snapshot_verification_failed" in codes(report)


@pytest.mark.parametrize(
    "change, expected",
    [
        ("hash", "evidence_hash_mismatch"),
        ("range", "evidence_line_range"),
        ("missing", "ineligible_evidence_file"),
        ("traversal", "invalid_question"),
    ],
)
def test_invalid_evidence_is_rejected(benchmark_repo, tmp_path, change, expected):
    repository, commit = benchmark_repo
    question = record(commit)
    evidence = question["evidence"][0]
    if change == "hash":
        evidence["excerpt_sha256"] = "0" * 64
    elif change == "range":
        evidence["end_line"] = 4
    elif change == "missing":
        evidence["path"] = "src/missing.py"
    else:
        evidence["path"] = "../outside.py"
    path = write_dataset(tmp_path, [question])
    assert expected in codes(validate_benchmark(path, repository, commit))


def test_excerpt_hash_does_not_include_trailing_newline(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    question = record(commit)
    question["evidence"][0].update(
        start_line=3,
        end_line=3,
        excerpt_sha256=hashlib.sha256(b"    return 42\n").hexdigest(),
    )
    path = write_dataset(tmp_path, [question])
    assert "evidence_hash_mismatch" in codes(validate_benchmark(path, repository, commit))


def test_policy_exclusions_also_apply_to_benchmark_evidence(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    question = record(commit)
    question["evidence"][0].update(
        path="excluded.py",
        start_line=1,
        end_line=1,
        excerpt_sha256=hashlib.sha256(b"generated = True").hexdigest(),
    )
    path = write_dataset(tmp_path, [question])
    policy = DiscoveryPolicy(exclude_globs=("excluded.py",))
    assert "ineligible_evidence_file" in codes(
        validate_benchmark(path, repository, commit, policy=policy)
    )


def test_symlink_evidence_is_not_eligible(benchmark_repo, tmp_path):
    repository, _ = benchmark_repo
    (repository / "link.py").symlink_to("src/example.py")
    git(repository, "add", "link.py")
    git(repository, "commit", "--quiet", "-m", "Fixture symlink")
    commit = git(repository, "rev-parse", "HEAD")
    question = record(commit)
    question["evidence"][0]["path"] = "link.py"
    path = write_dataset(tmp_path, [question])
    assert "ineligible_evidence_file" in codes(validate_benchmark(path, repository, commit))


def test_dirty_repository_cannot_produce_a_valid_report(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    path = write_dataset(tmp_path, [record(commit)])
    (repository / "src" / "example.py").write_text("return 43\n", encoding="utf-8")
    assert "snapshot_verification_failed" in codes(validate_benchmark(path, repository, commit))


def pilot_records(commit: str) -> list[dict]:
    records = []
    for category in ("conceptual", "structural", "cross_file"):
        for number in range(10):
            question = record(commit, identifier=f"{category}-{number:02d}")
            question["question"] = f"Fixture {category} question {number}?"
            question["category"] = category
            question["split"] = "development" if number < 5 else "held_out"
            records.append(question)
    return records


def test_pilot_requires_30_questions_balanced_categories_and_splits(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    questions = pilot_records(commit)
    path = write_dataset(tmp_path, questions)
    assert validate_benchmark(path, repository, commit, pilot=True).valid
    questions.pop()
    path = write_dataset(tmp_path, questions)
    report = validate_benchmark(path, repository, commit, pilot=True)
    assert {"pilot_question_count", "pilot_category_count"} <= codes(report)


def test_pilot_requires_each_category_in_each_split(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    questions = pilot_records(commit)
    for question in questions:
        if question["category"] == "structural":
            question["split"] = "development"
    report = validate_benchmark(write_dataset(tmp_path, questions), repository, commit, pilot=True)
    assert "pilot_missing_split" in codes(report)


def test_pilot_requires_five_questions_per_category_per_split(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    questions = pilot_records(commit)
    questions[4]["split"] = "held_out"
    report = validate_benchmark(write_dataset(tmp_path, questions), repository, commit, pilot=True)
    assert report.category_counts["conceptual"] == 10
    assert report.question_count == 30
    assert "pilot_split_balance" in codes(report)


def test_missing_dataset_is_reported_without_exception(benchmark_repo, tmp_path):
    repository, commit = benchmark_repo
    path = tmp_path / "missing.jsonl"
    report = validate_benchmark(path, repository, commit)
    assert not report.valid
    assert report.dataset_sha256 is None
    assert "dataset_read_error" in codes(report)
    with pytest.raises(BenchmarkLoadError):
        load_benchmark(path)


def test_schema_export_is_authoring_schema(tmp_path):
    destination = tmp_path / "question.schema.json"
    export_benchmark_schema(destination)
    schema = json.loads(destination.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert {"question", "evidence", "repo_commit", "split", "provenance"} <= set(schema["required"])

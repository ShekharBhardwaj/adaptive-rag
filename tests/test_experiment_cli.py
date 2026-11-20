"""Offline CLI boundaries using explicitly synthetic frozen experiment records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from adaptive_rag.cli import main
from adaptive_rag.config import FoundationConfig
from adaptive_rag.evaluation.experiment_models import ExperimentRecord, question_sha256
from adaptive_rag.evaluation.reviews import output_sha256
from adaptive_rag.evaluation.runner import _canonical
from adaptive_rag.evaluation.storage import RunStore
from adaptive_rag.models import BenchmarkQuestion


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "repository:\n"
        "  url: https://fixture.invalid/source.git\n"
        "  path: source\n"
        f"  commit_sha: {'f' * 40}\n"
        "experiment:\n"
        "  dataset: synthetic.jsonl\n"
        "  conditions: [no_retrieval]\n"
        "  repetitions: 2\n"
        "  require_pilot: false\n"
    )
    return path


def synthetic_question():
    return BenchmarkQuestion.model_validate(
        {
            "id": "synthetic-question",
            "question": "What value does the synthetic fixture return?",
            "category": "conceptual",
            "ground_truth_answer": "It returns the synthetic fixture value.",
            "evidence": [
                {
                    "path": "source.py",
                    "start_line": 1,
                    "end_line": 1,
                    "excerpt_sha256": hashlib.sha256(b"value = 'fixture'").hexdigest(),
                }
            ],
            "repo_commit": "f" * 40,
            "provenance": {
                "author": "Synthetic Fixture Author",
                "created_at": "2026-11-01T12:00:00Z",
                "method": "source_inspection",
                "notes": "Schema fixture only; not an actual research benchmark.",
                "review": {
                    "reviewer": "Synthetic Fixture Reviewer",
                    "reviewed_at": "2026-11-02T12:00:00Z",
                    "method": "source_inspection",
                    "notes": "Synthetic validation fixture; no actual human review claim.",
                },
            },
            "difficulty": "easy",
            "split": "development",
        }
    )


@pytest.fixture
def frozen_run(tmp_path):
    directory = tmp_path / "synthetic-run"
    question = synthetic_question()
    benchmark = (question.model_dump_json() + "\n").encode()
    configuration = FoundationConfig.model_validate(
        {
            "repository": {
                "url": "https://fixture.invalid/source.git",
                "path": str(tmp_path / "source"),
                "commit_sha": "f" * 40,
            },
            "experiment": {
                "dataset": str(tmp_path / "synthetic.jsonl"),
                "conditions": ["no_retrieval"],
                "repetitions": 2,
                "require_pilot": False,
            },
        }
    ).model_dump(mode="json")
    records = tuple(
        ExperimentRecord(
            run_id="synthetic-run",
            job_id=identifier * 64,
            question_id=question.id,
            question_sha256=question_sha256(question),
            category=question.category,
            split=question.split,
            condition="no_retrieval",
            repetition=repetition,
            status="completed",
            created_at=datetime(2026, 11, 3, tzinfo=UTC),
            answer={"status": "completed", "answer": f"Synthetic output {repetition}"},
        )
        for repetition, identifier in enumerate(("a", "b"))
    )
    manifest = {
        "schema_version": "1",
        "run_id": "synthetic-run",
        "benchmark_sha256": hashlib.sha256(benchmark).hexdigest(),
        "configuration_sha256": hashlib.sha256(_canonical(configuration)).hexdigest(),
        "planned_jobs": [
            {
                "job_id": record.job_id,
                "question_id": question.id,
                "condition": record.condition,
                "repetition": record.repetition,
            }
            for record in records
        ],
        "question_hashes": {question.id: question_sha256(question)},
        "question_count": 1,
        "split": question.split,
    }
    with RunStore(directory, manifest) as store:
        store.write_artifact("benchmark.jsonl", benchmark)
        store.write_artifact("configuration.json", configuration)
        for record in records:
            store.record(record)
        store.finish("completed")
    return SimpleNamespace(path=directory, records=records, question=question, manifest=manifest)


def rewrite_records(run, rows):
    (run.path / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )


def test_plan_uses_frozen_preparation_without_api_admission(
    config_path, tmp_path, monkeypatch, capsys
):
    calls = []

    def prepare(config):
        calls.append(config)
        return SimpleNamespace(manifest={"run_id": "synthetic-plan", "planned_jobs": []})

    monkeypatch.setattr("adaptive_rag.evaluation.runner.prepare_experiment", prepare)
    assert main(["experiment", "plan", "--config", str(config_path)]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "synthetic-plan"
    assert len(calls) == 1
    target = tmp_path / "plan.json"
    assert main(["experiment", "plan", "--config", str(config_path), "--output", str(target)]) == 0
    assert json.loads(target.read_text())["planned_jobs"] == []


def test_run_requires_explicit_api_admission_before_preparation(
    config_path, tmp_path, monkeypatch, capsys
):
    def unexpected(*_args, **_kwargs):
        pytest.fail("denied execution must not prepare or call a model")

    monkeypatch.setattr("adaptive_rag.evaluation.runner.prepare_experiment", unexpected)
    output = tmp_path / "denied"
    assert main(["experiment", "run", "--config", str(config_path), "--output", str(output)]) == 2
    assert "--allow-api" in json.loads(capsys.readouterr().err)["error"]
    assert not output.exists()


@pytest.mark.parametrize(
    "status,code",
    [
        ("completed", 0),
        ("completed_with_errors", 2),
        ("budget_exhausted", 2),
        ("interrupted", 130),
    ],
)
def test_run_passes_opt_in_and_preserves_execution_exit_status(
    config_path, tmp_path, monkeypatch, capsys, status, code
):
    calls = []

    def run(config, output, *, allow_api):
        calls.append((config, output, allow_api))
        return {"status": status, "run_id": "synthetic-adapter-fixture"}

    monkeypatch.setattr("adaptive_rag.evaluation.runner.run_experiment", run)
    output = tmp_path / "adapter-result"
    assert (
        main(
            [
                "experiment",
                "run",
                "--config",
                str(config_path),
                "--output",
                str(output),
                "--allow-api",
            ]
        )
        == code
    )
    assert calls[0][2] is True and calls[0][1] == output
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_plan_and_run_output_guards_precede_preparation(config_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "adaptive_rag.evaluation.runner.prepare_experiment",
        lambda *_args, **_kwargs: pytest.fail("invalid output must fail before preparation"),
    )
    existing = tmp_path / "existing"
    existing.mkdir()
    for command in ("plan", "run"):
        assert (
            main(["experiment", command, "--config", str(config_path), "--output", str(existing)])
            == 2
        )
        assert "exists" in json.loads(capsys.readouterr().err)["error"]
        inside = tmp_path / "source" / f"{command}.json"
        assert (
            main(["experiment", command, "--config", str(config_path), "--output", str(inside)])
            == 2
        )
        assert "outside" in json.loads(capsys.readouterr().err)["error"]
        assert not inside.exists()


def test_review_template_is_blinded_and_bound_to_frozen_outputs(frozen_run, tmp_path, capsys):
    target = tmp_path / "review-items.jsonl"
    assert (
        main(
            [
                "experiment",
                "review-template",
                str(frozen_run.path),
                "--output",
                str(target),
                "--seed",
                "42",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["review_items"] == 2 and report["run_partial"] is False
    items = [json.loads(line) for line in target.read_text().splitlines()]
    assert {item["generated_answer"] for item in items} == {
        "Synthetic output 0",
        "Synthetic output 1",
    }
    for item in items:
        assert not {"condition", "category", "repetition", "status"}.intersection(item)
        assert item["reference_answer"] == frozen_run.question.ground_truth_answer
        assert item["score"]["correctness"] is None and item["score"]["reviewer"] is None
        assert item["score"]["output_sha256"] in {
            output_sha256(record) for record in frozen_run.records
        }


def test_summary_keeps_correctness_pending_without_independent_reviews(
    frozen_run, tmp_path, capsys
):
    target = tmp_path / "summary.json"
    assert (
        main(
            [
                "experiment",
                "summarize",
                str(frozen_run.path),
                "--output",
                str(target),
                "--bootstrap-samples",
                "25",
            ]
        )
        == 0
    )
    summary = json.loads(target.read_text())
    assert summary["observed"] == summary["planned"] == 2 and summary["missing"] == 0
    assert summary["raw_run_partial"] is False and summary["raw_load_issues"] == []
    condition = summary["conditions"]["no_retrieval"]
    assert condition["failure_aware_correctness"]["mean"] is None
    assert condition["pending_completed_reviews"] == 2
    assert json.loads(capsys.readouterr().out)["status"] == "written"


def test_summary_accepts_explicit_synthetic_scores_bound_to_exact_outputs(
    frozen_run, tmp_path, capsys
):
    reviews = tmp_path / "synthetic-scores.jsonl"
    reviews.write_text(
        "".join(
            json.dumps(
                {
                    "run_id": record.run_id,
                    "job_id": record.job_id,
                    "output_sha256": output_sha256(record),
                    "reviewer": "Synthetic Test Reviewer",
                    "reviewed_at": "2026-11-04T00:00:00Z",
                    "correctness": 1.0,
                    "citation_support": None,
                    "notes": "Synthetic scoring fixture; no research result.",
                }
            )
            + "\n"
            for record in frozen_run.records
        )
    )
    target = tmp_path / "reviewed-summary.json"
    assert (
        main(
            [
                "experiment",
                "summarize",
                str(frozen_run.path),
                "--reviews",
                str(reviews),
                "--output",
                str(target),
            ]
        )
        == 0
    )
    condition = json.loads(target.read_text())["conditions"]["no_retrieval"]
    assert condition["reviewed_completed"] == 2
    assert condition["failure_aware_correctness"]["mean"] == 1.0
    capsys.readouterr()


def test_partial_run_summary_keeps_missing_jobs_and_load_issues(frozen_run, tmp_path, capsys):
    rewrite_records(frozen_run, [frozen_run.records[0].model_dump(mode="json")])
    with (frozen_run.path / "results.jsonl").open("ab") as stream:
        stream.write(b'{"interrupted":')
    target = tmp_path / "partial-summary.json"
    assert main(["experiment", "summarize", str(frozen_run.path), "--output", str(target)]) == 0
    summary = json.loads(target.read_text())
    assert summary["raw_run_partial"] is True
    assert summary["observed"] == 1 and summary["missing"] == 1
    assert any("valid prefix" in issue for issue in summary["raw_load_issues"])
    condition = summary["conditions"]["no_retrieval"]
    assert condition["completion_rate"] == 0.5
    assert condition["failure_aware_correctness"]["mean"] is None
    capsys.readouterr()


@pytest.mark.parametrize("command", ["summarize", "review-template"])
def test_derived_artifacts_never_modify_raw_run_or_existing_output(
    frozen_run, tmp_path, capsys, command
):
    inside = frozen_run.path / "new-artifact.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(inside)]) == 2
    assert "outside" in json.loads(capsys.readouterr().err)["error"]
    assert not inside.exists()
    existing = tmp_path / "existing.txt"
    existing.write_text("keep original")
    assert main(["experiment", command, str(frozen_run.path), "--output", str(existing)]) == 2
    assert "exists" in json.loads(capsys.readouterr().err)["error"]
    assert existing.read_text() == "keep original"


@pytest.mark.parametrize(
    "artifact,message",
    [
        ("benchmark.jsonl", "benchmark checksum"),
        ("configuration.json", "configuration checksum"),
    ],
)
@pytest.mark.parametrize("command", ["summarize", "review-template"])
def test_frozen_input_checksum_tampering_is_rejected(
    frozen_run, tmp_path, capsys, artifact, message, command
):
    path = frozen_run.path / artifact
    if artifact == "benchmark.jsonl":
        question = frozen_run.question.model_copy(update={"ground_truth_answer": "changed"})
        path.write_text(question.model_dump_json() + "\n")
    else:
        path.write_text('{"changed": true}\n')
    target = tmp_path / "must-not-exist.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert message in json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


@pytest.mark.parametrize("command", ["summarize", "review-template"])
def test_record_annotation_hash_tampering_is_rejected(frozen_run, tmp_path, capsys, command):
    row = frozen_run.records[0].model_dump(mode="json")
    row["question_sha256"] = "c" * 64
    rewrite_records(frozen_run, [row])
    target = tmp_path / "must-not-exist.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert "different benchmark" in json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


def test_experiment_help_lists_current_commands(capsys):
    with pytest.raises(SystemExit) as result:
        main(["experiment", "--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert all(command in help_text for command in ("plan", "run", "summarize", "review-template"))


@pytest.mark.parametrize("command", ["summarize", "review-template"])
@pytest.mark.parametrize(
    "changes",
    [
        {"run_id": "different-run"},
        {"job_id": "c" * 64},
        {"repetition": 99},
        {"condition": "vectorless", "status": "error"},
        {"category": "structural"},
        {"split": "held_out"},
    ],
)
def test_offline_commands_reject_rows_outside_the_frozen_job_or_annotation(
    frozen_run, tmp_path, capsys, command, changes
):
    row = frozen_run.records[0].model_dump(mode="json")
    row.update(changes)
    rewrite_records(frozen_run, [row])
    target = tmp_path / "must-not-exist.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


@pytest.mark.parametrize("command", ["summarize", "review-template"])
@pytest.mark.parametrize("mutation", ["missing", "invalid_job", "duplicate_identity"])
def test_offline_commands_reject_malformed_or_ambiguous_job_plans(
    frozen_run, tmp_path, capsys, command, mutation
):
    path = frozen_run.path / "manifest.json"
    manifest = json.loads(path.read_text())
    if mutation == "missing":
        del manifest["planned_jobs"]
    elif mutation == "invalid_job":
        manifest["planned_jobs"][0]["repetition"] = True
    else:
        duplicate = dict(manifest["planned_jobs"][0], job_id="c" * 64)
        manifest["planned_jobs"].append(duplicate)
    path.write_text(json.dumps(manifest))
    target = tmp_path / "must-not-exist.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


@pytest.mark.parametrize("command", ["summarize", "review-template"])
def test_derived_artifact_symlink_alias_cannot_write_inside_raw_run(
    frozen_run, tmp_path, capsys, command
):
    alias = tmp_path / "raw-alias"
    alias.symlink_to(frozen_run.path, target_is_directory=True)
    target = alias / "derived.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert "outside" in json.loads(capsys.readouterr().err)["error"]
    assert not (frozen_run.path / "derived.json").exists()


def test_stale_manual_output_score_is_rejected(frozen_run, tmp_path, capsys):
    record = frozen_run.records[0]
    reviews = tmp_path / "stale-score.jsonl"
    reviews.write_text(
        json.dumps(
            {
                "run_id": record.run_id,
                "job_id": record.job_id,
                "output_sha256": "0" * 64,
                "reviewer": "Synthetic Test Reviewer",
                "reviewed_at": "2026-11-04T00:00:00Z",
                "correctness": 1.0,
                "notes": "Synthetic stale-output rejection fixture.",
            }
        )
        + "\n"
    )
    target = tmp_path / "must-not-exist.json"
    assert (
        main(
            [
                "experiment",
                "summarize",
                str(frozen_run.path),
                "--reviews",
                str(reviews),
                "--output",
                str(target),
            ]
        )
        == 2
    )
    assert "stale" in json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


@pytest.mark.parametrize("command", ["summarize", "review-template"])
def test_frozen_plan_cannot_shrink_the_repetition_denominator(
    frozen_run, tmp_path, capsys, command
):
    path = frozen_run.path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["planned_jobs"] = manifest["planned_jobs"][:1]
    path.write_text(json.dumps(manifest))
    rewrite_records(frozen_run, [frozen_run.records[0].model_dump(mode="json")])
    target = tmp_path / "must-not-exist.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert "cover" in json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()


@pytest.mark.parametrize("command", ["summarize", "review-template"])
def test_manifest_question_bindings_cannot_disagree_with_frozen_benchmark(
    frozen_run, tmp_path, capsys, command
):
    path = frozen_run.path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["question_hashes"][frozen_run.question.id] = "c" * 64
    path.write_text(json.dumps(manifest))
    target = tmp_path / "must-not-exist.json"
    assert main(["experiment", command, str(frozen_run.path), "--output", str(target)]) == 2
    assert "question hashes" in json.loads(capsys.readouterr().err)["error"]
    assert not target.exists()

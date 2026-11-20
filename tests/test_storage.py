from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from adaptive_rag.evaluation.experiment_models import ExperimentRecord
from adaptive_rag.evaluation.storage import RunStore, capture_environment, load_run


def record(**changes):
    return ExperimentRecord.model_validate(
        {
            "run_id": "fixture-run",
            "job_id": "a" * 64,
            "question_id": "fixture-question",
            "question_sha256": "b" * 64,
            "category": "conceptual",
            "split": "development",
            "condition": "no_retrieval",
            "repetition": 0,
            "status": "completed",
            "answer": {"status": "completed", "answer": "Synthetic fixture output"},
            **changes,
        }
    )


def manifest(**changes):
    return {
        "run_id": "fixture-run",
        "planned_jobs": [
            {
                "job_id": "a" * 64,
                "question_id": "fixture-question",
                "condition": "no_retrieval",
                "repetition": 0,
            }
        ],
        **changes,
    }


def complete_run(path: Path, *records, plan=None):
    with RunStore(path, manifest() if plan is None else plan) as store:
        store.event({"kind": "started"})
        for item in records:
            store.record(item)
        store.finish("completed")


def test_new_only_durable_roundtrip_and_artifacts(tmp_path, monkeypatch):
    path = tmp_path / "run"
    fsync = os.fsync
    synchronized = []

    def sync(descriptor):
        synchronized.append(descriptor)
        return fsync(descriptor)

    monkeypatch.setattr(os, "fsync", sync)
    original = manifest()
    store = RunStore(path, original)
    original["run_id"] = "mutated after construction"
    with store:
        before = len(synchronized)
        store.event({"kind": "started", "note": "café"})
        store.record(record())
        assert len(synchronized) == before + 2
        store.write_artifact("inputs/config.yaml", b"value: 1\n")
        store.write_artifact("inputs/identity.json", {"sha": "fixture"})
        store.finish("completed", completed_jobs=1)
    loaded = load_run(path)
    assert not loaded.partial and loaded.issues == ()
    assert loaded.manifest["run_id"] == "fixture-run"
    assert loaded.records[0].job_id == "a" * 64
    assert loaded.events[0]["note"] == "café"
    assert loaded.status["records_written"] == loaded.status["events_written"] == 1
    assert (path / "inputs/config.yaml").read_bytes() == b"value: 1\n"
    assert json.loads((path / "inputs/identity.json").read_text()) == {"sha": "fixture"}


def test_existing_directory_is_never_resumed_or_overwritten(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record())
    before = {item.name: item.read_bytes() for item in path.iterdir()}
    with pytest.raises(FileExistsError):
        with RunStore(path, {"different": "manifest"}):
            pass
    assert {item.name: item.read_bytes() for item in path.iterdir()} == before


def test_failure_preserves_raw_records_and_final_status(tmp_path):
    path = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with RunStore(path, manifest()) as store:
            store.record(record())
            raise RuntimeError("synthetic failure")
    loaded = load_run(path)
    assert loaded.partial and len(loaded.records) == 1
    assert loaded.status["status"] == "failed"
    assert loaded.status["error"] == "synthetic failure"
    assert loaded.status["records_written"] == 1


def test_normal_exit_without_finish_and_keyboard_interrupt_are_explicit(tmp_path):
    path = tmp_path / "unfinished"
    with RunStore(path, manifest()) as store:
        store.record(record())
    assert load_run(path).status["status"] == "interrupted"
    interrupted = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        with RunStore(interrupted, manifest()) as store:
            store.event({"kind": "started"})
            raise KeyboardInterrupt()
    loaded = load_run(interrupted)
    assert loaded.partial and loaded.status["status"] == "interrupted"
    assert len(loaded.events) == 1


def test_store_refuses_changes_after_finish_and_outside_context(tmp_path):
    store = RunStore(tmp_path / "run", manifest())
    with pytest.raises(RuntimeError):
        store.record(record())
    with store:
        store.finish("completed")
        for operation in (
            lambda: store.event({}),
            lambda: store.record(record()),
            lambda: store.finish("failed"),
            lambda: store.write_artifact("late.json", {}),
        ):
            with pytest.raises(RuntimeError):
                operation()
    with pytest.raises(RuntimeError):
        with store:
            pass


@pytest.mark.parametrize("name", ["../outside", "/tmp/outside", "a/../outside", "a\\b", "a//b"])
def test_artifacts_are_canonical_children_only(tmp_path, name):
    with RunStore(tmp_path / "run", {}) as store:
        with pytest.raises(ValueError):
            store.write_artifact(name, b"invalid")
        store.finish("completed")


def test_artifacts_and_symlink_paths_are_never_overwritten(tmp_path):
    path = tmp_path / "run"
    outside = tmp_path / "outside"
    outside.mkdir()
    with RunStore(path, {}) as store:
        store.write_artifact("same.json", {"original": True})
        with pytest.raises(FileExistsError):
            store.write_artifact("same.json", {"original": False})
        with pytest.raises(FileExistsError):
            store.write_artifact("manifest.json", {})
        (path / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError, match="symlinks"):
            store.write_artifact("link/new.json", {})
        (path / "target").symlink_to(outside / "missing")
        with pytest.raises(ValueError, match="symlinks"):
            store.write_artifact("target", b"invalid")
        store.finish("completed")
    assert not list(outside.iterdir())


def test_nonfinite_values_fail_before_append_without_poisoning_jsonl(tmp_path):
    path = tmp_path / "run"
    with RunStore(path, {}) as store:
        with pytest.raises(ValueError):
            store.event({"cost": float("nan")})
        with pytest.raises(ValueError):
            store.record({"cost": float("inf")})
        assert (path / "events.jsonl").read_bytes() == b""
        assert (path / "results.jsonl").read_bytes() == b""
        store.finish("completed")


def test_loader_retains_valid_prefix_and_reports_truncated_tail(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record())
    with (path / "results.jsonl").open("ab") as stream:
        stream.write(b'{"job_id": "truncated')
    (path / "status.json").unlink()
    loaded = load_run(path)
    assert loaded.partial and len(loaded.records) == 1
    assert any("results.jsonl:2" in issue and "valid prefix" in issue for issue in loaded.issues)
    assert any("interrupted" in issue for issue in loaded.issues)


def test_complete_unterminated_json_line_is_retained_but_partial(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record())
    results = path / "results.jsonl"
    results.write_bytes(results.read_bytes().rstrip(b"\n"))
    loaded = load_run(path)
    assert len(loaded.records) == 1 and loaded.partial
    assert any("unterminated" in issue for issue in loaded.issues)


def test_schema_invalid_records_and_nonobject_events_are_explicit(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record())
    with (path / "results.jsonl").open("ab") as stream:
        stream.write(b'{"not": "an experiment record"}\n')
        stream.write(record(job_id="c" * 64).model_dump_json().encode() + b"\n")
    with (path / "events.jsonl").open("ab") as stream:
        stream.write(b"[]\n")
    loaded = load_run(path)
    assert len(loaded.records) == 1 and len(loaded.events) == 1
    assert loaded.partial
    assert any("results.jsonl:2" in issue for issue in loaded.issues)
    assert any("events.jsonl:2" in issue for issue in loaded.issues)


def test_duplicates_are_retained_and_conflicts_unknown_jobs_reported(tmp_path):
    path = tmp_path / "run"
    first = record()
    complete_run(
        path, first, first, first.model_copy(update={"status": "error"}), record(job_id="c" * 64)
    )
    loaded = load_run(path)
    assert len(loaded.records) == 4 and loaded.partial
    assert any("conflicting duplicate" in issue for issue in loaded.issues)
    assert any("duplicate job_id" in issue for issue in loaded.issues)
    assert any("unknown job_id" in issue for issue in loaded.issues)


def test_plan_membership_run_identity_and_counts_are_checked(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record(run_id="another-run"))
    status = json.loads((path / "status.json").read_text())
    status["records_written"] = 99
    (path / "status.json").write_text(json.dumps(status))
    loaded = load_run(path)
    assert loaded.partial
    assert any("different run_id" in issue for issue in loaded.issues)
    assert any("contradicts" in issue for issue in loaded.issues)
    missing = tmp_path / "missing"
    complete_run(missing)
    assert any("planned jobs have no valid record" in issue for issue in load_run(missing).issues)
    duplicate_plan = manifest()
    duplicate_plan["planned_jobs"] *= 2
    duplicated = tmp_path / "duplicated"
    complete_run(duplicated, record(), plan=duplicate_plan)
    assert any("duplicate planned" in issue for issue in load_run(duplicated).issues)


def test_manifest_errors_duplicate_json_keys_and_invalid_utf8_are_explicit(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record())
    (path / "manifest.json").write_bytes(b'{"run_id":"a","run_id":"b"}')
    with (path / "events.jsonl").open("ab") as stream:
        stream.write(b"\xff\n")
    loaded = load_run(path)
    assert loaded.manifest == {} and loaded.partial
    assert any("duplicate JSON object key" in issue for issue in loaded.issues)
    assert any("events.jsonl:2" in issue for issue in loaded.issues)


def test_loader_rejects_run_and_artifact_symlinks(tmp_path):
    path = tmp_path / "run"
    complete_run(path, record())
    alias = tmp_path / "alias"
    alias.symlink_to(path, target_is_directory=True)
    with pytest.raises(ValueError):
        load_run(alias)
    (path / "results.jsonl").unlink()
    (path / "results.jsonl").symlink_to(path / "events.jsonl")
    loaded = load_run(path)
    assert loaded.partial and loaded.records == ()
    assert any("symlink" in issue for issue in loaded.issues)


def test_environment_records_reproducibility_without_credentials():
    environment = capture_environment()
    assert len(environment["framework_source_sha256"]) == 64
    assert environment["python"] and environment["platform"]
    assert environment["dependencies"]["pydantic"]
    assert "api_key" not in json.dumps(environment).lower()

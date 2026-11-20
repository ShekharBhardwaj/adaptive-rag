from pathlib import Path

import pytest

from adaptive_rag.config import ConfigurationError, load_config


def write_config(tmp_path: Path, text: str) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(text, encoding="utf-8")
    return config


def valid_config() -> str:
    return (
        "repository:\n  url: https://example.org/repo.git\n  path: repo\n  commit_sha: "
        + "a" * 40
        + "\n"
    )


def test_paths_are_config_relative_not_cwd(tmp_path, monkeypatch):
    path = write_config(tmp_path, valid_config())
    monkeypatch.chdir(tmp_path.parent)
    assert load_config(path).repository.path == tmp_path / "repo"


@pytest.mark.parametrize(
    "suffix", ["unknown: true\n", "files:\n  max_file_bytes: 0\n", "files:\n  typo: true\n"]
)
def test_reject_unknown_settings_and_invalid_limits(tmp_path, suffix):
    with pytest.raises(ConfigurationError):
        load_config(write_config(tmp_path, valid_config() + suffix))


def test_reject_duplicate_keys_and_moving_refs(tmp_path):
    with pytest.raises(ConfigurationError, match="duplicate"):
        load_config(write_config(tmp_path, valid_config() + "files: {}\nfiles: {}\n"))
    with pytest.raises(ConfigurationError):
        load_config(write_config(tmp_path, valid_config().replace("a" * 40, "main")))


def test_reject_unsafe_yaml_empty_and_missing(tmp_path):
    for content in ["", "[]", "!!python/object/apply:os.system ['echo forbidden']", "key: ["]:
        with pytest.raises(ConfigurationError):
            load_config(write_config(tmp_path, content))
    with pytest.raises(ConfigurationError):
        load_config(tmp_path / "absent.yaml")

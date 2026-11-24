import os
from pathlib import Path

import pytest

from argus import config
from argus.config import find_env_file, load_config

NEW_VARS = (
    "ARGUS_WHISPER_MODEL",
    "ARGUS_ELEVEN_MODEL",
    "ARGUS_RENDER_CONCURRENCY",
    "ARGUS_SCRIPTS_DIR",
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Empty cwd and repo root, no ARGUS_ variables from the developer's machine."""
    cwd = tmp_path / "cwd"
    repo = tmp_path / "repo"
    cwd.mkdir()
    repo.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(config, "REPO_ROOT", repo)
    monkeypatch.delenv("ARGUS_ENV_FILE", raising=False)
    for name in NEW_VARS:
        monkeypatch.delenv(name, raising=False)
    return cwd, repo


def test_env_lookup_prefers_explicit_file(isolated, monkeypatch, tmp_path):
    cwd, repo = isolated
    explicit = tmp_path / "custom.env"
    explicit.write_text("X=1\n", encoding="utf-8")
    (cwd / ".env").write_text("X=2\n", encoding="utf-8")
    (repo / ".env").write_text("X=3\n", encoding="utf-8")
    monkeypatch.setenv("ARGUS_ENV_FILE", str(explicit))

    assert find_env_file() == explicit.resolve()


def test_missing_explicit_file_falls_through_to_cwd(isolated, monkeypatch, tmp_path):
    cwd, repo = isolated
    (cwd / ".env").write_text("X=2\n", encoding="utf-8")
    monkeypatch.setenv("ARGUS_ENV_FILE", str(tmp_path / "missing.env"))

    assert find_env_file() == (cwd / ".env").resolve()


def test_cwd_env_beats_repo_env(isolated):
    cwd, repo = isolated
    (cwd / ".env").write_text("X=2\n", encoding="utf-8")
    (repo / ".env").write_text("X=3\n", encoding="utf-8")

    assert find_env_file() == (cwd / ".env").resolve()


def test_repo_env_is_used_when_cwd_has_none(isolated):
    cwd, repo = isolated
    (repo / ".env").write_text("X=3\n", encoding="utf-8")

    assert find_env_file() == (repo / ".env").resolve()


def test_no_env_file_returns_none(isolated):
    assert find_env_file() is None


def test_dotenv_values_do_not_override_real_environment(isolated, monkeypatch):
    cwd, _ = isolated
    key = "ARGUS_TEST_PRECEDENCE_KEY"
    monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(key, "from-process")
    (cwd / ".env").write_text(f"{key}=from-file\n", encoding="utf-8")

    config._load_dotenv()

    assert os.environ[key] == "from-process"


def test_dotenv_values_load_from_repo_root(isolated, monkeypatch):
    _, repo = isolated
    key = "ARGUS_TEST_REPO_FALLBACK_KEY"
    monkeypatch.delenv(key, raising=False)
    (repo / ".env").write_text(f"{key}=from-repo\n", encoding="utf-8")

    config._load_dotenv()

    assert os.environ[key] == "from-repo"


def test_new_fields_have_documented_defaults(isolated, monkeypatch):
    for name in ("ARGUS_ELEVEN_MODEL", "ARGUS_TTS_MODEL"):
        monkeypatch.delenv(name, raising=False)  # a pinned id in the user's .env is loaded into os.environ
    cfg = load_config()

    assert cfg.whisper_model == "small"
    assert cfg.eleven_model == ""  # empty: the newest model the key lists is used
    assert cfg.tts_model == ""
    assert cfg.render_concurrency == 0
    assert cfg.scripts_dir == Path.home() / ".argus" / "scripts"


def test_new_fields_read_from_environment(isolated, monkeypatch, tmp_path):
    monkeypatch.setenv("ARGUS_WHISPER_MODEL", "medium")
    monkeypatch.setenv("ARGUS_ELEVEN_MODEL", "eleven_multilingual_v2")
    monkeypatch.setenv("ARGUS_RENDER_CONCURRENCY", "4")
    monkeypatch.setenv("ARGUS_SCRIPTS_DIR", str(tmp_path / "scripts"))

    cfg = load_config()

    assert cfg.whisper_model == "medium"
    assert cfg.eleven_model == "eleven_multilingual_v2"
    assert cfg.render_concurrency == 4
    assert cfg.scripts_dir == (tmp_path / "scripts").resolve()


def test_negative_render_concurrency_is_rejected(isolated, monkeypatch):
    monkeypatch.setenv("ARGUS_RENDER_CONCURRENCY", "-1")

    with pytest.raises(ValueError, match="ARGUS_RENDER_CONCURRENCY"):
        load_config()


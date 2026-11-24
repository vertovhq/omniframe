"""omniframe-install writes only the omniframe entry, into temporary homes only."""

import json
from pathlib import Path

import sys

import pytest

from omniframe import install
from omniframe.install import local_server, main

ARGS = ["--from", "git+https://github.com/vertovhq/omniframe", "omniframe"]


@pytest.fixture(autouse=True)
def _no_local_script(monkeypatch):
    """Most tests check the uvx fallback; the local-script tests below call local_server directly."""
    monkeypatch.setattr(install, "local_server", lambda: None)


def test_local_script_is_used_when_present(tmp_path):
    name = "omniframe.exe" if sys.platform == "win32" else "omniframe"
    (tmp_path / name).write_text("", encoding="utf-8")
    command, args = local_server(tmp_path)
    assert Path(command) == (tmp_path / name).resolve()
    assert args == []


def test_no_local_script_falls_back_to_uvx(tmp_path):
    assert local_server(tmp_path) is None


def test_main_writes_the_local_script(tmp_path, monkeypatch):
    script = str(tmp_path / "venv" / "omniframe.exe")
    monkeypatch.setattr(install, "local_server", lambda: (script, []))
    (tmp_path / ".cursor").mkdir()
    assert main(["--client", "cursor"], home=tmp_path, env={}) == 0
    entry = _read(tmp_path / ".cursor" / "mcp.json")["mcpServers"]["omniframe"]
    assert entry == {"type": "stdio", "command": script, "args": []}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _kiro_file(home: Path) -> Path:
    return home / ".kiro" / "settings" / "mcp.json"


@pytest.mark.parametrize(
    "key, marker, config",
    [
        ("kiro", ".kiro", ".kiro/settings/mcp.json"),
        ("cursor", ".cursor", ".cursor/mcp.json"),
        ("claude", ".claude.json", ".claude.json"),
        ("antigravity", ".gemini", ".gemini/config/mcp_config.json"),
    ],
)
def test_adds_entry_for_each_installed_client(tmp_path, key, marker, config):
    marker_path = tmp_path / marker
    if marker_path.suffix == ".json":
        _write(marker_path, {})
    else:
        marker_path.mkdir()

    assert main(["--client", key], home=tmp_path, env={}) == 0

    entry = _read(tmp_path / config)["mcpServers"]["omniframe"]
    assert entry["command"] == "uvx"
    assert entry["args"] == ARGS


def test_empty_file_gets_entry_and_no_backup(tmp_path):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)

    assert main(["--client", "kiro"], home=tmp_path, env={}) == 0

    assert _read(kiro) == {"mcpServers": {"omniframe": {"command": "uvx", "args": ARGS}}}
    assert not kiro.with_name("mcp.json.omniframe-backup").exists()


def test_other_servers_and_fields_are_kept(tmp_path):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    fetch = {"command": "uvx", "args": ["mcp-server-fetch"]}
    _write(kiro, {"mcpServers": {"fetch": fetch}, "theme": "dark"})

    assert main(["--client", "kiro"], home=tmp_path, env={}) == 0

    data = _read(kiro)
    assert data["mcpServers"]["fetch"] == fetch
    assert data["theme"] == "dark"
    assert data["mcpServers"]["omniframe"]["args"] == ARGS


def test_old_omniframe_entry_is_updated_and_env_kept(tmp_path):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    old = {"command": "python", "args": ["-m", "omniframe"], "env": {"OMNIFRAME_OUTPUT_DIR": "./output"}}
    _write(kiro, {"mcpServers": {"omniframe": old}})

    assert main(["--client", "kiro", "--update"], home=tmp_path, env={}) == 0

    entry = _read(kiro)["mcpServers"]["omniframe"]
    assert entry["command"] == "uvx"
    assert entry["args"] == ARGS
    assert entry["env"] == {"OMNIFRAME_OUTPUT_DIR": "./output"}


def test_existing_omniframe_entry_is_kept_without_update(tmp_path, capsys):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    text = json.dumps({"mcpServers": {"omniframe": {"command": "python", "args": ["-m", "omniframe"]}}})
    kiro.parent.mkdir(parents=True)
    kiro.write_text(text, encoding="utf-8")

    assert main(["--client", "kiro"], home=tmp_path, env={}) == 0

    assert kiro.read_text(encoding="utf-8") == text
    assert not kiro.with_name("mcp.json.omniframe-backup").exists()
    assert "--update" in capsys.readouterr().out


def test_backup_is_written_once_and_holds_the_original(tmp_path):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    original = json.dumps({"mcpServers": {"fetch": {"command": "uvx"}}})
    kiro.parent.mkdir(parents=True)
    kiro.write_text(original, encoding="utf-8")
    backup = kiro.with_name("mcp.json.omniframe-backup")

    assert main(["--client", "kiro"], home=tmp_path, env={}) == 0
    assert backup.read_text(encoding="utf-8") == original

    # A later change must not overwrite the backup of the original file.
    _write(kiro, {"mcpServers": {"omniframe": {"command": "python"}}})
    assert main(["--client", "kiro", "--update"], home=tmp_path, env={}) == 0
    assert backup.read_text(encoding="utf-8") == original


def test_dry_run_writes_nothing_and_hides_env_values(tmp_path, capsys):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    text = json.dumps({"mcpServers": {"omniframe": {"command": "python", "env": {"K": "SECRET123"}}}})
    kiro.parent.mkdir(parents=True)
    kiro.write_text(text, encoding="utf-8")

    assert main(["--dry-run", "--update"], home=tmp_path, env={}) == 0

    assert kiro.read_text(encoding="utf-8") == text
    assert not kiro.with_name("mcp.json.omniframe-backup").exists()
    out = capsys.readouterr().out
    assert "dry run" in out
    assert "SECRET123" not in out


def test_dry_run_creates_no_folders(tmp_path):
    (tmp_path / ".kiro").mkdir()

    assert main(["--dry-run", "--client", "kiro"], home=tmp_path, env={}) == 0

    assert not (tmp_path / ".kiro" / "settings").exists()


def test_remove_deletes_only_omniframe(tmp_path):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    fetch = {"command": "uvx", "args": ["mcp-server-fetch"]}
    _write(kiro, {"mcpServers": {"fetch": fetch, "omniframe": {"command": "uvx"}}})

    assert main(["--remove", "--client", "kiro"], home=tmp_path, env={}) == 0

    assert _read(kiro) == {"mcpServers": {"fetch": fetch}}


def test_remove_without_entry_changes_nothing(tmp_path):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    text = json.dumps({"mcpServers": {"fetch": {"command": "uvx"}}})
    kiro.parent.mkdir(parents=True)
    kiro.write_text(text, encoding="utf-8")

    assert main(["--remove", "--client", "kiro"], home=tmp_path, env={}) == 0
    assert kiro.read_text(encoding="utf-8") == text


def test_invalid_json_fails_without_writing(tmp_path, capsys):
    (tmp_path / ".kiro").mkdir()
    kiro = _kiro_file(tmp_path)
    kiro.parent.mkdir(parents=True)
    kiro.write_text("{ not json", encoding="utf-8")

    assert main(["--client", "kiro"], home=tmp_path, env={}) == 1

    assert kiro.read_text(encoding="utf-8") == "{ not json"
    assert not kiro.with_name("mcp.json.omniframe-backup").exists()
    assert "Nothing was written" in capsys.readouterr().err


def test_client_not_installed_is_skipped(tmp_path, capsys):
    assert main(["--client", "cursor"], home=tmp_path, env={}) == 0

    assert not (tmp_path / ".cursor").exists()
    assert "not installed" in capsys.readouterr().out


def test_default_run_touches_only_installed_clients(tmp_path):
    (tmp_path / ".kiro").mkdir()

    assert main([], home=tmp_path, env={}) == 0

    assert "omniframe" in _read(_kiro_file(tmp_path))["mcpServers"]
    assert not (tmp_path / ".cursor").exists()
    assert not (tmp_path / ".gemini").exists()


def test_autoapprove_only_for_kiro_with_trust(tmp_path):
    (tmp_path / ".kiro").mkdir()
    (tmp_path / ".cursor").mkdir()

    assert main(["--trust"], home=tmp_path, env={}) == 0

    assert _read(_kiro_file(tmp_path))["mcpServers"]["omniframe"]["autoApprove"] == ["*"]
    cursor = _read(tmp_path / ".cursor" / "mcp.json")["mcpServers"]["omniframe"]
    assert "autoApprove" not in cursor


def test_kiro_without_trust_has_no_autoapprove(tmp_path):
    (tmp_path / ".kiro").mkdir()

    assert main(["--client", "kiro"], home=tmp_path, env={}) == 0

    assert "autoApprove" not in _read(_kiro_file(tmp_path))["mcpServers"]["omniframe"]


def test_vscode_uses_copilot_home_when_set(tmp_path):
    copilot = tmp_path / "copilot-home"
    copilot.mkdir()

    assert main(["--client", "vscode"], home=tmp_path, env={"COPILOT_HOME": str(copilot)}) == 0

    entry = _read(copilot / "mcp-config.json")["mcpServers"]["omniframe"]
    assert entry["type"] == "stdio"
    assert not (tmp_path / ".copilot").exists()


def test_claude_user_file_keeps_other_state(tmp_path):
    claude = tmp_path / ".claude.json"
    _write(claude, {"numStartups": 5, "projects": {"C:/work": {"allowedTools": []}}})

    assert main(["--client", "claude"], home=tmp_path, env={}) == 0

    data = _read(claude)
    assert data["numStartups"] == 5
    assert data["projects"] == {"C:/work": {"allowedTools": []}}
    assert data["mcpServers"]["omniframe"]["type"] == "stdio"

"""Engine lookup and the package-install bootstrap (task 21b). Offline: no npm or Remotion runs."""

from pathlib import Path

from omniframe import engine_setup


def test_override_wins_and_is_not_a_package_install(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIFRAME_ENGINE_DIR", str(tmp_path))
    assert engine_setup.resolve_engine_dir() == tmp_path.resolve()
    assert engine_setup.is_packaged() is False


def _fake_package(root: Path) -> Path:
    src = root / "_engine"
    (src / "src").mkdir(parents=True)
    (src / "public" / "fonts").mkdir(parents=True)
    (src / "package.json").write_text('{"name": "engine"}', encoding="utf-8")
    (src / "src" / "Root.tsx").write_text("export {};", encoding="utf-8")
    (src / "public" / "fonts" / "A.otf").write_bytes(b"x")
    return src


def test_sync_copies_the_packaged_engine_and_keeps_an_existing_copy(monkeypatch, tmp_path) -> None:
    src = _fake_package(tmp_path / "pkg")
    dst = tmp_path / "home" / "engine"
    monkeypatch.delenv("OMNIFRAME_ENGINE_DIR", raising=False)
    monkeypatch.setattr(engine_setup, "packaged_engine", lambda: src)
    monkeypatch.setattr(engine_setup, "user_engine", lambda: dst)
    monkeypatch.setattr(engine_setup, "repo_engine", lambda: tmp_path / "no-repo" / "engine")

    assert engine_setup.sync_packaged_engine() == dst
    assert (dst / "src" / "Root.tsx").is_file()
    assert (dst / "public" / "fonts" / "A.otf").is_file()
    marker = (dst / engine_setup.PACKAGE_MARKER).read_text(encoding="utf-8")
    assert marker == engine_setup.__version__

    # same version: the copy is not refreshed
    (dst / "src" / "Root.tsx").write_text("changed", encoding="utf-8")
    engine_setup.sync_packaged_engine()
    assert (dst / "src" / "Root.tsx").read_text(encoding="utf-8") == "changed"


def test_a_running_installer_is_not_started_twice(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OMNIFRAME_ENGINE_DIR", raising=False)
    monkeypatch.setattr(engine_setup, "omniframe_home", lambda: tmp_path)
    monkeypatch.setattr(engine_setup, "repo_engine", lambda: tmp_path / "no-repo" / "engine")
    monkeypatch.setattr(engine_setup, "user_engine", lambda: tmp_path / "engine")
    monkeypatch.setattr(engine_setup, "_pid_alive", lambda pid: True)
    (tmp_path / "engine-setup.json").write_text(
        '{"state": "installing", "pid": 4242}', encoding="utf-8"
    )

    def no_second_installer(*args, **kwargs):
        raise AssertionError("a second installer was started")

    monkeypatch.setattr(engine_setup.subprocess, "Popen", no_second_installer)
    assert engine_setup.ensure_started()["pid"] == 4242


def test_error_state_reaches_the_render_message(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OMNIFRAME_ENGINE_DIR", raising=False)
    monkeypatch.setattr(engine_setup, "omniframe_home", lambda: tmp_path)
    monkeypatch.setattr(engine_setup, "repo_engine", lambda: tmp_path / "no-repo" / "engine")
    monkeypatch.setattr(engine_setup, "user_engine", lambda: tmp_path / "engine")
    (tmp_path / "engine-setup.json").write_text(
        '{"state": "error", "error": "npm install failed with exit code 1"}', encoding="utf-8"
    )
    message = engine_setup.not_ready_message()
    assert "npm install failed with exit code 1" in message
    assert "restart the omniframe MCP server" in message

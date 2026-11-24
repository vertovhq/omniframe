"""Offline doctor tests: fake executable paths + mocked subprocess.

Nothing real is executed — every probe goes through doctor._run (mocked here)
except the edge live probe, which is tested via a mocked subprocess.run.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import doctor  # noqa: E402
from omniframe.config import OmniFrameConfig  # noqa: E402


def _fake_exe(tmp_path: Path, name: str) -> str:
    p = tmp_path / name
    p.write_bytes(b"")  # dummy: doctor mocks _run, so the bytes never execute
    return str(p)


def _pin_which(monkeypatch, tmp_path: Path, missing: tuple[str, ...] = ()) -> None:
    """Pin doctor._which to tmp_path dummies so the host's real PATH is irrelevant.

    Absolute existing paths resolve to themselves; names not in the dummies
    (or listed in `missing`) resolve to None.
    """
    dummies = {"node": _fake_exe(tmp_path, "node.exe"), "npx": _fake_exe(tmp_path, "npx.cmd")}

    def fake_which(exe):
        if exe in missing:
            return None
        if exe in dummies:
            return dummies[exe]
        return str(exe) if Path(exe).exists() else None

    monkeypatch.setattr(doctor, "_which", fake_which)


def _make_cfg(tmp_path: Path, *, key: str = "test-key", eleven: str = "el-key") -> OmniFrameConfig:
    return OmniFrameConfig(
        gemini_api_key=key,
        elevenlabs_api_key=eleven,
        output_dir=tmp_path / "out",
        ffmpeg=_fake_exe(tmp_path, "ffmpeg.exe"),
        ffprobe=_fake_exe(tmp_path, "ffprobe.exe"),
    )


def _mock_run_ok(monkeypatch, node_version: str = "v20.11.1") -> None:
    """All doctor._run probes succeed; canned outputs by command shape."""

    def fake_run(cmd, timeout=20.0, cwd=None):
        argv = " ".join(cmd)
        if cmd[-1] == "--version" and "node" in Path(cmd[0]).name:
            return SimpleNamespace(returncode=0, stdout=node_version + "\n", stderr="")
        if cmd[-1] == "--version":  # npx
            return SimpleNamespace(returncode=0, stdout="10.2.4\n", stderr="")
        if "-version" in argv:  # ffmpeg/ffprobe -version
            return SimpleNamespace(returncode=0, stdout=f"{cmd[0]} version 7.1-2024", stderr="")
        if cmd[:2] == [sys.executable, "-c"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")  # import numpy / PIL / edge_tts / ...
        raise AssertionError(f"unexpected probe: {argv}")

    monkeypatch.setattr(doctor, "_run", fake_run)


def _fake_engine(tmp_path: Path, monkeypatch, *, with_modules: bool = True, skip: tuple[str, ...] = ()) -> Path:
    """An engine folder; `with_modules` adds node_modules with the renderer packages except `skip`."""
    eng = tmp_path / "engine"
    eng.mkdir(parents=True, exist_ok=True)
    (eng / "package.json").write_text("{}", encoding="utf-8")
    if with_modules:
        (eng / "node_modules").mkdir(parents=True)
        for name in doctor.ENGINE_PACKAGES:
            if name not in skip:
                (eng / "node_modules" / name).mkdir(parents=True)
    monkeypatch.setenv("OMNIFRAME_ENGINE_DIR", str(eng))
    return eng


def _run_failing_import(monkeypatch, module: str) -> None:
    """Every probe succeeds except `import <module>` in the child python."""

    def fake_run(cmd, timeout=20.0, cwd=None):
        argv = " ".join(cmd)
        if cmd[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="v20.11.1\n" if "node" in Path(cmd[0]).name else "10.2.4\n", stderr="")
        if "-version" in argv:
            return SimpleNamespace(returncode=0, stdout="x version 1", stderr="")
        if cmd[:2] == [sys.executable, "-c"]:
            if cmd[2] == f"import {module}":
                return SimpleNamespace(returncode=1, stdout="", stderr=f"No module named {module}")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected probe: {argv}")

    monkeypatch.setattr(doctor, "_run", fake_run)


# ------------------------------------------------------------------- happy path

def test_all_critical_ok(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = _make_cfg(tmp_path)

    report = doctor.run_checks(live=False, config=cfg)

    assert report["ok"] is True
    assert report["critical_failures"] == []
    ids = {c["id"] for c in report["checks"]}
    optional = {"faster_whisper", "edge_tts", "gemini_key", "elevenlabs_key", "render_browser"}
    assert ids == set(doctor.CRITICAL_IDS) | optional
    assert not {i for i in ids if "ass" in i}  # no ASS subtitle check any more
    assert {"numpy", "pillow"} <= set(doctor.CRITICAL_IDS)
    for c in report["checks"]:
        assert c["status"] in ("ok", "warn")
        if c["status"] == "fail":
            raise AssertionError(f"unexpected fail: {c}")
    # output dir was created by the check itself
    assert Path(cfg.output_dir).is_dir()


def test_output_dir_created_deep(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = OmniFrameConfig(
        gemini_api_key="k",
        output_dir=tmp_path / "a" / "b" / "out",
        ffmpeg=_fake_exe(tmp_path, "ffmpeg.exe"),
        ffprobe=_fake_exe(tmp_path, "ffprobe.exe"),
    )
    check = next(c for c in doctor.run_checks(live=False, config=cfg)["checks"]
                 if c["id"] == "output_dir")
    assert check["status"] == "ok"
    assert "created" in check["detail"]
    assert Path(cfg.output_dir).is_dir()


# ------------------------------------------------------------------ failures

def test_ffmpeg_missing_fails_with_hint(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = OmniFrameConfig(
        gemini_api_key="k",
        output_dir=tmp_path / "out",
        ffmpeg="no-such-ffmpeg-anywhere",
        ffprobe="no-such-ffprobe-anywhere",
    )
    report = doctor.run_checks(live=False, config=cfg)

    assert report["ok"] is False
    assert set(report["critical_failures"]) == {"ffmpeg", "ffprobe"}
    by_id = {c["id"]: c for c in report["checks"]}
    for cid in ("ffmpeg", "ffprobe"):
        assert by_id[cid]["status"] == "fail"
        assert by_id[cid]["hint"]  # one install hint per ✗
    text = doctor.render_text(report)
    assert "✗" in text and "→" in text


def test_node_too_old(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch, node_version="v16.14.0")
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    report = doctor.run_checks(live=False, config=_make_cfg(tmp_path))

    node = next(c for c in report["checks"] if c["id"] == "node")
    assert node["status"] == "fail"
    assert "18" in node["hint"]
    assert report["ok"] is False and "node" in report["critical_failures"]


@pytest.mark.parametrize(("module", "check_id"), [("numpy", "numpy"), ("PIL", "pillow")])
def test_core_python_packages_are_critical(tmp_path, monkeypatch, module, check_id):
    _run_failing_import(monkeypatch, module)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    report = doctor.run_checks(live=False, config=_make_cfg(tmp_path))

    check = next(c for c in report["checks"] if c["id"] == check_id)
    assert check["status"] == "fail" and "pip install" in check["hint"]
    assert report["critical_failures"] == [check_id]
    assert report["ok"] is False


@pytest.mark.parametrize(("module", "check_id"), [("faster_whisper", "faster_whisper"), ("edge_tts", "edge_tts")])
def test_optional_python_packages_only_warn(tmp_path, monkeypatch, module, check_id):
    _run_failing_import(monkeypatch, module)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    report = doctor.run_checks(live=False, config=_make_cfg(tmp_path))

    check = next(c for c in report["checks"] if c["id"] == check_id)
    assert check["status"] == "warn" and check["hint"]
    assert report["critical_failures"] == []
    assert report["ok"] is True


def test_engine_missing_renderer_packages(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    eng = _fake_engine(tmp_path, monkeypatch, skip=("@remotion/renderer",))
    report = doctor.run_checks(live=False, config=_make_cfg(tmp_path))

    engine = next(c for c in report["checks"] if c["id"] == "engine")
    assert engine["status"] == "fail"
    assert "@remotion/renderer" in engine["detail"] and "@remotion/bundler" not in engine["detail"]
    assert f"cd {eng}" in engine["hint"] and "npm install" in engine["hint"]
    assert report["critical_failures"] == ["engine"]


def test_engine_needs_npm_install(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    eng = _fake_engine(tmp_path, monkeypatch, with_modules=False)
    report = doctor.run_checks(live=False, config=_make_cfg(tmp_path))

    engine = next(c for c in report["checks"] if c["id"] == "engine")
    assert engine["status"] == "fail"
    assert f"cd {eng}" in engine["hint"] and "npm install" in engine["hint"]


def test_gemini_key_absent_is_status_not_error(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = _make_cfg(tmp_path, key="")
    report = doctor.run_checks(live=False, config=cfg)

    key = next(c for c in report["checks"] if c["id"] == "gemini_key")
    assert key["status"] == "warn"
    assert "gemini_key" not in report["critical_failures"]
    assert report["ok"] is True  # warnings never flip the verdict


def test_elevenlabs_key_optional(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)

    with_key = doctor.run_checks(live=False, config=_make_cfg(tmp_path))
    key = next(c for c in with_key["checks"] if c["id"] == "elevenlabs_key")
    assert key["status"] == "ok"

    cfg = OmniFrameConfig(
        gemini_api_key="k",
        elevenlabs_api_key="",
        output_dir=tmp_path / "out",
        ffmpeg=_fake_exe(tmp_path, "ffmpeg.exe"),
        ffprobe=_fake_exe(tmp_path, "ffprobe.exe"),
    )
    without = doctor.run_checks(live=False, config=cfg)
    key = next(c for c in without["checks"] if c["id"] == "elevenlabs_key")
    assert key["status"] == "warn"  # optional: absence is a status, not an error
    assert "elevenlabs_key" not in without["critical_failures"]
    assert without["ok"] is True


# ------------------------------------------------------------ edge live probe

def test_edge_probe_retries_then_ok(tmp_path, monkeypatch):
    """First attempt times out, second succeeds — retry logic works."""
    monkeypatch.setattr(doctor.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    def fake_subprocess_run(*args, **kwargs):
        cmd = args[0]
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))
        out = Path(cmd[3])  # [python, -c, PROBE, out_path]
        out.write_bytes(b"mp3-bytes")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", fake_subprocess_run)
    alive, err = doctor.probe_edge()
    assert alive is True and err == "" and attempts["n"] == 2


def test_edge_probe_reports_last_error(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.time, "sleep", lambda s: None)

    def fake_subprocess_run(*args, **kwargs):
        cmd = args[0]
        if "import edge_tts" in cmd[2]:  # import probe inside check_edge_tts
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="no route to host")

    monkeypatch.setattr(doctor.subprocess, "run", fake_subprocess_run)
    alive, err = doctor.probe_edge()
    assert alive is False and "no route to host" in err

    check = doctor.check_edge_tts(live=True)
    assert check["status"] == "warn"  # the service is silent: the environment is not at fault
    assert "pip" not in check["hint"]  # nothing to install


# ------------------------------------------------------------------- CLI/wiring

def test_main_json_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_checks", lambda **kw: {
        "omniframe": "test", "platform": "test", "live": False,
        "checks": [], "critical_failures": [], "ok": True,
    })
    assert doctor.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: {
        "omniframe": "test", "platform": "test", "live": False,
        "checks": [{"id": "node", "label": "node", "status": "fail", "detail": "x", "hint": "y"}],
        "critical_failures": ["node"], "ok": False,
    })
    assert doctor.main(["--json"]) == 1


# ------------------------------------------------------------- render browser

def test_render_browser_found_is_ok(tmp_path, monkeypatch):
    from omniframe.tools import render

    browser = _fake_exe(tmp_path, "chrome.exe")
    monkeypatch.setattr(render, "_find_browser", lambda: browser)
    check = doctor.check_render_browser()
    assert check["status"] == "ok" and check["detail"] == browser


def test_render_browser_missing_says_remotion_downloads(tmp_path, monkeypatch):
    from omniframe.tools import render

    monkeypatch.setattr(render, "_find_browser", lambda: None)
    check = doctor.check_render_browser()
    assert check["status"] == "warn"  # optional: Remotion downloads its own browser
    assert "Remotion downloads" in check["detail"]
    assert "REMOTION_BROWSER" in check["hint"]


# ------------------------------------------------------------------ language

def test_doctor_messages_are_english():
    """Tool messages are English (product steering); the doctor source and this file have no Cyrillic."""
    for path in (Path(doctor.__file__), Path(__file__)):
        assert re.search("[\u0400-\u04FF]", path.read_text(encoding="utf-8")) is None, path.name

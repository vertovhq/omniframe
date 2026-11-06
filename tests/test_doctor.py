"""Offline doctor tests: fake executable paths + mocked subprocess.

Nothing real is executed — every probe goes through doctor._run (mocked here)
except the edge live probe, which is tested via a mocked subprocess.run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import doctor  # noqa: E402
from argus.config import ArgusConfig  # noqa: E402


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


def _make_cfg(tmp_path: Path, *, key: str = "test-key") -> ArgusConfig:
    return ArgusConfig(
        gemini_api_key=key,
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
        if "ass=probe.ass" in argv:  # libass trial render
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == [sys.executable, "-c"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")  # import edge_tts / playwright
        raise AssertionError(f"unexpected probe: {argv}")

    monkeypatch.setattr(doctor, "_run", fake_run)


def _fake_engine(tmp_path: Path, monkeypatch, *, with_modules: bool = True) -> Path:
    eng = tmp_path / "engine"
    eng.mkdir(parents=True, exist_ok=True)
    (eng / "package.json").write_text("{}", encoding="utf-8")
    if with_modules:
        (eng / "node_modules").mkdir(parents=True)
    monkeypatch.setenv("ARGUS_ENGINE_DIR", str(eng))
    return eng


# ------------------------------------------------------------------- happy path

def test_all_critical_ok(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = _make_cfg(tmp_path)

    report = doctor.run_checks(flow=False, live=False, config=cfg)

    assert report["ok"] is True
    assert report["critical_failures"] == []
    ids = {c["id"] for c in report["checks"]}
    assert ids == set(doctor.CRITICAL_IDS) | {"playwright", "gemini_key"}
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
    cfg = ArgusConfig(
        gemini_api_key="k",
        output_dir=tmp_path / "a" / "b" / "out",
        ffmpeg=_fake_exe(tmp_path, "ffmpeg.exe"),
        ffprobe=_fake_exe(tmp_path, "ffprobe.exe"),
    )
    check = next(c for c in doctor.run_checks(flow=False, live=False, config=cfg)["checks"]
                 if c["id"] == "output_dir")
    assert check["status"] == "ok"
    assert "создан" in check["detail"]
    assert Path(cfg.output_dir).is_dir()


# ------------------------------------------------------------------ failures

def test_ffmpeg_missing_fails_with_hint(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = ArgusConfig(
        gemini_api_key="k",
        output_dir=tmp_path / "out",
        ffmpeg="no-such-ffmpeg-anywhere",
        ffprobe="no-such-ffprobe-anywhere",
    )
    report = doctor.run_checks(flow=False, live=False, config=cfg)

    assert report["ok"] is False
    # libass fails too: its trial render needs ffmpeg to exist
    assert set(report["critical_failures"]) == {"ffmpeg", "ffprobe", "libass"}
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
    report = doctor.run_checks(flow=False, live=False, config=_make_cfg(tmp_path))

    node = next(c for c in report["checks"] if c["id"] == "node")
    assert node["status"] == "fail"
    assert "18" in node["hint"]
    assert report["ok"] is False and "node" in report["critical_failures"]


def test_libass_missing(tmp_path, monkeypatch):
    def fake_run(cmd, timeout=20.0, cwd=None):
        argv = " ".join(cmd)
        if cmd[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="v20.11.1\n" if "node" in Path(cmd[0]).name else "10.2.4\n", stderr="")
        if "-version" in argv:
            return SimpleNamespace(returncode=0, stdout="ffmpeg version 7.1", stderr="")
        if "ass=probe.ass" in argv:
            return SimpleNamespace(returncode=1, stdout="", stderr="No such filter: 'ass'")
        if cmd[:2] == [sys.executable, "-c"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected probe: {argv}")

    monkeypatch.setattr(doctor, "_run", fake_run)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    report = doctor.run_checks(flow=False, live=False, config=_make_cfg(tmp_path))

    libass = next(c for c in report["checks"] if c["id"] == "libass")
    assert libass["status"] == "fail"
    assert "libass" in libass["hint"]


def test_engine_needs_npm_install(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    eng = _fake_engine(tmp_path, monkeypatch, with_modules=False)
    report = doctor.run_checks(flow=False, live=False, config=_make_cfg(tmp_path))

    engine = next(c for c in report["checks"] if c["id"] == "engine")
    assert engine["status"] == "fail"
    assert f"cd {eng}" in engine["hint"] and "npm install" in engine["hint"]


def test_gemini_key_absent_is_status_not_error(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)
    cfg = _make_cfg(tmp_path, key="")
    report = doctor.run_checks(flow=False, live=False, config=cfg)

    key = next(c for c in report["checks"] if c["id"] == "gemini_key")
    assert key["status"] == "warn"
    assert "gemini_key" not in report["critical_failures"]
    assert report["ok"] is True  # warnings never flip the verdict


def test_playwright_optional_vs_flow(tmp_path, monkeypatch):
    _mock_run_ok(monkeypatch)
    _pin_which(monkeypatch, tmp_path)
    _fake_engine(tmp_path, monkeypatch)

    def fake_run(cmd, timeout=20.0, cwd=None):
        argv = " ".join(cmd)
        if cmd[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="v20.11.1\n" if "node" in Path(cmd[0]).name else "10.2.4\n", stderr="")
        if "-version" in argv:
            return SimpleNamespace(returncode=0, stdout="x version 1", stderr="")
        if "ass=probe.ass" in argv:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == [sys.executable, "-c"]:
            if "import playwright" in cmd[2]:  # playwright отсутствует
                return SimpleNamespace(returncode=1, stdout="", stderr="No module named playwright")
            return SimpleNamespace(returncode=0, stdout="", stderr="")  # import edge_tts
        raise AssertionError(f"unexpected probe: {argv}")

    monkeypatch.setattr(doctor, "_run", fake_run)
    cfg = _make_cfg(tmp_path)

    offline = doctor.run_checks(flow=False, live=False, config=cfg)
    pw = next(c for c in offline["checks"] if c["id"] == "playwright")
    assert pw["status"] == "warn"  # пометка «опционально»
    assert offline["ok"] is True

    flow = doctor.run_checks(flow=True, live=False, config=cfg)
    pw_flow = next(c for c in flow["checks"] if c["id"] == "playwright")
    assert pw_flow["status"] == "fail"  # в режиме flow — критично
    assert flow["ok"] is False and "playwright" in flow["critical_failures"]


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
    assert check["status"] == "warn"  # сервис молчит — окружение не виновато
    assert "pip" not in check["hint"]  # доустанавливать ничего не нужно


# ------------------------------------------------------------------- CLI/wiring

def test_main_json_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_checks", lambda **kw: {
        "argus": "test", "platform": "test", "flow_mode": False, "live": False,
        "checks": [], "critical_failures": [], "ok": True,
    })
    assert doctor.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: {
        "argus": "test", "platform": "test", "flow_mode": False, "live": False,
        "checks": [{"id": "node", "label": "node", "status": "fail", "detail": "x", "hint": "y"}],
        "critical_failures": ["node"], "ok": False,
    })
    assert doctor.main(["--json"]) == 1

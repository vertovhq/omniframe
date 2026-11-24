"""Every child process OmniFrame starts passes NO_WINDOW, so Windows opens no console window."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from omniframe import ffmpeg  # noqa: E402

SRC = ROOT / "src" / "omniframe"
SPAWNERS = {"run", "Popen", "call", "check_call", "check_output"}
CREATE_NO_WINDOW = 0x08000000


def test_flag_hides_the_console_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW, raising=False)
    assert ffmpeg.no_window_flag("nt") == CREATE_NO_WINDOW
    monkeypatch.delattr(subprocess, "CREATE_NO_WINDOW", raising=False)
    assert ffmpeg.no_window_flag("nt") == CREATE_NO_WINDOW  # documented value when subprocess lacks it


def test_flag_is_zero_off_windows() -> None:
    # Popen rejects a non-zero creationflags on POSIX, so the flag must be 0 there.
    assert ffmpeg.no_window_flag("posix") == 0


def test_shared_ffmpeg_wrapper_passes_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ffmpeg._run(["ffmpeg", "-version"])
    assert seen["creationflags"] == ffmpeg.NO_WINDOW


def _spawn_calls():
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            func = getattr(node, "func", None)
            if (
                isinstance(node, ast.Call)
                and isinstance(func, ast.Attribute)
                and func.attr in SPAWNERS
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                yield path, node


def test_every_spawn_in_src_uses_the_shared_flag() -> None:
    calls = list(_spawn_calls())
    # the scan must see the known spawners, or the check below proves nothing
    found = {path.name for path, _ in calls}
    assert {"ffmpeg.py", "jobs.py", "doctor.py", "render.py", "sfx.py", "beats.py",
            "components.py", "scripts_runner.py"} <= found
    missing = []
    for path, node in calls:
        flag = next((kw.value for kw in node.keywords if kw.arg == "creationflags"), None)
        uses_shared = flag is not None and any(
            isinstance(part, ast.Name) and part.id == "NO_WINDOW" for part in ast.walk(flag)
        )
        if not uses_shared:
            missing.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert not missing, "spawns without creationflags=NO_WINDOW: " + ", ".join(missing)

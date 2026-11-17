"""User scripts (task 17, requirement 14): listing, running, name checks, timeouts.

Each test gets its own output folder and its own user scripts folder. The runs start real
Python subprocesses through the `scripts_runner` job; nothing needs the network or the engine.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import jobs, project, server  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.media_out import Image  # noqa: E402
from argus.tools import scripts_runner  # noqa: E402

RED_CARD = '''"""Draw one red picture and list it.

Args: {"project": "card-check"}
"""
import json

from PIL import Image

Image.new("RGB", (64, 36), (200, 30, 30)).save("card.png")
print(json.dumps({"caption": "red", "images": ["card.png"]}))
'''


@pytest.fixture(autouse=True)
def scripts_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out", scripts_dir=tmp_path / "user-scripts")
    cfg.scripts_dir.mkdir()
    for module in (jobs, project, scripts_runner):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield {"out": cfg.output_dir, "scripts": cfg.scripts_dir, "tmp": tmp_path}
    for proc in list(jobs._PROCS.values()):
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    jobs._PROCS.clear()


def _script(folder: Path, name: str, text: str) -> Path:
    path = folder / f"{name}.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_list_shows_summary_and_args_and_does_not_run_scripts(scripts_env: dict) -> None:
    marker = scripts_env["tmp"] / "ran.txt"
    _script(scripts_env["scripts"], "hello_there", '"""Say hello to a name.\n\nArgs: {"who": "world"}\n"""\nprint("{}")\n')
    _script(
        scripts_env["scripts"],
        "leaves_marker",
        f'"""Writes a marker file.\n\nArgs: {{}}\n"""\nfrom pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n',
    )

    listed = scripts_runner.run_script()
    by_name = {entry["name"]: entry for entry in listed["scripts"]}

    assert by_name["frame_stats"]["summary"] == "Mean color and brightness of the given frames."
    assert by_name["frame_stats"]["args"].startswith('{"project"')
    assert by_name["hello_there"]["summary"] == "Say hello to a name."
    assert by_name["hello_there"]["args"] == '{"who": "world"}'
    assert not marker.exists(), "listing must read the docstring, not run the script"


def test_run_returns_the_scripts_json_result(scripts_env: dict) -> None:
    renders = project.project_dir("stats-check") / "renders"
    PILImage.new("RGB", (40, 20), (128, 128, 128)).save(renders / "gray.png")

    out = scripts_runner.run_script("frame_stats", {"project": "stats-check", "images": ["renders/gray.png"]})

    assert isinstance(out, dict), out
    assert out["ok"] is True
    assert out["name"] == "frame_stats"
    frame = out["result"]["frames"][0]
    assert frame["path"] == "renders/gray.png"
    assert (frame["width"], frame["height"]) == (40, 20)
    assert frame["mean_rgb"] == [128.0, 128.0, 128.0]
    assert frame["brightness"] == pytest.approx(128 / 255, abs=0.001)


def test_images_a_script_lists_come_back_as_pictures(scripts_env: dict) -> None:
    _script(scripts_env["scripts"], "red_card", RED_CARD)

    out = scripts_runner.run_script("red_card", {"project": "card-check"})

    assert isinstance(out, list), out
    summary = json.loads(out[0])
    assert summary["result"] == {"caption": "red"}
    assert summary["images"][0]["full_path"].endswith("card.png")
    assert len(out) == 2 and isinstance(out[1], Image)


@pytest.mark.parametrize("bad", ["../secrets", "frame-stats", "Frame_Stats", "frame_stats.py", "a/b", "", "x" * 41])
def test_a_bad_name_is_rejected_before_any_job_starts(scripts_env: dict, bad: str) -> None:
    out = scripts_runner.run_script(bad)

    assert out["ok"] is False
    assert "invalid script name" in out["error"]
    assert not jobs.jobs_root().exists()


def test_an_unknown_name_is_refused_with_the_available_names(scripts_env: dict) -> None:
    out = scripts_runner.run_script("not_there")

    assert out["ok"] is False
    assert "no script named 'not_there'" in out["error"]
    assert "frame_stats" in out["available"]


def test_a_script_that_runs_too_long_is_stopped_and_reported(scripts_env: dict) -> None:
    _script(scripts_env["scripts"], "too_slow", '"""Sleeps far longer than the test allows.\n\nArgs: {}\n"""\nimport time\n\ntime.sleep(120)\n')

    assert scripts_runner.run_script("too_slow", {}, timeout_s=0)["ok"] is False  # below the 1 s minimum

    out = scripts_runner.run_script("too_slow", {}, timeout_s=1)

    assert out["ok"] is False
    assert out["timed_out"] is True
    assert out["timeout_s"] == 1.0


def test_server_registers_run_script() -> None:
    assert "run_script" in server._registered_tool_names()

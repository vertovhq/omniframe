"""Task 20.10 item 22: `render_video(mode="final", then=["qa", "export"], export={...})` runs the export in
the same job, `job_status` waits on the server by default, and a render records the project's stage
(task 20.10 item 24).

Offline. The engine, the export and the job queue are replaced by fakes.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import jobs, project, server, state  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.tools import export as export_job  # noqa: E402
from argus.tools import render  # noqa: E402


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    monkeypatch.setattr(project, "CONFIG", cfg)
    monkeypatch.setattr(state, "CONFIG", cfg)


def test_export_step_needs_the_export_arguments() -> None:
    reply = render.render_video({}, "demo", mode="final", then=["export"])
    assert reply["valid"] is False
    assert any("export" in error for error in reply["errors"])


def test_export_step_is_for_final_renders_only() -> None:
    reply = render.render_video({}, "demo", mode="preview", then=["qa", "export"], export={"texts": {}})
    assert reply["valid"] is False
    assert "applies to mode \"final\" only" in reply["errors"][0]


def test_unknown_step_names_the_two_steps() -> None:
    reply = render.render_video({}, "demo", mode="final", then=["publish"])
    assert "\"qa\" and \"export\"" in reply["errors"][0]


def test_chained_export_uses_this_render_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_prepare(root, videos, texts, cover_times, name, library):
        seen["videos"] = videos
        seen["texts"] = texts
        return {"base": "demo"}, []

    monkeypatch.setattr(export_job, "prepare_export", fake_prepare)
    monkeypatch.setattr(export_job, "run_job", lambda payload, report: {"final": "ok", "base": payload["base"]})
    out = tmp_path / "demo-final-9x16.mp4"

    result = render._chained_export(tmp_path, out, "9:16", {"texts": {"tiktok": {"caption": "c"}}}, lambda *a: None)

    assert seen["videos"] == {"9:16": str(out)}
    assert seen["texts"] == {"tiktok": {"caption": "c"}}
    assert result == {"final": "ok", "base": "demo"}


def test_chained_export_reports_invalid_arguments_without_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_job, "prepare_export", lambda *a: (None, ["texts: give an object"]))
    monkeypatch.setattr(export_job, "run_job", lambda *a: (_ for _ in ()).throw(AssertionError("must not run")))

    result = render._chained_export(tmp_path, tmp_path / "x.mp4", "9:16", {}, lambda *a: None)

    assert result["valid"] is False
    assert result["errors"] == ["texts: give an object"]


def test_render_reply_is_recorded_in_the_project_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "prepare_render", lambda *a, **k: ({"then": []}, []))
    monkeypatch.setattr(jobs, "run_or_detach", lambda kind, payload, **k: {"job_id": "render-1", "summary": "started"})

    reply = render.render_video({"scenes": []}, "demo", mode="audio")

    assert reply["job_id"] == "render-1"
    assert state.load("demo")["last_render"]["job_id"] == "render-1"
    assert "plan" not in state.load("demo")  # a plan object is not a path, so no path is recorded


def test_job_status_waits_on_the_server_by_default() -> None:
    assert inspect.signature(server.job_status).parameters["wait_s"].default == jobs.DEFAULT_WAIT_S
    assert jobs.clamp_status_wait(jobs.DEFAULT_WAIT_S) == jobs.DEFAULT_WAIT_S

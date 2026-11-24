"""Detached jobs: inline result, detach + poll, error tail, single-flight, dead worker."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs  # noqa: E402
from omniframe.media_out import Image  # noqa: E402

WAIT = 60  # generous: a worker is a fresh Python process


@pytest.fixture(autouse=True)
def job_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Every test gets its own output dir, so jobs never leak between tests."""
    monkeypatch.setattr(jobs, "CONFIG", dataclasses.replace(jobs.CONFIG, output_dir=tmp_path / "out"))
    yield
    for proc in list(jobs._PROCS.values()):
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    jobs._PROCS.clear()


def _wait_for(job_id: str, states: tuple[str, ...] = ("done", "error"), timeout: float = WAIT) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = jobs.status(job_id)
        if snap["state"] in states:
            return snap
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} still {jobs.status(job_id)['state']} after {timeout}s")


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _plant_job(kind: str, state: str, pid: int | None, *, created: float | None = None, key: str = "k") -> str:
    """A job folder as the server would have left it, without a real worker."""
    job_id = f"{kind}-20260101-000000-abcdef"
    job_dir = jobs.jobs_root() / job_id
    job_dir.mkdir(parents=True)
    created = time.time() if created is None else created
    (job_dir / "job.json").write_text(json.dumps({
        "id": job_id, "kind": kind, "payload": {}, "key": key, "created": created,
    }))
    (job_dir / "status.json").write_text(json.dumps({
        "state": state, "progress": 0.3, "pid": pid, "started": created, "result": None, "error": None,
    }))
    (job_dir / "log.txt").write_text("Traceback...\nSomethingBroke: boom in worker\n")
    return job_id


def test_inline_result_when_job_finishes_in_time() -> None:
    out = jobs.run_or_detach("selftest", {"result": {"answer": 42}}, key="inline", wait_s=WAIT)
    assert out["answer"] == 42
    assert out["engine"].startswith("OmniFrame ")
    assert "job_id" not in out


def test_detach_then_poll_until_done() -> None:
    first = jobs.run_or_detach(
        "selftest", {"sleep": 2.0, "progress": [[0.5, "half way"]], "result": {"n": 7}}, key="slow", wait_s=0.2,
    )
    assert first["state"] in ("queued", "running")
    assert first["job_id"].startswith("selftest-")
    assert "job_status" in first["note"]

    done = _wait_for(first["job_id"])
    assert done["state"] == "done"
    assert done["result"] == {"n": 7}
    assert done["progress"] == 1.0

    # the same data through the tool function
    via_tool = jobs.job_status(first["job_id"])
    assert via_tool["state"] == "done" and via_tool["result"] == {"n": 7}


def test_progress_and_note_are_visible_while_running() -> None:
    first = jobs.run_or_detach(
        "selftest", {"sleep": 4.0, "progress": [[0.25, "decoding"]]}, key="prog", wait_s=0,
    )
    deadline = time.monotonic() + WAIT
    snap = jobs.status(first["job_id"])
    while snap["progress"] is None and time.monotonic() < deadline:
        time.sleep(0.1)
        snap = jobs.status(first["job_id"])
    assert snap["state"] == "running"
    assert snap["progress"] == 0.25 and snap["note"] == "decoding"
    _wait_for(first["job_id"])


def test_clamp_status_wait_caps_and_ignores_bad_values() -> None:
    assert jobs.clamp_status_wait(None) == 0.0
    assert jobs.clamp_status_wait(-3) == 0.0
    assert jobs.clamp_status_wait(float("nan")) == 0.0
    assert jobs.clamp_status_wait("oops") == 0.0
    assert jobs.clamp_status_wait(5) == 5.0
    assert jobs.clamp_status_wait(99) == jobs.MAX_STATUS_WAIT_S == 20.0


def test_job_status_waits_until_a_short_job_is_done() -> None:
    job_id = jobs.start("selftest", {"sleep": 0.5, "result": {"n": 1}}, key="wait-done")
    started = time.monotonic()
    snap = jobs.job_status(job_id, wait_s=15)
    assert snap["state"] == "done" and snap["result"] == {"n": 1}
    assert time.monotonic() - started < 15  # returned when the job ended, not when the wait ran out


def test_job_status_stops_waiting_when_wait_runs_out_and_estimates_the_rest() -> None:
    job_id = jobs.start("selftest", {"sleep": 6.0, "progress": [[0.5, "half way"]]}, key="wait-out")
    started = time.monotonic()
    snap = jobs.job_status(job_id, wait_s=1.0)
    assert 0.8 <= time.monotonic() - started < 5
    assert snap["state"] in ("queued", "running")
    if snap["progress"] is not None:  # progress known: the status carries a rough remaining time
        assert snap["eta_s"] >= 0


def test_error_tail_is_reported() -> None:
    first = jobs.run_or_detach("selftest", {"fail": "kaboom happened"}, key="bad", wait_s=WAIT)
    assert first["state"] == "error"
    assert "kaboom happened" in first["error"]
    assert "ValueError" in first["error"]

    snap = jobs.status(first["job_id"])
    assert snap["state"] == "error" and "kaboom happened" in snap["error"]
    assert "result" not in snap


def test_unknown_kind_is_an_error_not_a_hang() -> None:
    out = jobs.run_or_detach("no_such_kind", {}, key="x", wait_s=WAIT)
    assert out["state"] == "error"
    assert "unknown job kind" in out["error"]


def test_single_flight_returns_the_running_job_and_restarts_after_it_ends() -> None:
    a = jobs.start("selftest", {"sleep": 3.0}, key="same")
    b = jobs.start("selftest", {"sleep": 3.0}, key="same")
    assert a == b

    detached = jobs.run_or_detach("selftest", {"sleep": 3.0}, key="same", wait_s=0)
    assert detached["job_id"] == a
    assert "already running" in detached["note"]

    other = jobs.start("selftest", {"sleep": 0.0}, key="different")
    assert other != a

    _wait_for(a)
    again = jobs.start("selftest", {"sleep": 0.0}, key="same")
    assert again != a  # finished jobs do not block a new run
    _wait_for(again)
    _wait_for(other)


def test_default_key_is_the_payload() -> None:
    a = jobs.start("selftest", {"sleep": 3.0, "result": {"a": 1}})
    assert jobs.start("selftest", {"result": {"a": 1}, "sleep": 3.0}) == a
    assert jobs.start("selftest", {"sleep": 3.0, "result": {"a": 2}}) != a


def test_worker_that_dies_is_reported_as_error() -> None:
    job_id = jobs.start("selftest", {"sleep": 30.0}, key="victim")
    _wait_for(job_id, states=("running",))
    jobs._PROCS[job_id].kill()
    jobs._PROCS[job_id].wait()

    snap = jobs.status(job_id)
    assert snap["state"] == "error"
    assert "ended without a result" in snap["error"]
    # the verdict is stored: a new run with the same key is allowed
    assert jobs.start("selftest", {"sleep": 0.0}, key="victim") != job_id


def test_dead_pid_in_status_file_is_reported_as_error() -> None:
    """Server restarted: no process handle, only the pid in status.json."""
    job_id = _plant_job("selftest", "running", _dead_pid())
    snap = jobs.status(job_id)
    assert snap["state"] == "error"
    assert "ended without a result" in snap["error"]
    assert "boom in worker" in snap["error"]  # log tail included


def test_live_pid_in_status_file_stays_running() -> None:
    job_id = _plant_job("selftest", "running", os.getpid())
    assert jobs.status(job_id)["state"] == "running"


def test_queued_job_without_a_worker_times_out() -> None:
    fresh = _plant_job("selftest", "queued", None, created=time.time())
    assert jobs.status(fresh)["state"] == "queued"  # inside the start grace period

    job_dir = jobs.jobs_root() / "selftest-20260101-000000-abcdef"
    for name in ("job.json", "status.json"):
        data = json.loads((job_dir / name).read_text())
        data["created"] = time.time() - 3600
        data["started"] = None
        (job_dir / name).write_text(json.dumps(data))
    assert jobs.status(fresh)["state"] == "error"


def test_pid_alive() -> None:
    assert jobs.pid_alive(os.getpid())
    assert not jobs.pid_alive(_dead_pid())
    assert not jobs.pid_alive(None) and not jobs.pid_alive(0)


def test_unknown_and_invalid_job_ids() -> None:
    with pytest.raises(FileNotFoundError):
        jobs.status("selftest-20260101-000000-000000")
    with pytest.raises(ValueError):
        jobs.status("../../etc")


def test_job_status_returns_images_as_content(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    PILImage.new("RGB", (1600, 900), (10, 120, 200)).save(frame)
    result = {"video": "v.mp4", "images": [{"t": 2.5, "path": str(frame)}]}
    job_id = jobs.start("selftest", {"result": result}, key="pics")
    _wait_for(job_id)

    out = jobs.job_status(job_id)
    assert isinstance(out, list) and isinstance(out[0], str) and isinstance(out[1], Image)
    summary = json.loads(out[0])
    assert summary["state"] == "done" and summary["job_id"] == job_id
    assert summary["result"] == {"video": "v.mp4"}
    assert summary["images"][0]["t"] == 2.5
    assert summary["images"][0]["path"].endswith("frame.view.jpg")

    # inline path gives the same shape
    inline = jobs.run_or_detach("selftest", {"result": result}, key="pics2", wait_s=WAIT)
    assert isinstance(inline, list) and isinstance(inline[1], Image)

    # a result whose image file disappeared still lists the path
    frame.unlink()
    (tmp_path / "frame.view.jpg").unlink()
    gone = jobs.job_status(job_id)
    assert isinstance(gone, dict) and gone["images"][0]["path"] == str(frame)


def test_cleanup_removes_only_old_finished_jobs() -> None:
    old_done = _plant_job("selftest", "done", None, key="a")
    old_dir = jobs.jobs_root() / old_done
    (old_dir / "status.json").write_text(json.dumps({"state": "done", "result": {}}))
    week_plus = time.time() - 8 * 24 * 3600
    for p in (old_dir, *old_dir.iterdir()):
        os.utime(p, (week_plus, week_plus))

    fresh = jobs.start("selftest", {"result": {}}, key="fresh")
    _wait_for(fresh)

    assert jobs.cleanup_old_jobs() == 1
    assert not old_dir.exists()
    assert (jobs.jobs_root() / fresh).is_dir()
    assert jobs.cleanup_old_jobs() == 0

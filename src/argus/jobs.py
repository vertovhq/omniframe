"""Detached background jobs (design §5).

MCP clients cut tool calls after a short time, so anything that can run longer than
~20 s runs in a separate worker process and reports through files:

    <output_dir>/.jobs/<job_id>/
        job.json      kind, payload, key, created        (written once by the server)
        status.json   state, progress, note, pid, result, error   (written by the worker)
        log.txt       the worker's stderr

`run_or_detach` starts a job, waits a short budget and returns the result inline when
the job finishes in time; otherwise it returns a `job_id` to poll with `job_status`.
The same kind + key never runs twice at once. A worker that died without a result is
reported as `error`, never as `running` forever.

The worker entry is `python -I -m argus.jobs <job_dir>`. A job function is
`fn(payload: dict, report) -> dict` where `report(progress, note)` updates the status.
Functions are found by `register(kind)`, or else as `run_job` in `argus.tools.<kind>`.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path

from . import __version__
from .config import CONFIG

RETENTION_S = 7 * 24 * 3600      # jobs older than this are deleted at server start
MAX_RUN_S = 4 * 3600             # a running job older than this counts as stuck
START_GRACE_S = 60.0             # a worker that has not reported a pid yet gets this long
DEFAULT_WAIT_S = 20.0
# `job_status(wait_s=...)` is capped here, so one tool call stays well under the client's timeout.
MAX_STATUS_WAIT_S = 20.0
POLL_S = 0.15
ERROR_TAIL_CHARS = 1500

JobFn = Callable[[dict, Callable[..., None]], dict]

_REGISTRY: dict[str, JobFn] = {}
_PROCS: dict[str, subprocess.Popen] = {}   # workers started by this server process
_START_LOCK = threading.Lock()
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,100}")
_KIND_RE = re.compile(r"[a-z][a-z0-9_]{0,40}")


# ------------------------------------------------------------------ files

def jobs_root() -> Path:
    return Path(CONFIG.output_dir) / ".jobs"


def _job_dir(job_id: str) -> Path:
    if not _ID_RE.fullmatch(job_id):
        raise ValueError(f"invalid job_id {job_id!r}")
    return jobs_root() / job_id


def _write_json(path: Path, data: dict) -> None:
    """Atomic write; Windows can refuse a replace while a reader holds the file, so retry."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    # A scanner (Windows Defender) or a poll of status.json can hold the new file for a second or more.
    # Up to about 18 s in total, because a lost final status turns a finished render into an error.
    for attempt in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 39:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(min(0.05 * (attempt + 1), 0.5))


def _read_json(path: Path) -> dict | None:
    """The JSON object in `path`, or None when missing or unreadable after a few tries."""
    for attempt in range(5):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):  # half-written or locked: try again
            time.sleep(0.02 * (attempt + 1))
            continue
        return data if isinstance(data, dict) else None
    return None


def _log_tail(job_dir: Path, limit: int = ERROR_TAIL_CHARS) -> str:
    try:
        text = (job_dir / "log.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text.strip()[-limit:]


# ------------------------------------------------------------------ liveness

def pid_alive(pid: int | None) -> bool:
    """Whether a process with this pid exists.

    `os.kill(pid, 0)` is not an existence probe on Windows (signal 0 is Ctrl+C
    there), so Windows asks the process API instead.
    """
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists, we may not query it
        try:
            code = ctypes.c_uint32()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _worker_alive(job_id: str, status: dict, job: dict) -> bool:
    """Is the worker of a queued/running job still there (and not stuck)?"""
    now = time.time()
    started = float(status.get("started") or job.get("created") or now)
    proc = _PROCS.get(job_id)
    if proc is not None:
        if proc.poll() is not None:  # also reaps a zombie on POSIX
            _PROCS.pop(job_id, None)
            return False
        alive = True
    elif status.get("pid"):
        alive = pid_alive(int(status["pid"]))
    else:
        # server restarted, or the worker has not written its pid yet
        alive = now - float(job.get("created") or now) < START_GRACE_S
    if alive and now - started > MAX_RUN_S:
        if proc is not None:
            proc.kill()  # only a process this server started: a stored pid could have been reused
        return False
    return alive


# ------------------------------------------------------------------ registry

def register(kind: str) -> Callable[[JobFn], JobFn]:
    """Decorator: make `fn(payload, report) -> dict` the worker function for `kind`."""

    def deco(fn: JobFn) -> JobFn:
        _REGISTRY[kind] = fn
        return fn

    return deco


def _resolve(kind: str) -> JobFn:
    if kind in _REGISTRY:
        return _REGISTRY[kind]
    if not _KIND_RE.fullmatch(kind):
        raise ValueError(f"invalid job kind {kind!r}")
    try:
        module = importlib.import_module(f"argus.tools.{kind}")
    except ModuleNotFoundError as exc:
        if exc.name != f"argus.tools.{kind}":
            raise
        raise ValueError(f"unknown job kind {kind!r}") from exc
    if kind in _REGISTRY:  # the module registered itself on import
        return _REGISTRY[kind]
    fn = getattr(module, "run_job", None)
    if fn is None:
        raise ValueError(f"argus.tools.{kind} has no run_job(payload, report) for job kind {kind!r}")
    return fn


@register("selftest")
def _selftest(payload: dict, report: Callable[..., None]) -> dict:
    """Job used by the tests and as a smoke check of the job machinery.

    payload: `progress` [[p, note], ...] reported first, `sleep` seconds, then
    `fail` (raise ValueError with this text) or `result` (returned as is).
    """
    for p, note in payload.get("progress", []):
        report(p, note)
    time.sleep(float(payload.get("sleep", 0)))
    if payload.get("fail"):
        raise ValueError(str(payload["fail"]))
    return dict(payload.get("result", {}))


# ------------------------------------------------------------------ server side

def _key_hash(kind: str, payload: dict, key: str | None) -> str:
    basis = key if key is not None else json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(f"{kind}\0{basis}".encode()).hexdigest()[:24]


def _live_state(job_id: str) -> tuple[dict, dict] | None:
    """(job, status) of a job, or None if unknown. A worker that died without a result is recorded as `error`."""
    job_dir = _job_dir(job_id)
    job = _read_json(job_dir / "job.json")
    if job is None:
        return None
    status = _read_json(job_dir / "status.json") or {"state": "queued"}
    if status.get("state") in ("queued", "running") and not _worker_alive(job_id, status, job):
        # the worker may have finished between our read and the liveness probe
        status = _read_json(job_dir / "status.json") or status
        if status.get("state") in ("queued", "running"):
            tail = _log_tail(job_dir)
            status = {
                **status,
                "state": "error",
                "finished": time.time(),
                "error": "worker process ended without a result"
                + (f" (pid {status['pid']})" if status.get("pid") else "")
                + (f":\n{tail}" if tail else ""),
            }
            _write_json(job_dir / "status.json", status)
    return job, status


def _find_active(key: str) -> str | None:
    root = jobs_root()
    if not root.is_dir():
        return None
    for job_dir in sorted(root.iterdir(), reverse=True):
        job = _read_json(job_dir / "job.json") if job_dir.is_dir() and _ID_RE.fullmatch(job_dir.name) else None
        if not job or job.get("key") != key:
            continue
        live = _live_state(job_dir.name)
        if live and live[1].get("state") in ("queued", "running"):
            return job_dir.name
    return None


def _start(kind: str, payload: dict, key: str | None) -> tuple[str, bool]:
    """(job_id, reused). Reuses a queued/running job with the same kind + key."""
    if not _KIND_RE.fullmatch(kind):
        raise ValueError(f"invalid job kind {kind!r}")
    key_hash = _key_hash(kind, payload, key)
    with _START_LOCK:
        existing = _find_active(key_hash)
        if existing:
            return existing, True

        job_id = f"{kind}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job_dir = _job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        _write_json(job_dir / "job.json", {
            "id": job_id, "kind": kind, "payload": payload, "key": key_hash, "created": time.time(),
        })
        _write_json(job_dir / "status.json", {
            "state": "queued", "progress": None, "note": None, "started": None, "finished": None,
            "pid": None, "result": None, "error": None,
        })

        creationflags = 0
        extra: dict = {}
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            extra["start_new_session"] = True
        env = {**os.environ, "OMNIFRAME_OUTPUT_DIR": str(Path(CONFIG.output_dir))}
        with open(job_dir / "log.txt", "wb") as log:
            _PROCS[job_id] = subprocess.Popen(
                [sys.executable, "-I", "-m", "argus.jobs", str(job_dir)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
                creationflags=creationflags, env=env, **extra,
            )
        return job_id, False


def start(kind: str, payload: dict, key: str | None = None) -> str:
    """Start a detached job and return its id; an active job with the same kind + key is returned instead.

    `key` identifies the operation (default: the payload itself).
    """
    return _start(kind, payload, key)[0]


def _snapshot(job_id: str) -> dict:
    """Public view of a job (no images handling): job_id, kind, state, progress, note, times, result/error."""
    live = _live_state(job_id)
    if live is None:
        raise FileNotFoundError(f"unknown job_id {job_id!r} (jobs older than 7 days are deleted)")
    job, status = live
    now = time.time()
    began = status.get("started") or job.get("created") or now
    out: dict = {
        "engine": f"ARGUS {__version__}",
        "job_id": job_id,
        "kind": job.get("kind"),
        "state": status.get("state"),
        "progress": status.get("progress"),
        "note": status.get("note"),
        "elapsed_s": round(float(status.get("finished") or now) - float(began), 1),
    }
    progress = status.get("progress")
    if out["state"] == "running" and isinstance(progress, (int, float)) and 0 < progress < 1:
        # Linear estimate from the time spent so far; a rough number, not a promise.
        out["eta_s"] = round(out["elapsed_s"] * (1 - progress) / progress, 1)
    if status.get("state") == "done":
        out["result"] = status.get("result") or {}
    elif status.get("state") == "error":
        out["error"] = status.get("error") or "unknown error"
    return out


def status(job_id: str) -> dict:
    """Current status of a job as a dict (see `_snapshot`); raises FileNotFoundError for an unknown id."""
    return _snapshot(job_id)


def _with_images(summary: dict, entries: object, max_side: int | None = None) -> dict | list:
    """`summary` plus its `images` entries as MCP image content when the files exist.

    The model needs the entries (timecode + path) either way: without image support
    in the client it opens the paths itself (requirement 3.4).
    """
    from .media_out import DEFAULT_MAX_SIDE, tool_result

    if not isinstance(entries, list) or not entries:
        return summary
    paths = [Path(e["path"]) for e in entries if isinstance(e, dict) and e.get("path")]
    if len(paths) != len(entries) or not all(p.is_file() for p in paths):
        return {**summary, "images": entries}
    return tool_result({**summary, "images": entries}, paths, max_side=max_side or DEFAULT_MAX_SIDE)


def _image_max_side(result: dict) -> int | None:
    """`image_max_side` of a job result: the longest side its images may keep (default 1024).

    A job whose pictures need more pixels than a single frame (a contact sheet) sets it.
    """
    value = result.get("image_max_side")
    return int(value) if isinstance(value, int) and value > 0 else None


def result_for_model(result: dict) -> dict | list:
    """A job result as a tool return value: with `images` entries it becomes `[json, Image, ...]`."""
    summary = {k: v for k, v in result.items() if k != "image_max_side"}
    return _with_images(summary, result.get("images"), _image_max_side(result))


def clamp_status_wait(wait_s: float | None) -> float:
    """`job_status` waits at most `MAX_STATUS_WAIT_S` seconds; negative or missing means no wait."""
    try:
        value = float(wait_s or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    return min(max(0.0, value), MAX_STATUS_WAIT_S)


def job_status(job_id: str, wait_s: float = 0.0) -> dict | list:
    """Tool logic of `job_status`: status dict, or `[json, Image, ...]` when the result has images.

    With `wait_s` it waits, polling, until the job is done or failed or the time is up.
    """
    deadline = time.monotonic() + clamp_status_wait(wait_s)
    snap = _snapshot(job_id)
    while snap["state"] not in ("done", "error") and time.monotonic() < deadline:
        time.sleep(max(0.0, min(POLL_S, deadline - time.monotonic())))
        snap = _snapshot(job_id)
    result = snap.get("result")
    if snap["state"] == "done" and isinstance(result, dict) and result.get("images"):
        kept = {k: v for k, v in result.items() if k not in ("images", "image_max_side")}
        return _with_images({**snap, "result": kept}, result["images"], _image_max_side(result))
    return snap


def run_or_detach(
    kind: str,
    payload: dict,
    key: str | None = None,
    wait_s: float = DEFAULT_WAIT_S,
) -> dict | list:
    """Run a job and wait up to `wait_s` seconds.

    Done in time: the job result (`[json, Image, ...]` when it has images).
    Failed in time: `{"state": "error", "error": <tail>, "job_id": ...}`.
    Still running: `{"job_id", "state", "progress", "note"}`: poll `job_status`.
    """
    job_id, reused = _start(kind, payload, key)
    deadline = time.monotonic() + max(0.0, wait_s)
    while True:
        snap = _snapshot(job_id)
        if snap["state"] == "done":
            return result_for_model({"engine": f"ARGUS {__version__}", **snap["result"]})
        if snap["state"] == "error":
            return {k: snap[k] for k in ("engine", "job_id", "kind", "state", "error")}
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_S)
    snap["note"] = (
        "still running in a background process; call job_status with this job_id to follow it"
        + (" (an identical job was already running)" if reused else "")
    )
    return {k: snap[k] for k in ("engine", "job_id", "kind", "state", "progress", "note", "elapsed_s")}


def project_render_totals(project_root: Path) -> dict:
    """Sum of the `timing` of the finished `render` jobs of one project, in seconds.

    Counts the job folders still kept (7 days). `jobs` is the number of renders summed.
    """
    totals: dict = {"jobs": 0}
    root = jobs_root()
    if not root.is_dir():
        return totals
    for job_dir in root.iterdir():
        if not (job_dir.is_dir() and _ID_RE.fullmatch(job_dir.name)):
            continue
        live = _live_state(job_dir.name)
        if live is None:
            continue
        job, status = live
        payload = job.get("payload") or {}
        if job.get("kind") != "render" or status.get("state") != "done":
            continue
        if Path(str(payload.get("project_root", ""))) != Path(project_root):
            continue
        timing = (status.get("result") or {}).get("timing") or {}
        totals["jobs"] += 1
        for key, value in timing.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = round(totals.get(key, 0.0) + value, 3)
    return totals


def cleanup_old_jobs(max_age_s: float = RETENTION_S, now: float | None = None) -> int:
    """Delete job folders not touched for `max_age_s` seconds. Active jobs are kept. Returns the count."""
    root = jobs_root()
    if not root.is_dir():
        return 0
    now = time.time() if now is None else now
    removed = 0
    for job_dir in root.iterdir():
        if not job_dir.is_dir():
            continue
        try:
            newest = max(p.stat().st_mtime for p in (job_dir, *job_dir.iterdir()))
        except OSError:
            continue
        if now - newest < max_age_s:
            continue
        if _ID_RE.fullmatch(job_dir.name):
            live = _live_state(job_dir.name)
            if live and live[1].get("state") in ("queued", "running"):
                continue
        shutil.rmtree(job_dir, ignore_errors=True)
        removed += not job_dir.exists()
    return removed


# ------------------------------------------------------------------ worker side

def _worker_main(job_dir: Path) -> int:
    job = _read_json(job_dir / "job.json")
    if job is None:
        print(f"no job.json in {job_dir}", file=sys.stderr)
        return 2
    status_path = job_dir / "status.json"
    state: dict = _read_json(status_path) or {}

    def update(**fields: object) -> None:
        state.update(fields)
        _write_json(status_path, state)

    def report(progress: float | None = None, note: str | None = None) -> None:
        fields: dict = {}
        if progress is not None:
            fields["progress"] = max(0.0, min(1.0, float(progress)))
        if note is not None:
            fields["note"] = str(note)
        if fields:
            update(**fields)

    update(state="running", pid=os.getpid(), started=time.time())
    try:
        result = _resolve(str(job["kind"]))(job.get("payload") or {}, report)
        if not isinstance(result, dict):
            raise TypeError(f"job function returned {type(result).__name__}, expected dict")
        json.dumps(result, default=str)  # fail here, not while writing status
        update(state="done", progress=1.0, finished=time.time(), result=result, error=None)
        return 0
    except BaseException as exc:  # noqa: BLE001 - every failure must end up in status.json
        trace = traceback.format_exc()
        print(trace, file=sys.stderr)
        update(state="error", finished=time.time(), error=trace.strip()[-ERROR_TAIL_CHARS:])
        return 1 if isinstance(exc, Exception) else 130


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m argus.jobs <job_dir>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(_worker_main(Path(sys.argv[1])))

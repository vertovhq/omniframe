"""User scripts: Python files the model can run through `run_script` (design §13, requirement 14).

A script is a `.py` file in `<repo>/scripts/` or in `ARGUS_SCRIPTS_DIR`. Its module docstring
starts with a one-line summary and has a line `Args: {...}` with an example argument. Listing
reads that docstring with `ast`, so listing never runs a script.

A run starts `python -P <script> <args.json>` in the project folder (when `args.project` is set)
or in the output folder. The script prints its result as one JSON object on the last line of
stdout. A result may list `images`, which come back as pictures. The run goes through the
`scripts_runner` job, so a slow script keeps running after the MCP call returns.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from .. import __version__, jobs
from ..config import CONFIG, REPO_ROOT
from ..project import project_dir

JOB_KIND = "scripts_runner"
SCRIPT_NAME = re.compile(r"[a-z0-9_]{1,40}")
DEFAULT_TIMEOUT_S = 120.0
MIN_TIMEOUT_S = 1.0
MAX_TIMEOUT_S = 3600.0          # the job worker itself gives up after 4 hours
TAIL_CHARS = 1500
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window per script


def script_folders() -> list[Path]:
    """Where scripts are looked up, in order: `<repo>/scripts/`, then `ARGUS_SCRIPTS_DIR`."""
    folders: list[Path] = []
    for folder in (REPO_ROOT / "scripts", Path(CONFIG.scripts_dir)):
        resolved = folder.resolve()
        if resolved not in folders:
            folders.append(resolved)
    return folders


def find_script(name: str) -> Path | None:
    """The file of a valid script name in the first folder that has it, or None."""
    for folder in script_folders():
        path = folder / f"{name}.py"
        if path.is_file():
            return path
    return None


def _describe(path: Path) -> dict:
    """Summary and argument example from a script's module docstring. The file is parsed, never run."""
    entry: dict = {"name": path.stem, "summary": "", "args": None, "path": str(path)}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, ValueError) as exc:
        entry["error"] = f"cannot read the script: {exc}"
        return entry
    lines = [line.strip() for line in (ast.get_docstring(tree) or "").splitlines()]
    entry["summary"] = next((line for line in lines if line and not line.startswith("Args:")), "")
    entry["args"] = next((line[len("Args:"):].strip() for line in lines if line.startswith("Args:")), None)
    if not entry["summary"] or entry["args"] is None:
        entry["note"] = "the module docstring needs a one-line summary and an 'Args: {...}' line"
    return entry


def list_scripts() -> dict:
    """Every valid script name in the script folders. A name in two folders is listed once, from the first."""
    scripts: dict[str, dict] = {}
    for folder in script_folders():
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py")):
            if SCRIPT_NAME.fullmatch(path.stem) and path.stem not in scripts:
                scripts[path.stem] = _describe(path)
    return {
        "engine": f"ARGUS {__version__}",
        "scripts": [scripts[name] for name in sorted(scripts)],
        "folders": [str(folder) for folder in script_folders()],
    }


def _error(message: str, **extra: object) -> dict:
    return {"engine": f"ARGUS {__version__}", "ok": False, "error": message, **extra}


def _checked_timeout(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if MIN_TIMEOUT_S <= value <= MAX_TIMEOUT_S else None


def run_script(name: str | None = None, args: dict | None = None, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict | list:
    """Tool logic of `run_script`: list the scripts when `name` is None, otherwise run one through a job."""
    if name is None:
        return list_scripts()
    if not isinstance(name, str) or not SCRIPT_NAME.fullmatch(name):
        return _error(f"invalid script name {name!r}: use 1 to 40 lowercase letters, digits or underscores")
    if args is not None and not isinstance(args, dict):
        return _error('args must be a JSON object, for example {"key": "value"}')
    timeout = _checked_timeout(timeout_s)
    if timeout is None:
        return _error(f"timeout_s must be a number from {MIN_TIMEOUT_S:g} to {MAX_TIMEOUT_S:g}, got {timeout_s!r}")
    script = find_script(name)
    if script is None:
        known = [entry["name"] for entry in list_scripts()["scripts"]]
        return _error(f"no script named {name!r}", available=known)

    args = dict(args or {})
    project = args.get("project")
    try:
        if project is None:
            cwd = Path(CONFIG.output_dir)
            cwd.mkdir(parents=True, exist_ok=True)
        elif isinstance(project, str):
            cwd = project_dir(project)
        else:
            return _error("args.project must be a project name")
    except ValueError as exc:
        return _error(str(exc))

    payload = {"name": name, "script": str(script), "args": args, "timeout_s": timeout, "cwd": str(cwd)}
    return jobs.run_or_detach(JOB_KIND, payload)


def _tail(text: str) -> str:
    return text.strip()[-TAIL_CHARS:]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _failed(name: str, message: str, stderr: str, stdout: str | None = None) -> dict:
    out: dict = {"name": name, "ok": False, "error": message}
    if stdout is not None and stdout.strip():
        out["stdout_tail"] = _tail(stdout)
    if stderr.strip():
        out["stderr_tail"] = _tail(stderr)
    return out


def _last_json_object(stdout: str) -> dict | None:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        value = json.loads(lines[-1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _image_entries(raw: object, cwd: Path) -> tuple[list[dict], list[str]]:
    """Existing image files a result lists, as `{"path", "full_path"}` entries, and the paths that do not exist.

    Relative paths are relative to the folder the script ran in.
    """
    if raw is None:
        return [], []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("the result's 'images' must be a list of file paths")
    entries: list[dict] = []
    missing: list[str] = []
    for item in raw:
        path = Path(item)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if path.is_file():
            entries.append({"path": str(path), "full_path": str(path)})
        else:
            missing.append(item)
    return entries, missing


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Worker side of `run_script` (job kind `scripts_runner`): run one script and read its result.

    A script that fails, prints no JSON, or runs past its timeout gives `ok: false` with the
    reason and the tail of its output; the job itself still ends as done.
    """
    name = str(payload["name"])
    cwd = Path(payload["cwd"])
    timeout_s = float(payload["timeout_s"])
    report(None, f"running {name}")

    scratch_root = Path(CONFIG.output_dir) / ".scripts"
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=scratch_root) as scratch:
        scratch_dir = Path(scratch)
        args_file = scratch_dir / "args.json"
        args_file.write_text(json.dumps(payload.get("args") or {}, ensure_ascii=False), encoding="utf-8")
        stdout_file = scratch_dir / "stdout.txt"
        stderr_file = scratch_dir / "stderr.txt"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

        # Output goes to files, not pipes: a grandchild that outlives a killed script cannot
        # keep subprocess waiting for output.
        with stdout_file.open("wb") as out, stderr_file.open("wb") as err:
            try:
                proc = subprocess.run(
                    [sys.executable, "-P", str(payload["script"]), str(args_file)],
                    cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    timeout=timeout_s, creationflags=_NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                stderr_text = _read(stderr_file)
                timed_out: dict = {
                    "name": name, "ok": False, "timed_out": True, "timeout_s": timeout_s,
                    "error": f"the script was stopped after {timeout_s:g} s without finishing",
                }
                if stderr_text.strip():
                    timed_out["stderr_tail"] = _tail(stderr_text)
                return timed_out
        stdout = _read(stdout_file)
        stderr = _read(stderr_file)

        if proc.returncode != 0:
            return _failed(name, f"the script exited with code {proc.returncode}", stderr)
        result = _last_json_object(stdout)
        if result is None:
            return _failed(name, "the script did not print a JSON object as the last line of stdout", stderr, stdout)
        try:
            entries, missing = _image_entries(result.pop("images", None), cwd)
        except ValueError as exc:
            return _failed(name, str(exc), stderr)

    out_result: dict = {"name": name, "ok": True, "result": result}
    if entries:
        out_result["images"] = entries
    if missing:
        out_result["missing_images"] = missing
    return out_result

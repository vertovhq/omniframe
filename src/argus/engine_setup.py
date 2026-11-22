"""Where the Remotion render engine lives, and how it is installed without a repository checkout.

The engine is chosen in this order:

1. `ARGUS_ENGINE_DIR`, when it is set.
2. The `engine/` folder of a repository checkout (development).
3. A package install (`uvx`, Kiro Power). The wheel carries the engine as `argus/_engine`.
   On the first server start it is copied to `~/.argus/engine`, and `npm install` plus
   `remotion browser ensure` run there in a detached process. The state is kept in
   `~/.argus/engine-setup.json`, the output in `~/.argus/engine-setup.log`. `argus-doctor` shows both.

The installer can also run in the foreground: `python -m argus.engine_setup`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .ffmpeg import NO_WINDOW

# Version of the files copied from the package. A new ARGUS version copies them again.
PACKAGE_MARKER = ".argus-engine-version"
# Version whose Node packages and Remotion browser were installed. Written only for package installs.
READY_MARKER = ".argus-engine-ready"


def argus_home() -> Path:
    """`~/.argus`: state, the engine copy and the optional `.env` for package installs."""
    return Path.home() / ".argus"


def repo_engine() -> Path:
    # src/argus/engine_setup.py -> parents[2] is the repository root
    return Path(__file__).resolve().parents[2] / "engine"


def packaged_engine() -> Path:
    return Path(__file__).resolve().parent / "_engine"


def user_engine() -> Path:
    return argus_home() / "engine"


def status_path() -> Path:
    return argus_home() / "engine-setup.json"


def log_path() -> Path:
    return argus_home() / "engine-setup.log"


def _override() -> str:
    return os.environ.get("ARGUS_ENGINE_DIR", "").strip()


def is_packaged() -> bool:
    """True when ARGUS runs from an installed package, not from a repository checkout."""
    return not _override() and not (repo_engine() / "package.json").is_file()


def resolve_engine_dir() -> Path:
    override = _override()
    if override:
        return Path(override).resolve()
    if (repo_engine() / "package.json").is_file():
        return repo_engine()
    return user_engine()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def sync_packaged_engine() -> Path:
    """Copy the engine that comes with the package into `~/.argus/engine`, if missing or from another version."""
    dst = user_engine()
    src = packaged_engine()
    if not (src / "package.json").is_file():
        return dst
    if (dst / "package.json").is_file() and _read_text(dst / PACKAGE_MARKER) == __version__:
        return dst
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    (dst / PACKAGE_MARKER).write_text(__version__, encoding="utf-8")
    return dst


def engine_ready() -> bool:
    eng = resolve_engine_dir()
    if not (eng / "package.json").is_file() or not (eng / "node_modules" / "remotion").is_dir():
        return False
    if is_packaged():
        return _read_text(eng / READY_MARKER) == __version__
    return True


def read_status() -> dict:
    try:
        return json.loads(status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_status(**fields) -> None:
    current = read_status()
    current.update(fields)
    current["updated"] = time.time()
    argus_home().mkdir(parents=True, exist_ok=True)
    tmp = status_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
    os.replace(tmp, status_path())


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def installer_running() -> bool:
    status = read_status()
    return status.get("state") == "installing" and _pid_alive(int(status.get("pid") or 0))


def ensure_started() -> dict:
    """Start the background installer when a package install has no ready engine. Never waits."""
    if not is_packaged() or engine_ready() or installer_running():
        return read_status()
    argus_home().mkdir(parents=True, exist_ok=True)
    with open(log_path(), "a", encoding="utf-8") as log:
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            [sys.executable, "-m", "argus.engine_setup"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(argus_home()), **kwargs,
        )
    _write_status(state="installing", step="starting", pid=proc.pid, error="", started=time.time())
    return read_status()


def not_ready_message() -> str:
    """Why a render cannot start yet, for the model and for the user."""
    if not is_packaged():
        return f"The engine is not installed: run `npm install` inside {resolve_engine_dir()}."
    status = read_status()
    state = status.get("state")
    if state == "installing" and _pid_alive(int(status.get("pid") or 0)):
        return (
            f"The render engine is still installing in the background (step: {status.get('step') or 'starting'}). "
            f"Wait, then run argus-doctor. Log: {log_path()}"
        )
    if state == "error":
        return (
            f"The render engine could not be installed: {status.get('error')}. "
            f"Fix it, then restart the argus-studio MCP server. Log: {log_path()}"
        )
    return (
        "The render engine is not installed yet. Restart the argus-studio MCP server, which installs it "
        "in the background, or run `python -m argus.engine_setup`."
    )


def _fail(message: str) -> int:
    _write_status(state="error", error=message, pid=0)
    print(f"[engine] error: {message}", flush=True)
    return 1


def install() -> int:
    """Copy the packaged engine, then install its Node packages and the Remotion browser. Returns an exit code."""
    _write_status(state="installing", step="copy", pid=os.getpid(), error="", started=time.time())
    try:
        eng = sync_packaged_engine()
        if not (eng / "package.json").is_file():
            return _fail(f"engine files not found (expected {eng / 'package.json'})")
        npm = shutil.which("npm")
        npx = shutil.which("npx")
        if not npm or not npx:
            return _fail("Node.js 18 or newer (npm and npx) is not on PATH. Install it, then restart the MCP server.")
        log = log_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        steps = [
            ("npm install", [npm, "install", "--no-audit", "--no-fund"]),
            ("remotion browser", [npx, "remotion", "browser", "ensure"]),
        ]
        for step, cmd in steps:
            _write_status(step=step)
            print(f"[engine] {step} in {eng}", flush=True)
            with open(log, "a", encoding="utf-8") as out:
                out.write(f"\n== {step} ({__version__}, {time.strftime('%Y-%m-%d %H:%M:%S')}) ==\n")
                out.flush()
                rc = subprocess.run(
                    cmd, cwd=str(eng), stdout=out, stderr=subprocess.STDOUT, check=False,
                    creationflags=NO_WINDOW if os.name == "nt" else 0,
                ).returncode
            if rc != 0:
                return _fail(f"{step} failed with exit code {rc}; see {log}")
        if is_packaged():
            (eng / READY_MARKER).write_text(__version__, encoding="utf-8")
        _write_status(state="ready", step="", pid=0, error="")
        print("[engine] ready", flush=True)
        return 0
    except Exception as exc:  # the status file must say what went wrong
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(install())

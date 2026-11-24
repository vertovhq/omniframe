"""argus doctor — one-command environment self-check.

Verifies everything the pipeline needs before a new user hits "nothing works".
Critical: python, ffmpeg, ffprobe, Node.js + npx, the engine (node_modules with remotion
and the renderer/bundler packages), numpy, Pillow and OMNIFRAME_OUTPUT_DIR. Optional (a
warning, never an error): faster-whisper, edge-tts (installed + service alive),
a Chrome or Edge for the renderer (otherwise Remotion downloads its own browser), the Gemini key
and the ElevenLabs key.

Console:  argus-doctor [--json] [--no-live]
MCP:      doctor() -> the same report as JSON.
Exit code 0 when every critical check passed (warnings are fine).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .config import ArgusConfig, load_config
from .ffmpeg import NO_WINDOW

# ids whose failure flips the exit code / report["ok"]; warnings never do
CRITICAL_IDS = frozenset({"python", "ffmpeg", "ffprobe", "node", "npx", "engine", "numpy", "pillow", "output_dir"})

# packages the renderer needs inside engine/node_modules (engine/package.json)
ENGINE_PACKAGES = ("remotion", "@remotion/renderer", "@remotion/bundler")

HINT_NODE = "install Node.js 18+: winget install OpenJS.NodeJS.LTS (or https://nodejs.org)"
HINT_FFMPEG = "install ffmpeg: winget install Gyan.FFmpeg (or choco install ffmpeg, or https://www.gyan.dev/ffmpeg/builds/)"
HINT_CORE = 'pip install -e .  (numpy and Pillow are core dependencies)'
HINT_EDGE = 'pip install edge-tts  (or pip install -e ".[voice]")'
HINT_ASR = 'pip install -e ".[asr]"  (faster-whisper)'

# 1-word live synthesis probe for edge-tts (runs in a child python, 15s budget)
_EDGE_PROBE = (
    "import asyncio, sys, edge_tts; "
    "asyncio.run(edge_tts.Communicate('hello', 'en-US-AriaNeural').save(sys.argv[1]))"
)


def _which(exe: str) -> str | None:
    """shutil.which alias — tests swap this to pin fake executable paths."""
    return shutil.which(exe)


def _run(cmd: list[str], timeout: float = 20.0, cwd: str | Path | None = None):
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, creationflags=NO_WINDOW,
    )


def _check(cid: str, label: str, status: str, detail: str = "", hint: str = "") -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail, "hint": hint}


# --------------------------------------------------------------------- checks

def check_python() -> dict:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 11):
        return _check("python", "python", "ok", detail)
    return _check(
        "python", "python", "fail", detail,
        "Python 3.11+ is needed: winget install Python.Python.3.12 (or https://python.org)",
    )


def _exe_status(cid: str, label: str, exe: str, env_var: str) -> dict:
    resolved = _which(exe)
    if not resolved:
        via = f" (from {env_var})" if os.environ.get(env_var, "").strip() else ""
        return _check(cid, label, "fail", f"not found{via}: {exe}", HINT_FFMPEG)
    try:
        p = _run([resolved, "-version"])
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check(cid, label, "fail", f"{resolved}: {e}", HINT_FFMPEG)
    if p.returncode != 0:
        return _check(cid, label, "fail", resolved, HINT_FFMPEG)
    m = re.search(r"(ffmpeg|ffprobe) version (\S+)", p.stdout or "")
    version = m.group(2) if m else "?"
    return _check(cid, label, "ok", f"{version} — {resolved}")


def check_ffmpeg(cfg: ArgusConfig) -> dict:
    return _exe_status("ffmpeg", "ffmpeg", cfg.ffmpeg, "ARGUS_FFMPEG")


def check_ffprobe(cfg: ArgusConfig) -> dict:
    return _exe_status("ffprobe", "ffprobe", cfg.ffprobe, "ARGUS_FFPROBE")


def _check_module(cid: str, label: str, module: str, missing_status: str, hint: str, note: str = "") -> dict:
    """Import `module` in a child python: ok when it loads, `missing_status` otherwise."""
    try:
        p = _run([sys.executable, "-c", f"import {module}"], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check(cid, label, missing_status, str(e), hint)
    if p.returncode != 0:
        detail = "module not installed" + (f"; {note}" if note else "")
        return _check(cid, label, missing_status, detail, hint)
    return _check(cid, label, "ok", "installed")


def check_numpy() -> dict:
    return _check_module("numpy", "numpy", "numpy", "fail", HINT_CORE)


def check_pillow() -> dict:
    return _check_module("pillow", "Pillow", "PIL", "fail", HINT_CORE)


def check_faster_whisper() -> dict:
    # optional: without it, watch_video returns no transcript (frames and sound events still work)
    return _check_module(
        "faster_whisper", "faster-whisper", "faster_whisper", "warn", HINT_ASR,
        "optional: without it, watch_video returns no transcript",
    )


def _node_version(exe: str) -> dict:
    try:
        p = _run([exe, "--version"])
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check("node", "node", "fail", str(e), HINT_NODE)
    m = re.match(r"v?(\d+)", (p.stdout or "").strip())
    if p.returncode != 0 or not m:
        return _check("node", "node", "fail", (p.stderr or "").strip()[:120] or exe, HINT_NODE)
    major = int(m.group(1))
    if major < 18:
        return _check("node", "node", "fail", f"v{major} (18+ needed)", HINT_NODE)
    return _check("node", "node", "ok", f"v{major}")


def check_node() -> dict:
    exe = _which("node")
    if not exe:
        return _check("node", "node", "fail", "not found on PATH", HINT_NODE)
    return _node_version(exe)


def check_npx() -> dict:
    exe = _which("npx")
    if not exe:
        return _check("npx", "npx", "fail", "not found on PATH", HINT_NODE)
    try:
        p = _run([exe, "--version"])
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check("npx", "npx", "fail", str(e), HINT_NODE)
    if p.returncode != 0:
        return _check("npx", "npx", "fail", (p.stderr or "").strip()[:120], HINT_NODE)
    return _check("npx", "npx", "ok", (p.stdout or "").strip())


def check_engine() -> dict:
    from . import engine_setup

    if engine_setup.is_packaged():
        return _check_packaged_engine(engine_setup)
    eng = engine_setup.resolve_engine_dir()
    if not (eng / "package.json").exists():
        return _check(
            "engine", "engine/ (Remotion)", "fail", f"engine not found: {eng}",
            "clone the argus-studio repo, or set ARGUS_ENGINE_DIR to the engine/ folder",
        )
    install = f"cd {eng} && npm install --no-audit --no-fund"
    modules = eng / "node_modules"
    if not modules.exists():
        return _check("engine", "engine/ (Remotion)", "fail", f"node_modules missing: {eng}", install)
    missing = [name for name in ENGINE_PACKAGES if not (modules / name).is_dir()]
    if missing:
        return _check(
            "engine", "engine/ (Remotion)", "fail", f"render packages missing: {', '.join(missing)} ({eng})", install,
        )
    return _check("engine", "engine/ (Remotion)", "ok", str(eng))


def _check_packaged_engine(engine_setup) -> dict:
    """Engine from a package install: its state comes from the background installer."""
    label = "engine/ (Remotion)"
    eng = engine_setup.resolve_engine_dir()
    if engine_setup.engine_ready():
        return _check("engine", label, "ok", f"{eng} (installed by ARGUS {__version__})")
    status = engine_setup.read_status()
    state = status.get("state")
    if state == "installing" and engine_setup._pid_alive(int(status.get("pid") or 0)):
        return _check(
            "engine", label, "warn",
            f"installing in the background, step: {status.get('step') or 'starting'}; log: {engine_setup.log_path()}",
            "wait and run argus-doctor again",
        )
    if state == "error":
        return _check(
            "engine", label, "fail", str(status.get("error") or "install failed"),
            f"fix the problem, restart the argus-studio MCP server to retry; log: {engine_setup.log_path()}",
        )
    return _check(
        "engine", label, "fail", "not installed yet",
        "restart the argus-studio MCP server (it installs the engine in the background), "
        "or run: python -m argus.engine_setup",
    )


def check_render_browser() -> dict:
    """The browser the renderer uses. Without Chrome or Edge, Remotion downloads its own."""
    try:
        from .tools.render import _find_browser
    except ImportError as e:  # the render module needs Pillow; its own check reports that
        return _check("render_browser", "render browser", "warn", f"could not check: {e}")
    found = _find_browser()
    if found:
        return _check("render_browser", "render browser", "ok", found)
    return _check(
        "render_browser", "render browser", "warn",
        "no Chrome or Edge found; Remotion downloads its own headless browser on the first render",
        "optional: set REMOTION_BROWSER to a Chrome or Edge executable to skip the download",
    )


def probe_edge(retries: int = 2, timeout: float = 15.0) -> tuple[bool, str]:
    """1-word live synthesis; returns (alive, last_error). Direct subprocess.run
    so the 15s per-attempt budget is enforced even if the service hangs."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td, "probe.mp3")
        last = ""
        for attempt in range(retries):
            if attempt:
                time.sleep(1.5)  # edge throttles back-to-back requests (see KNOWLEDGE_BASE)
            try:
                p = subprocess.run(
                    [sys.executable, "-c", _EDGE_PROBE, str(out)],
                    capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                last = f"timeout after {timeout:.0f} s"
                continue
            if p.returncode == 0 and out.exists() and out.stat().st_size > 0:
                return True, ""
            lines = (p.stderr or p.stdout or "").strip().splitlines()
            last = lines[-1] if lines else "empty result"
        return False, last


def check_edge_tts(live: bool) -> dict:
    try:
        p = _run([sys.executable, "-c", "import edge_tts"], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check("edge_tts", "edge-tts", "warn", str(e), HINT_EDGE)
    if p.returncode != 0:
        # optional: the free voice; Gemini and ElevenLabs (with keys) are the alternatives
        return _check("edge_tts", "edge-tts", "warn", "module not installed; optional: the free voice", HINT_EDGE)
    if not live:
        return _check("edge_tts", "edge-tts", "ok", "installed (live probe skipped)")
    alive, err = probe_edge()
    if alive:
        return _check("edge_tts", "edge-tts", "ok", "installed, service answers")
    return _check(
        "edge_tts", "edge-tts", "warn", f"installed, but the service is silent ({err})",
        "check the network or proxy (speech.platform.bing.com); this is a temporary service error, not an environment problem",
    )


def check_gemini_key(cfg: ArgusConfig) -> dict:
    if cfg.gemini_api_key:
        return _check("gemini_key", "Gemini key", "ok", "set (Gemini TTS available)")
    return _check(
        "gemini_key", "Gemini key", "warn", "not set; offline tools work, Gemini TTS does not",
        "copy .env.example to .env and set ARGUS_GEMINI_API_KEY (or export the variable)",
    )


def check_elevenlabs_key(cfg: ArgusConfig) -> dict:
    # optional: needed only for the ElevenLabs voice
    if cfg.elevenlabs_api_key:
        return _check("elevenlabs_key", "ElevenLabs key", "ok", "set (voice clones available)")
    return _check(
        "elevenlabs_key", "ElevenLabs key", "warn", "not set; not required, edge and gemini work without it",
        "voice clones: set ELEVENLABS_API_KEY in .env (or export it), only if you need them",
    )


def check_output_dir(cfg: ArgusConfig) -> dict:
    try:
        if cfg.output_dir.exists():
            return _check("output_dir", "output folder", "ok", str(cfg.output_dir))
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        return _check("output_dir", "output folder", "ok", f"created: {cfg.output_dir}")
    except OSError as e:
        return _check(
            "output_dir", "output folder", "fail", f"{cfg.output_dir}: {e}",
            "check OMNIFRAME_OUTPUT_DIR and the folder permissions",
        )


# ------------------------------------------------------------------- report

def run_checks(live: bool = True, config: ArgusConfig | None = None) -> dict:
    """Run every check and return the report dict (same shape for CLI and MCP)."""
    cfg = config if config is not None else load_config()

    checks = [
        check_python(),
        check_ffmpeg(cfg),
        check_ffprobe(cfg),
        check_node(),
        check_npx(),
        check_engine(),
        check_render_browser(),
        check_numpy(),
        check_pillow(),
        check_faster_whisper(),
        check_edge_tts(live),
        check_gemini_key(cfg),
        check_elevenlabs_key(cfg),
        check_output_dir(cfg),
    ]
    critical_failures = [c["id"] for c in checks if c["status"] == "fail" and c["id"] in CRITICAL_IDS]
    return {
        "argus": __version__,
        "platform": sys.platform,
        "live": live,
        "checks": checks,
        "critical_failures": critical_failures,
        "ok": not critical_failures,
    }


def render_text(report: dict) -> str:
    marks = {"ok": "✓", "fail": "✗", "warn": "⚠"}
    lines = [
        f"ARGUS doctor v{report['argus']} — {report['platform']}, "
        f"python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        + (" | no live probes" if not report["live"] else ""),
        "",
    ]
    for c in report["checks"]:
        lines.append(f"{marks[c['status']]} {c['label']:<20} {c['detail']}".rstrip())
        if c["hint"]:
            lines.append(f"   → {c['hint']}")
    warns = sum(1 for c in report["checks"] if c["status"] == "warn")
    fails = len(report["critical_failures"])
    lines.append("")
    if fails:
        lines.append(f"RESULT: ✗ {fails} critical checks failed, warnings: {warns}")
    else:
        lines.append("RESULT: ✓ environment ready" + (f" (warnings: {warns})" if warns else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="argus-doctor", description="ARGUS environment self-check")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--no-live", action="store_true", help="skip network probes (edge-tts service)")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    report = run_checks(live=not args.no_live)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

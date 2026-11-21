"""argus doctor — one-command environment self-check.

Verifies everything the pipeline needs before a new user hits
"ничего не работает". Critical: python, ffmpeg, ffprobe, Node.js + npx, the engine
(node_modules with remotion and the renderer/bundler packages), numpy, Pillow and
OMNIFRAME_OUTPUT_DIR. Optional (a warning, never an error): faster-whisper, edge-tts
(installed + service alive), playwright+chromium (critical only in flow mode), the
Gemini key and the ElevenLabs key.

Console:  argus-doctor [--json] [--flow] [--no-live]
MCP:      doctor(check_flow=False) -> the same report as JSON.
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

HINT_NODE = "установи Node.js 18+: winget install OpenJS.NodeJS.LTS (или https://nodejs.org)"
HINT_FFMPEG = "поставь ffmpeg: winget install Gyan.FFmpeg (или choco install ffmpeg, или https://www.gyan.dev/ffmpeg/builds/)"
HINT_CORE = 'pip install -e .  (numpy и Pillow входят в основные зависимости)'
HINT_EDGE = 'pip install edge-tts  (или pip install -e ".[voice]")'
HINT_ASR = 'pip install -e ".[asr]"  (faster-whisper)'
HINT_FLOW = 'pip install -e ".[flow]" && playwright install chromium'

# 1-word live synthesis probe for edge-tts (runs in a child python, 15s budget)
_EDGE_PROBE = (
    "import asyncio, sys, edge_tts; "
    "asyncio.run(edge_tts.Communicate('привет', 'ru-RU-DmitryNeural').save(sys.argv[1]))"
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
        "нужен Python 3.11+: winget install Python.Python.3.12 (или https://python.org)",
    )


def _exe_status(cid: str, label: str, exe: str, env_var: str) -> dict:
    resolved = _which(exe)
    if not resolved:
        via = f" (из {env_var})" if os.environ.get(env_var, "").strip() else ""
        return _check(cid, label, "fail", f"не найден{via}: {exe}", HINT_FFMPEG)
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
        detail = "модуль не установлен" + (f"; {note}" if note else "")
        return _check(cid, label, missing_status, detail, hint)
    return _check(cid, label, "ok", "установлен")


def check_numpy() -> dict:
    return _check_module("numpy", "numpy", "numpy", "fail", HINT_CORE)


def check_pillow() -> dict:
    return _check_module("pillow", "Pillow", "PIL", "fail", HINT_CORE)


def check_faster_whisper() -> dict:
    # опциональный: без него watch_video не отдаёт транскрипт (кадры и звуковые события работают)
    return _check_module(
        "faster_whisper", "faster-whisper", "faster_whisper", "warn", HINT_ASR,
        "опционально: без него watch_video не отдаёт транскрипт",
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
        return _check("node", "node", "fail", f"v{major} (нужен 18+)", HINT_NODE)
    return _check("node", "node", "ok", f"v{major}")


def check_node() -> dict:
    exe = _which("node")
    if not exe:
        return _check("node", "node", "fail", "не найден в PATH", HINT_NODE)
    return _node_version(exe)


def check_npx() -> dict:
    exe = _which("npx")
    if not exe:
        return _check("npx", "npx", "fail", "не найден в PATH", HINT_NODE)
    try:
        p = _run([exe, "--version"])
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check("npx", "npx", "fail", str(e), HINT_NODE)
    if p.returncode != 0:
        return _check("npx", "npx", "fail", (p.stderr or "").strip()[:120], HINT_NODE)
    return _check("npx", "npx", "ok", (p.stdout or "").strip())


def check_engine() -> dict:
    env = os.environ.get("ARGUS_ENGINE_DIR", "").strip()
    eng = Path(env).resolve() if env else Path(__file__).resolve().parents[2] / "engine"
    if not (eng / "package.json").exists():
        return _check(
            "engine", "engine/ (Remotion)", "fail", f"движок не найден: {eng}",
            "склонируй репо argus-studio или задай ARGUS_ENGINE_DIR на папку engine/",
        )
    install = f"cd {eng} && npm install --no-audit --no-fund"
    modules = eng / "node_modules"
    if not modules.exists():
        return _check("engine", "engine/ (Remotion)", "fail", f"нет node_modules: {eng}", install)
    missing = [name for name in ENGINE_PACKAGES if not (modules / name).is_dir()]
    if missing:
        return _check(
            "engine", "engine/ (Remotion)", "fail", f"нет пакетов рендера: {', '.join(missing)} ({eng})", install,
        )
    return _check("engine", "engine/ (Remotion)", "ok", str(eng))


def probe_edge(retries: int = 2, timeout: float = 15.0) -> tuple[bool, str]:
    """1-word live synthesis; returns (alive, last_error). Direct subprocess.run
    so the 15s per-attempt budget is enforced even if the service hangs."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td, "probe.mp3")
        last = ""
        for attempt in range(retries):
            if attempt:
                time.sleep(1.5)  # edge троттлит подряд-запросы (см. KNOWLEDGE_BASE)
            try:
                p = subprocess.run(
                    [sys.executable, "-c", _EDGE_PROBE, str(out)],
                    capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                last = f"таймаут {timeout:.0f}с"
                continue
            if p.returncode == 0 and out.exists() and out.stat().st_size > 0:
                return True, ""
            lines = (p.stderr or p.stdout or "").strip().splitlines()
            last = lines[-1] if lines else "пустой результат"
        return False, last


def check_edge_tts(live: bool) -> dict:
    try:
        p = _run([sys.executable, "-c", "import edge_tts"], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _check("edge_tts", "edge-tts", "warn", str(e), HINT_EDGE)
    if p.returncode != 0:
        # опциональный: бесплатный голос; без него есть Gemini и ElevenLabs по ключам
        return _check("edge_tts", "edge-tts", "warn", "модуль не установлен; опционально: бесплатный голос", HINT_EDGE)
    if not live:
        return _check("edge_tts", "edge-tts", "ok", "установлен (live-проба пропущена)")
    alive, err = probe_edge()
    if alive:
        return _check("edge_tts", "edge-tts", "ok", "установлен, сервис отвечает")
    return _check(
        "edge_tts", "edge-tts", "warn", f"установлен, но сервис молчит ({err})",
        "проверь сеть/прокси (speech.platform.bing.com); это временная ошибка сервиса, не окружения",
    )


def _playwright_browsers_dir() -> Path:
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env:
        return Path(env)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def check_playwright(flow: bool) -> dict:
    try:
        p = _run([sys.executable, "-c", "import playwright"], timeout=30)
        importable = p.returncode == 0
        err = (p.stderr or "").strip()[:120]
    except (OSError, subprocess.TimeoutExpired) as e:
        importable, err = False, str(e)
    if importable:
        chromiums = sorted(_playwright_browsers_dir().glob("chromium-*"))
        if chromiums:
            return _check("playwright", "playwright+chromium", "ok", f"chromium: {chromiums[-1].name}")
        missing, hint = "chromium не скачан", "playwright install chromium"
    else:
        missing, hint = f"не установлен ({err})", HINT_FLOW
    # отсутствует = пометка «опционально»; критично только в режиме flow
    status = "fail" if flow else "warn"
    note = "опционально, только для provider=\"flow\"" if not flow else "нужен для provider=\"flow\""
    return _check("playwright", "playwright+chromium", status, f"{missing}; {note}", hint)


def check_gemini_key(cfg: ArgusConfig) -> dict:
    if cfg.gemini_api_key:
        return _check("gemini_key", "ключ Gemini", "ok", "есть (Veo api / TTS доступны)")
    return _check(
        "gemini_key", "ключ Gemini", "warn", "нет — offline-тулзы работают, Veo api и Gemini TTS недоступны",
        "cp .env.example .env и впиши ARGUS_GEMINI_API_KEY (или экспортируй переменную)",
    )


def check_elevenlabs_key(cfg: ArgusConfig) -> dict:
    # опциональный: нужен только для голоса ElevenLabs
    if cfg.elevenlabs_api_key:
        return _check("elevenlabs_key", "ключ ElevenLabs", "ok", "есть (клоны голоса доступны)")
    return _check(
        "elevenlabs_key", "ключ ElevenLabs", "warn", "нет — это не обязательно: edge/gemini/xtts работают без него",
        "клоны голоса: впиши ELEVENLABS_API_KEY в .env (или экспортируй) — только если нужны",
    )


def check_output_dir(cfg: ArgusConfig) -> dict:
    try:
        if cfg.output_dir.exists():
            return _check("output_dir", "папка вывода", "ok", str(cfg.output_dir))
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        return _check("output_dir", "папка вывода", "ok", f"создана: {cfg.output_dir}")
    except OSError as e:
        return _check("output_dir", "папка вывода", "fail", f"{cfg.output_dir}: {e}", "проверь OMNIFRAME_OUTPUT_DIR и права на папку")


# ------------------------------------------------------------------- report

def run_checks(flow: bool | None = None, live: bool = True, config: ArgusConfig | None = None) -> dict:
    """Run every check and return the report dict (same shape for CLI and MCP)."""
    cfg = config if config is not None else load_config()
    if flow is None:
        flow = os.environ.get("ARGUS_VEO_PROVIDER", "").strip().lower() == "flow"

    checks = [
        check_python(),
        check_ffmpeg(cfg),
        check_ffprobe(cfg),
        check_node(),
        check_npx(),
        check_engine(),
        check_numpy(),
        check_pillow(),
        check_faster_whisper(),
        check_edge_tts(live),
        check_playwright(flow),
        check_gemini_key(cfg),
        check_elevenlabs_key(cfg),
        check_output_dir(cfg),
    ]
    # playwright становится критичным только в режиме flow (иначе — опциональный ⚠)
    critical_failures = [
        c["id"] for c in checks
        if c["status"] == "fail" and (c["id"] in CRITICAL_IDS or (c["id"] == "playwright" and flow))
    ]
    return {
        "argus": __version__,
        "platform": sys.platform,
        "flow_mode": flow,
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
        + (" | режим flow" if report["flow_mode"] else "")
        + (" | без live-проб" if not report["live"] else ""),
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
        lines.append(f"ИТОГ: ✗ {fails} критичных проверок не пройдено, предупреждений: {warns}")
    else:
        lines.append(f"ИТОГ: ✓ окружение готово" + (f" (предупреждений: {warns})" if warns else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="argus-doctor", description="ARGUS environment self-check")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--flow", action="store_true", help="treat playwright+chromium as critical (provider=flow)")
    ap.add_argument("--no-live", action="store_true", help="skip network probes (edge-tts service)")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    report = run_checks(flow=True if args.flow else None, live=not args.no_live)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

"""Kinetic vertical videos from pure graphics — no AI generation needed.

Drives the bundled Remotion engine (engine/) with a JSON plan:
word-by-word typography, title/card/big/counter/act/cta scenes,
dark or light theme. Voiceover + word timings are optional; when a
voice track is given the words pop exactly on their spoken timestamps.

Plan example:
    {
      "theme": "dark",
      "voice": "voice.mp3",            # optional
      "words": [{"w": "...", "s": 0.0, "e": 0.3}, ...],  # optional
      "scenes": [
        {"at": 0.0, "kind": "words", "text": "весь текст сцены"},
        {"at": 3.0, "kind": "title", "kicker": "глава 1", "text": "заголовок"},
        {"at": 6.0, "kind": "card", "media": "shot.jpg", "caption": "подпись"},
        {"at": 8.0, "kind": "big", "text": "НУ"},
        {"at": 9.0, "kind": "counter", "value": 87, "suffix": "%", "sub": "подпись"},
        {"at": 10.5, "kind": "act", "index": "02", "title": "как это работает"},
        {"at": 11.5, "kind": "cta", "text": "забирай", "handle": "@name"}
      ]
    }
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from ..config import CONFIG

SCENE_KINDS = ("words", "title", "card", "big", "counter", "act", "cta")
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm", ".mkv"}


def engine_dir() -> Path:
    override = os.environ.get("ARGUS_ENGINE_DIR", "").strip()
    if override:
        return Path(override).resolve()
    # src/argus/tools/kinetic.py -> repo root -> engine/
    return Path(__file__).resolve().parents[3] / "engine"


def _npx() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def _find_browser() -> str | None:
    env = os.environ.get("REMOTION_BROWSER", "").strip()
    if env and Path(env).exists():
        return env
    cands = [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        p = Path(os.path.expandvars(c))
        if p.exists():
            return str(p)
    return None


def _prepare_public(plan: dict, base: Path, pub: Path) -> None:
    (pub / "m").mkdir(parents=True, exist_ok=True)
    fonts_src = engine_dir() / "public" / "fonts"
    if fonts_src.exists():
        shutil.copytree(fonts_src, pub / "fonts", dirs_exist_ok=True)

    def link_media(value: str) -> str:
        src = Path(value)
        if not src.is_absolute():
            src = base / value
        if not src.exists():
            raise FileNotFoundError(f"media not found: {value}")
        if src.suffix.lower() not in MEDIA_EXT:
            raise ValueError(f"unsupported media type: {value}")
        dst = pub / "m" / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        return f"m/{src.name}"

    for scene in plan.get("scenes", []):
        media = scene.get("media")
        if media:
            scene["media"] = link_media(media)

    voice = plan.get("voice")
    if voice:
        vsrc = Path(voice)
        if not vsrc.is_absolute():
            vsrc = base / voice
        if not vsrc.exists():
            raise FileNotFoundError(f"voice not found: {voice}")
        shutil.copy2(vsrc, pub / vsrc.name)
        plan["voice"] = vsrc.name


def _derive_duration(plan: dict) -> float:
    if plan.get("duration"):
        return float(plan["duration"])
    end = 0.0
    for w in plan.get("words") or []:
        end = max(end, float(w.get("e", 0)))
    for s in plan.get("scenes") or []:
        end = max(end, float(s.get("at", 0)) + 2.0)
    if end <= 0:
        raise ValueError("plan needs duration, scenes or words")
    return round(end + float(plan.get("tail", 0.8)), 3)


def build_kinetic_video(plan: dict | str, output_path: str, *, preview: bool = False) -> dict:
    """Render a vertical kinetic video from a plan (dict or path to JSON)."""
    eng = engine_dir()
    if not (eng / "package.json").exists():
        raise RuntimeError(
            f"Kinetic engine not found at {eng}. Set ARGUS_ENGINE_DIR or run "
            "npm install inside the engine/ folder of the repo."
        )
    if isinstance(plan, (str, Path)):
        base = Path(plan).resolve().parent
        plan = json.loads(Path(plan).read_text(encoding="utf-8"))
    else:
        base = Path.cwd()

    for scene in plan.get("scenes", []):
        if scene.get("kind") not in SCENE_KINDS:
            raise ValueError(
                f"unknown scene kind {scene.get('kind')!r}; expected one of {SCENE_KINDS}"
            )
    plan.setdefault("fps", CONFIG.fps)
    plan.setdefault("theme", "dark")
    plan["duration"] = _derive_duration(plan)
    if plan.get("words") and isinstance(plan["words"], (str, Path)):
        wpath = Path(plan["words"])
        if not wpath.is_absolute():
            wpath = base / wpath
        plan["words"] = json.loads(wpath.read_text(encoding="utf-8"))

    out = Path(output_path).resolve()
    work = out.parent / "_kinetic"
    pub = work / "public"
    work.mkdir(parents=True, exist_ok=True)
    _prepare_public(plan, base, pub)

    props_path = work / "props.json"
    props_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    started = time.monotonic()
    npx = _npx()
    cmd = [
        npx, "remotion", "render", "src/index.ts", "Kinetic", str(out),
        "--props", str(props_path), "--public-dir", str(pub),
        "--log", "error", "--timeout", "120000",
        "--codec", "h264", "--crf", "18",
    ]
    if preview:
        cmd += ["--scale", "0.5"]
    browser = _find_browser()
    if browser:
        cmd += ["--browser-executable", browser]
    proc = subprocess.run(cmd, cwd=eng, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError("Remotion render failed:\n" + "\n".join(tail))

    return {
        "output": str(out),
        "duration": plan["duration"],
        "scenes": len(plan.get("scenes", [])),
        "theme": plan["theme"],
        "preview": preview,
        "elapsed_s": round(time.monotonic() - started, 1),
    }

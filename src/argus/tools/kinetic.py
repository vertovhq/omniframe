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
      "hud": {                         # optional overlay over all scenes
        "at": 0.5, "until": 9.0,
        "rows": [{"label": "ДО СРОКА", "value": "365 ДНЕЙ"},
                 {"label": "РАБОЧИЕ", "value": "0/100"}],
        "pos": "top",                  # top | bottom
        "accent_changes": [{"at": 4.5, "row": 1, "value": "20/100"}]
      },
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
from .. import __version__
from ..ffmpeg import temp_sibling

SCENE_KINDS = ("words", "title", "card", "big", "counter", "act", "cta", "chip")
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm", ".mkv"}
DEFAULT_SFX = ("whoosh.mp3", "pop.mp3", "hit.wav")


def _ensure_default_sfx() -> Path:
    """Synthesize the default whoosh/pop/hit set once into engine/public/sfx.

    Users can drop premium sounds with the same names into ARGUS_SFX_DIR.
    """
    user_dir = os.environ.get("ARGUS_SFX_DIR", "").strip()
    if user_dir:
        user = Path(user_dir).expanduser()
        if all((user / n).exists() for n in DEFAULT_SFX):
            return user
    cache = engine_dir() / "public" / "sfx"
    cache.mkdir(parents=True, exist_ok=True)
    if not all((cache / n).exists() for n in DEFAULT_SFX):
        synth = {
            "whoosh.mp3": [
                "-f", "lavfi", "-i", "anoisesrc=color=pink:d=0.45:seed=5",
                "-af", "highpass=f=350,lowpass=f=2400,afade=t=in:st=0:d=0.18,"
                       "afade=t=out:st=0.2:d=0.25,volume=2.2",
                "-q:a", "4",
            ],
            "pop.mp3": [
                "-f", "lavfi", "-i", "sine=frequency=620:duration=0.12",
                "-af", "afade=t=out:st=0.02:d=0.1,volume=1.6",
                "-q:a", "4",
            ],
            "hit.wav": [
                "-f", "lavfi", "-i", "sine=frequency=110:duration=0.3",
                "-f", "lavfi", "-i", "anoisesrc=color=brown:d=0.08:seed=9",
                "-filter_complex",
                "[0]afade=t=out:st=0.03:d=0.27,volume=2.0[a];"
                "[1]afade=t=out:st=0.01:d=0.07,volume=1.4[b];"
                "[a][b]amix=inputs=2:duration=first",
            ],
        }
        for name, args in synth.items():
            dst = cache / name
            if dst.exists():
                continue
            subprocess.run(
                [CONFIG.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args, str(dst)],
                check=True,
            )
    return cache


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

    music = plan.get("music")
    if isinstance(music, dict) and music.get("src"):
        msrc = Path(music["src"])
        if not msrc.is_absolute():
            msrc = base / music["src"]
        if not msrc.exists():
            raise FileNotFoundError(f"music not found: {music['src']}")
        shutil.copy2(msrc, pub / msrc.name)
        music["src"] = msrc.name

    if plan.get("sfx", True):
        sfx_src = _ensure_default_sfx()
        (pub / "sfx").mkdir(parents=True, exist_ok=True)
        for name in DEFAULT_SFX:
            shutil.copy2(sfx_src / name, pub / "sfx" / name)
        for i, e in enumerate(plan.get("sfx_list") or []):
            esrc = Path(e["src"])
            if not esrc.is_absolute():
                esrc = base / esrc
            if not esrc.exists():
                raise FileNotFoundError(f"sfx not found: {e['src']}")
            dst = f"sfx/custom_{i}{esrc.suffix.lower()}"
            shutil.copy2(esrc, pub / dst)
            e["src"] = dst


def _validate_hud(plan: dict) -> None:
    """Light shape check: a bad hud must fail here, not inside Remotion."""
    hud = plan.get("hud")
    if hud is None:
        return
    if not isinstance(hud, dict):
        raise ValueError("hud must be an object {at, until, rows, pos?, accent_changes?}")
    if not isinstance(hud.get("at"), (int, float)) or not isinstance(hud.get("until"), (int, float)):
        raise ValueError("hud needs numeric 'at' and 'until'")
    rows = hud.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise ValueError("hud.rows must be a non-empty list of {label, value}")
    if hud.get("pos") not in (None, "top", "bottom"):
        raise ValueError("hud.pos must be 'top' or 'bottom'")


def _derive_duration(plan: dict) -> float:
    if plan.get("duration"):
        return float(plan["duration"])
    end = 0.0
    for w in plan.get("words") or []:
        end = max(end, float(w.get("e", 0)))
    for s in plan.get("scenes") or []:
        end = max(end, float(s.get("at", 0)) + 2.0)
    hud = plan.get("hud")
    if isinstance(hud, dict) and isinstance(hud.get("until"), (int, float)):
        # HUD живёт дольше последней сцены — не обрезать его концом ролика
        end = max(end, float(hud["until"]))
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
    _validate_hud(plan)
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
    hud_mark = " + hud" if isinstance(plan.get("hud"), dict) else ""
    print(f"[ARGUS] кинетика: рендер {len(plan.get("scenes", []))} сцен{hud_mark}, {plan["duration"]:.1f}с, тема {plan["theme"]}...", flush=True)
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

    # подпись происхождения: metadata-comment "Made with ARGUS" (stream copy)
    tagged = temp_sibling(out, ".tag.mp4")
    m = subprocess.run(
        [CONFIG.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(out), "-c", "copy",
         "-metadata", f"comment=Made with ARGUS Studio v{__version__}",
         str(tagged)],
        capture_output=True, text=True,
    )
    if m.returncode == 0:
        out.unlink(missing_ok=True)
        tagged.replace(out)
    else:
        tagged.unlink(missing_ok=True)

    return {
        "engine": f"ARGUS {__version__}",
        "output": str(out),
        "duration": plan["duration"],
        "scenes": len(plan.get("scenes", [])),
        "theme": plan["theme"],
        "preview": preview,
        "elapsed_s": round(time.monotonic() - started, 1),
    }

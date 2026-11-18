"""`render_video`: stills, previews and final renders of a plan v2 (design §9).

The model writes a plan (`argus.plan`), looks at stills, then at a half-size preview, then
renders the final file. The engine is the Remotion project in `engine/`; the node side is
`engine/scripts/render.mjs` (bundle once per job, then stills or one video file).

Flow of one call:

1. `prepare_render` (in the server process, quick): validate the plan and every file it
   names, load and remap the caption words, derive the duration, check `times`/`compare`.
   Every problem comes back as `path: message` and nothing is started.
2. `jobs.run_or_detach("render", payload)`: the `render` job (`run_job`, in a worker
   process) builds `<project>/.work/render-<id>/public/` (engine fonts, project media as
   hardlinks), runs node, then for a final render normalises loudness and tags the file.
3. Outputs go to `<project>/renders/`; a final render also saves `<project>/plan.json`.
   The work folder is deleted when the job succeeds.

Custom scene components (`tools/components.py`): `prepare_render` checks their source; the job
reserves the engine folder (lock), installs and typechecks them, and frees the folder as soon
as the bundle is built. Compile errors come back as `{"valid": false, "errors": [...]}`.

Clips (`tools/media_prep.py`): before the node step the job swaps each clip's file for a
proxy in `<project>/cache/proxies/` when it is variable-rate, not H.264, or needs `clean_audio`.

This module also holds the engine helpers: `engine_dir`, `_find_browser` and the synthesis
of the built-in sound files a plan may name (`sfx/whoosh.mp3`, `sfx/pop.mp3`, `sfx/hit.wav`).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from .. import __version__, jobs
from ..captions import clean_word_timings, load_words, remap_words_to_clips
from ..config import CONFIG
from ..ffmpeg import FFmpegError, measure_loudness, run_ffmpeg, run_ffmpeg_stderr, stream_info, temp_sibling
from ..plan import (
    FORMAT_SIZES,
    TAIL_S,
    CardScene,
    MediaBackground,
    Plan,
    WordsRemap,
    validate_plan,
)
from ..project import project_dir, slugify
from . import media_prep
from .components import EngineHold, check_components, used_components
from .watch import format_time

MODES = ("stills", "preview", "final")
MAX_STILLS = 8                 # images per call; more would flood the model's context
DEFAULT_STILLS = 6
STILLS_WAIT_S = 90.0           # stills usually finish inside one tool call (bundle + a few frames)
PREVIEW_SCALE = 0.5
PREVIEW_CRF = 28
FINAL_CRF = 18
STILL_JPEG_QUALITY = 92
LOUDNESS_TP = -1.5             # true-peak ceiling, dB (design §9 step 6)
LOUDNESS_LRA = 11.0
AUDIO_BITRATE = "192k"
COMPARE_MAX_WIDTH = 1600       # side-by-side image: both panels together
COMPARE_MAX_HEIGHT = 960
COMPARE_LABEL_H = 44
COMPARE_GAP = 8

CLIP_END_SLACK_S = 0.1         # container durations are rounded; `out` may exceed the file by this much
PROTOCOL = "@@ARGUS "          # prefix of the stdout lines of engine/scripts/render.mjs
DEFAULT_SFX = ("whoosh.mp3", "pop.mp3", "hit.wav")
MEDIA_DIR = "m"                # inside the public dir; plan files are linked here
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


# ------------------------------------------------------------------ engine helpers

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
    # src/argus/tools/render.py -> repo root -> engine/
    return Path(__file__).resolve().parents[3] / "engine"


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


# ------------------------------------------------------------------ files named by the plan

def _bases(project_root: Path, plan_dir: Path | None) -> list[Path]:
    """Folders a relative path of the plan is looked up in, first match wins.

    The project folder (`audio/voice.mp3`), the folder of the plan file, the working
    directory, and the engine's own `public/` (so `fonts/InterDisplay-Bold.otf` and
    `sfx/whoosh.mp3` work without copying them into the project).
    """
    out = [project_root]
    if plan_dir is not None:
        out.append(plan_dir)
    out += [Path.cwd(), engine_dir() / "public"]
    return out


def resolve_asset(value: str, bases: Sequence[Path]) -> Path | None:
    """The existing file a plan path points to, or None."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve() if path.is_file() else None
    for base in bases:
        cand = base / path
        if cand.is_file():
            return cand.resolve()
    return None


def _builtin_sfx(value: str) -> bool:
    return Path(value).name in DEFAULT_SFX


def _asset_refs(plan: Plan) -> list[tuple[str, str, str]]:
    """`(path in the plan, value, kind)` for every file the plan names.

    Kinds: `font`, `media`, `words`, `audio`, `sfx`.
    """
    refs: list[tuple[str, str, str]] = []
    for role in ("display", "body", "mono"):
        font = getattr(plan.style.fonts, role)
        if font is not None and font.src:
            refs.append((f"style.fonts.{role}.src", font.src, "font"))
    if isinstance(plan.style.background, MediaBackground):
        refs.append(("style.background.src", plan.style.background.src, "media"))
    for i, clip in enumerate(plan.clips):
        refs.append((f"clips[{i}].src", clip.src, "media"))
    for i, scene in enumerate(plan.scenes):
        if isinstance(scene, CardScene):
            refs.append((f"scenes[{i}].media", scene.media, "media"))
    words = plan.captions.words if plan.captions else None
    if isinstance(words, str):
        refs.append(("captions.words", words, "words"))
    elif isinstance(words, WordsRemap):
        refs.append(("captions.words.source", words.source, "words"))
        if words.media:
            refs.append(("captions.words.media", words.media, "media"))
    if plan.audio:
        if plan.audio.voice:
            refs.append(("audio.voice.src", plan.audio.voice.src, "audio"))
        if plan.audio.music:
            refs.append(("audio.music.src", plan.audio.music.src, "audio"))
        for i, event in enumerate(plan.audio.sfx):
            refs.append((f"audio.sfx[{i}].src", event.src, "sfx"))
    return refs


def _caption_words(plan: Plan, bases: Sequence[Path]) -> tuple[list[dict] | None, list[str]]:
    """Caption words as `[{w, s, e}]` on the output timeline, or `(None, errors)`.

    Loads a words file, takes inline words, or moves a footage transcript onto the kept
    clips (`remap: 'clips'`); then makes the timings monotonic (`clean_word_timings`).
    Phrase grouping stays in the engine.
    """
    if plan.captions is None:
        return None, []
    spec = plan.captions.words
    try:
        if isinstance(spec, str):
            path = resolve_asset(spec, bases)
            if path is None:
                return None, []  # reported as a missing file by the asset check
            words = load_words(path)
        elif isinstance(spec, WordsRemap):
            source = resolve_asset(spec.source, bases)
            media_ref = spec.media or plan.clips[0].src
            media = resolve_asset(media_ref, bases)
            if source is None or media is None:
                return None, []
            clips = []
            for clip in plan.clips:
                src = resolve_asset(clip.src, bases)
                clips.append({"src": str(src or clip.src), "at": clip.at, "in": clip.in_, "out": clip.out})
            words = remap_words_to_clips(load_words(source), clips, media)
            if not words:
                return None, [
                    f"captions.words: no word of {spec.source} falls inside the clips made from {media_ref}"
                ]
        else:
            words = [{"word": w.w, "start": w.s, "end": w.e} for w in spec]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, [f"captions.words: cannot read the words ({exc})"]
    words, _ = clean_word_timings(words)
    return [{"w": w["word"], "s": round(w["start"], 3), "e": round(w["end"], 3)} for w in words], []


def _plan_warnings(plan: Plan) -> list[str]:
    """Things the plan asks for that this engine version does not draw or apply."""
    notes: list[str] = []
    music = plan.audio.music if plan.audio else None
    if music is not None and music.duck < 1 and plan.captions is None:
        notes.append("audio.music.duck has no effect without `captions`: the ducking follows the caption words")
    return notes


# ------------------------------------------------------------------ request validation

def _load_plan(plan: Any, project_root: Path) -> tuple[dict | None, Path | None, list[str]]:
    """The plan as a dict, the folder of its file (or None), and errors."""
    if isinstance(plan, dict):
        return plan, None, []
    if not isinstance(plan, str) or not plan.strip():
        return None, None, [f"plan: expected a plan object or the path of a plan .json file, got {type(plan).__name__}"]
    text = plan.strip()
    if text.startswith("{"):  # some clients pass the object as a JSON string
        try:
            data = json.loads(text)
        except ValueError as exc:
            return None, None, [f"plan: not valid JSON ({exc})"]
        return (data, None, []) if isinstance(data, dict) else (None, None, ["plan: must be a JSON object"])
    path = Path(text).expanduser()
    found = resolve_asset(text, _bases(project_root, None))
    if found is None:
        return None, None, [f"plan: file not found: {path}"]
    try:
        data = json.loads(found.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, None, [f"plan: cannot read {found} ({exc})"]
    if not isinstance(data, dict):
        return None, None, [f"plan: {found} must hold a JSON object"]
    return data, found.parent, []


def _default_times(duration: float) -> list[float]:
    n = max(1, min(DEFAULT_STILLS, int(duration)))
    return [round(duration * (i + 0.5) / n, 3) for i in range(n)]


def _check_times(times: Any, duration: float, label: str) -> tuple[list[float], list[str]]:
    if not isinstance(times, (list, tuple)) or not times:
        return [], [f"{label}: must be a non-empty list of seconds"]
    errors: list[str] = []
    out: list[float] = []
    for i, t in enumerate(times):
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            errors.append(f"{label}[{i}]: {t!r} is not a number of seconds")
        elif t < 0 or t > duration:
            errors.append(f"{label}[{i}]: {t} is outside the video (0..{duration:g} s)")
        else:
            out.append(round(float(t), 3))
    return out, errors


def prepare_render(
    plan: Any,
    project_root: Path,
    *,
    mode: str,
    times: list[float] | None,
    compare: dict | None,
    format: str | None,
    name: str,
) -> tuple[dict | None, list[str]]:
    """Validate everything a render needs. Returns `(job payload, [])` or `(None, errors)`.

    Errors are `path: message` strings. Nothing is written and nothing is started here.
    """
    errors: list[str] = []
    if mode not in MODES:
        errors.append(f"mode: unknown mode {mode!r} (expected {', '.join(MODES)})")
    if format is not None and format not in FORMAT_SIZES:
        errors.append(f"format: unknown format {format!r} (expected {', '.join(FORMAT_SIZES)})")
    try:
        name_slug = slugify(name)
    except ValueError as exc:
        name_slug = "video"
        errors.append(f"name: {exc}")

    data, plan_dir, load_errors = _load_plan(plan, project_root)
    errors += load_errors
    parsed: Plan | None = None
    if data is not None:
        parsed, plan_errors = validate_plan(data)
        errors += plan_errors
    if parsed is None:
        return None, errors

    bases = _bases(project_root, plan_dir)
    for where, value, kind in _asset_refs(parsed):
        if mode == "stills" and kind in ("audio", "sfx"):
            continue  # a still has no sound
        if resolve_asset(value, bases) is None and not (kind == "sfx" and _builtin_sfx(value)):
            errors.append(f"{where}: file not found: {value} (relative paths are looked up in the project folder {project_root})")

    component_errors, component_warnings = check_components(parsed, project_root)
    errors += component_errors

    words, word_errors = _caption_words(parsed, bases)
    errors += word_errors

    voice_s: float | None = None
    voice = parsed.audio.voice if parsed.audio else None
    voice_file = resolve_asset(voice.src, bases) if voice else None
    if voice_file is not None and mode != "stills":
        try:
            voice_s = stream_info(voice_file).duration or None
        except FFmpegError as exc:
            errors.append(f"audio.voice.src: cannot read the file ({str(exc).splitlines()[0]})")
    clip_lengths: dict[int, float] = {}
    for i, clip in enumerate(parsed.clips):
        file = resolve_asset(clip.src, bases)
        if file is None or media_prep.is_image(file):
            continue  # missing files are reported above; a picture has no length of its own
        try:
            source_s = stream_info(file).duration
        except FFmpegError as exc:
            errors.append(f"clips[{i}].src: cannot read the file ({str(exc).splitlines()[0]})")
            continue
        errors += _clip_range_errors(i, clip, source_s)
        length = source_s - (clip.in_ or 0.0)
        if clip.length is None and length > 0:
            clip_lengths[i] = length

    resolved: Plan | None = None
    if not errors:
        resolved = parsed.resolved(
            format=format,
            voice_duration=voice_s,
            words_end=max((w["e"] for w in words), default=None) if words else None,
            clip_lengths=clip_lengths,
        )
        assert resolved.duration is not None
        if resolved.duration <= TAIL_S + 1e-9:
            errors.append("plan: nothing sets the length of the video; add scenes, clips, captions or `duration`")

    clean_times: list[float] = []
    compare_payload: dict | None = None
    if resolved is not None and mode == "stills":
        if times is None:
            if compare is not None:
                errors.append("times: needed with `compare`, one render time per compare time")
            clean_times = _default_times(resolved.duration)
        else:
            clean_times, time_errors = _check_times(times, resolved.duration, "times")
            errors += time_errors
            if not time_errors and len(clean_times) > MAX_STILLS:
                errors.append(f"times: at most {MAX_STILLS} stills per call, got {len(clean_times)}; ask for the rest in another call")
        if compare is not None and times is not None:
            compare_payload, compare_errors = _check_compare(compare, len(times), bases)
            errors += compare_errors
    elif compare is not None and mode != "stills":
        errors.append("compare: only works with mode='stills'")

    if errors or resolved is None:
        return None, errors
    return {
        "mode": mode,
        "name": name_slug,
        "project_root": str(project_root),
        "bases": [str(b) for b in bases],
        "plan": resolved.to_dict(),
        "caption_words": words,
        "times": clean_times,
        "compare": compare_payload,
        "warnings": _plan_warnings(resolved) + component_warnings,
    }, []


def _clip_range_errors(index: int, clip: Any, source_s: float) -> list[str]:
    """A clip must lie inside its file; past the end the engine would show a frozen or black picture."""
    if source_s <= 0:
        return [f"clips[{index}].src: the file has no length (is it a video?)"]
    start = clip.in_ or 0.0
    if start >= source_s:
        return [f"clips[{index}].in: {start:g} s is past the end of the file ({source_s:.2f} s)"]
    if clip.out is not None and clip.out > source_s + CLIP_END_SLACK_S:
        return [f"clips[{index}].out: {clip.out:g} s is past the end of the file ({source_s:.2f} s)"]
    return []


def _check_compare(compare: Any, n_times: int, bases: Sequence[Path]) -> tuple[dict | None, list[str]]:
    if not isinstance(compare, dict):
        return None, ["compare: must be {\"video\": path, \"times\": [seconds, ...]}"]
    errors = [f"compare.{k}: unknown field (allowed: video, times)" for k in compare if k not in ("video", "times")]
    video = compare.get("video")
    ref: Path | None = None
    if not isinstance(video, str) or not video.strip():
        errors.append("compare.video: required, the path of the reference video")
    else:
        ref = resolve_asset(video, bases)
        if ref is None:
            errors.append(f"compare.video: file not found: {video}")
    ref_times = compare.get("times")
    if ref_times is None:
        errors.append("compare.times: required, one time in the reference per render time")
        return None, errors
    if isinstance(ref_times, (list, tuple)) and len(ref_times) != n_times:
        errors.append(f"compare.times: has {len(ref_times)} times but `times` has {n_times}; they must match one to one")
    if ref is not None:
        try:
            ref_len = stream_info(ref).duration
        except FFmpegError as exc:
            return None, [*errors, f"compare.video: cannot read the file ({str(exc).splitlines()[0]})"]
        ref_times, time_errors = _check_times(ref_times, ref_len, "compare.times")
        errors += time_errors
    if errors or ref is None:
        return None, errors
    return {"video": str(ref), "times": ref_times}, []


# ------------------------------------------------------------------ public dir

def _link_or_copy(src: Path, dst: Path) -> None:
    """Hardlink `src` to `dst`; copy when that is not possible (another drive, no hardlinks)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


class _PublicDir:
    """The per-job public dir: engine fonts plus every file of the plan, under `m/`."""

    def __init__(self, root: Path, bases: Sequence[Path]) -> None:
        self.root = root
        self.bases = list(bases)
        self._done: dict[Path, str] = {}
        fonts = engine_dir() / "public" / "fonts"
        if fonts.is_dir():
            for font in fonts.iterdir():
                if font.is_file():
                    _link_or_copy(font, root / "fonts" / font.name)

    def add(self, value: str, where: str) -> str:
        """Link the file `value` names; returns its path relative to the public dir."""
        src = resolve_asset(value, self.bases)
        if src is None and _builtin_sfx(value):
            src = (_ensure_default_sfx() / Path(value).name).resolve()
        if src is None or not src.is_file():
            raise FileNotFoundError(f"{where}: file not found: {value}")
        rel = self._done.get(src)
        if rel is None:
            digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:8]
            rel = f"{MEDIA_DIR}/{digest}-{_SAFE_NAME.sub('_', src.name)}"
            _link_or_copy(src, self.root / rel)
            self._done[src] = rel
        return rel


def _prepare_clip_media(
    plan: Plan,
    bases: Sequence[Path],
    root: Path,
    *,
    with_audio: bool,
    report: Callable[..., None],
) -> list[media_prep.ClipMedia]:
    """The file the engine plays for each clip: the source, or a proxy in `<project>/cache/proxies/`.

    A still has no sound, so `clean_audio` is not applied (and does not force a proxy) there.
    """
    sources: list[tuple[Path, bool]] = []
    for i, clip in enumerate(plan.clips):
        src = resolve_asset(clip.src, bases)
        if src is None:
            raise FileNotFoundError(f"clips[{i}].src: file not found: {clip.src}")
        sources.append((src, clip.clean_audio and with_audio))
    if not sources:
        return []
    return media_prep.prepare_clips(
        sources, root / "cache" / "proxies", fps=plan.fps, report=lambda note: report(0.02, note),
    )


def _engine_props(
    plan: dict,
    words: list[dict] | None,
    public: _PublicDir,
    *,
    with_audio: bool,
    clip_media: Sequence[media_prep.ClipMedia] | None = None,
) -> dict:
    """The plan as the engine wants it: every file path points into the public dir, words are inline.

    `clip_media` (from `_prepare_clip_media`) swaps a clip's file for its proxy. For a clip
    without `out` it also sets `length`, the seconds the clip lasts (file length minus `in`);
    this field exists only in the engine props, it is not part of the plan.
    """
    props = json.loads(json.dumps(plan))  # deep copy
    for role, font in props["style"]["fonts"].items():
        if font.get("src"):
            font["src"] = public.add(font["src"], f"style.fonts.{role}.src")
    background = props["style"].get("background")
    if background and background.get("type") == "media":
        background["src"] = public.add(background["src"], "style.background.src")
    for i, clip in enumerate(props.get("clips", [])):
        media = clip_media[i] if clip_media is not None else None
        clip["src"] = public.add(str(media.path) if media is not None else clip["src"], f"clips[{i}].src")
        if media is not None and clip.get("out") is None and media.length:
            clip["length"] = round(max(0.0, media.length - (clip.get("in") or 0.0)), 3)
    for i, scene in enumerate(props.get("scenes", [])):
        if scene.get("kind") == "card":
            scene["media"] = public.add(scene["media"], f"scenes[{i}].media")
    if props.get("captions") is not None:
        props["captions"]["words"] = words or []
    audio = props.pop("audio", None)
    if audio and with_audio:
        if audio.get("voice"):
            audio["voice"]["src"] = public.add(audio["voice"]["src"], "audio.voice.src")
        if audio.get("music"):
            audio["music"]["src"] = public.add(audio["music"]["src"], "audio.music.src")
        for i, event in enumerate(audio.get("sfx", [])):
            event["src"] = public.add(event["src"], f"audio.sfx[{i}].src")
        props["audio"] = audio
    return props


# ------------------------------------------------------------------ node

def _concurrency() -> int:
    return CONFIG.render_concurrency or max(1, (os.cpu_count() or 2) // 2)


def _run_node(
    spec: dict,
    work: Path,
    report: Callable[..., None],
    lo: float,
    hi: float,
    hold: EngineHold | None = None,
) -> dict:
    """Run `engine/scripts/render.mjs` and return its result event; progress goes to `report`.

    `hold` (the engine folder reserved by `EngineHold.acquire`) is released when the script
    reports that the bundle is built, and in any case when this function ends.
    """
    try:
        return _run_node_script(spec, work, report, lo, hi, hold)
    finally:
        if hold is not None:
            hold.release()


def _run_node_script(
    spec: dict,
    work: Path,
    report: Callable[..., None],
    lo: float,
    hi: float,
    hold: EngineHold | None,
) -> dict:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js was not found on PATH. Install Node 18+ (https://nodejs.org) and run `npm install` in engine/.")
    script = engine_dir() / "scripts" / "render.mjs"
    spec_path = work / "spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result: dict | None = None
    failure: str | None = None
    tail: deque[str] = deque(maxlen=30)
    with open(work / "render.log", "wb") as log:
        proc = subprocess.Popen(
            [node, str(script), str(spec_path)],
            cwd=engine_dir(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
            text=True, encoding="utf-8", errors="replace", creationflags=creationflags,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if not line.startswith(PROTOCOL):
                if line:
                    tail.append(line)
                continue
            try:
                msg = json.loads(line[len(PROTOCOL):])
            except ValueError:
                continue
            event = msg.get("event")
            if event == "progress":
                report(lo + (hi - lo) * float(msg.get("value", 0)), msg.get("note"))
            elif event == "bundled":
                if hold is not None:
                    hold.release()  # the bundle no longer reads engine/src
            elif event == "result":
                result = msg
            elif event == "error":
                failure = str(msg.get("message", ""))
        code = proc.wait()
    if code != 0 or result is None:
        detail = failure or "\n".join(tail)
        if not detail:
            try:
                detail = (work / "render.log").read_text(encoding="utf-8", errors="replace")
            except OSError:
                detail = ""
        lines = detail.strip().splitlines()
        raise RuntimeError(f"Remotion render failed (node exit {code}):\n" + "\n".join(lines[:12])[-1500:])
    return result


# ------------------------------------------------------------------ stills

def compose_side_by_side(
    reference: Path,
    render: Path,
    out: Path,
    ref_label: str,
    render_label: str,
) -> Path:
    """One JPEG: the reference frame on the left, the render on the right, each with a label."""
    with PILImage.open(reference) as a_img, PILImage.open(render) as b_img:
        a, b = a_img.convert("RGB"), b_img.convert("RGB")
    ratio_a, ratio_b = a.width / a.height, b.width / b.height
    height = min(COMPARE_MAX_HEIGHT, int((COMPARE_MAX_WIDTH - COMPARE_GAP) / (ratio_a + ratio_b)))
    wa, wb = max(1, round(height * ratio_a)), max(1, round(height * ratio_b))
    canvas = PILImage.new("RGB", (wa + COMPARE_GAP + wb, height + COMPARE_LABEL_H), (18, 18, 22))
    canvas.paste(a.resize((wa, height), PILImage.Resampling.LANCZOS), (0, COMPARE_LABEL_H))
    canvas.paste(b.resize((wb, height), PILImage.Resampling.LANCZOS), (wa + COMPARE_GAP, COMPARE_LABEL_H))
    draw = ImageDraw.Draw(canvas)
    font = _label_font(26)
    draw.text((12, COMPARE_LABEL_H // 2), ref_label, fill=(240, 240, 245), font=font, anchor="lm")
    draw.text((wa + COMPARE_GAP + 12, COMPARE_LABEL_H // 2), render_label, fill=(255, 190, 90), font=font, anchor="lm")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="JPEG", quality=90)
    return out


def _label_font(size: int) -> Any:
    try:
        return ImageFont.truetype(str(engine_dir() / "public" / "fonts" / "InterDisplay-Bold.otf"), size)
    except OSError:
        return ImageFont.load_default()


def _extract_reference_frame(video: str, t: float, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    run_ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1", "-q:v", "2", str(out)])
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"could not read a frame at {t:.2f} s from {video}")


# ------------------------------------------------------------------ final post-processing

def _loudnorm_pass1(path: Path, target: float) -> dict | None:
    """Measure the audio for a two-pass loudnorm; None when it is silent."""
    text = run_ffmpeg_stderr([
        "-i", str(path), "-vn", "-af",
        f"loudnorm=I={target}:TP={LOUDNESS_TP}:LRA={LOUDNESS_LRA}:print_format=json",
        "-f", "null", "-",
    ])
    start, end = text.rfind("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise FFmpegError("loudnorm produced no JSON report")
    report = json.loads(text[start:end + 1])
    try:
        values = {k: float(report[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (KeyError, ValueError):
        return None
    return values if all(math.isfinite(v) for v in values.values()) else None


def finalize_video(raw: Path, out: Path) -> dict:
    """Loudness-normalise the audio (two-pass `loudnorm`), add faststart and the ARGUS tag.

    The video stream is copied. A file without audio, or with silent audio, is only tagged.
    Returns `{"loudness_target", "loudness_before", "loudness_after", "note"?}`.
    """
    target = CONFIG.loudness_target
    info = stream_info(raw)
    tag = ["-metadata", f"comment=Made with ARGUS Studio v{__version__}", "-movflags", "+faststart"]
    measured = _loudnorm_pass1(raw, target) if info.has_audio else None
    staged = temp_sibling(out, ".final.mp4")
    result: dict[str, Any] = {"loudness_target": target}
    try:
        if measured is None:
            run_ffmpeg(["-i", str(raw), "-c", "copy", *tag, str(staged)])
            result["note"] = "no audio to normalise" if not info.has_audio else "audio is silent, loudness left as is"
        else:
            result["loudness_before"] = round(measured["input_i"], 1)
            filt = (
                f"loudnorm=I={target}:TP={LOUDNESS_TP}:LRA={LOUDNESS_LRA}"
                f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
                f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
                f":offset={measured['target_offset']}:linear=true"
            )
            run_ffmpeg([
                "-i", str(raw), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                "-af", filt, "-ar", "48000", "-c:a", "aac", "-b:a", AUDIO_BITRATE, *tag, str(staged),
            ])
        os.replace(staged, out)
    finally:
        staged.unlink(missing_ok=True)
    if info.has_audio and measured is not None:
        after = measure_loudness(out)["input_i"]
        result["loudness_after"] = None if after is None else round(after, 1)
    return result


# ------------------------------------------------------------------ job

def _fmt_tag(fmt: str) -> str:
    return fmt.replace(":", "x")


def _remove_stale(folder: Path, pattern: str) -> None:
    for old in folder.glob(pattern):
        old.unlink(missing_ok=True)


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Worker side of `render_video` (job kind `render`)."""
    started = time.monotonic()
    plan = Plan.model_validate(payload["plan"])
    mode = str(payload["mode"])
    name = str(payload["name"])
    root = Path(payload["project_root"])
    fmt = plan.format
    tag = _fmt_tag(fmt)
    renders = root / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    work = root / ".work" / f"render-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True)

    report(0.01, "preparing files")
    public = _PublicDir(work / "public", [Path(b) for b in payload["bases"]])
    bases = [Path(b) for b in payload["bases"]]
    clip_media = _prepare_clip_media(plan, bases, root, with_audio=mode != "stills", report=report)
    props = _engine_props(
        payload["plan"], payload.get("caption_words"), public,
        with_audio=mode != "stills", clip_media=clip_media,
    )
    spec: dict[str, Any] = {
        "props": props,
        "publicDir": str(public.root),
        "bundleDir": str(work / "bundle"),
        "browser": _find_browser(),
        "concurrency": _concurrency(),
    }
    width, height = FORMAT_SIZES[fmt]
    result: dict[str, Any] = {
        "mode": mode,
        "format": fmt,
        "width": width,
        "height": height,
        "fps": plan.fps,
        "duration": plan.duration,
        "project": root.name,
    }
    if payload.get("warnings"):
        result["warnings"] = list(payload["warnings"])
    proxies = [
        {"clip": i, "source": str(m.source), "proxy": str(m.path), "why": list(m.reasons)}
        for i, m in enumerate(clip_media) if m.proxied
    ]
    if proxies:
        result["proxies"] = proxies

    # Reserve the engine folder until the bundle is built; custom components are installed and
    # typechecked here. `_run_node` releases the hold (and `acquire` cleans up when it raises).
    report(0.02, "preparing the engine")
    hold = EngineHold(engine_dir(), root, used_components(plan), work)
    compile_errors = hold.acquire()
    if compile_errors:
        hold.release()
        shutil.rmtree(work, ignore_errors=True)
        return {
            "valid": False,
            "errors": compile_errors,
            "note": "the custom components do not compile; nothing was rendered. Fix the listed "
                    "problems in <project>/components and call again",
        }

    if mode == "stills":
        times: list[float] = payload["times"]
        compare = payload.get("compare")
        _remove_stale(renders, f"{name}-stills-{tag}-*")
        _remove_stale(renders, f"{name}-compare-{tag}-*")
        files = [renders / f"{name}-stills-{tag}-{i + 1:02d}-t{t:.2f}s.jpg" for i, t in enumerate(times)]
        spec.update(mode="stills", times=times, outputs=[str(f) for f in files], quality=STILL_JPEG_QUALITY)
        _run_node(spec, work, report, 0.03, 0.9 if compare else 0.97, hold)
        entries: list[dict] = []
        if compare:
            report(0.92, "building the side-by-side images")
            for i, (t, ref_t) in enumerate(zip(times, compare["times"])):
                ref_frame = work / f"reference-{i + 1:02d}.jpg"
                _extract_reference_frame(compare["video"], ref_t, ref_frame)
                out = renders / f"{name}-compare-{tag}-{i + 1:02d}-t{t:.2f}s.jpg"
                compose_side_by_side(
                    ref_frame, files[i], out, f"REFERENCE {format_time(ref_t)}", f"RENDER {format_time(t)}",
                )
                entries.append({"t": t, "reference_t": ref_t, "path": str(out)})
            result["image_max_side"] = COMPARE_MAX_WIDTH
        else:
            entries = [{"t": t, "path": str(f)} for t, f in zip(times, files)]
        result["images"] = entries
        result["stills"] = [str(f) for f in files]
        result["note"] = (
            "images are side by side: reference on the left, render on the right"
            if compare else "stills of the render; the full-size files are listed in `stills`"
        )
    else:
        out = renders / f"{name}-{mode}-{tag}.mp4"
        raw = work / "raw.mp4"
        preview = mode == "preview"
        spec.update(
            mode="media", output=str(raw), scale=PREVIEW_SCALE if preview else 1,
            crf=PREVIEW_CRF if preview else FINAL_CRF,
        )
        _run_node(spec, work, report, 0.03, 0.9, hold)
        report(0.92, "finishing the file")
        if preview:
            os.replace(raw, out)
        else:
            result.update(finalize_video(raw, out))
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(payload["plan"], ensure_ascii=False, indent=2), encoding="utf-8")
            result["plan_path"] = str(plan_path)
        info = stream_info(out)
        result.update(
            output=str(out),
            output_width=info.width,
            output_height=info.height,
            output_duration=round(info.duration, 3),
            has_audio=info.has_audio,
            size_bytes=out.stat().st_size,
        )

    shutil.rmtree(work, ignore_errors=True)
    result["elapsed_s"] = round(time.monotonic() - started, 1)
    return result


# ------------------------------------------------------------------ tool

def render_video(
    plan: Any,
    project: str,
    mode: str = "stills",
    times: list[float] | None = None,
    compare: dict | None = None,
    format: str | None = None,
    name: str = "video",
    wait_s: float | None = None,
) -> dict | list:
    """Tool logic of `render_video`: validate, then run the `render` job.

    An invalid request returns `{"valid": false, "errors": [...]}` and starts nothing.
    """
    root = project_dir(project)
    payload, errors = prepare_render(
        plan, root, mode=mode, times=times, compare=compare, format=format, name=name,
    )
    if payload is None:
        return {
            "engine": f"ARGUS {__version__}",
            "valid": False,
            "errors": errors,
            "note": "nothing was rendered; fix the listed problems and call again",
        }
    if not (engine_dir() / "node_modules").is_dir():
        raise RuntimeError(f"The engine is not installed: run `npm install` inside {engine_dir()}.")
    wait = wait_s if wait_s is not None else (STILLS_WAIT_S if mode == "stills" else jobs.DEFAULT_WAIT_S)
    return jobs.run_or_detach("render", payload, wait_s=wait)

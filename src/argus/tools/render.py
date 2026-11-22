"""`render_video`: stills, previews and final renders of a plan v2 (design §9).

The model writes a plan (`argus.plan`), looks at stills, then at a half-size preview, then
renders the final file. The engine is the Remotion project in `engine/`; the node side is
`engine/scripts/render.mjs` (bundle, or reuse the bundle of the same engine state from
`<project>/cache/bundle/`, then stills or one video file). Each result has `timing` in seconds.

Flow of one call:

1. `prepare_render` (in the server process, quick): validate the plan and every file it
   names, load and remap the caption words, derive the duration, check `times`/`compare`.
   Every problem comes back as `path: message` and nothing is started.
2. `jobs.run_or_detach("render", payload)`: the `render` job (`run_job`, in a worker
   process) builds `<project>/.work/render-<id>/public/` (engine fonts, project media as
   hardlinks), runs node, then for a final render normalises loudness and tags the file.
3. Outputs go to `<project>/renders/`; a final render also saves `<project>/plan.json`.
   The work folder is deleted when the job succeeds.

Mode `audio` skips the engine: `_run_audio` places the sounds (`tools/sounds.py`), mixes the
tracks into `<name>-audio.wav` and draws `<name>-audio-timeline.jpg`. Sound events of the other
modes are rendered to WAV files in `<project>/cache/sfx/` before the engine runs.

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
import sys
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from .. import __version__, jobs
from ..engine_setup import not_ready_message, resolve_engine_dir
from ..captions import _token as _caption_token
from ..captions import clean_word_timings, load_words, remap_words_to_clips, resolve_cues
from ..config import CONFIG
from ..ffmpeg import (
    NO_WINDOW,
    FFmpegError,
    measure_loudness,
    run_ffmpeg,
    run_ffmpeg_stderr,
    stream_info,
    temp_sibling,
)
from ..plan import (
    FORMAT_SIZES,
    TAIL_S,
    CardScene,
    MediaBackground,
    Plan,
    WordCue,
    WordsRemap,
    builtin_preset,
    validate_plan,
)
from ..project import project_dir, slugify
from . import media_prep, sounds
from .components import COMPONENTS_DIR, EngineHold, check_components, used_components
from .library import project_library_dir
from .watch import format_time

MODES = ("stills", "preview", "final", "audio")  # "audio": the sound mix and timeline, no browser (task 20.5b)
AUDIO_TIMELINE_NAME = "audio-timeline"
TIMELINE_MAX_SIDE = 1600       # the timeline image keeps its width (the model sees it at this size)
MAX_STILLS = 12                # frames per call; they come back as one contact sheet, so one image
DEFAULT_STILLS = 6
SHEET_MAX_SIDE = 1280          # longest side of the contact sheet (image tokens follow the pixel size)
SINGLE_FRAME_MAX_SIDE = 768    # one frame asked alone is sent at this size
STILLS_SENT = "stills-sent.json"  # <project>/cache/: picture hashes of the last stills call
SHEET_LABEL_H = 40             # timecode and scene line under each cell
SHEET_BG = (18, 18, 22)
EMPTY_FRAME_SPREAD = 3         # a still whose channels all lie within this many levels is one colour
BUNDLE_KEEP_S = 600            # bundles of other engine states older than this are removed
BUNDLE_DIR = "bundle"          # <project>/cache/bundle/<key>/, one per engine state
STILLS_WAIT_S = 90.0           # stills usually finish inside one tool call (bundle + a few frames)
# Information only: a stills or preview answer carries the line for the built-in preset the plan uses.
STYLE_NOTE = (
    "style: engine defaults (dark, #7C5CFA, Inter). Set your own palette, fonts and layout "
    "from the reference or the user's request."
)
STYLE_NOTE_LIGHT = (
    "style: built-in preset light (#7C5CFA accent, Inter). Set your own palette, fonts and layout "
    "from the reference or the user's request."
)
STYLE_NOTES = {"dark": STYLE_NOTE, "light": STYLE_NOTE_LIGHT}
PREVIEW_SCALE = 0.5
PREVIEW_CRF = 28
FINAL_CRF = 18
STILL_JPEG_QUALITY = 92
LOUDNESS_TP = -1.5             # true-peak ceiling, dB (design §9 step 6)
LOUDNESS_LRA = 11.0
# `loudnorm` only applies gain, so a loud transient can still pass the QA ceiling (-1 dBTP).
# The limiter after it caps the sample peaks at -2 dBFS, leaving about 1 dB for the peaks
# between samples and the AAC encode. `alimiter` takes a linear limit (0.0625 to 1):
# https://ffmpeg.org/ffmpeg-filters.html#alimiter
PEAK_LIMIT_DB = -2.0
PEAK_LIMIT = round(10 ** (PEAK_LIMIT_DB / 20), 4)  # 0.7943
# level=disabled: the default auto-levels the output back up to 0 dBFS.
# latency=true: delay the audio by the lookahead so it stays in sync.
LIMITER_FILTER = f"alimiter=limit={PEAK_LIMIT}:attack=5:release=50:level=disabled:latency=true"
AUDIO_BITRATE = "192k"
COMPARE_MAX_WIDTH = 1600       # side-by-side image: both panels together
COMPARE_MAX_HEIGHT = 960
COMPARE_LABEL_H = 44
COMPARE_GAP = 8

CLIP_END_SLACK_S = 0.1         # container durations are rounded; `out` may exceed the file by this much
PROTOCOL = "@@ARGUS "          # prefix of the stdout lines of engine/scripts/render.mjs
DEFAULT_SFX = ("whoosh.mp3", "pop.mp3", "hit.wav")
MEDIA_DIR = "m"                # inside the public dir; plan files are linked here
PUBLIC_INDEX = "public-index.json"  # <project>/cache/: public name under m/ -> source file (see _PublicDir)
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
                check=True, creationflags=NO_WINDOW,
            )
    return cache


def engine_dir() -> Path:
    """The Remotion engine folder: `ARGUS_ENGINE_DIR`, the repository `engine/`, or `~/.argus/engine`."""
    return resolve_engine_dir()


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


def _resolve_file(value: str, bases: Sequence[Path]) -> Path | None:
    """`resolve_asset`, plus the built-in sound names (`whoosh.mp3`, `pop.mp3`, `hit.wav`) that are synthesized on demand."""
    found = resolve_asset(value, bases)
    if found is None and _builtin_sfx(value):
        found = (_ensure_default_sfx() / Path(value).name).resolve()
    return found


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
            if event.src is not None:  # a `sound` event names no file
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


def _plan_warnings(plan: Plan, words: list[dict] | None = None) -> list[str]:
    """Things the plan asks for that this engine version does not draw or apply.

    With the caption `words`, also the accent words that are never spoken: the engine boxes
    nothing for them. Matching follows the engine (exact, "prefix*" or "*").
    """
    notes: list[str] = []
    music = plan.audio.music if plan.audio else None
    if music is not None and music.duck < 1 and plan.captions is None:
        notes.append("audio.music.duck has no effect without `captions`: the ducking follows the caption words")
    if plan.captions is not None and words is not None:
        spoken = [_caption_token(w["w"]) for w in words]
        for entry in plan.captions.accent_words:
            if entry == "*":
                continue
            if entry.endswith("*"):
                prefix = _caption_token(entry[:-1])
                found = any(t.startswith(prefix) for t in spoken)
            else:
                found = _caption_token(entry) in spoken
            if not found:
                notes.append(
                    f"captions.accent_words: {entry!r} is not spoken in captions.words, so no word is boxed for it"
                )
    return notes


def scene_label(plan: Plan, t: float) -> str:
    """Which plan scenes are on screen at `t`, as `scenes[i]` (a full scene, and an overlay if one covers `t`).

    Same rule as the engine: a full scene lasts until the next full scene starts (or its `until`).
    """
    full = [i for i, s in enumerate(plan.scenes) if not s.overlay and s.at <= t]
    base = max(full, key=lambda i: plan.scenes[i].at) if full else None
    overlays = [
        i for i, s in enumerate(plan.scenes)
        if s.overlay and s.at <= t and (s.until is None or t < s.until)
    ]
    parts = ([f"scenes[{base}]"] if base is not None else []) + [f"scenes[{i}] overlay" for i in overlays]
    return " + ".join(parts) if parts else "no scene"


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
    save_sounds: Any = None,
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

    component_errors, component_warnings = check_components(parsed, project_root, project_library_dir(project_root))
    errors += component_errors

    words, word_errors = _caption_words(parsed, bases)
    errors += word_errors

    cue_seconds: dict[str, float] = {}
    follows_words = any(isinstance(c, WordCue) for c in parsed.cues.values())
    if parsed.cues and (words is not None or not follows_words):  # no words: the cause is reported above
        cue_seconds, cue_errors = resolve_cues(parsed.cues, words)
        errors += cue_errors

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

    clean_saves: list[dict] | None = None
    if save_sounds is not None:
        if mode != "audio":
            errors.append("save_sounds: only works with mode='audio' (save the sounds you approved after listening)")
        elif parsed is not None and not errors:
            clean_saves, save_errors = sounds.validate_save_sounds(save_sounds, parsed, project_library_dir(project_root))
            errors += save_errors

    if errors or resolved is None:
        return None, errors
    payload = {
        "mode": mode,
        "name": name_slug,
        "project_root": str(project_root),
        "bases": [str(b) for b in bases],
        "plan": resolved.to_dict(),
        "caption_words": words,
        "cues": cue_seconds,
        "times": clean_times,
        "compare": compare_payload,
        "warnings": _plan_warnings(resolved, words) + component_warnings,
    }
    if clean_saves is not None:
        payload["save_sounds"] = clean_saves
    return payload, []


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
    """The per-job public dir: engine fonts plus every file of the plan, under `m/`.

    `index` is the project's `cache/public-index.json`, which maps each name under `m/` to its source
    file. Custom components name media by that path, so `link_component_media` needs it to link a file
    that an earlier job added and this job's plan no longer names.
    """

    def __init__(self, root: Path, bases: Sequence[Path], index: Path | None = None, collect: bool = False) -> None:
        self.root = root
        self.bases = list(bases)
        # `collect` (stills jobs, task 20.10 item 5c): a missing file is listed in `missing` instead of raising,
        # so the stills job reports every missing file at once.
        self.collect = collect
        self.missing: list[str] = []
        self._done: dict[Path, str] = {}
        self._index_path = index
        self._names: dict[str, str] = _read_name_index(index)
        self._new: dict[str, str] = {}
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
            if self.collect:
                self.missing.append(f"{where}: file not found: {value}")
                return value
            raise FileNotFoundError(f"{where}: file not found: {value}")
        rel = self._done.get(src)
        if rel is None:
            digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:8]
            rel = f"{MEDIA_DIR}/{digest}-{_SAFE_NAME.sub('_', src.name)}"
            _link_or_copy(src, self.root / rel)
            self._done[src] = rel
            if self._names.get(rel) != str(src):
                self._new[rel] = str(src)
                self._names[rel] = str(src)
        return rel

    def source_of(self, rel: str) -> Path | None:
        """The source file a name under `m/` was made from, from this project's index."""
        value = self._names.get(rel)
        return Path(value) if value else None

    def remember(self) -> None:
        """Merge the names this job added into the project index.

        Jobs of one project can run at the same time, so the file is read again before it is
        written. The index is only a shortcut: a failed write is ignored.
        """
        if self._index_path is None or not self._new:
            return
        merged = _read_name_index(self._index_path)
        merged.update(self._new)
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._index_path.with_name(f"{self._index_path.name}.{uuid.uuid4().hex[:6]}.tmp")
            tmp.write_text(json.dumps(merged, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self._index_path)
        except OSError:
            return
        self._new = {}


def _read_name_index(path: Path | None) -> dict[str, str]:
    """`{name under m/: source path}` from the project index; empty when missing or unreadable."""
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


COMPONENT_MEDIA = re.compile(r"m/[0-9a-f]{8}-[A-Za-z0-9._-]+")


def link_component_media(public: _PublicDir, components: Path) -> list[str]:
    """Link the files that custom components name by their public path, `m/<digest>-<file>`.

    A component reads a media file by the name `_PublicDir.add` gave it in an earlier job
    (`components/mediaPaths.ts`). A plan that no longer names that file would leave it out of the
    public dir, and the render would fail with HTTP 404 on the file. The name is looked up in the
    project index and the file is linked again. Returns the names that were linked.
    """
    if not components.is_dir():
        return []
    named: set[str] = set()
    for path in components.rglob("*"):
        if path.is_file() and path.suffix in (".ts", ".tsx"):
            named.update(COMPONENT_MEDIA.findall(path.read_text(encoding="utf-8", errors="replace")))
    linked: list[str] = []
    for rel in sorted(named):
        dst = public.root / rel
        if dst.exists():
            continue
        src = public.source_of(rel)
        if src is None or not src.is_file():
            continue  # never added by a job of this project: nothing to link, the render reports the 404
        _link_or_copy(src, dst)
        linked.append(rel)
    return linked


PROJECT_MEDIA_NAME = re.compile(r"""["'`]([A-Za-z0-9_./-]+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mov))["'`]""", re.IGNORECASE)


def _media_key(name: str) -> str:
    """The name under `m/` for a project file a component names. Must match `mediaKey` in engine/src/kit/media.ts."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def link_project_images(public: _PublicDir, components: Path, bases: Sequence[Path]) -> dict[str, str]:
    """Link every project file that a custom component names in a string, e.g. `mediaUrl("media/octo.png")`.

    Plan files are linked by `_PublicDir.add`; a component names its files only in its own code, so
    this scans the component sources for image and video names and resolves them in the project
    folder, then the other bases. Names that do not resolve are left out, and the render reports the
    missing file. Returns `{name: "m/<key>"}` for the files it linked.
    """
    if not components.is_dir():
        return {}
    names: set[str] = set()
    for path in components.rglob("*"):
        if path.is_file() and path.suffix in (".ts", ".tsx"):
            names.update(PROJECT_MEDIA_NAME.findall(path.read_text(encoding="utf-8", errors="replace")))
    linked: dict[str, str] = {}
    for name in sorted(names):
        src = resolve_asset(name, bases)
        if src is None or not src.is_file():
            continue
        rel = f"{MEDIA_DIR}/{_media_key(name)}"
        if not (public.root / rel).exists():
            _link_or_copy(src, public.root / rel)
        linked[name] = rel
    return linked


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


def engine_plan_with_sounds(plan: dict, placed: Sequence[sounds.Placed]) -> dict:
    """A copy of the plan dict whose `audio.sfx` holds the rendered events (numbers and files) for the engine.

    The named `sounds` are dropped: the engine only plays the events.
    """
    out = json.loads(json.dumps(plan))
    audio = out["audio"]
    audio["sfx"] = sounds.engine_events(placed)
    audio.pop("sounds", None)
    return out


def _engine_props(
    plan: dict,
    words: list[dict] | None,
    public: _PublicDir,
    *,
    with_audio: bool,
    clip_media: Sequence[media_prep.ClipMedia] | None = None,
    cues: Mapping[str, float] | None = None,
) -> dict:
    """The plan as the engine wants it: every file path points into the public dir, words are inline.

    `cues` are the plan's cues resolved to seconds (`resolve_cues`); the engine gets only those.
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
    props["cues"] = dict(cues or {})
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
    # Default: half the CPU threads. Measured on the 4-thread author PC (10 s slice, frames + encode):
    # 2 workers 41 s and 51 s, 3 workers 48 s and 55 s, 4 workers 50 s. No gain above 2, so the
    # default stays; ARGUS_RENDER_CONCURRENCY still overrides it.
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
    result: dict | None = None
    failure: str | None = None
    tail: deque[str] = deque(maxlen=30)
    with open(work / "render.log", "wb") as log:
        proc = subprocess.Popen(
            [node, str(script), str(spec_path)],
            cwd=engine_dir(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
            text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
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


# ------------------------------------------------------------------ bundle reuse

def bundle_key(public_root: Path) -> str:
    """Digest of the engine state a bundle is built from: `engine/src` (with the generated custom
    files), `engine/package.json`, and the job's public dir (names, sizes, modification times).

    Equal digests mean the bundle of an earlier job is the same program and can be served again.
    Props are not part of the bundle, so a new plan with the same engine state reuses it.
    """
    engine = engine_dir()
    digest = hashlib.sha256(f"argus {__version__}\n".encode("utf-8"))
    for path in sorted((engine / "src").rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(engine).as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    digest.update((engine / "package.json").read_bytes())
    for path in sorted(public_root.rglob("*")):
        if path.is_file():
            st = path.stat()
            digest.update(f"{path.relative_to(public_root).as_posix()}\0{st.st_size}\0{st.st_mtime_ns}\0".encode("utf-8"))
    return digest.hexdigest()


def _prune_bundles(bundles: Path, keep: Path) -> None:
    """Remove bundles of other engine states that have not been touched for `BUNDLE_KEEP_S`."""
    now = time.time()
    for old in bundles.iterdir():
        if old != keep and old.is_dir() and now - old.stat().st_mtime >= BUNDLE_KEEP_S:
            shutil.rmtree(old, ignore_errors=True)


def _restore_public(bundle: Path, public_src: Path) -> list[str]:
    """Link every file of the job's public dir that `bundle/public` lacks; returns their relative paths.

    A cached bundle was seen without its `public/fonts` folder (a 404 for the font at render time),
    so the files are checked again before the bundle is served.
    """
    added: list[str] = []
    for src in sorted(public_src.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(public_src)
        dst = bundle / "public" / rel
        if not dst.exists():
            _link_or_copy(src, dst)
            added.append(rel.as_posix())
    return added


def _run_node_bundled(
    spec: dict,
    work: Path,
    report: Callable[..., None],
    lo: float,
    hi: float,
    hold: EngineHold | None,
    root: Path,
    key: str,
) -> dict:
    """`_run_node`, but the bundle is taken from `<project>/cache/bundle/<key>/` when it is there.

    A new bundle is built in a temporary folder and renamed into place after the node script
    succeeds, so a failed render never leaves a half bundle behind.
    """
    bundles = root / "cache" / BUNDLE_DIR
    final = bundles / key[:16]
    building: Path | None = None
    if (final / "index.html").is_file():
        added = _restore_public(final, Path(spec["publicDir"]))
        if added:
            report(lo, "bundle: restored missing public files: " + ", ".join(added))
        spec["serveUrl"] = str(final)  # the node script skips the bundle step
    else:
        bundles.mkdir(parents=True, exist_ok=True)
        building = bundles / f"{key[:16]}.tmp-{uuid.uuid4().hex[:6]}"
        spec["bundleDir"] = str(building)
    try:
        result = _run_node(spec, work, report, lo, hi, hold)
        if building is not None:
            try:
                os.replace(building, final)
            except OSError:
                pass  # a parallel job stored the same engine state first
            _prune_bundles(bundles, final)
        return result
    finally:
        if building is not None and building.exists():
            shutil.rmtree(building, ignore_errors=True)


# ------------------------------------------------------------------ stills

def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_hashes(path: Path) -> set[str]:
    """Picture hashes of the previous stills call; empty when there is none or the file is unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(h) for h in data} if isinstance(data, list) else set()


def _write_hashes(path: Path, hashes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hashes), encoding="utf-8")


def one_colour(path: Path) -> tuple[int, int, int] | None:
    """The mean colour of a still that is one colour all over (an empty frame), else None."""
    with PILImage.open(path) as img:
        bands = img.convert("RGB").getextrema()
    if all(hi - lo <= EMPTY_FRAME_SPREAD for lo, hi in bands):
        return tuple((lo + hi) // 2 for lo, hi in bands)  # type: ignore[return-value]
    return None


def sheet_grid(n: int, ratio: float) -> tuple[int, int, int, int]:
    """Grid for `n` pictures of width/height `ratio`: (cols, rows, cell_w, cell_h).

    The sheet's longest side stays within `SHEET_MAX_SIDE`, labels included.
    """
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell_w = int(min(SHEET_MAX_SIDE / cols, ratio * (SHEET_MAX_SIDE - rows * SHEET_LABEL_H) / rows))
    return cols, rows, cell_w, round(cell_w / ratio)


def build_contact_sheet(cells: Sequence[tuple[Path | None, str]], out: Path) -> Path:
    """One JPEG: every picture in a grid, reading order, each with its label under it.

    The pictures of one call share a size; the first real one sets the grid. A cell with no
    picture (`None`) is a grey box: the frame was sent by an earlier call.
    """
    with PILImage.open(next(p for p, _ in cells if p is not None)) as first:
        ratio = first.width / first.height
    cols, rows, cw, ch = sheet_grid(len(cells), ratio)
    sheet = PILImage.new("RGB", (cols * cw, rows * (ch + SHEET_LABEL_H)), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    size = max(12, min(22, cw // 17))
    font = _label_font(size)
    for i, (picture, label) in enumerate(cells):
        x, y = (i % cols) * cw, (i // cols) * (ch + SHEET_LABEL_H)
        if picture is None:
            draw.rectangle([x, y, x + cw - 1, y + ch - 1], fill=(44, 44, 52))
            label = f"{label} | unchanged"
        else:
            with PILImage.open(picture) as img:
                sheet.paste(img.convert("RGB").resize((cw, ch), PILImage.Resampling.LANCZOS), (x, y))
        while len(label) > 4 and draw.textlength(label, font=font) > cw - 16:
            label = label[:-2] + "…"
        draw.text((x + 8, y + ch + SHEET_LABEL_H // 2), label, fill=(235, 235, 240), font=font, anchor="lm")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, format="JPEG", quality=90)
    return out


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
                f":offset={measured['target_offset']}:linear=true,{LIMITER_FILTER}"
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


def _run_audio(payload: dict, plan: Plan, root: Path, report: Callable[..., None], started: float) -> dict:
    """`render_video(mode="audio")`: the sound mix, its timeline image and checks. No browser, no bundle."""
    bases = [Path(b) for b in payload["bases"]]
    name = str(payload["name"])
    cues = {k: float(v) for k, v in (payload.get("cues") or {}).items()}
    report(0.05, "placing the sounds")
    t_prep = time.monotonic()
    placed, sfx_warnings = sounds.resolve_events(plan, cues, root / "cache" / "sfx", lambda v: _resolve_file(v, bases))
    voice = plan.audio.voice if plan.audio else None
    music = plan.audio.music if plan.audio else None
    voice_path = resolve_asset(voice.src, bases) if voice is not None else None
    music_path = resolve_asset(music.src, bases) if music is not None else None
    renders = root / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    report(0.4, "mixing")
    audio = sounds.audio_render(
        plan, placed, sfx_warnings, voice_path, music_path, payload.get("caption_words"), cues,
        renders / f"{name}-audio.wav", renders / f"{name}-{AUDIO_TIMELINE_NAME}.jpg",
        title=f"{name} · {plan.format} · {plan.duration:g} s",
    )
    result: dict[str, Any] = {
        "mode": "audio",
        "format": plan.format,
        "duration": plan.duration,
        "project": root.name,
        "images": [{"path": str(renders / f"{name}-{AUDIO_TIMELINE_NAME}.jpg")}],
        "image_max_side": TIMELINE_MAX_SIDE,
        **audio,
    }
    if payload.get("save_sounds"):
        report(0.9, "saving the approved sounds")
        result["saved_sounds"] = sounds.save_sounds(payload["save_sounds"], project_library_dir(root), root.name)
    result["elapsed_s"] = round(time.monotonic() - started, 1)
    result["timing"] = {"prepare_s": round(t_prep - started, 3), "total_s": round(time.monotonic() - started, 3)}
    return result


def style_note(mode: str, plan: Plan) -> str | None:
    """`style_note` for a stills or preview answer whose plan uses a built-in preset (dark or light); else None."""
    if mode not in ("stills", "preview"):
        return None
    preset = builtin_preset(plan.style)
    return STYLE_NOTES[preset] if preset is not None else None


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Worker side of `render_video` (job kind `render`)."""
    started = time.monotonic()
    plan = Plan.model_validate(payload["plan"])
    mode = str(payload["mode"])
    name = str(payload["name"])
    root = Path(payload["project_root"])
    if mode == "audio":
        return _run_audio(payload, plan, root, report, started)
    fmt = plan.format
    tag = _fmt_tag(fmt)
    renders = root / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    work = root / ".work" / f"render-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True)

    timing: dict[str, Any] = {}
    report(0.01, "preparing files")
    public = _PublicDir(
        work / "public", [Path(b) for b in payload["bases"]], index=root / "cache" / PUBLIC_INDEX,
        collect=mode == "stills",
    )
    bases = [Path(b) for b in payload["bases"]]
    clip_media = _prepare_clip_media(plan, bases, root, with_audio=mode != "stills", report=report)
    # Sound events become WAV files at known times (`sounds.resolve_events`); the engine only plays them.
    sfx_warnings: list[str] = []
    engine_plan = payload["plan"]
    if mode != "stills" and plan.audio is not None:
        placed, sfx_warnings = sounds.resolve_events(
            plan, payload.get("cues") or {}, root / "cache" / "sfx", lambda v: _resolve_file(v, bases),
        )
        engine_plan = engine_plan_with_sounds(payload["plan"], placed)
    props = _engine_props(
        engine_plan, payload.get("caption_words"), public,
        with_audio=mode != "stills", clip_media=clip_media, cues=payload.get("cues"),
    )
    if public.missing:  # stills only (task 20.10 item 5c): every missing file at once, nothing is drawn
        shutil.rmtree(work, ignore_errors=True)
        return {
            "engine": f"ARGUS {__version__}",
            "valid": False,
            "mode": mode,
            "missing_media": public.missing,
            "summary": f"{len(public.missing)} media file(s) not found, so no still was drawn. "
                       "Fix the paths in the plan, then render the stills again.",
        }
    relinked = link_component_media(public, root / COMPONENTS_DIR)
    linked_images = link_project_images(public, root / COMPONENTS_DIR, bases)
    public.remember()
    spec: dict[str, Any] = {
        "props": props,
        "publicDir": str(public.root),
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
    if linked_images:
        result["linked_images"] = linked_images  # project files a component names with mediaUrl("...")
    if relinked:
        result["relinked_media"] = relinked  # files a component names that this plan does not
    if payload.get("warnings") or sfx_warnings:
        result["warnings"] = [*payload.get("warnings", []), *sfx_warnings]
    if (note := style_note(mode, plan)) is not None:
        result["style_note"] = note
    proxies = [
        {"clip": i, "source": str(m.source), "proxy": str(m.path), "why": list(m.reasons)}
        for i, m in enumerate(clip_media) if m.proxied
    ]
    if proxies:
        result["proxies"] = proxies

    # Reserve the engine folder until the bundle is built; custom components are installed and
    # typechecked here. `_run_node` releases the hold (and `acquire` cleans up when it raises).
    report(0.02, "preparing the engine")
    hold = EngineHold(engine_dir(), root, used_components(plan), work, library_root=project_library_dir(root))
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
    # The engine state (engine/src with the generated custom files, and the public files) decides
    # whether a bundle from an earlier job can be reused. Computed while the engine lock is held.
    try:
        bundle_key_value = bundle_key(public.root)
    except Exception:
        hold.release()  # `_run_node` would release it; without a node step nothing else does
        raise

    timing["prepare_s"] = round(time.monotonic() - started, 3)
    if mode == "stills":
        times: list[float] = payload["times"]
        compare = payload.get("compare")
        _remove_stale(renders, f"{name}-stills-{tag}-*")
        _remove_stale(renders, f"{name}-compare-{tag}-*")
        files = [renders / f"{name}-stills-{tag}-{i + 1:02d}-t{t:.2f}s.jpg" for i, t in enumerate(times)]
        spec.update(mode="stills", times=times, outputs=[str(f) for f in files], quality=STILL_JPEG_QUALITY)
        node = _run_node_bundled(spec, work, report, 0.03, 0.9 if compare else 0.97, hold, root, bundle_key_value)
        timing.update(node.get("timing") or {})
        for i, f in enumerate(files):
            colour = one_colour(f)
            if colour is not None:
                result.setdefault("warnings", []).append(
                    f"stills[{i}] at {times[i]:.2f} s is one colour (#{colour[0]:02X}{colour[1]:02X}{colour[2]:02X}), "
                    f"so it is an empty frame; fine only if the plan wants a blank moment ({scene_label(plan, times[i])})"
                )
        report(0.92, "building the images")
        t_sheet = time.monotonic()
        entries: list[dict] = []
        for i, t in enumerate(times):
            entry: dict[str, Any] = {"t": t, "scene": scene_label(plan, t)}
            if compare:
                ref_t = compare["times"][i]
                ref_frame = work / f"reference-{i + 1:02d}.jpg"
                _extract_reference_frame(compare["video"], ref_t, ref_frame)
                out = renders / f"{name}-compare-{tag}-{i + 1:02d}-t{t:.2f}s.jpg"
                compose_side_by_side(
                    ref_frame, files[i], out, f"REFERENCE {format_time(ref_t)}", f"RENDER {format_time(t)}",
                )
                entry.update(reference_t=ref_t, path=str(out))
            else:
                entry["path"] = str(files[i])
            entries.append(entry)
        # A picture the previous stills call of this project already sent is not sent again (task 20.10 item 16).
        sent_file = root / "cache" / STILLS_SENT
        before = _read_hashes(sent_file)
        for e in entries:
            e["hash"] = _file_hash(Path(e["path"]))
            e["unchanged"] = e["hash"] in before
        _write_hashes(sent_file, [e["hash"] for e in entries])
        if len(entries) >= 2:
            # One image for the model: every frame in a grid, each cell labelled with its time and scenes.
            # An unchanged frame keeps its cell as a grey box, so the grid stays in place.
            sheet = renders / f"{name}-{'compare' if compare else 'stills'}-{tag}-sheet.jpg"
            cells = [
                (None if e["unchanged"] else Path(e["path"]), f"t {e['t']:.2f} s | {e['scene']}") for e in entries
            ]
            if any(not e["unchanged"] for e in entries):
                build_contact_sheet(cells, sheet)
                result["images"] = [{"path": str(sheet), "cells": entries}]
            else:
                result["images"] = []
            result["image_max_side"] = SHEET_MAX_SIDE
        else:
            result["images"] = [] if entries[0]["unchanged"] else entries
            result["image_max_side"] = COMPARE_MAX_WIDTH if compare else SINGLE_FRAME_MAX_SIDE
        unchanged = [e["t"] for e in entries if e["unchanged"]]
        if unchanged:
            result["unchanged"] = unchanged
            result["unchanged_note"] = (
                "these frames are the same pictures the previous stills call sent, so they are not sent again"
            )
        timing["sheet_s"] = round(time.monotonic() - t_sheet, 3)
        result["stills"] = [str(f) for f in files]
        result["note"] = (
            "one image: a contact sheet, each cell shows its time and the scenes on screen; "
            "reference on the left of each cell, render on the right"
            if compare and len(entries) >= 2 else
            "images are side by side: reference on the left, render on the right"
            if compare else
            "one image: a contact sheet, each cell shows its time and the scenes on screen; "
            "full-size frames are listed in `stills`" if len(entries) >= 2 else
            "stills of the render; the full-size files are listed in `stills`"
        )
    else:
        out = renders / f"{name}-{mode}-{tag}.mp4"
        raw = work / "raw.mp4"
        preview = mode == "preview"
        spec.update(
            mode="media", output=str(raw), scale=PREVIEW_SCALE if preview else 1,
            crf=PREVIEW_CRF if preview else FINAL_CRF,
        )
        timing.update(_run_node_bundled(spec, work, report, 0.03, 0.9, hold, root, bundle_key_value).get("timing") or {})
        report(0.92, "finishing the file")
        if preview:
            os.replace(raw, out)
        else:
            t_fin = time.monotonic()
            result.update(finalize_video(raw, out))
            timing["finalize_s"] = round(time.monotonic() - t_fin, 3)
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
        if not preview and "qa" in payload.get("then", []):
            # `then: ["qa"]`: the technical checks run in this job, so the model makes one call less.
            from . import qa as qa_checks

            report(0.96, "checking the file")
            t_qa = time.monotonic()
            checked = qa_checks.verify_video(out, format=fmt)
            timing["qa_s"] = round(time.monotonic() - t_qa, 3)
            result["qa"] = {k: checked[k] for k in ("passed", "failures", "warnings", "summary") if k in checked}
        if not preview and "export" in payload.get("then", []):
            # `then: ["export"]`: the publishing folder is written in this job, from the file rendered here.
            report(0.97, "writing the export")
            t_exp = time.monotonic()
            result["export"] = _chained_export(root, out, fmt, payload.get("export") or {}, report)
            timing["export_s"] = round(time.monotonic() - t_exp, 3)

    shutil.rmtree(work, ignore_errors=True)
    result["elapsed_s"] = round(time.monotonic() - started, 1)
    timing["total_s"] = round(time.monotonic() - started, 3)
    result["timing"] = timing
    # ARGUS time per stage only (model time is outside ARGUS); the worker sends stderr to the job's log.txt.
    print("ARGUS stage times: " + ", ".join(f"{k} {v}" for k, v in timing.items()), file=sys.stderr, flush=True)
    return result


def _chained_export(root: Path, out: Path, fmt: str, args: dict, report: Any) -> dict:
    """`then: ["export"]`: run the export job's own functions in this job, with this render's final file.

    `args` are the arguments of `export_package` (`texts`, `cover_times`, `name`, `save_to_library`).
    The project and the video come from this render, so the model does not pass them again.
    """
    from . import export as export_job  # local: the export module is not needed by a plain render

    payload, errors = export_job.prepare_export(
        root, {fmt: str(out)}, args.get("texts") or {}, args.get("cover_times"),
        args.get("name"), args.get("save_to_library"),
    )
    if payload is None:
        return {"valid": False, "errors": errors, "note": "the export was not written; fix the listed problems"}
    return export_job.run_job(payload, report)


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
    save_sounds: Any = None,
    then: list[str] | None = None,
    export: Any = None,
) -> dict | list:
    """Tool logic of `render_video`: validate, then run the `render` job.

    `then` may hold "qa" and "export"; "export" takes `export`, the arguments of `export_package`, and
    writes the publishing folder from this render's final file (task 20.10 item 22).
    An invalid request returns `{"valid": false, "errors": [...]}` and starts nothing.
    """
    root = project_dir(project)
    chained = [str(step) for step in (then or [])]
    bad_steps = [
        f"then: {step!r} is not a step; the steps are \"qa\" and \"export\"" for step in chained if step not in ("qa", "export")
    ]
    if "export" in chained and not isinstance(export, dict):
        bad_steps.append("then: \"export\" needs `export`, the arguments of export_package as an object")
    if chained and mode != "final":
        bad_steps.append("then: applies to mode \"final\" only")
    if bad_steps:
        return {"engine": f"ARGUS {__version__}", "valid": False, "errors": bad_steps,
                "note": "nothing was rendered; fix the listed problems and call again"}
    payload, errors = prepare_render(
        plan, root, mode=mode, times=times, compare=compare, format=format, name=name, save_sounds=save_sounds,
    )
    if payload is None:
        return {
            "engine": f"ARGUS {__version__}",
            "valid": False,
            "errors": errors,
            "note": "nothing was rendered; fix the listed problems and call again",
        }
    payload["then"] = chained
    if "export" in chained:
        payload["export"] = export
    if mode != "audio" and not (engine_dir() / "node_modules").is_dir():
        raise RuntimeError(not_ready_message())
    wait = wait_s if wait_s is not None else (STILLS_WAIT_S if mode == "stills" else jobs.DEFAULT_WAIT_S)
    reply = jobs.run_or_detach("render", payload, wait_s=wait)
    from .. import state as project_state  # the project's stage for studio_guide(project=...)

    if isinstance(plan, str):
        project_state.record(project, plan=plan)
    if isinstance(reply, dict):
        project_state.record(project, last_render={
            "mode": mode, "job_id": reply.get("job_id"), "summary": str(reply.get("summary", ""))[:160],
        })
    return reply

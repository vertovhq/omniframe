"""Watching video: `watch_video` and `get_frames` (design §6).

`watch_video` gives the model what a person gets from watching a clip once: every
shot boundary, representative frames on labelled contact sheets, the spoken words
and the sharp sounds, all with timecodes. Nothing here judges the video; it only
measures and shows.

The work runs in a detached job (`jobs.run_or_detach("watch", ...)`): shot detection
decodes the whole file and transcription of a long file takes minutes. Results are
cached by file content under `<project>/cache/watch/<key>/`, in stages (analysis,
frames, transcript), so a repeated call, or a call with another `page`, costs
almost nothing.

`get_frames` returns exact frames (optionally cropped) as images, inline.
"""

from __future__ import annotations

import bisect
import hashlib
import importlib.util
import json
import math
import os
import re
from collections.abc import Callable
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont, ImageOps

from .. import jobs
from ..config import CONFIG
from ..ffmpeg import FFmpegError, decode_audio, run_ffmpeg, run_ffmpeg_stderr, stream_info, temp_sibling
from ..media_out import DEFAULT_MAX_SIDE, tool_result
from ..project import project_dir, slugify
from . import beats

# --- technical detector settings (measurement parameters, not creative rules) ---
SCENE_THRESHOLD = 0.30        # ffmpeg `scene` score above which a frame starts a new shot
SCENE_WIDTH = 320             # shot detection runs on a downscaled stream, at full frame rate
ONSET_MIN_STRENGTH = 0.20     # onsets weaker than this share of the strongest one are ignored
ONSET_MIN_GAP_S = 0.08        # two sound events closer than this count as one
MAX_SOUND_EVENTS = 200

# --- frame budget and contact sheets ---
FRAME_OFFSET_S = 0.15         # a shot's frame is taken this long after its first frame
LONG_SHOT_S = 6.0             # shots longer than this also get a middle frame
HOOK_T = 0.5                  # the frame that decides whether a viewer stays
HOOK_NEAR_S = 0.2             # a chosen frame this close to the hook time already is the hook frame
DEFAULT_MAX_FRAMES = 24
MAX_FRAMES_LIMIT = 120
TILES_PER_SHEET = 6           # 2x3 for portrait video, 3x2 for landscape
SHEETS_PER_PAGE = 2           # contact sheets returned per call
SHEET_MAX_SIDE = 1600         # longest side of a contact sheet, in pixels
SHEET_GAP = 6

# --- get_frames ---
GET_FRAMES_MAX_TIMES = 8
MIN_VIEW_SIDE = 64
MAX_VIEW_SIDE = 2048

HASH_CHUNK = 8 * 1024 * 1024  # content key = size + first and last 8 MB
CACHE_VERSION = 1             # bump when the cached files change meaning

# Verbatim prompt: Whisper otherwise "tidies" Russian speech and drops stumbles and
# repeats, which the editing flow needs to see. Same prompt as the montazh skills.
RUSSIAN_VERBATIM_PROMPT = (
    "Ну, э-э, я я хотел, хотел сказать, что что это, это ми- миллион. "
    "Можно, можно ли стать... И при, и при таких условиях."
)

_PTS_RE = re.compile(r"pts_time:\s*(-?[0-9]+(?:\.[0-9]+)?)")
_whisper_models: dict[str, object] = {}


# ------------------------------------------------------------------ small helpers

def _write_json(path: Path, data: object) -> None:
    """Write JSON through a temp file, so a reader never sees a half-written cache file."""
    tmp = temp_sibling(path, ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def format_time(t: float) -> str:
    """`mm:ss.s`, rounded to a tenth (59.96 s is `01:00.0`, never `00:60.0`)."""
    tenths = max(0, round(t * 10))
    return f"{tenths // 600:02d}:{(tenths % 600) / 10:04.1f}"


def content_key(path: Path) -> str:
    """Cache key: sha256 over the file size and its first and last 8 MB."""
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as fh:
        digest.update(fh.read(HASH_CHUNK))
        if size > HASH_CHUNK:
            fh.seek(max(HASH_CHUNK, size - HASH_CHUNK))
            digest.update(fh.read(HASH_CHUNK))
    return digest.hexdigest()[:24]


def _extract_frame(src: Path, t: float, out: Path) -> bool:
    """One full-resolution frame at `t` seconds into `out`; False if ffmpeg produced nothing."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    try:
        run_ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(out)])
    except FFmpegError:
        out.unlink(missing_ok=True)
        return False
    return out.is_file() and out.stat().st_size > 0


# ------------------------------------------------------------------ shots

def detect_cuts(src: Path, duration: float) -> list[float]:
    """Times (s) where a new shot starts, from one ffmpeg pass over every frame of the file."""
    text = run_ffmpeg_stderr([
        "-i", str(src), "-an", "-sn",
        "-vf", f"scale={SCENE_WIDTH}:-2,select='gt(scene,{SCENE_THRESHOLD})',showinfo",
        "-f", "null", "-",
    ])
    cuts = sorted({round(float(m.group(1)), 3) for m in _PTS_RE.finditer(text)})
    return [t for t in cuts if 0.02 < t < duration - 0.02]


def shots_from_cuts(cuts: list[float], duration: float) -> list[list[float]]:
    """`[[start, end], ...]` covering the whole file."""
    edges = [0.0, *cuts, round(duration, 3)]
    return [[edges[i], edges[i + 1]] for i in range(len(edges) - 1)]


# ------------------------------------------------------------------ frame budget

def select_frames(shots: list[list[float]], duration: float, max_frames: int) -> list[tuple[float, int]]:
    """Pick `(time, shot_number)` frames within `max_frames` (design §6 step 4).

    Candidates: the start of every shot (+0.15 s) and the middle of shots longer than
    6 s, plus a frame at about 0.5 s (the hook). Under budget, evenly spaced frames fill
    the rest, so a one-take video still gets `max_frames` frames. Over budget, the first
    shot, the hook and the last shot stay and the rest are spread evenly over the timeline.
    `shot_number` is the 1-based position in `shots`.
    """
    latest = max(0.0, duration - 0.05)
    starts = [s for s, _ in shots]
    cands: list[tuple[float, int]] = []
    shot_start_cand: dict[int, tuple[float, int]] = {}
    for number, (start, end) in enumerate(shots, 1):
        length = end - start
        first = (round(min(start + min(FRAME_OFFSET_S, length / 2), latest), 3), number)
        shot_start_cand[number] = first
        cands.append(first)
        if length > LONG_SHOT_S:
            cands.append((round(start + length / 2, 3), number))

    hook_t = round(min(HOOK_T, latest), 3)
    near = [c for c in cands if abs(c[0] - hook_t) <= HOOK_NEAR_S]
    if near:
        hook = min(near, key=lambda c: abs(c[0] - hook_t))
    else:
        hook = (hook_t, max(1, bisect.bisect_right(starts, hook_t)))
        cands.append(hook)

    cands = sorted(set(cands))
    if len(cands) < max_frames:
        # Few detected shots (one continuous take, soft transitions the detector misses):
        # spend the rest of the budget on evenly spaced frames so no long stretch goes unseen.
        # Shot frames all stay; grid points that are not next to one fill the free slots,
        # picked evenly over the whole timeline.
        spacing = duration / max_frames
        grid: list[tuple[float, int]] = []
        for k in range(max_frames):
            t = round(min(duration * (k + 0.5) / max_frames, latest), 3)
            if all(abs(t - c[0]) >= spacing / 2 for c in cands):
                grid.append((t, max(1, bisect.bisect_right(starts, t))))
        room = max_frames - len(cands)
        for k in range(min(room, len(grid))):
            target = duration * (k + 0.5) / room
            pick = min(grid, key=lambda c: abs(c[0] - target))
            grid.remove(pick)
            cands.append(pick)
        return sorted(set(cands))
    if len(cands) <= max_frames:
        return cands

    must: list[tuple[float, int]] = []
    for c in (shot_start_cand[1], hook, shot_start_cand[len(shots)]):
        if c not in must:
            must.append(c)
    chosen = must[:max_frames]
    others = [c for c in cands if c not in chosen]
    room = max_frames - len(chosen)
    for k in range(min(room, len(others))):
        target = duration * (k + 0.5) / room
        pick = min(others, key=lambda c: abs(c[0] - target))
        others.remove(pick)
        chosen.append(pick)
    return sorted(chosen)


# ------------------------------------------------------------------ contact sheets

def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without sized default fonts
        return ImageFont.load_default()


def _sheet_layout(frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    """(columns, rows, tile_w, tile_h): 2x3 for portrait video, 3x2 otherwise; long side <= SHEET_MAX_SIDE."""
    aspect = frame_w / frame_h
    if frame_h > frame_w:
        cols, rows = 2, 3
        tile_h = (SHEET_MAX_SIDE - SHEET_GAP * (rows + 1)) // rows
        tile_w = int(tile_h * aspect)
    else:
        cols, rows = 3, 2
        tile_w = (SHEET_MAX_SIDE - SHEET_GAP * (cols + 1)) // cols
        tile_h = int(tile_w / aspect)
    return cols, rows, max(tile_w, 16), max(tile_h, 16)


def build_sheet(tiles: list[tuple[Path, float, int]], frame_size: tuple[int, int], out: Path) -> None:
    """One contact sheet of up to 6 `(frame_file, time, shot_number)` tiles, labelled `mm:ss.s  #shot`."""
    cols, rows, tile_w, tile_h = _sheet_layout(*frame_size)
    width = cols * tile_w + (cols + 1) * SHEET_GAP
    height = rows * tile_h + (rows + 1) * SHEET_GAP
    sheet = PILImage.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    font = _font(max(12, min(tile_w, tile_h) // 11))
    for n, (file, t, shot) in enumerate(tiles):
        col, row = n % cols, n // cols
        x = SHEET_GAP + col * (tile_w + SHEET_GAP)
        y = SHEET_GAP + row * (tile_h + SHEET_GAP)
        with PILImage.open(file) as img:
            tile = ImageOps.contain(img.convert("RGB"), (tile_w, tile_h), PILImage.Resampling.LANCZOS)
        sheet.paste(tile, (x, y))
        label = f"{format_time(t)}  #{shot}"
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        pad = 4
        draw.rectangle((x, y, x + (right - left) + 2 * pad, y + (bottom - top) + 2 * pad), fill=(0, 0, 0))
        draw.text((x + pad - left, y + pad - top), label, fill=(255, 255, 255), font=font)
    staged = temp_sibling(out, ".tmp")
    try:
        sheet.save(staged, format="JPEG", quality=85)
        os.replace(staged, out)
    finally:
        staged.unlink(missing_ok=True)


# ------------------------------------------------------------------ sound events

def detect_sound_events(src: Path) -> tuple[list[dict], str | None]:
    """Sharp sound onsets as `[{"t", "strength"}]` (strength 0..1 relative to the strongest), plus a note if none.

    Uses the onset envelope of `tools/beats.py`. Each envelope peak is then moved to
    the first sample that reaches a quarter of the local maximum, because the envelope
    window is ~46 ms long and would place the onset up to a window early.
    """
    import numpy as np

    samples = decode_audio(src, beats.RATE)
    try:
        env = np.asarray(beats._onset_envelope(samples), dtype=np.float64)
    except ValueError as exc:  # too short, or silent
        return [], str(exc)

    padded = np.pad(env, 1)
    peaks = np.flatnonzero((env >= ONSET_MIN_STRENGTH) & (env >= padded[:-2]) & (env > padded[2:]))
    min_gap = ONSET_MIN_GAP_S * beats.RATE / beats.HOP
    kept: list[int] = []
    for i in sorted(peaks.tolist(), key=lambda k: -env[k]):
        if all(abs(i - j) >= min_gap for j in kept):
            kept.append(i)
    kept = sorted(kept[:MAX_SOUND_EVENTS])

    events = []
    for i in kept:
        lo = max(0, (i - 2) * beats.HOP)
        hi = min(samples.size, i * beats.HOP + beats.WIN + beats.HOP)
        seg = np.abs(samples[lo:hi])
        first = int(np.argmax(seg >= 0.25 * seg.max())) if seg.size and seg.max() > 0 else 0
        events.append({"t": round((lo + first) / beats.RATE, 3), "strength": round(float(env[i]), 2)})
    return events, None


# ------------------------------------------------------------------ transcript

def whisper_available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _whisper_model(name: str):
    """The faster-whisper model `name`, loaded once per process (CPU, int8)."""
    if name not in _whisper_models:
        from faster_whisper import WhisperModel

        _whisper_models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _whisper_models[name]


def transcribe(src: Path, language: str | None, duration: float, report: Callable[..., None]) -> dict:
    """Word-level transcript with timestamps -> `{language, words, segments}`.

    Audio goes in as a 16 kHz numpy array (avoids PyAV/faster-whisper incompatibilities);
    `vad_filter` skips silence, `condition_on_previous_text=False` and `temperature=0`
    keep long files from drifting. Russian gets the verbatim prompt so stumbles and
    repeats survive.
    """
    model = _whisper_model(CONFIG.whisper_model)
    audio = decode_audio(src, 16000)
    lang = language
    if lang is None:
        try:
            lang = model.detect_language(audio)[0]
        except Exception:  # detection is a convenience; transcribe() can still auto-detect
            lang = None
    segments_iter, info = model.transcribe(
        audio,
        language=lang,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,
        initial_prompt=RUSSIAN_VERBATIM_PROMPT if lang == "ru" else None,
        temperature=0,
    )
    words: list[dict] = []
    segments: list[dict] = []
    for seg in segments_iter:
        segments.append({"s": round(seg.start, 2), "e": round(seg.end, 2), "text": seg.text.strip()})
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)})
        if duration > 0:
            report(0.65 + 0.3 * min(1.0, seg.end / duration), f"transcribing {seg.end:.0f}s of {duration:.0f}s")
    return {"language": lang or getattr(info, "language", None), "words": words, "segments": segments}


# ------------------------------------------------------------------ watch pipeline

def _analysis(src: Path, cache: Path, report: Callable[..., None]) -> tuple[dict, bool]:
    """Probe, shots and sound events of the file -> (analysis, from_cache)."""
    path = cache / "analysis.json"
    stored = _read_json(path)
    if stored and stored.get("version") == CACHE_VERSION:
        return stored, True

    info = stream_info(src)
    if not info.has_video:
        raise ValueError(f"no video stream in {src}")
    if not info.duration or info.duration <= 0:
        raise ValueError(f"cannot read the duration of {src}")
    report(0.1, "detecting shots")
    cuts = detect_cuts(src, info.duration)
    events: list[dict] = []
    note = None
    if info.has_audio:
        report(0.4, "listening for sound events")
        events, note = detect_sound_events(src)
    else:
        note = "the file has no audio track"
    analysis = {
        "version": CACHE_VERSION,
        "duration": round(info.duration, 3),
        "width": info.width,
        "height": info.height,
        "fps": info.fps,
        "has_audio": info.has_audio,
        "shots": shots_from_cuts(cuts, info.duration),
        "sound_events": events,
        "sound_events_note": note if not events else None,
    }
    _write_json(path, analysis)
    return analysis, False


def _frames_stage(src: Path, cache: Path, analysis: dict, max_frames: int, report: Callable[..., None]) -> tuple[dict, bool]:
    """Selected frames and their contact sheets for this frame budget -> (stage, from_cache)."""
    path = cache / f"frames.{max_frames}.json"
    stored = _read_json(path)
    if stored and stored.get("version") == CACHE_VERSION:
        files = [Path(f["file"]) for f in stored["frames"]] + [Path(s["file"]) for s in stored["sheets"]]
        if all(f.is_file() for f in files):
            return stored, True

    report(0.5, "extracting frames")
    frames_dir = cache / "frames"
    frames: list[dict] = []
    for t, shot in select_frames(analysis["shots"], analysis["duration"], max_frames):
        out = frames_dir / f"t{round(t * 1000):08d}.jpg"
        if out.is_file() or _extract_frame(src, t, out):
            frames.append({"t": t, "file": str(out), "shot": shot})
    if not frames:
        raise RuntimeError(f"could not extract any frame from {src}")

    with PILImage.open(frames[0]["file"]) as probe:
        frame_size = probe.size  # display size: ffmpeg applies the rotation flag, ffprobe's width/height do not

    report(0.58, "building contact sheets")
    sheets = []
    for k in range(math.ceil(len(frames) / TILES_PER_SHEET)):
        group = frames[k * TILES_PER_SHEET:(k + 1) * TILES_PER_SHEET]
        # `.view.jpg` marks the file as ready for the model: media_out will not copy it again
        out = cache / f"sheet_{max_frames}_{k + 1:02d}.view.jpg"
        build_sheet([(Path(f["file"]), f["t"], f["shot"]) for f in group], frame_size, out)
        sheets.append({"file": str(out), "times": [f["t"] for f in group]})

    stage = {"version": CACHE_VERSION, "frame_size": list(frame_size), "frames": frames, "sheets": sheets}
    _write_json(path, stage)
    return stage, False


def _transcript_stage(src: Path, cache: Path, language: str | None, duration: float,
                      report: Callable[..., None]) -> tuple[dict, bool]:
    """Words and segments -> (stage, from_cache). One transcript is kept per file; another language replaces it."""
    path = cache / "transcript.json"
    stored = _read_json(path)
    if stored and stored.get("version") == CACHE_VERSION and Path(stored["words_path"]).is_file():
        if language is None or language in (stored.get("language_requested"), stored.get("language")):
            return stored, True

    report(0.62, "transcribing")
    result = transcribe(src, language, duration, report)
    words_path = cache / "words.json"
    _write_json(words_path, result["words"])
    stage = {
        "version": CACHE_VERSION,
        "language_requested": language,
        "language": result["language"],
        "words_path": str(words_path),
        "word_count": len(result["words"]),
        "segments": result["segments"],
    }
    _write_json(cache / "segments.json", result["segments"])
    _write_json(path, stage)
    return stage, False


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Worker side of `watch_video` (called by `argus.jobs` for kind `watch`)."""
    src = Path(payload["path"]).resolve()
    project = str(payload["project"])
    max_frames = int(payload.get("max_frames", DEFAULT_MAX_FRAMES))
    want_transcript = bool(payload.get("transcript", True))
    language = payload.get("language") or None
    page = int(payload.get("page", 1))

    report(0.02, "reading file")
    key = content_key(src)
    cache = project_dir(project) / "cache" / "watch" / key
    cache.mkdir(parents=True, exist_ok=True)

    analysis, analysis_cached = _analysis(src, cache, report)
    stage, frames_cached = _frames_stage(src, cache, analysis, max_frames, report)

    transcript: dict | None = None
    transcript_cached = True
    transcript_note: str | None = None
    if not want_transcript:
        transcript_note = "transcript not requested (transcript=False)"
    elif not analysis["has_audio"]:
        transcript_note = "the file has no audio track"
    elif not whisper_available():
        transcript_note = "faster-whisper is not installed, so there is no transcript (pip install faster-whisper)"
    else:
        transcript, transcript_cached = _transcript_stage(src, cache, language, analysis["duration"], report)

    sheets = stage["sheets"]
    pages_total = max(1, math.ceil(len(sheets) / SHEETS_PER_PAGE))
    chosen = sheets[(page - 1) * SHEETS_PER_PAGE: page * SHEETS_PER_PAGE] if page >= 1 else []
    first = (page - 1) * SHEETS_PER_PAGE
    images = [
        {"sheet": first + n + 1, "times": s["times"], "path": s["file"]}
        for n, s in enumerate(chosen)
    ]
    width, height = stage["frame_size"]
    result: dict = {
        "source": str(src),
        "project": slugify(project),
        "cache_key": key,
        "cache_hit": analysis_cached and frames_cached and transcript_cached,
        "duration": analysis["duration"],
        "width": width,
        "height": height,
        "fps": analysis["fps"],
        "has_audio": analysis["has_audio"],
        "shots": analysis["shots"],
        "frames": [{"t": f["t"], "path": f["file"], "shot": f["shot"]} for f in stage["frames"]],
        "sheets_total": len(sheets),
        "pages_total": pages_total,
        "page": page,
        "words_path": transcript["words_path"] if transcript else None,
        "language": transcript["language"] if transcript else None,
        "segments": transcript["segments"] if transcript else [],
        "sound_events": analysis["sound_events"],
        "images": images,
        "image_max_side": SHEET_MAX_SIDE,
    }
    if transcript_note:
        result["transcript_note"] = transcript_note
    if analysis.get("sound_events_note"):
        result["sound_events_note"] = analysis["sound_events_note"]
    if not images:
        result["page_note"] = f"page {page} does not exist: this video has {pages_total} page(s)"
    elif page < pages_total:
        result["page_note"] = f"call again with page={page + 1} for the remaining contact sheets"
    return result


def watch_video(
    path: str,
    project: str,
    max_frames: int = DEFAULT_MAX_FRAMES,
    transcript: bool = True,
    language: str | None = None,
    page: int = 1,
    wait_s: float = jobs.DEFAULT_WAIT_S,
) -> dict | list:
    """Tool logic of `watch_video`: validate, then run the `watch` job.

    Quick results come back inline; after `wait_s` seconds the call returns a job_id instead.
    """
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"video not found: {src}")
    slugify(project)  # fail early, with a clear message, on a name that cannot become a folder
    if not 1 <= max_frames <= MAX_FRAMES_LIMIT:
        raise ValueError(f"max_frames must be between 1 and {MAX_FRAMES_LIMIT}, got {max_frames}")
    if page < 1:
        raise ValueError(f"page must be >= 1, got {page}")
    lang = (language or "").strip().lower()
    payload = {
        "path": str(src),
        "project": project,
        "max_frames": max_frames,
        "transcript": bool(transcript),
        "language": None if lang in ("", "auto") else lang,
        "page": page,
    }
    return jobs.run_or_detach("watch", payload, wait_s=wait_s)


# ------------------------------------------------------------------ get_frames

def _frames_workdir(src: Path) -> Path:
    """`<project>/.work/frames` when `src` lives in a project folder, else `<output>/.work/frames`."""
    projects = (CONFIG.output_dir / "projects").resolve()
    base = CONFIG.output_dir
    try:
        parts = src.resolve().relative_to(projects).parts
    except ValueError:
        parts = ()
    if len(parts) > 1:  # parts[0] is the project folder, the rest is a file inside it
        base = projects / parts[0]
    out = base / ".work" / "frames"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _check_crop(crop: list[float] | None) -> tuple[float, float, float, float] | None:
    if crop is None:
        return None
    if len(crop) != 4:
        raise ValueError("crop must be [x, y, w, h] as fractions of the frame (each between 0 and 1)")
    x, y, w, h = (float(v) for v in crop)
    eps = 1e-6
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1 + eps or y + h > 1 + eps:
        raise ValueError(f"crop [x, y, w, h] = {[x, y, w, h]} must lie inside the frame: x, y >= 0, w, h > 0, x+w <= 1, y+h <= 1")
    return x, y, w, h


def get_frames(path: str, times: list[float], crop: list[float] | None = None, max_side: int = DEFAULT_MAX_SIDE) -> list:
    """Exact frames at `times` (seconds), optionally cropped, as `[summary_json, Image, ...]`.

    At most 8 times per call; extra times are listed under `skipped_times`. `crop` is
    `[x, y, w, h]` as fractions of the frame. The images are downscaled to `max_side`;
    the full-resolution file of each is listed as `full_path`.
    """
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"video not found: {src}")
    if not times:
        raise ValueError("times is empty: give at least one time in seconds")
    if not MIN_VIEW_SIDE <= max_side <= MAX_VIEW_SIDE:
        raise ValueError(f"max_side must be between {MIN_VIEW_SIDE} and {MAX_VIEW_SIDE}, got {max_side}")
    box = _check_crop(crop)
    info = stream_info(src)
    if not info.has_video or not info.duration:
        raise ValueError(f"no readable video stream in {src}")
    for t in times:
        if t < 0 or t > info.duration + 0.05:
            raise ValueError(f"time {t} is outside the video (0 to {info.duration:.2f} s)")

    wanted = [float(t) for t in times[:GET_FRAMES_MAX_TIMES]]
    skipped = [float(t) for t in times[GET_FRAMES_MAX_TIMES:]]
    workdir = _frames_workdir(src)
    tag = hashlib.sha1(str(src).encode()).hexdigest()[:6]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", src.stem)[:32]
    crop_tag = "" if box is None else "_c" + "-".join(f"{round(v * 1000):04d}" for v in box)

    entries: list[dict] = []
    files: list[Path] = []
    for t in wanted:
        at = min(t, max(0.0, info.duration - 0.05))
        final = workdir / f"{stem}_{tag}_{round(t * 1000):08d}{crop_tag}.jpg"
        raw = temp_sibling(final, ".png")  # lossless step: crop first, compress once
        try:
            if not _extract_frame_png(src, at, raw):
                raise RuntimeError(f"ffmpeg could not read a frame at {t} s from {src}")
            with PILImage.open(raw) as img:
                frame = img.convert("RGB")
            if box is not None:
                fw, fh = frame.size
                left, top = round(box[0] * fw), round(box[1] * fh)
                right = max(left + 1, min(fw, round((box[0] + box[2]) * fw)))
                bottom = max(top + 1, min(fh, round((box[1] + box[3]) * fh)))
                frame = frame.crop((left, top, right, bottom))
            frame.save(final, format="JPEG", quality=92)
        finally:
            raw.unlink(missing_ok=True)
        files.append(final)
        entries.append({"t": t, "full_path": str(final), "size": list(frame.size)})

    summary: dict = {
        "source": str(src),
        "duration": round(info.duration, 3),
        "crop": list(box) if box else None,
        "max_side": max_side,
        "images": entries,
    }
    if skipped:
        summary["skipped_times"] = skipped
        summary["note"] = f"at most {GET_FRAMES_MAX_TIMES} times per call: {len(skipped)} time(s) were not read"
    return tool_result(summary, files, max_side=max_side)


def _extract_frame_png(src: Path, t: float, out: Path) -> bool:
    """Like `_extract_frame`, but lossless (the file must end in .png)."""
    try:
        run_ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1", str(out)])
    except FFmpegError:
        return False
    return out.is_file() and out.stat().st_size > 0


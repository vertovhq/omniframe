"""Sound design in a video (task 20.5b): where each sound goes, the audio render, the sound library.

- `resolve_events` turns every `audio.sfx` event into a WAV file the engine plays, at a number of
  seconds. `at` may be seconds, `cue:<name>` or `cut:<n>`; `align` moves the sound so its start,
  peak or end sits on that moment. A `sound` is rendered from `audio.sounds` (or a starting
  recipe) by `synth.py`; a `src` file is only transformed when the event asks for it. Files are
  cached in `<project>/cache/sfx/`.
- `audio_render` (`render_video(mode="audio")`) mixes voice, music and the sounds without a
  browser, writes the mix and one timeline image, and returns measured values and technical
  warnings. Nothing is gated on them.
- `save_sounds` / `list_sfx` keep the sound recipes the user approved in the sound library
  (`<OMNIFRAME_OUTPUT_DIR>/library/sfx/<name>.json`), one JSON file per sound.
- `starting_sheet` draws every starting recipe (waveform and spectrogram) into one image for
  `studio_guide(kit_group="sfx")`.

No code here adds or moves a sound on its own. The model places every event.
"""

from __future__ import annotations

import datetime
import json
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from ..ffmpeg import decode_audio
from ..plan import SOUND_NAME_RE, Plan, SfxEvent
from . import synth

SFX_LIBRARY = "sfx"               # folder name under the library
SAVE_KEYS = ("sound", "name", "what", "fits_when", "replace")
FIELD_LIMITS = {"what": 200, "fits_when": 250}
SYNC_TOLERANCE_S = 1.0 / 30.0     # one frame: the peak lands on its cue within this
STACK_LIMIT = 10 ** (-1.0 / 20.0)  # two peaks that add up above -1 dBFS
SPEECH_GAP_S = 0.05
TIMELINE_W = 1600
SHEET_CELL_W = 740
SHEET_CELL_H = 150
SHEET_GAP = 20


@dataclass(frozen=True)
class Placed:
    """One sound event after rendering: its file, where it starts, and its measured values."""

    index: int
    name: str           # the sound name, or the file name
    src: Path           # the file the engine plays (a WAV of the cache, or the source file)
    volume: float       # the engine volume: the event's volume times its gain
    anchor: float       # seconds that `at` refers to (a number, a cue or a scene start)
    at: float           # seconds on the output timeline, after `align`
    measures: dict[str, Any]
    mono: np.ndarray    # the samples, mono, before `volume`


# ------------------------------------------------------------------ anchors and sound specs

def anchor_seconds(at: float | str, scenes: Sequence[Any], cues: Mapping[str, float]) -> float:
    """Seconds for an `at` value: a number as it is, `cue:<name>` from the resolved cues, `cut:<n>` from the scene start."""
    if isinstance(at, (int, float)):
        return float(at)
    kind, _, ref = at.partition(":")
    if kind == "cue":
        return float(cues[ref])
    return float(scenes[int(ref)].at)


def sound_spec(plan: Plan, name: str) -> dict[str, Any]:
    """The plan's spec of a named sound (as a dict), or `{"from": name}` for a starting recipe."""
    if plan.audio is not None and name in plan.audio.sounds:
        return plan.audio.sounds[name].model_dump(by_alias=True, exclude_none=True)
    return {"from": name}


def _file_key(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"file": str(path), "size": st.st_size, "mtime": st.st_mtime_ns}


def _gain(event: SfxEvent) -> float:
    return 10.0 ** (event.gain_db / 20.0) if event.gain_db is not None else 1.0


# ------------------------------------------------------------------ rendering one event

def render_event(
    event: SfxEvent,
    index: int,
    spec: Mapping[str, Any] | None,
    src: Path | None,
    cache_dir: Path,
) -> tuple[Path, np.ndarray, dict[str, Any]]:
    """Render one event to a cached WAV. Returns `(file, mono samples, measures)`.

    `spec` is set for a `sound` event, `src` for a file. A plain file event (no transform) is
    returned as it is. A repeat of a sound varies with `index` unless `vary` is 0.
    """
    if spec is None and src is not None and not event.transforms:
        mono = decode_audio(src, synth.SR).astype(float)
        return src, mono, synth.measure(mono)

    if spec is not None:
        recipe = synth.resolve_recipe(spec)
        vary = 1.0 if event.vary is None else float(event.vary)
        seed = int(recipe["seed"]) + (index + 1 if vary > 0 else 0)
        samples = synth.render_recipe(recipe, seed=seed, jitter=vary)
        source_key: dict[str, Any] = {"recipe": recipe, "seed": seed, "jitter": vary}
    else:
        assert src is not None
        mono = decode_audio(src, synth.SR).astype(float)
        samples = np.column_stack([mono, mono])
        vary = float(event.vary or 0.0)
        jitter = float(np.random.default_rng(index + 1).uniform(-0.4, 0.4)) * vary if vary > 0 else 0.0
        source_key = {"file": _file_key(src), "jitter": jitter}
        event = event.model_copy(update={"pitch": event.pitch + jitter})

    trim = tuple(event.trim) if event.trim is not None else None
    samples = synth.transform(
        samples, pitch=event.pitch, rate=event.rate, pan=event.pan,
        reverse=event.reverse, trim=trim, fade=event.fade,
    )
    key = synth.cache_key({
        "source": source_key,
        "transform": {"pitch": event.pitch, "rate": event.rate, "pan": event.pan, "reverse": event.reverse,
                      "trim": trim, "fade": event.fade},
    })
    out = cache_dir / f"{key}.wav"
    if not out.is_file():
        synth.write_wav(out, samples)
    mono = samples.mean(axis=1)
    return out, mono, synth.measure(mono)


def resolve_events(
    plan: Plan,
    cues: Mapping[str, float],
    cache_dir: Path,
    resolve: Callable[[str], Path | None],
) -> tuple[list[Placed], list[str]]:
    """Every `audio.sfx` event rendered and placed. Returns `(placed, warnings)`.

    `resolve` finds a plan file (`src`) on disk, or returns None. A sound that would start before
    the video is set to start at 0 and reported in the warnings.
    """
    if plan.audio is None or not plan.audio.sfx:
        return [], []
    placed: list[Placed] = []
    warnings: list[str] = []
    for i, event in enumerate(plan.audio.sfx):
        spec = sound_spec(plan, event.sound) if event.sound is not None else None
        src = resolve(event.src) if event.src is not None else None
        if event.src is not None and src is None:
            raise FileNotFoundError(f"audio.sfx[{i}].src: file not found: {event.src}")
        file, mono, measures = render_event(event, i, spec, src, cache_dir)
        anchor = anchor_seconds(event.at, plan.scenes, cues)
        if event.align == "peak":
            at = anchor - measures["peak_at"]
        elif event.align == "end":
            at = anchor - measures["length"]
        else:
            at = anchor
        if at < 0:
            warnings.append(f"audio.sfx[{i}]: with align {event.align!r} it would start at {at:.2f} s, before the video; it starts at 0 s")
            at = 0.0
        volume = float(event.volume) * _gain(event)
        name = event.sound if event.sound is not None else Path(event.src or "").name
        placed.append(Placed(i, name, file, volume, anchor, round(at, 4), measures, mono))
    return placed, warnings


def engine_events(placed: Sequence[Placed]) -> list[dict[str, Any]]:
    """`audio.sfx` as the engine reads it: numbers and file paths (the job copies the files)."""
    return [{"at": round(p.at, 4), "src": str(p.src), "volume": round(p.volume, 4)} for p in placed]


def brightness_word(placed: Placed) -> str:
    return synth.brightness(float(placed.measures["centroid_hz"]))


def table(placed: Sequence[Placed]) -> list[dict[str, Any]]:
    """The measured values the model reads for each event (one row per event)."""
    rows = []
    for p in placed:
        m = p.measures
        rows.append({
            "event": p.index + 1,
            "sound": p.name,
            "at": round(p.at, 3),
            "length_s": m["length"],
            "attack_ms": m["attack_ms"],
            "peak_dbfs": m["peak_db"],
            "rms_dbfs": m["rms_db"],
            "centroid_hz": m["centroid_hz"],
            "brightness": brightness_word(p),
        })
    return rows


# ------------------------------------------------------------------ the audio render

def mix(
    duration: float,
    placed: Sequence[Placed],
    voice: np.ndarray | None,
    voice_volume: float,
    music: np.ndarray | None,
    music_volume: float,
) -> np.ndarray:
    """Mono mix at `synth.SR`: voice and music as given (no ducking), every sound at its place and volume."""
    n = max(1, int(math.ceil(duration * synth.SR)))
    out = np.zeros(n)
    for track, gain in ((voice, voice_volume), (music, music_volume)):
        if track is not None:
            cut = track[:n]
            out[: len(cut)] += cut * gain
    for p in placed:
        start = int(round(p.at * synth.SR))
        seg = p.mono[: max(0, n - start)] * p.volume
        out[start: start + len(seg)] += seg
    return out


def _rms_db(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x ** 2)))
    return 20 * math.log10(rms) if rms > 0 else -120.0


def checks(
    duration: float,
    placed: Sequence[Placed],
    mixed: np.ndarray,
    voice: np.ndarray | None,
    words: Sequence[Mapping[str, Any]] | None,
) -> list[str]:
    """Technical problems in the mix, as text. These are warnings, never a gate."""
    notes: list[str] = []
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 1.0:
        at = float(np.argmax(np.abs(mixed))) / synth.SR
        notes.append(f"the mix clips: {20 * math.log10(peak):+.1f} dBFS at {at:.2f} s (voice, music and sounds added together)")

    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            pa, pb = a.at + a.measures["peak_at"], b.at + b.measures["peak_at"]
            amp_a = a.volume * float(np.max(np.abs(a.mono))) if a.mono.size else 0.0
            amp_b = b.volume * float(np.max(np.abs(b.mono))) if b.mono.size else 0.0
            if abs(pa - pb) < 0.03 and amp_a + amp_b > STACK_LIMIT:
                notes.append(
                    f"events {a.index + 1} and {b.index + 1} peak within 30 ms of each other at {min(pa, pb):.2f} s, "
                    "together above -1 dBFS: lower one of them or move it"
                )

    for p in placed:
        end = p.at + p.measures["length"]
        if p.at >= duration:
            notes.append(f"event {p.index + 1} ({p.name}) starts at {p.at:.2f} s, after the video ends at {duration:.2f} s: it is never heard")
        elif end > duration + 0.005:
            notes.append(f"event {p.index + 1} ({p.name}) is cut off by the video end at {duration:.2f} s (it runs to {end:.2f} s)")

    if voice is not None and words:
        spans = [(float(w["s"]), float(w["e"])) for w in words]
        for p in placed:
            start, end = p.at, p.at + p.measures["length"]
            overlap = [(max(s, start), min(e, end)) for s, e in spans if s < end and e > start]
            if not overlap or p.mono.size == 0:
                continue
            voice_part = np.concatenate([
                voice[int(a * synth.SR): int(b * synth.SR)] for a, b in overlap if b - a > SPEECH_GAP_S
            ] or [np.zeros(0)])
            sfx_db = _rms_db(p.mono * p.volume)
            voice_db = _rms_db(voice_part)
            if voice_part.size and sfx_db > voice_db:
                notes.append(
                    f"event {p.index + 1} ({p.name}) is {sfx_db - voice_db:+.1f} dB louder than the voice while words are spoken "
                    f"(at {overlap[0][0]:.2f} s)"
                )
    return notes


# ------------------------------------------------------------------ timeline image

def _font(size: int) -> Any:
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, OSError):
        return ImageFont.load_default()


def timeline_image(
    out: Path,
    duration: float,
    title: str,
    placed: Sequence[Placed],
    voice: np.ndarray | None,
    music: np.ndarray | None,
    scene_starts: Sequence[float],
    cues: Mapping[str, float],
) -> Path:
    """One JPEG: lanes for voice, music and sounds, scene cuts and cues as lines, every sound labelled."""
    lanes = [("voice", voice, (120, 200, 255))]
    if music is not None:
        lanes.append(("music", music, (150, 220, 150)))
    lane_h = 130
    left, right, top = 150, 40, 70
    height = top + lane_h * (len(lanes) + 1) + 70
    canvas = PILImage.new("RGB", (TIMELINE_W, height), (18, 18, 22))
    draw = ImageDraw.Draw(canvas)
    plot_w = TIMELINE_W - left - right
    def x_of(t: float) -> float:
        return left + plot_w * min(max(t, 0.0), duration) / duration

    draw.text((left, 22), title, fill=(240, 240, 245), font=_font(26))
    sfx_top = top + lane_h * len(lanes)
    for k, (label, track, color) in enumerate(lanes):
        y0 = top + k * lane_h
        draw.text((12, y0 + lane_h // 2 - 10), label, fill=color, font=_font(20))
        draw.line([(left, y0 + lane_h - 4), (left + plot_w, y0 + lane_h - 4)], fill=(60, 60, 70))
        if track is None:
            continue
        for col in range(plot_w):
            a = int(col / plot_w * duration * synth.SR)
            b = int((col + 1) / plot_w * duration * synth.SR)
            level = _rms_db(track[a:b])
            h = int(max(0.0, min(1.0, (level + 60) / 60)) * (lane_h - 14))
            draw.line([(left + col, y0 + lane_h - 4), (left + col, y0 + lane_h - 4 - h)], fill=color)
    draw.text((12, sfx_top + lane_h // 2 - 10), "sounds", fill=(255, 190, 90), font=_font(20))
    draw.line([(left, sfx_top + lane_h - 4), (left + plot_w, sfx_top + lane_h - 4)], fill=(60, 60, 70))
    for p in placed:
        x = x_of(p.at)
        level = max(0.0, min(1.0, (p.measures["peak_db"] + 60) / 60))
        h = int(level * (lane_h - 40))
        draw.line([(x, sfx_top + lane_h - 4), (x, sfx_top + lane_h - 4 - h)], fill=(255, 190, 90), width=3)
        draw.text((x + 4, sfx_top + 6), str(p.index + 1), fill=(255, 190, 90), font=_font(18))
        draw.text((x + 4, sfx_top + lane_h - 26), p.name[:14], fill=(200, 200, 210), font=_font(13))

    for i, start in enumerate(scene_starts):
        if start <= 0 or start >= duration:
            continue
        x = x_of(start)
        draw.line([(x, top), (x, top + lane_h * (len(lanes) + 1))], fill=(120, 120, 140))
        draw.text((x + 3, top - 22), f"scene {i}", fill=(160, 160, 175), font=_font(14))
    for name, t in cues.items():
        if not 0 <= t <= duration:
            continue
        x = x_of(t)
        draw.line([(x, top), (x, top + lane_h * (len(lanes) + 1))], fill=(110, 200, 200))
        draw.text((x + 3, top + lane_h * (len(lanes) + 1) + 4), name[:16], fill=(110, 200, 200), font=_font(14))

    axis_y = top + lane_h * (len(lanes) + 1) + 26
    step = 1 if duration <= 20 else 2 if duration <= 40 else 5 if duration <= 120 else 10
    for t in range(0, int(duration) + 1, step):
        x = x_of(float(t))
        draw.line([(x, axis_y - 6), (x, axis_y)], fill=(160, 160, 170))
        draw.text((x - 6, axis_y + 2), f"{t}", fill=(160, 160, 170), font=_font(14))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="JPEG", quality=88)
    return out


# ------------------------------------------------------------------ the audio render (job side)

def audio_render(
    plan: Plan,
    placed: Sequence[Placed],
    warnings: list[str],
    voice_path: Path | None,
    music_path: Path | None,
    words: list[dict] | None,
    cues: Mapping[str, float],
    out_wav: Path,
    out_png: Path,
    title: str,
) -> dict[str, Any]:
    """Mix, write the WAV and the timeline, and collect the checks. Returns the job result's audio part.

    `cues` are the plan's cues in seconds (named moments drawn on the timeline).
    """
    duration = float(plan.duration or 0.0)
    voice = decode_audio(voice_path, synth.SR).astype(float) if voice_path is not None else None
    music = decode_audio(music_path, synth.SR).astype(float) if music_path is not None else None
    voice_volume = plan.audio.voice.volume if plan.audio and plan.audio.voice else 1.0
    music_volume = plan.audio.music.volume if plan.audio and plan.audio.music else 0.0
    mixed = mix(duration, placed, voice, voice_volume, music, music_volume)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_wav.with_name(f"{out_wav.stem}.{os.getpid()}.tmp.wav")
    synth.write_wav(tmp, np.column_stack([mixed, mixed]))
    os.replace(tmp, out_wav)
    all_warnings = list(warnings) + checks(duration, placed, mixed, voice, words)
    scene_starts = [float(s.at) for s in plan.scenes]
    timeline_image(out_png, duration, title, placed, voice, music, scene_starts, cues)
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    return {
        "output": str(out_wav),
        "duration": round(duration, 3),
        "events": len(placed),
        "mix_peak_dbfs": round(20 * math.log10(peak), 2) if peak > 0 else -120.0,
        "sounds": table(placed),
        "warnings": all_warnings,
        "note": (
            "the mix is a check copy: voice and music without ducking, and the sounds at their set "
            "volumes. Read the timeline image and the table, fix what the warnings name, then render the preview"
        ),
    }


# ------------------------------------------------------------------ the sound library

def library_root(library: Path) -> Path:
    return library / SFX_LIBRARY


def validate_save_sounds(items: Any, plan: Plan, library: Path) -> tuple[list[dict] | None, list[str]]:
    """Check a `save_sounds` request. Returns `(clean list, [])` or `(None, errors)`. Writes nothing."""
    where = "save_sounds"
    if not isinstance(items, list) or not items:
        return None, [f"{where}: give a list of {{sound, what, fits_when}}"]
    defined = sorted({*(plan.audio.sounds if plan.audio else {}), *synth.STARTING_NAMES})
    errors: list[str] = []
    clean: list[dict] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        at = f"{where}[{i}]"
        before = len(errors)
        if not isinstance(item, dict):
            errors.append(f"{at}: give an object with sound, what and fits_when")
            continue
        errors += [f"{at}.{k}: unknown field (expected {', '.join(SAVE_KEYS)})" for k in item if k not in SAVE_KEYS]
        sound = item.get("sound")
        if not isinstance(sound, str) or sound not in defined:
            errors.append(f"{at}.sound: unknown sound {sound!r} (defined: {', '.join(defined)})")
            continue
        name = item.get("name", sound)
        if not isinstance(name, str) or not SOUND_NAME_RE.fullmatch(name):
            errors.append(f"{at}.name: letters, digits and _, starting with a letter (at most 40)")
            continue
        if name in seen:
            errors.append(f"{at}.name: {name!r} is given twice")
        seen.add(name)
        texts: dict[str, str] = {}
        for key, limit in FIELD_LIMITS.items():
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{at}.{key}: required, a short text")
            elif len(" ".join(value.split())) > limit:
                errors.append(f"{at}.{key}: at most {limit} characters")
            else:
                texts[key] = " ".join(value.split())
        replace = item.get("replace", False)
        if not isinstance(replace, bool):
            errors.append(f"{at}.replace: true or false")
        elif (library_root(library) / f"{name}.json").exists() and not replace:
            errors.append(f"{at}.name: the sound library already has {name!r}; set replace=true to overwrite it")
        if len(errors) == before:
            clean.append({"sound": sound, "name": name, "replace": replace is True, "spec": sound_spec(plan, sound), **texts})
    if errors:
        return None, errors
    return clean, []


def save_sounds(items: list[dict], library: Path, project_name: str) -> list[dict[str, Any]]:
    """Write one JSON per sound: its spec (`from` and overrides, or a full sound), the card text and the source project."""
    folder = library_root(library)
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for item in items:
        data = {
            "name": item["name"],
            "what": item["what"],
            "fits_when": item["fits_when"],
            "source": project_name,
            "saved": datetime.date.today().isoformat(),
            "sound": item["spec"],
            "version": synth.RECIPE_VERSION,
        }
        path = folder / f"{item['name']}.json"
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        saved.append({"name": item["name"], "file": str(path), "replaced": item["replace"]})
    return saved


def list_sfx(library: Path) -> list[dict[str, Any]]:
    """Every sound in the library (a JSON file that fails to read is skipped), sorted by name."""
    folder = library_root(library)
    if not folder.is_dir():
        return []
    entries = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("name"):
            entries.append({**data, "file": str(path)})
    return entries


def library_lines(library: Path) -> list[str]:
    """One line per library sound for `studio_guide`: name, what, when it fits, and the file to copy from."""
    return [
        f"- **{e['name']}**: {e.get('what', '')} Fits when: {e.get('fits_when', '')} Recipe: {e['file']}"
        for e in list_sfx(library)
    ]


# ------------------------------------------------------------------ the starting recipes

def describe(name: str) -> str:
    """One line for a starting recipe: its length, its layers, its peak."""
    recipe = synth.resolve_recipe({"from": name})
    parts = []
    for layer in recipe["layers"]:
        text = layer["source"] + " noise" if layer["source"] in synth.NOISE_SOURCES else layer["source"]
        if layer["freq_start"] is not None:
            end = layer["freq_end"] if layer["freq_end"] is not None else layer["freq_start"]
            text += f" {layer['freq_start']:g}→{end:g} Hz" if end != layer["freq_start"] else f" {layer['freq_start']:g} Hz"
        if layer["filter"]:
            cut_end = layer["cutoff_end"] if layer["cutoff_end"] is not None else layer["cutoff_start"]
            text += f", {layer['filter']} {layer['cutoff_start']:g}→{cut_end:g} Hz"
        parts.append(text)
    extras = []
    if recipe["reverb"]:
        extras.append("reverb tail")
    if recipe["reverse"]:
        extras.append("reversed")
    tail = f"; {', '.join(extras)}" if extras else ""
    return f"- {name}: {recipe['length']:g} s; " + " + ".join(parts) + tail


def starting_lines() -> list[str]:
    return [describe(name) for name in synth.STARTING_NAMES]


def _spectrogram(mono: np.ndarray, width: int, height: int) -> PILImage.Image:
    window, hop = 512, 128
    frames = max(1, (len(mono) - window) // hop)
    idx = np.arange(window)[None, :] + hop * np.arange(frames)[:, None]
    stack = mono[idx] * np.hanning(window)[None, :] if len(mono) > window else np.zeros((1, window))
    mag = np.abs(np.fft.rfft(stack, axis=1))
    db = 20 * np.log10(mag + 1e-9)
    top = float(np.max(db))
    scaled = np.clip((db - (top - 60.0)) / 60.0, 0.0, 1.0)
    picture = (scaled.T[::-1] * 255).astype(np.uint8)  # low frequencies at the bottom
    return PILImage.fromarray(picture, "L").resize((width, height), PILImage.Resampling.BILINEAR).convert("RGB")


def _waveform(mono: np.ndarray, width: int, height: int) -> PILImage.Image:
    picture = PILImage.new("RGB", (width, height), (24, 24, 30))
    draw = ImageDraw.Draw(picture)
    if mono.size == 0:
        return picture
    peak = float(np.max(np.abs(mono))) or 1.0
    edges = np.linspace(0, len(mono), width + 1).astype(int)
    mid = height // 2
    for x in range(width):
        seg = mono[edges[x]: max(edges[x] + 1, edges[x + 1])]
        if seg.size:
            draw.line([(x, mid - float(seg.max()) / peak * mid), (x, mid - float(seg.min()) / peak * mid)], fill=(120, 200, 255))
    return picture


def starting_sheet(out: Path) -> Path:
    """One JPEG: every starting recipe with its waveform and spectrogram, two columns, reading order."""
    names = list(synth.STARTING_NAMES)
    rows = (len(names) + 1) // 2
    width = SHEET_CELL_W * 2 + SHEET_GAP
    sheet = PILImage.new("RGB", (width, rows * (SHEET_CELL_H + SHEET_GAP) + 50), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 14), f"Starting sound recipes (OmniFrame {synth.RECIPE_VERSION}): {', '.join(names)}", fill=(230, 230, 236), font=_font(18))
    for i, name in enumerate(names):
        samples = synth.render_recipe(synth.resolve_recipe({"from": name}))
        mono = samples.mean(axis=1)
        m = synth.measure(samples)
        x = (i % 2) * (SHEET_CELL_W + SHEET_GAP)
        y = 50 + (i // 2) * (SHEET_CELL_H + SHEET_GAP)
        label = f"{i + 1}. {name}   {m['length']:.2f} s   peak {m['peak_db']:.1f} dBFS   centroid {m['centroid_hz']:.0f} Hz   {synth.brightness(m['centroid_hz'])}"
        draw.text((x, y), label, fill=(240, 240, 245), font=_font(15))
        sheet.paste(_waveform(mono, SHEET_CELL_W, 48), (x, y + 24))
        sheet.paste(_spectrogram(mono, SHEET_CELL_W, 66), (x, y + 76))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, format="JPEG", quality=88)
    return out


def starting_sheet_path(output_dir: Path) -> Path:
    """Where the sheet is cached: built once per recipe version."""
    return Path(output_dir) / "cache" / "sfx" / f"starting-v{synth.RECIPE_VERSION}.jpg"


def ensure_starting_sheet(output_dir: Path) -> Path:
    path = starting_sheet_path(output_dir)
    if not path.is_file():
        starting_sheet(path)
    return path

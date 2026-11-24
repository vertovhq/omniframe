"""Synthesized sound effects: recipes rendered offline to 48 kHz stereo (task 20.5b).

A recipe is a small dict: `length` seconds, 1 to 4 `layers` mixed together, optional `reverb`,
`reverse`, `peak_db` and `seed`. A layer has a source (sine, saw, square, triangle, or white,
pink, brown noise), an optional pitch sweep (`freq_start`, `freq_end`, `curve`), an amplitude
envelope (`attack`, `decay` time constant, `release`, `amp`), an optional state-variable filter
with a cutoff sweep (`filter`, `cutoff_start`, `cutoff_end`, `resonance`), `drive` (tanh
saturation), `bits` (bit reduction), `start` (delay inside the sound) and `pan`.

Everything is deterministic: noise and jitter come from `numpy.random.default_rng(seed)`, so the
same recipe, seed and `jitter` give the same samples. Nothing here reads a file, so the sounds
need no licence line.

`STARTING` holds one working recipe per common sound (whoosh, impact, click...). They are a
start: the model changes their parameters per video. `resolve_recipe` turns a plan's sound
spec (`{"from": "whoosh", "pitch_end": 300, "length": 0.6}`) into a full recipe.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import wave
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

SR = 48000
RECIPE_VERSION = 1                 # bump when the rendering changes, so cached files are rebuilt
SOURCES = ("sine", "saw", "square", "triangle", "white", "pink", "brown")
NOISE_SOURCES = frozenset({"white", "pink", "brown"})
FILTERS = ("lowpass", "highpass", "bandpass")
MAX_LAYERS = 4
DEFAULT_PEAK_DB = -3.0             # starting recipes peak here: -1 dBFS and below, with headroom
MAX_CUTOFF = SR / 7.0              # the state-variable filter is only stable below about SR/6

LAYER_DEFAULTS: dict[str, Any] = {
    "freq_start": None, "freq_end": None, "curve": "linear", "amp": 1.0,
    "attack": 0.005, "decay": 0.0, "release": 0.0, "start": 0.0,
    "filter": None, "cutoff_start": None, "cutoff_end": None, "resonance": 0.7,
    "drive": 0.0, "bits": None, "pan": 0.0,
}
RECIPE_DEFAULTS: dict[str, Any] = {
    "reverb": 0.0, "reverb_decay": 1.0, "reverse": False, "peak_db": DEFAULT_PEAK_DB, "seed": 1,
}

# One line per starting recipe, for the sheet and for `studio_guide(kit_group="sfx")`.
_STARTING_LAYERS: dict[str, dict[str, Any]] = {
    "whoosh": {"length": 0.6, "layers": [
        {"source": "white", "amp": 0.9, "filter": "bandpass", "cutoff_start": 400, "cutoff_end": 2400,
         "curve": "exp", "resonance": 1.2, "attack": 0.18, "release": 0.25}]},
    "swish": {"length": 0.35, "layers": [
        {"source": "white", "amp": 0.8, "filter": "bandpass", "cutoff_start": 1500, "cutoff_end": 6000,
         "curve": "exp", "resonance": 1.5, "attack": 0.08, "release": 0.12}]},
    "whip": {"length": 0.3, "layers": [
        {"source": "pink", "amp": 1.0, "filter": "bandpass", "cutoff_start": 700, "cutoff_end": 4000,
         "curve": "exp", "resonance": 1.0, "attack": 0.02, "decay": 0.09}]},
    "hit": {"length": 0.5, "layers": [
        {"source": "sine", "freq_start": 120, "freq_end": 45, "curve": "exp", "amp": 1.0,
         "attack": 0.002, "decay": 0.12, "drive": 1.5},
        {"source": "white", "amp": 0.4, "filter": "lowpass", "cutoff_start": 3000,
         "attack": 0.001, "decay": 0.02}]},
    "impact": {"length": 1.4, "reverb": 0.25, "reverb_decay": 0.8, "layers": [
        {"source": "sine", "freq_start": 55, "freq_end": 35, "curve": "exp", "amp": 1.0,
         "attack": 0.002, "decay": 0.5, "drive": 1.0},
        {"source": "white", "amp": 0.6, "filter": "lowpass", "cutoff_start": 4000,
         "attack": 0.001, "decay": 0.03},
        {"source": "pink", "amp": 0.3, "filter": "lowpass", "cutoff_start": 600,
         "attack": 0.05, "decay": 0.6}]},
    "sub_drop": {"length": 1.2, "layers": [
        {"source": "sine", "freq_start": 90, "freq_end": 30, "curve": "exp", "amp": 1.0,
         "attack": 0.01, "release": 0.3}]},
    "riser": {"length": 1.5, "layers": [
        {"source": "white", "amp": 0.9, "filter": "bandpass", "cutoff_start": 300, "cutoff_end": 6000,
         "curve": "exp", "resonance": 1.0, "attack": 1.0, "release": 0.05},
        {"source": "saw", "freq_start": 110, "freq_end": 440, "curve": "exp", "amp": 0.25,
         "filter": "lowpass", "cutoff_start": 800, "cutoff_end": 8000, "attack": 1.0, "release": 0.05}]},
    "reverse_swell": {"length": 1.2, "reverb": 0.3, "reverb_decay": 1.2, "reverse": True, "layers": [
        {"source": "pink", "amp": 1.0, "filter": "lowpass", "cutoff_start": 1200, "cutoff_end": 7000,
         "curve": "exp", "attack": 0.9, "release": 0.05}]},
    "braam": {"length": 1.0, "layers": [
        {"source": "saw", "freq_start": 55, "freq_end": 50, "amp": 0.6, "attack": 0.02, "release": 0.3,
         "drive": 3.0, "filter": "lowpass", "cutoff_start": 900},
        {"source": "square", "freq_start": 110, "freq_end": 100, "amp": 0.3, "attack": 0.02, "release": 0.3,
         "drive": 3.0, "filter": "lowpass", "cutoff_start": 900}]},
    "stinger": {"length": 0.6, "layers": [
        {"source": "sine", "freq_start": 660, "amp": 0.6, "attack": 0.005, "decay": 0.35},
        {"source": "triangle", "freq_start": 990, "amp": 0.4, "attack": 0.005, "decay": 0.35}]},
    "click": {"length": 0.03, "layers": [
        {"source": "white", "amp": 1.0, "filter": "highpass", "cutoff_start": 2000,
         "attack": 0.0005, "decay": 0.006}]},
    "tick": {"length": 0.05, "layers": [
        {"source": "sine", "freq_start": 2400, "amp": 0.8, "attack": 0.001, "decay": 0.012}]},
    "ui_blip": {"length": 0.1, "layers": [
        {"source": "sine", "freq_start": 900, "freq_end": 1400, "curve": "exp", "amp": 0.8,
         "attack": 0.005, "decay": 0.04}]},
    "glitch": {"length": 0.2, "layers": [
        {"source": "square", "freq_start": 200, "freq_end": 1200, "curve": "exp", "amp": 0.7,
         "bits": 4, "drive": 2.0, "attack": 0.001, "decay": 0.05},
        {"source": "white", "amp": 0.5, "filter": "highpass", "cutoff_start": 3000,
         "attack": 0.001, "decay": 0.03}]},
    "data_chatter": {"length": 0.25, "layers": [
        {"source": "square", "freq_start": 1800, "amp": 0.5, "bits": 4, "attack": 0.001, "decay": 0.015}]},
    "typing": {"length": 0.04, "layers": [
        {"source": "white", "amp": 1.0, "filter": "bandpass", "cutoff_start": 2500, "resonance": 2.0,
         "attack": 0.001, "decay": 0.008}]},
    "pop": {"length": 0.12, "layers": [
        {"source": "sine", "freq_start": 400, "freq_end": 180, "curve": "exp", "amp": 1.0,
         "attack": 0.002, "decay": 0.05}]},
    "shimmer": {"length": 1.5, "reverb": 0.4, "reverb_decay": 1.0, "layers": [
        {"source": "triangle", "freq_start": 1800, "freq_end": 2400, "curve": "exp", "amp": 0.4,
         "attack": 0.4, "release": 0.4},
        {"source": "sine", "freq_start": 3600, "amp": 0.2, "attack": 0.4, "release": 0.4}]},
    "heartbeat": {"length": 0.45, "layers": [
        {"source": "sine", "freq_start": 60, "freq_end": 40, "curve": "exp", "amp": 1.0,
         "attack": 0.005, "decay": 0.08},
        {"source": "sine", "freq_start": 60, "freq_end": 40, "curve": "exp", "amp": 0.7,
         "start": 0.22, "attack": 0.005, "decay": 0.08}]},
    "static": {"length": 0.8, "layers": [
        {"source": "white", "amp": 0.5, "attack": 0.01, "release": 0.2}]},
}
STARTING: dict[str, dict[str, Any]] = _STARTING_LAYERS
STARTING_NAMES: tuple[str, ...] = tuple(STARTING)


# ------------------------------------------------------------------ recipes

def resolve_recipe(spec: Mapping[str, Any]) -> dict[str, Any]:
    """A full recipe (every default filled in) from a plan's sound spec.

    `from` names a starting recipe; the other fields of `spec` replace its fields. `layers`
    replaces the whole layer list. `pitch_start` and `pitch_end` set the frequency of every
    layer that has one (noise layers have none and are left alone).
    Raises ValueError for a missing starting recipe, length or layers.
    """
    spec = dict(spec)
    base_name = spec.pop("from", None)
    pitch_start = spec.pop("pitch_start", None)
    pitch_end = spec.pop("pitch_end", None)
    if base_name is None:
        recipe: dict[str, Any] = {}
    elif base_name in STARTING:
        recipe = copy.deepcopy(STARTING[base_name])
    else:
        raise ValueError(f"unknown starting recipe {base_name!r} (expected one of {', '.join(STARTING_NAMES)})")
    layers_given = spec.pop("layers", None)
    recipe.update({k: v for k, v in spec.items() if v is not None})
    if layers_given is not None:
        recipe["layers"] = [dict(layer) for layer in layers_given]
    if "length" not in recipe or not recipe.get("layers"):
        raise ValueError("a sound needs `length` and `layers` (or start from one with `from`)")
    if len(recipe["layers"]) > MAX_LAYERS:
        raise ValueError(f"a sound has at most {MAX_LAYERS} layers, got {len(recipe['layers'])}")

    layers = []
    for given in recipe["layers"]:
        layer = {**LAYER_DEFAULTS, **{k: v for k, v in given.items() if v is not None}}
        if layer["source"] not in SOURCES:
            raise ValueError(f"unknown source {layer['source']!r} (expected one of {', '.join(SOURCES)})")
        if layer["source"] not in NOISE_SOURCES:
            if layer["freq_start"] is None:
                raise ValueError(f"a {layer['source']} layer needs freq_start")
            if pitch_start is not None:
                layer["freq_start"] = float(pitch_start)
            if pitch_end is not None:
                layer["freq_end"] = float(pitch_end)
        if layer["filter"] is not None and layer["cutoff_start"] is None:
            raise ValueError(f"a {layer['filter']} filter needs cutoff_start")
        layers.append(layer)

    out = {**RECIPE_DEFAULTS, **{k: v for k, v in recipe.items() if k != "layers"}}
    out["length"] = float(out["length"])
    out["layers"] = layers
    return out


def _wave(source: str, phase: np.ndarray) -> np.ndarray:
    if source == "sine":
        return np.sin(phase)
    if source == "square":
        return np.sign(np.sin(phase))
    if source == "saw":
        return 2.0 * np.mod(phase / (2 * np.pi), 1.0) - 1.0
    return (2.0 / np.pi) * np.arcsin(np.clip(np.sin(phase), -1.0, 1.0))  # triangle


def _noise(source: str, m: int, rng: np.random.Generator) -> np.ndarray:
    if source == "white":
        x = rng.standard_normal(m)
    elif source == "pink":  # 1/sqrt(f) spectral shaping
        spectrum = np.fft.rfft(rng.standard_normal(m))
        freqs = np.fft.rfftfreq(m, 1.0 / SR)
        freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
        x = np.fft.irfft(spectrum / np.sqrt(freqs), m)
    else:  # brown: integrated white noise, without its drift
        x = np.cumsum(rng.standard_normal(m))
        x = x - np.linspace(x[0], x[-1], m)
    peak = float(np.max(np.abs(x))) if m else 0.0
    return x / peak if peak > 0 else x


def _svf(x: np.ndarray, cutoff: np.ndarray, resonance: float, kind: str) -> np.ndarray:
    """Chamberlin state-variable filter with a per-sample cutoff (Hz)."""
    f = (2.0 * np.sin(np.pi * np.clip(cutoff, 20.0, MAX_CUTOFF) / SR)).tolist()
    damp = max(1.0 / max(resonance, 0.1), 0.05)
    low = band = 0.0
    out = [0.0] * len(x)
    for i, sample in enumerate(x.tolist()):
        high = sample - low - damp * band
        band += f[i] * high
        low += f[i] * band
        out[i] = low if kind == "lowpass" else high if kind == "highpass" else band
    return np.asarray(out)


def _sweep(start: float, end: float, u: np.ndarray, curve: str) -> np.ndarray:
    if curve == "exp" and start > 0 and end > 0:
        return start * (end / start) ** u
    return start + (end - start) * u


def _layer(layer: Mapping[str, Any], n: int, rng: np.random.Generator, jitter: float) -> np.ndarray:
    """One layer as (n, 2) stereo samples; the layer starts `layer["start"]` seconds into the sound."""
    out = np.zeros((n, 2))
    begin = int(round(layer["start"] * SR))
    m = n - begin
    if m <= 0:
        return out
    t = np.arange(m) / SR
    span = m / SR
    u = t / span
    source = layer["source"]
    if source in NOISE_SOURCES:
        x = _noise(source, m, rng)
    else:
        detune = 1.0 + float(rng.uniform(-1.0, 1.0)) * 0.02 * jitter
        start_hz = float(layer["freq_start"]) * detune
        end_hz = float(layer["freq_end"] if layer["freq_end"] is not None else layer["freq_start"]) * detune
        freq = _sweep(start_hz, end_hz, u, layer["curve"])
        x = _wave(source, 2 * np.pi * np.cumsum(freq) / SR)
    if layer["filter"] is not None:
        c_start = float(layer["cutoff_start"])
        c_end = float(layer["cutoff_end"] if layer["cutoff_end"] is not None else c_start)
        cutoff = _sweep(c_start, c_end, u, layer["curve"]) * (1.0 + float(rng.uniform(-1.0, 1.0)) * 0.1 * jitter)
        x = _svf(x, cutoff, float(layer["resonance"]), layer["filter"])
    if layer["drive"] > 0:
        x = np.tanh(layer["drive"] * x) / math.tanh(layer["drive"])
    if layer["bits"]:
        levels = float(2 ** (int(layer["bits"]) - 1))
        x = np.round(x * levels) / levels
    env = np.minimum(1.0, t / max(float(layer["attack"]), 1e-6))
    if layer["decay"] > 0:
        env = env * np.exp(-t / float(layer["decay"]))
    if layer["release"] > 0:
        env = env * np.clip((span - t) / float(layer["release"]), 0.0, 1.0)
    x = x * env * float(layer["amp"])
    angle = (float(layer["pan"]) + 1.0) * math.pi / 4.0  # equal power: centre is 0.707 on both sides
    out[begin:, 0] = x * math.cos(angle)
    out[begin:, 1] = x * math.sin(angle)
    return out


def _reverb(sig: np.ndarray, wet: float, decay: float, rng: np.random.Generator) -> np.ndarray:
    """Dry/wet mix with a synthetic tail: decaying noise convolved by FFT. The tail stops at the sound's end."""
    tau = max(decay, 0.05) / 6.9  # the tail is down 60 dB after `decay` seconds
    taps = int(min(2.5 * decay, 3.0) * SR)
    ir = rng.standard_normal((taps, 2)) * np.exp(-np.arange(taps) / (tau * SR))[:, None]
    ir /= math.sqrt(float(np.sum(ir ** 2))) or 1.0
    size = 1 << int(math.ceil(math.log2(len(sig) + taps)))
    tail = np.fft.irfft(np.fft.rfft(sig, size, axis=0) * np.fft.rfft(ir, size, axis=0), size, axis=0)[: len(sig)]
    scale = float(np.max(np.abs(sig))) / max(float(np.max(np.abs(tail))), 1e-12)
    return (1.0 - wet) * sig + wet * tail * scale


def render_recipe(recipe: Mapping[str, Any], *, seed: int | None = None, jitter: float = 0.0) -> np.ndarray:
    """Render a recipe (see `resolve_recipe`) to (n, 2) float samples at `SR`.

    `seed` replaces the recipe's own seed. `jitter` (0..1) detunes tonal layers by up to 2 %
    and moves filter cutoffs by up to 10 %, each draw seeded: this is how an event's `vary`
    makes repeats differ. The peak is scaled to `peak_db`. An all-zero result stays zero.
    """
    r = recipe if "layers" in recipe and "reverb" in recipe else resolve_recipe(recipe)
    rng = np.random.default_rng(int(r["seed"] if seed is None else seed))
    n = max(1, int(round(float(r["length"]) * SR)))
    out = np.zeros((n, 2))
    for layer in r["layers"]:
        out += _layer(layer, n, rng, jitter)
    if float(r["reverb"]) > 0:
        out = _reverb(out, float(r["reverb"]), float(r["reverb_decay"]), rng)
    if r["reverse"]:
        out = out[::-1].copy()
    peak = float(np.max(np.abs(out)))
    if peak > 0:
        out *= (10.0 ** (float(r["peak_db"]) / 20.0)) / peak
    return out


# ------------------------------------------------------------------ events (a sound placed in a video)

def transform(
    samples: np.ndarray,
    *,
    pitch: float = 0.0,
    rate: float = 1.0,
    pan: float = 0.0,
    reverse: bool = False,
    trim: tuple[float, float] | None = None,
    fade: float | None = None,
) -> np.ndarray:
    """Event-level changes to (n, 2) samples: trim, speed/pitch (tape style: both move together), reverse, pan, fades.

    `pitch` is in semitones, `rate` is a speed factor; the resulting speed is `rate * 2**(pitch/12)`.
    """
    out = samples
    if trim is not None:
        a, b = int(round(trim[0] * SR)), int(round(trim[1] * SR))
        out = out[a:b]
    speed = rate * 2.0 ** (pitch / 12.0)
    if abs(speed - 1.0) > 1e-9 and len(out) > 1:
        idx = np.arange(0.0, len(out) - 1, speed)
        grid = np.arange(len(out))
        out = np.column_stack([np.interp(idx, grid, out[:, c]) for c in range(out.shape[1])])
    if reverse:
        out = out[::-1].copy()
    if pan != 0.0:
        angle = (pan + 1.0) * math.pi / 4.0
        out = out * np.array([math.cos(angle), math.sin(angle)]) * math.sqrt(2.0)
    if fade and len(out) > 0:
        size = max(1, int(round(fade * SR)))
        i = np.arange(len(out))
        edge = np.minimum(i, len(out) - 1 - i) + 1  # 1 at both ends, rising to the middle
        env = np.minimum(1.0, edge / size)
        out = out * env[:, None]
    return np.ascontiguousarray(out, dtype=float)


def measure(samples: np.ndarray) -> dict[str, float]:
    """Length, peak, loudness, attack and brightness of an event's samples (mono mix of the channels)."""
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    n = len(mono)
    if n < 2:
        return {"length": round(n / SR, 4), "peak_db": -120.0, "rms_db": -120.0,
                "peak_at": 0.0, "attack_ms": 0.0, "centroid_hz": 0.0}
    magnitude = np.abs(mono)
    peak_index = int(np.argmax(magnitude))
    peak = float(magnitude[peak_index])
    rms = float(np.sqrt(np.mean(mono ** 2)))
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    total = float(np.sum(spectrum))
    centroid = float(np.sum(freqs * spectrum) / total) if total > 1e-12 else 0.0
    return {
        "length": round(n / SR, 4),
        "peak_db": round(20 * math.log10(peak), 2) if peak > 0 else -120.0,
        "rms_db": round(20 * math.log10(rms), 2) if rms > 0 else -120.0,
        "peak_at": round(peak_index / SR, 4),
        "attack_ms": round(peak_index / SR * 1000.0, 1),
        "centroid_hz": round(centroid, 1),
    }


def brightness(centroid_hz: float) -> str:
    """The word the model reads for a spectral centroid: dark, mid or bright."""
    if centroid_hz < 800:
        return "dark"
    return "mid" if centroid_hz < 3000 else "bright"


def write_wav(path: Path, samples: np.ndarray) -> None:
    """16-bit stereo WAV at `SR`, written through a temp file so a half-written file never shows up."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    with wave.open(str(tmp), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes(np.ascontiguousarray(pcm).tobytes())
    os.replace(tmp, path)


def cache_key(payload: Mapping[str, Any]) -> str:
    """Digest of everything that changes a rendered file (recipe, seed, jitter, transforms, version)."""
    text = json.dumps({"v": RECIPE_VERSION, **payload}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]

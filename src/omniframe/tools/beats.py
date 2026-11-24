"""Music beat grid: tempo + beat times for cutting scenes ON the beat.

Methodology adapted from video-shotcraft's music-beat-sync (Apache 2.0):
"music first" - the grid is measured before scene timing is laid out, and
scene cuts snap to beats. Implementation is dependency-light: numpy +
ffmpeg PCM decode, spectral-flux onset envelope, tempo via autocorrelation
of the onset envelope, phase via cross-correlation with the strongest
onset period. Good enough for snapping scene cuts (perceptual threshold
is ~3 frames at 30fps); not a replacement for full-featured trackers.

Result feeds assemble/planning: pass beat times to the planner so scene
cuts land on beats instead of drifting against the music bed.
"""

from __future__ import annotations

import array
import json
import math
import subprocess
import tempfile
from pathlib import Path

from ..config import CONFIG
from ..ffmpeg import NO_WINDOW
from ..project import project_dir
from .. import __version__

MAX_INLINE_BEATS = 12  # the answer lists this many beat times; the full list is in the file at `beats_path`

RATE = 22050  # mono, enough for onset detection
HOP = 512     # ~23ms hop at 22050 Hz
WIN = 1024


def _decode_mono(path: Path) -> list[float]:
    """Decode audio to mono f32 samples via ffmpeg."""
    proc = subprocess.run(
        [CONFIG.ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0",
         "-ar", str(RATE), "-ac", "1", "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"],
        capture_output=True, check=True, creationflags=NO_WINDOW)
    values = array.array("f")
    values.frombytes(proc.stdout)
    if sys_little():
        pass
    else:
        values.byteswap()
    return values.tolist()


def sys_little() -> bool:
    import sys as _sys
    return _sys.byteorder == "little"


def _onset_envelope(samples: list[float]) -> list[float]:
    """Spectral-flux-ish energy envelope: per-hop RMS, positive differences."""
    import numpy as np
    x = np.asarray(samples, dtype=np.float32)
    if x.size < WIN * 4:
        raise ValueError("audio too short for a beat grid (need >2s)")
    n_hops = (x.size - WIN) // HOP
    # RMS per hop from a running sum of squares: O(n) time and memory, so a long
    # soundtrack (watch_video decodes whole files) does not build an n_hops x WIN matrix
    csum = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    starts = HOP * np.arange(n_hops)
    rms = np.sqrt(np.maximum(csum[starts + WIN] - csum[starts], 0.0) / WIN).astype(np.float32)
    # positive diff = energy increase (onset-like); prepend 0 so a track that
    # starts ON a downbeat still registers its first onset
    flux = np.diff(rms, prepend=np.zeros(1, dtype=rms.dtype))
    flux[flux < 0] = 0.0
    # normalize
    peak = float(flux.max())
    if peak <= 0:
        raise ValueError("audio has no detectable rhythmic energy (silence?)")
    return (flux / peak).tolist()


def _tempo_and_phase(env: list[float]) -> tuple[float, float, float]:
    """Autocorrelation of the onset envelope -> fundamental periodicity (BPM),
    phase = offset of the first strong onset inside that period.

    A click train's AC peaks at EVERY multiple of the true period with nearly
    equal magnitude; the fundamental is the SHORTEST strongly-correlated lag
    (pick the first local max >= 0.75 of the global max, not the global max -
    otherwise a 120 BPM track reads as 60).
    """
    import numpy as np
    env_np = np.asarray(env, dtype=np.float32)
    hop_s = HOP / RATE
    # BPM search range 60-180 -> lag in hops
    min_lag = int(round(60.0 / 180 / hop_s))   # 180 BPM
    max_lag = int(round(60.0 / 60 / hop_s))    # 60 BPM
    lags = np.arange(min_lag, max_lag + 1)
    ac = [float(np.corrcoef(env_np[:-lag], env_np[lag:])[0, 1]) if lag < env_np.size else 0.0
          for lag in lags]
    ac_np = np.asarray(ac)
    global_max = float(ac_np.max())
    # local maxima, then the shortest one within 75% of the best = fundamental
    candidates = [i for i in range(1, len(ac) - 1)
                  if ac[i] >= ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] >= 0.75 * global_max]
    best = candidates[0] if candidates else int(ac_np.argmax())
    # parabolic refinement around the chosen peak
    if 0 < best < len(ac) - 1:
        y0, y1, y2 = ac[best - 1], ac[best], ac[best + 1]
        denom = (y0 - 2 * y1 + y2)
        shift = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-9 else 0.0
        lag_f = lags[best] + max(-1.0, min(1.0, shift))
    else:
        lag_f = float(lags[best])
    bpm = 60.0 / (lag_f * hop_s)
    # phase: strongest onset within one period
    period = lag_f
    window = env_np[:int(period) + 1]
    phase_hops = int(window.argmax())
    confidence = float(ac_np[best])
    return float(bpm), float(phase_hops * hop_s), float(confidence)


def beats_file(audio: Path, project: str | None) -> Path:
    """Where the full beat list is written: the project's audio folder, or `<output>/beats/`."""
    folder = project_dir(project) / "audio" if project else Path(CONFIG.output_dir) / "beats"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{audio.stem}.beats.json"


def calculate_beat_grid(
    audio_path: str, snap_times: list[float] | None = None, project: str | None = None,
) -> dict:
    """Measure tempo + beat grid of a music track; optionally snap cut times.

    audio_path: music bed (mp3/wav). snap_times: candidate scene-cut seconds
    -> each is snapped to the nearest beat (never mid-scene drift).
    The answer has the tempo, the confidence, the first beats and `beats_path`, the JSON
    file with every beat time (a track of 2 minutes has about 300 beats, too many for a reply).
    """
    src = Path(audio_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"audio not found: {src}")
    samples = _decode_mono(src)
    env = _onset_envelope(samples)
    bpm, phase, confidence = _tempo_and_phase(env)
    hop_s = HOP / RATE
    period = 60.0 / bpm
    duration = len(samples) / RATE
    beats = [round(phase + i * period, 3) for i in range(int((duration - phase) / period) + 1)]
    full = {
        "audio": str(src),
        "bpm": round(bpm, 2),
        "beat_interval_s": round(period, 3),
        "first_beat_s": round(phase, 3),
        "confidence": round(confidence, 3),
        "beats": beats,
    }
    target = beats_file(src, project)
    target.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    result = {
        "engine": f"OmniFrame {__version__}",
        "audio": str(src),
        "bpm": round(bpm, 2),
        "beat_interval_s": round(period, 3),
        "first_beat_s": round(phase, 3),
        "confidence": round(confidence, 3),
        "beat_count": len(beats),
        "first_beats": beats[:MAX_INLINE_BEATS],
        "beats_path": str(target),
        "note": "snap scene cuts to beats (perceptual threshold ~3 frames); "
                "music first - measure the grid BEFORE laying out scene timing",
    }
    if snap_times:
        snapped = []
        for t in snap_times:
            if not beats:
                snapped.append(round(t, 3))
                continue
            nearest = min(beats, key=lambda b: abs(b - t))
            snapped.append(round(nearest, 3))
        result["snapped"] = snapped
        result["snap_shift_s"] = [round(s - t, 3) for s, t in zip(snapped, snap_times)]
    return result

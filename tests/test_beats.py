"""Beat-grid tests: synthetic click tracks at known BPM, no network."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.config import CONFIG  # noqa: E402
from argus.tools import beats  # noqa: E402


def _click_track(path: Path, bpm: float, seconds: float = 8.0) -> None:
    """Beeps every 60/bpm seconds: a perfect metronome."""
    period = 60.0 / bpm
    expr = f"if(lt(mod(t\\,{period:.6f})\\,0.06)\\,0.9*sin(2*PI*880*t)\\,0)"
    subprocess.run([
        CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"aevalsrc={expr}:d={seconds}:s=44100",
        "-codec:a", "pcm_s16le", str(path),
    ], check=True, capture_output=True)


@pytest.mark.parametrize("bpm", [90.0, 120.0, 140.0])
def test_grid_finds_known_tempo(tmp_path: Path, bpm: float) -> None:
    track = tmp_path / f"click_{bpm:g}.wav"
    _click_track(track, bpm)
    result = beats.calculate_beat_grid(str(track))
    assert abs(result["bpm"] - bpm) <= 3.0, result["bpm"]
    assert result["confidence"] > 0.3
    # beats are evenly spaced at the reported interval
    interval = result["beat_interval_s"]
    assert 60.0 / (bpm + 3) <= interval <= 60.0 / (bpm - 3)
    for a, b in zip(result["beats"], result["beats"][1:]):
        assert abs((b - a) - interval) < 0.01


def test_snap_times_to_beats(tmp_path: Path) -> None:
    track = tmp_path / "click.wav"
    _click_track(track, 120.0)  # beat every 0.5s, grid phase ~0
    result = beats.calculate_beat_grid(str(track), snap_times=[0.52, 2.47, 5.01])
    for snapped, shift in zip(result["snapped"], result["snap_shift_s"]):
        assert abs(shift) <= 0.05, (snapped, shift)
    assert result["snapped"][0] == pytest.approx(0.5, abs=0.05)


def test_silent_audio_fails_clean(tmp_path: Path) -> None:
    track = tmp_path / "silence.wav"
    subprocess.run([
        CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=5",
        "-codec:a", "pcm_s16le", str(track),
    ], check=True, capture_output=True)
    with pytest.raises(ValueError, match="rhythmic energy"):
        beats.calculate_beat_grid(str(track))


def test_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        beats.calculate_beat_grid(str(tmp_path / "nope.mp3"))

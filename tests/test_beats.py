"""Beat-grid tests: synthetic click tracks at known BPM, no network."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe.config import CONFIG  # noqa: E402
from omniframe.tools import beats  # noqa: E402


def _click_track(path: Path, bpm: float, seconds: float = 8.0) -> None:
    """Beeps every 60/bpm seconds: a perfect metronome."""
    period = 60.0 / bpm
    expr = f"if(lt(mod(t\\,{period:.6f})\\,0.06)\\,0.9*sin(2*PI*880*t)\\,0)"
    subprocess.run([
        CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"aevalsrc={expr}:d={seconds}:s=44100",
        "-codec:a", "pcm_s16le", str(path),
    ], check=True, capture_output=True)


@pytest.fixture(autouse=True)
def _output_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The beat list file goes to the output folder when no project is given: keep it in tmp_path."""
    monkeypatch.setattr(beats, "CONFIG", dataclasses.replace(CONFIG, output_dir=tmp_path / "out"))


@pytest.mark.parametrize("bpm", [90.0, 120.0, 140.0])
def test_grid_finds_known_tempo(tmp_path: Path, bpm: float) -> None:
    track = tmp_path / f"click_{bpm:g}.wav"
    _click_track(track, bpm)
    result = beats.calculate_beat_grid(str(track))
    assert abs(result["bpm"] - bpm) <= 3.0, result["bpm"]
    assert result["confidence"] > 0.3
    # beats are evenly spaced at the reported interval; the full list is in the file
    interval = result["beat_interval_s"]
    assert 60.0 / (bpm + 3) <= interval <= 60.0 / (bpm - 3)
    full = json.loads(Path(result["beats_path"]).read_text(encoding="utf-8"))
    for a, b in zip(full["beats"], full["beats"][1:]):
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


def test_reply_is_short_and_the_full_beat_list_goes_to_a_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2-minute track has about 340 beats: the reply lists 12 and points to the file."""
    track = tmp_path / "long.wav"
    _click_track(track, bpm=170.0, seconds=120.0)
    monkeypatch.setattr(beats, "project_dir", lambda name: tmp_path / "projects" / name)

    result = beats.calculate_beat_grid(str(track), project="demo")

    assert len(json.dumps(result, ensure_ascii=False)) < 3000
    assert result["beat_count"] > 300
    assert len(result["first_beats"]) == beats.MAX_INLINE_BEATS
    path = Path(result["beats_path"])
    assert path.parent == tmp_path / "projects" / "demo" / "audio"
    full = json.loads(path.read_text(encoding="utf-8"))
    assert len(full["beats"]) == result["beat_count"]


def test_without_a_project_the_file_goes_to_the_output_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    track = tmp_path / "click.wav"
    _click_track(track, bpm=120.0, seconds=8.0)
    monkeypatch.setattr(beats, "CONFIG", dataclasses.replace(CONFIG, output_dir=tmp_path / "out"))

    result = beats.calculate_beat_grid(str(track))

    assert Path(result["beats_path"]).parent == tmp_path / "out" / "beats"
    assert Path(result["beats_path"]).is_file()

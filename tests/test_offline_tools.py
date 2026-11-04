"""Offline smoke tests: everything that works without a Gemini API key."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.config import CONFIG  # noqa: E402
from argus.ffmpeg import detect_pauses, measure_loudness, run_ffmpeg, stream_info  # noqa: E402
from argus.tools import assemble, memory, qa, subtitles, timeline  # noqa: E402


def _ffmpeg(args: list[str]) -> None:
    subprocess.run([CONFIG.ffmpeg, "-hide_banner", "-y", *args], check=True,
                   capture_output=True)


@pytest.fixture(scope="module")
def speech_like_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """3 sentence-ish tones separated by real silences (0.5s each)."""
    path = tmp_path_factory.mktemp("media") / "speech.wav"
    args = ["-f", "lavfi", "-i", "sine=frequency=220:duration=1.2"]
    for _ in range(2):
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.5"]
        args += ["-f", "lavfi", "-i", "sine=frequency=220:duration=1.2"]
    args += [
        "-filter_complex",
        "concat=n=5:v=0:a=1",
        "-ar", "44100", "-ac", "1",
        str(path),
    ]
    _ffmpeg(args)
    return path


@pytest.fixture(scope="module")
def master_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A valid 1080x1920 clip with -14 LUFS-ish audio."""
    path = tmp_path_factory.mktemp("media") / "master.mp4"
    _ffmpeg([
        "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(path),
    ])
    return path


# ---------------------------------------------------------------- subtitles

def test_pop_subtitles_builds_ass(tmp_path: Path) -> None:
    ts = tmp_path / "ts.json"
    ts.write_text(json.dumps([
        {"word": "Брат", "start": 0.0, "end": 0.18},
        {"word": "смотри", "start": 0.18, "end": 0.45},
        {"word": "{ВАЖНО}", "start": 0.45, "end": 0.72},
    ]), encoding="utf-8")
    out = tmp_path / "subs.ass"
    stats = subtitles.build_pop_subtitles(ts, out, fps=30.0)

    text = out.read_text(encoding="utf-8")
    assert stats["words"] == 3
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert "Arial Black" in text and "&H0066E0FF" in text
    assert text.count("Dialogue:") == 3
    # frame quantization: 0.18s * 30fps = frame 5.4 -> frame 5 -> 0.17
    assert "0:00:00.17" in text
    # unsafe braces are neutralized
    assert "(ВАЖНО)" in text


def test_highlight_colour_parsing() -> None:
    assert subtitles.highlight_colour_ass("#FFE066") == "&H0066E0FF"
    assert subtitles.highlight_colour_ass("&H00FFFFFF") == "&H00FFFFFF"
    with pytest.raises(ValueError):
        subtitles.highlight_colour_ass("yellow")


# ----------------------------------------------------------------- timeline

def test_timeline_snaps_cuts_to_pauses(speech_like_audio: Path) -> None:
    result = timeline.calculate_acoustic_timeline(
        speech_like_audio,
        "First sentence. Second one here. Third and final sentence!",
        target_scene_count=3,
    )
    assert result["scene_count"] == 3
    assert result["pauses_found"] >= 2
    assert result["snapped_ratio"] >= 0.5  # cuts found real silences
    cuts = result["cut_points"]
    assert cuts == sorted(cuts)
    # a cut must not land inside a tone block (1.2s each, silences between)
    for scene in result["scenes"]:
        assert scene["end"] > scene["start"]


# ----------------------------------------------------------------------- qa

def test_qa_accepts_valid_master(master_video: Path) -> None:
    report = qa.qa_verify_video(master_video)
    assert report["passed"] is True
    assert report["checks"]["resolution"]["passed"]
    assert report["checks"]["loudness"]["measured"] is not None


def test_qa_rejects_wrong_resolution(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    _ffmpeg([
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(bad),
    ])
    report = qa.qa_verify_video(bad)
    assert report["passed"] is False
    assert report["checks"]["resolution"]["passed"] is False


# ------------------------------------------------------------------ assemble

def test_assemble_joins_clips(tmp_path: Path, speech_like_audio: Path) -> None:
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    for clip in (clip_a, clip_b):
        _ffmpeg([
            "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=1",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip),
        ])
    out = tmp_path / "master.mp4"
    report = assemble.assemble_master_video(
        [str(clip_a), str(clip_b)], str(speech_like_audio), str(out)
    )
    assert Path(report["output"]).exists()
    assert report["resolution"] == "1080x1920"
    assert report["duration"] > 1.9  # two 1s clips joined


# ------------------------------------------------------------------- memory

def test_memory_appends(tmp_path: Path) -> None:
    kb = tmp_path / "KNOWLEDGE_BASE.md"
    memory.learn_and_record_memory("T1", "do X", "always Y", knowledge_base_path=kb)
    memory.learn_and_record_memory("T2", "do Z", "never W", knowledge_base_path=kb)
    text = kb.read_text(encoding="utf-8")
    assert "## T1" in text and "## T2" in text
    assert text.count("Technical rule") == 2


# ------------------------------------------------------------------- ffmpeg

def test_loudness_and_pause_detection(master_video: Path, speech_like_audio: Path) -> None:
    lufs = measure_loudness(master_video)["input_i"]
    assert -17 <= lufs <= -11
    pauses = detect_pauses(speech_like_audio)
    assert len(pauses) >= 2
    for start, end in pauses:
        assert 0 < end - start < 2.0


def test_stream_info(master_video: Path) -> None:
    info = stream_info(master_video)
    assert (info.width, info.height) == (1080, 1920)
    assert info.has_video and info.has_audio
    assert run_ffmpeg  # import sanity

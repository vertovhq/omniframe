"""Offline smoke tests: everything that works without a Gemini API key."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import jobs  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.ffmpeg import detect_pauses, measure_loudness, run_ffmpeg, stream_info  # noqa: E402
from argus.media_out import Image  # noqa: E402
from argus.tools import assemble, memory, qa, subtitles, timeline  # noqa: E402
from argus.tools.render import finalize_video  # noqa: E402


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
    assert stats["style"] == "clean"
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    # clean default: white text, thin outline, no yellow anywhere
    assert "&H00FFFFFF" in text and "&H0066E0FF" not in text
    assert text.count("Dialogue:") == 3
    # frame quantization: 0.18s * 30fps = frame 5.4 -> frame 5 -> 0.17
    assert "0:00:00.17" in text
    # unsafe braces are neutralized
    assert "(ВАЖНО)" in text


def test_subtitles_styles(tmp_path: Path) -> None:
    ts = tmp_path / "ts.json"
    ts.write_text(json.dumps([{"word": "тест", "start": 0.0, "end": 0.3}]), encoding="utf-8")
    pop = tmp_path / "pop.ass"
    subtitles.build_pop_subtitles(ts, pop, style="pop", fps=30.0)
    pop_text = pop.read_text(encoding="utf-8")
    assert "&H0066E0FF" in pop_text and "Arial Black" in pop_text
    outline = tmp_path / "outline.ass"
    subtitles.build_pop_subtitles(ts, outline, style="outline", fps=30.0)
    assert "&H00FFFFFF" in outline.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        subtitles.build_pop_subtitles(ts, tmp_path / "x.ass", style="neon")


def test_highlight_colour_parsing() -> None:
    assert subtitles.hex_to_ass("#FFE066") == "&H0066E0FF"
    assert subtitles.hex_to_ass("&H00FFFFFF") == "&H00FFFFFF"
    with pytest.raises(ValueError):
        subtitles.hex_to_ass("yellow")


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

PICTURE = {
    "motion": "testsrc=size={size}:rate=30:duration={d}",
    "black": "color=c=black:size={size}:rate=30:duration={d}",
    "still": "color=c=0x336699:size={size}:rate=30:duration={d}",
    # the `dark` style background with one small caption block (1 % of a 1080x1920 frame)
    "dark_caption": "color=c=0x0A0A12:size={size}:rate=30:duration={d},drawbox=x=300:y=900:w=144:h=144:color=white:t=fill",
}
SOUND = {
    "tone": "sine=frequency=440:sample_rate=44100:duration={d}",
    "silence": "anullsrc=r=44100:cl=mono:d={d}",
    "hot": "aevalsrc=0.99*sin(2*PI*440*t):s=44100:c=mono:d={d}",
}


@pytest.fixture
def qa_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """QA frames and job files of a test go to its own folder, not to ./output."""
    monkeypatch.setattr(qa, "CONFIG", dataclasses.replace(qa.CONFIG, output_dir=tmp_path / "out"))
    return tmp_path


def _clip(
    path: Path,
    picture: list[tuple[str, float]],
    sound: list[tuple[str, float]],
    *,
    size: str = "1080x1920",
    normalise: bool = True,
) -> Path:
    """Synthetic clip: `picture` and `sound` are (kind, seconds) segments laid back to back.

    With `normalise` the sound goes through the final render's step (two-pass loudnorm to
    the target), so the clip is a valid master unless a test breaks it on purpose.
    """
    args: list[str] = []
    for kind, seconds in picture:
        args += ["-f", "lavfi", "-i", PICTURE[kind].format(size=size, d=seconds)]
    graph = "".join(f"[{i}:v]" for i in range(len(picture)))
    graph += f"concat=n={len(picture)}:v=1:a=0,format=yuv420p[v]"
    maps = ["-map", "[v]"]
    if sound:
        base = len(picture)
        for kind, seconds in sound:
            args += ["-f", "lavfi", "-i", SOUND[kind].format(d=seconds)]
        graph += ";" + "".join(f"[{base + j}:a]" for j in range(len(sound)))
        graph += f"concat=n={len(sound)}:v=0:a=1[a]"
        maps += ["-map", "[a]"]
    raw = path.with_name(f"{path.stem}.raw.mp4") if normalise and sound else path
    _ffmpeg([
        *args, "-filter_complex", graph, *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(raw),
    ])
    if raw != path:
        finalize_video(raw, path)
    return path


@pytest.mark.usefixtures("qa_output")
def test_qa_valid_master_passes(qa_output: Path) -> None:
    clip = _clip(qa_output / "master.mp4", [("motion", 4.0)], [("tone", 4.0)])
    report = qa.verify_video(clip)
    assert report["passed"] is True, report["hard_failures"]
    assert report["warnings"] == []
    assert report["format"] == "9:16"
    assert len(report["images"]) == qa.DEFAULT_FRAMES
    assert all(Path(img["path"]).is_file() for img in report["images"])


@pytest.mark.usefixtures("qa_output")
@pytest.mark.parametrize(("size", "fmt", "passes"), [
    ("720x1280", None, False),     # 9:16 shape, wrong size
    ("1920x1080", "9:16", False),  # 16:9 frame where 9:16 is expected
    ("1920x1080", "16:9", True),
])
def test_qa_resolution_follows_the_format(qa_output: Path, size: str, fmt: str | None, passes: bool) -> None:
    clip = _clip(qa_output / f"{size}.mp4", [("motion", 2.0)], [("tone", 2.0)], size=size)
    report = qa.verify_video(clip, format=fmt)
    assert report["checks"]["resolution"]["passed"] is passes
    assert report["passed"] is passes


@pytest.mark.usefixtures("qa_output")
def test_qa_black_gap_in_the_middle_is_a_hard_failure(qa_output: Path) -> None:
    clip = _clip(qa_output / "black_15.mp4", [("motion", 1.25), ("black", 1.5), ("motion", 1.25)], [("tone", 4.0)])
    report = qa.verify_video(clip)
    assert report["passed"] is False
    [gap] = [f for f in report["hard_failures"] if f["check"] == "black"]
    assert gap["start"] == pytest.approx(1.25, abs=0.1)
    assert gap["end"] == pytest.approx(2.75, abs=0.1)
    assert any(img["reason"].startswith("black") for img in report["images"])


@pytest.mark.usefixtures("qa_output")
def test_qa_short_black_gap_is_a_warning(qa_output: Path) -> None:
    clip = _clip(qa_output / "black_07.mp4", [("motion", 1.5), ("black", 0.7), ("motion", 1.5)], [("tone", 3.7)])
    report = qa.verify_video(clip)
    assert report["passed"] is True
    assert [w["check"] for w in report["warnings"]] == ["black"]


@pytest.mark.usefixtures("qa_output")
def test_qa_dark_background_with_a_small_caption_is_not_a_black_gap(qa_output: Path) -> None:
    """The `dark` style background is dark, not black: 1.5 s of it with one small caption is no gap."""
    clip = _clip(qa_output / "dark_15.mp4", [("motion", 1.25), ("dark_caption", 1.5), ("motion", 1.25)], [("tone", 4.0)])
    report = qa.verify_video(clip)
    assert [f for f in report["hard_failures"] + report["warnings"] if f["check"] == "black"] == []
    assert report["passed"] is True, report["hard_failures"]


@pytest.mark.usefixtures("qa_output")
def test_qa_three_second_silence_is_a_warning(qa_output: Path) -> None:
    clip = _clip(qa_output / "silence_3.mp4", [("motion", 7.0)],
                 [("tone", 2.0), ("silence", 3.0), ("tone", 2.0)])
    report = qa.verify_video(clip)
    assert report["passed"] is True
    [warning] = report["warnings"]
    assert warning["check"] == "silence"
    assert warning["start"] == pytest.approx(2.0, abs=0.1)
    assert warning["end"] == pytest.approx(5.0, abs=0.1)


@pytest.mark.usefixtures("qa_output")
def test_qa_hot_peak_is_a_hard_failure(qa_output: Path) -> None:
    clip = _clip(qa_output / "hot.mp4", [("motion", 2.0)], [("hot", 2.0)], normalise=False)
    report = qa.verify_video(clip)
    assert report["passed"] is False
    assert report["checks"]["true_peak"]["passed"] is False
    assert any(f["check"] == "true_peak" for f in report["hard_failures"])


@pytest.mark.usefixtures("qa_output")
def test_qa_frozen_picture_is_a_warning(qa_output: Path) -> None:
    clip = _clip(qa_output / "still_4.mp4", [("motion", 1.0), ("still", 4.0), ("motion", 1.0)], [("tone", 6.0)])
    report = qa.verify_video(clip)
    assert report["passed"] is True
    assert [w["check"] for w in report["warnings"]] == ["freeze"]
    assert any(img["reason"].startswith("freeze") for img in report["images"])


@pytest.mark.usefixtures("qa_output")
def test_qa_platform_duration_is_a_warning(qa_output: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clip = _clip(qa_output / "four_s.mp4", [("motion", 4.0)], [("tone", 4.0)])
    monkeypatch.setitem(qa.PLATFORM_LIMITS, "shorts", (2.0, "2 seconds (test limit)"))
    report = qa.verify_video(clip, target="shorts")
    assert report["passed"] is True
    assert [w["check"] for w in report["warnings"]] == ["platform_duration"]


@pytest.mark.usefixtures("qa_output")
def test_qa_tool_returns_summary_and_images_through_the_job(qa_output: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clip = _clip(qa_output / "job.mp4", [("motion", 2.0)], [("tone", 2.0)])
    monkeypatch.setattr(jobs, "CONFIG", dataclasses.replace(jobs.CONFIG, output_dir=qa_output / "jobs"))
    out = qa.qa_verify_video(str(clip), frames=2, wait_s=120)
    assert isinstance(out, list), out
    summary = json.loads(out[0])
    images = [item for item in out[1:] if isinstance(item, Image)]
    assert summary["passed"] is True
    assert len(images) == len(summary["images"]) == 2


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
    # async contract: call returns immediately with a status file; the detached
    # worker finishes and flips state to "done"
    report = assemble.assemble_master_video(
        [str(clip_a), str(clip_b)], str(speech_like_audio), str(out)
    )
    assert report["state"] == "running"
    status_path = Path(report["status_file"])
    assert status_path.exists()

    deadline = time.time() + 60
    state, status = "running", {}
    while time.time() < deadline:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        state = status.get("state")
        if state in ("done", "error"):
            break
        time.sleep(0.5)
    assert state == "done", status
    assert out.exists()
    info = stream_info(out)
    assert f"{info.width}x{info.height}" == "1080x1920"
    assert info.duration > 1.9  # two 1s clips joined


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


# --------------------------------------------------------------------- flow

def test_flow_requires_saved_session(tmp_path: Path) -> None:
    from argus.tools import flow_browser

    with pytest.raises(RuntimeError, match="flow_login"):
        flow_browser.flow_generate("тест", str(tmp_path / "out.mp4"), profile=str(tmp_path / "nope"))


def test_veo_provider_validation(tmp_path: Path) -> None:
    from argus.tools import veo

    with pytest.raises(ValueError, match="provider"):
        veo.generate_veo_clip("тест", str(tmp_path / "o.mp4"), provider="warp")

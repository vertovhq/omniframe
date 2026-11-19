"""watch_video and get_frames on synthetic media (ffmpeg lavfi), no network."""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import jobs, project, server  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.media_out import Image  # noqa: E402
from argus.tools import watch  # noqa: E402

FPS = 30
SEG_S = 1.2
FIVE = ["red", "cyan", "blue", "yellow", "black"]
MANY = (["white", "black", "yellow", "blue"] * 4)[:14]  # 14 segments, neighbours always far apart in luma
WAIT = 90  # a worker is a fresh Python process


def _make_video(path: Path, colours: list[str], seg_s: float, beeps: bool, size: str = "180x320") -> Path:
    """Solid-colour segments, one after another; with `beeps` a 0.15 s 880 Hz beep starts every segment."""
    cmd = [CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error"]
    for colour in colours:
        cmd += ["-f", "lavfi", "-i", f"color=c={colour}:s={size}:r={FPS}:d={seg_s}"]
    if beeps:
        expr = f"if(lt(mod(t\\,{seg_s})\\,0.15)\\,0.8*sin(2*PI*880*t)\\,0)"
        cmd += ["-f", "lavfi", "-i", f"aevalsrc={expr}:d={seg_s * len(colours)}:s=44100"]
    inputs = "".join(f"[{i}:v]" for i in range(len(colours)))
    cmd += ["-filter_complex", f"{inputs}concat=n={len(colours)}:v=1:a=0,format=yuv420p[v]", "-map", "[v]"]
    cmd += ["-map", f"{len(colours)}:a", "-c:a", "aac", "-b:a", "96k"] if beeps else ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-shortest", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.fixture(scope="module")
def five_segments(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_video(tmp_path_factory.mktemp("media") / "five.mp4", FIVE, SEG_S, beeps=True)


@pytest.fixture(scope="module")
def many_segments(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_video(tmp_path_factory.mktemp("media") / "many.mp4", MANY, 0.5, beeps=False)


@pytest.fixture(autouse=True)
def watch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Own output dir per test: caches, projects and jobs never leak between tests."""
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (jobs, project, watch):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield
    for proc in list(jobs._PROCS.values()):
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    jobs._PROCS.clear()


def _run(path: Path, **kw) -> dict:
    """The worker function, in this process."""
    payload = {"path": str(path), "project": "t", "transcript": False, **kw}
    return watch.run_job(payload, lambda *a, **k: None)


def _text(out: list) -> dict:
    assert isinstance(out, list) and isinstance(out[0], str), out
    return json.loads(out[0])


# ------------------------------------------------------------------ shots, sounds

def test_shots_within_one_frame(five_segments: Path) -> None:
    result = _run(five_segments)
    shots = result["shots"]
    assert len(shots) == 5
    assert shots[0][0] == 0.0
    for k, (start, end) in enumerate(shots):
        assert start == pytest.approx(k * SEG_S, abs=1 / FPS)
        assert end == pytest.approx((k + 1) * SEG_S, abs=1 / FPS)
    assert shots[-1][1] == pytest.approx(len(FIVE) * SEG_S, abs=0.1)


def test_sound_events_within_50_ms(five_segments: Path) -> None:
    events = _run(five_segments)["sound_events"]
    times = [e["t"] for e in events]
    assert len(events) == 5, events
    for k, t in enumerate(times):
        assert t == pytest.approx(k * SEG_S, abs=0.05)
    assert all(0 < e["strength"] <= 1 for e in events)


def test_video_without_audio_has_no_sound_events(many_segments: Path) -> None:
    result = _run(many_segments)
    assert result["has_audio"] is False
    assert result["sound_events"] == []
    assert "no audio" in result["sound_events_note"]


# ------------------------------------------------------------------ frames and sheets

def test_summary_shape_frames_and_sheets(five_segments: Path) -> None:
    result = _run(five_segments, max_frames=6)  # one sheet: shot starts + hook, no fill
    assert (result["width"], result["height"]) == (180, 320)
    assert result["duration"] == pytest.approx(6.0, abs=0.1)
    frames = result["frames"]
    assert [f["t"] for f in frames] == sorted(f["t"] for f in frames)
    assert all(Path(f["path"]).is_file() for f in frames)
    assert {f["shot"] for f in frames} == {1, 2, 3, 4, 5}
    assert result["sheets_total"] == 1 and result["page"] == 1 and result["pages_total"] == 1
    (sheet,) = result["images"]
    with PILImage.open(sheet["path"]) as img:
        assert max(img.size) <= watch.SHEET_MAX_SIDE
        assert img.size[1] > img.size[0]  # portrait video: 2 columns x 3 rows


def test_frame_colours_match_the_shot(five_segments: Path) -> None:
    frames = _run(five_segments)["frames"]
    expected = {1: (255, 0, 0), 4: (255, 255, 0)}
    for f in frames:
        if f["shot"] in expected:
            with PILImage.open(f["path"]) as img:
                r, g, b = img.convert("RGB").getpixel((90, 160))
            want = expected[f["shot"]]
            assert all(abs(a - b_) < 40 for a, b_ in zip((r, g, b), want)), (f, (r, g, b))


def test_landscape_video_uses_three_columns(tmp_path: Path) -> None:
    video = _make_video(tmp_path / "wide.mp4", ["red", "cyan"], 1.0, beeps=False, size="320x180")
    sheet = _run(video)["images"][0]["path"]
    with PILImage.open(sheet) as img:
        assert img.size[0] > img.size[1]
        assert max(img.size) <= watch.SHEET_MAX_SIDE


def test_select_frames_budget_keeps_first_hook_and_last() -> None:
    shots = [[float(i), float(i + 1)] for i in range(100)]
    chosen = watch.select_frames(shots, 100.0, 10)
    assert len(chosen) == 10
    times = [t for t, _ in chosen]
    assert times == sorted(times)
    assert chosen[0] == (0.15, 1)                      # first shot
    assert any(abs(t - 0.5) <= 0.2 for t in times)      # hook
    assert chosen[-1][1] == 100                         # last shot
    assert 20 < times[len(times) // 2] < 80             # the rest is spread over the timeline


def test_select_frames_long_shot_gets_a_middle_frame() -> None:
    chosen = watch.select_frames([[0.0, 20.0]], 20.0, 24)
    assert (10.0, 1) in chosen and (0.15, 1) in chosen
    assert any(abs(t - 0.5) <= 0.2 for t, _ in chosen)


def test_select_frames_one_take_fills_the_budget() -> None:
    # a 74 s single-take animation used to come back as 3 frames (first run, task 13)
    chosen = watch.select_frames([[0.0, 74.0]], 74.0, 24)
    times = [t for t, _ in chosen]
    assert 20 <= len(chosen) <= 24
    assert all(shot == 1 for _, shot in chosen)
    assert max(b - a for a, b in zip(times, times[1:])) <= 6.5
    assert times[-1] >= 68.0


def test_select_frames_within_budget_keeps_every_shot() -> None:
    shots = [[0.0, 0.3], [0.3, 0.6], [0.6, 5.0]]
    chosen = watch.select_frames(shots, 5.0, 24)
    assert {shot for _, shot in chosen} == {1, 2, 3}
    assert all(0 <= t <= 4.96 for t, _ in chosen)


# ------------------------------------------------------------------ pagination

def test_pagination_returns_two_sheets_per_page(many_segments: Path) -> None:
    first = _run(many_segments, max_frames=14, page=1)
    assert len(first["frames"]) == 14
    assert first["sheets_total"] == 3 and first["pages_total"] == 2
    assert [i["sheet"] for i in first["images"]] == [1, 2]
    assert "page=2" in first["page_note"]

    second = _run(many_segments, max_frames=14, page=2)
    assert [i["sheet"] for i in second["images"]] == [3]
    assert len(second["images"][0]["times"]) == 2
    assert "page_note" not in second

    # no frame is dropped: the sheets together cover every frame time once
    covered = [t for r in (first, second) for i in r["images"] for t in i["times"]]
    assert covered == [f["t"] for f in first["frames"]]

    beyond = _run(many_segments, max_frames=14, page=3)
    assert beyond["images"] == [] and "does not exist" in beyond["page_note"]


# ------------------------------------------------------------------ cache and job route

def test_cache_hit_on_second_call_through_the_job(five_segments: Path) -> None:
    first = watch.watch_video(str(five_segments), "cache", max_frames=6, transcript=False, wait_s=WAIT)
    second = watch.watch_video(str(five_segments), "cache", max_frames=6, transcript=False, wait_s=WAIT)
    one, two = _text(first), _text(second)
    assert one["cache_hit"] is False and two["cache_hit"] is True
    assert one["shots"] == two["shots"] and one["sound_events"] == two["sound_events"]
    assert one["engine"].startswith("ARGUS ")

    # the job result carries the contact sheet as image content, at the sheet's own size
    assert len(first) == 2 and isinstance(first[1], Image)
    with PILImage.open(one["images"][0]["path"]) as img:
        assert img.size[1] > 1024  # not shrunk to the 1024 default


def test_cache_is_keyed_by_content_not_by_path(five_segments: Path, tmp_path: Path, monkeypatch) -> None:
    copy = tmp_path / "renamed_copy.mp4"
    shutil.copy(five_segments, copy)
    assert watch.content_key(copy) == watch.content_key(five_segments)

    assert _run(five_segments)["cache_hit"] is False

    def boom(*a, **k):
        raise AssertionError("shot detection must not run on a cache hit")

    monkeypatch.setattr(watch, "detect_cuts", boom)
    monkeypatch.setattr(watch, "detect_sound_events", boom)
    monkeypatch.setattr(watch, "_extract_frame", boom)
    again = _run(copy)
    assert again["cache_hit"] is True and len(again["shots"]) == 5


def test_content_key_changes_with_content(tmp_path: Path) -> None:
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x" * 1000)
    b.write_bytes(b"x" * 999 + b"y")
    assert watch.content_key(a) != watch.content_key(b)
    big = tmp_path / "big.bin"
    big.write_bytes(b"a" * watch.HASH_CHUNK + b"m" * 1000 + b"z" * watch.HASH_CHUNK)
    assert len(watch.content_key(big)) == 24


def test_other_frame_budget_reuses_shots_but_rebuilds_frames(five_segments: Path) -> None:
    _run(five_segments, max_frames=24)
    other = _run(five_segments, max_frames=3)
    assert other["cache_hit"] is False
    assert len(other["frames"]) == 3


def test_frames_file_from_an_older_select_frames_is_rebuilt(five_segments: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeWhisper()
    monkeypatch.setattr(watch, "whisper_available", lambda: True)
    monkeypatch.setattr(watch, "_whisper_model", lambda name: fake)
    first = _run(five_segments, max_frames=24, transcript=True)
    frames_file = project.project_dir("t") / "cache" / "watch" / first["cache_key"] / "frames.24.json"
    assert json.loads(frames_file.read_text(encoding="utf-8"))["frames_version"] == watch.FRAMES_VERSION

    # what an older select_frames left behind: no frames_version and only 3 frames
    stored = json.loads(frames_file.read_text(encoding="utf-8"))
    stored.pop("frames_version")
    stored["frames"] = stored["frames"][:3]
    frames_file.write_text(json.dumps(stored), encoding="utf-8")

    def no_rerun(*args, **kwargs):
        raise AssertionError("analysis must come from the cache")

    monkeypatch.setattr(watch, "detect_cuts", no_rerun)
    monkeypatch.setattr(watch, "detect_sound_events", no_rerun)
    selections: list[int] = []
    real_select = watch.select_frames

    def counting_select(*args, **kwargs):
        selections.append(1)
        return real_select(*args, **kwargs)

    monkeypatch.setattr(watch, "select_frames", counting_select)

    rebuilt = _run(five_segments, max_frames=24, transcript=True)
    assert rebuilt["cache_hit"] is False
    assert len(selections) == 1                              # the frames stage ran again
    assert len(rebuilt["frames"]) == len(first["frames"]) > 3
    assert rebuilt["shots"] == first["shots"]                # analysis came from the cache
    assert len(fake.calls) == 1                              # transcript came from the cache

    assert json.loads(frames_file.read_text(encoding="utf-8"))["frames_version"] == watch.FRAMES_VERSION
    again = _run(five_segments, max_frames=24, transcript=True)
    assert again["cache_hit"] is True and len(selections) == 1


def test_validation_errors(five_segments: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        watch.watch_video(str(tmp_path / "nope.mp4"), "x")
    with pytest.raises(ValueError, match="max_frames"):
        watch.watch_video(str(five_segments), "x", max_frames=0)
    with pytest.raises(ValueError, match="page"):
        watch.watch_video(str(five_segments), "x", page=0)
    with pytest.raises(ValueError, match="letters or digits"):
        watch.watch_video(str(five_segments), "***")


# ------------------------------------------------------------------ transcript

class _FakeWhisper:
    """Stands in for faster-whisper's WhisperModel; records how it was called."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def detect_language(self, audio, **kw):
        return "ru", 0.99, {}

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        word = SimpleNamespace(word=" Ну", start=0.1, end=0.3)
        again = SimpleNamespace(word=" ну ", start=0.4, end=0.6)
        seg = SimpleNamespace(start=0.1, end=0.6, text=" Ну ну ", words=[word, again])
        return iter([seg]), SimpleNamespace(language=kw.get("language") or "en")


def test_transcript_words_and_cache(five_segments: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeWhisper()
    monkeypatch.setattr(watch, "whisper_available", lambda: True)
    monkeypatch.setattr(watch, "_whisper_model", lambda name: fake)

    result = _run(five_segments, transcript=True)
    assert result["language"] == "ru"
    segments = json.loads(Path(result["segments_path"]).read_text(encoding="utf-8"))
    assert segments == [{"s": 0.1, "e": 0.6, "text": "Ну ну"}]
    assert result["transcript_head"] == "Ну ну" and "segments" not in result and "words" not in result
    words = json.loads(Path(result["words_path"]).read_text(encoding="utf-8"))
    assert words == [{"w": "Ну", "s": 0.1, "e": 0.3}, {"w": "ну", "s": 0.4, "e": 0.6}]  # repeats kept
    call = fake.calls[0]
    assert call["word_timestamps"] is True and call["vad_filter"] is True
    assert call["condition_on_previous_text"] is False and call["temperature"] == 0
    assert call["initial_prompt"] == watch.RUSSIAN_VERBATIM_PROMPT  # Russian: verbatim prompt
    assert result["word_count"] == 2

    again = _run(five_segments, transcript=True)
    assert again["cache_hit"] is True and len(fake.calls) == 1

    english = _run(five_segments, transcript=True, language="en")
    assert english["language"] == "en" and len(fake.calls) == 2
    assert fake.calls[1]["initial_prompt"] == watch.ENGLISH_VERBATIM_PROMPT  # English: verbatim prompt too

    german = _run(five_segments, transcript=True, language="de")
    assert german["language"] == "de" and fake.calls[2]["initial_prompt"] is None  # no prompt in other languages


class _LongWhisper(_FakeWhisper):
    """About eight minutes of speech: 240 sentences of ten words each."""

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        segs = []
        for i in range(240):
            words = [
                SimpleNamespace(word=f" слово{i}x{j}", start=i * 2.0 + j * 0.15, end=i * 2.0 + j * 0.15 + 0.12)
                for j in range(10)
            ]
            text = " " + " ".join(w.word.strip() for w in words) + "."
            segs.append(SimpleNamespace(start=i * 2.0, end=i * 2.0 + 1.8, text=text, words=words))
        return iter(segs), SimpleNamespace(language="ru")


def test_words_and_sentences_are_never_listed_inline(five_segments: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watch, "whisper_available", lambda: True)
    monkeypatch.setattr(watch, "_whisper_model", lambda name: _FakeWhisper())

    result = _run(five_segments, transcript=True)  # the fake speaks two words
    assert "words" not in result and "segments" not in result
    assert result["word_count"] == 2 and "words_path" in result["words_note"]
    assert len(json.loads(Path(result["words_path"]).read_text(encoding="utf-8"))) == 2
    assert Path(result["segments_path"]).is_file()


def test_a_long_talk_result_stays_far_below_the_client_limit(five_segments: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watch, "whisper_available", lambda: True)
    monkeypatch.setattr(watch, "_whisper_model", lambda name: _LongWhisper())

    result = _run(five_segments, transcript=True, max_frames=24)
    assert result["word_count"] == 2400
    assert len(json.dumps(result, ensure_ascii=False)) < 10_000  # the client cuts results at 30,000
    assert len(result["transcript_head"]) <= watch.TRANSCRIPT_HEAD_CHARS + 3


def test_transcript_missing_package_is_reported(five_segments: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watch, "whisper_available", lambda: False)
    result = _run(five_segments, transcript=True)
    assert result["words_path"] is None and result["segments_path"] is None
    assert "faster-whisper" in result["transcript_note"]


def test_real_transcript_runs_when_faster_whisper_is_installed(five_segments: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("faster_whisper")
    monkeypatch.setattr(watch, "CONFIG", dataclasses.replace(watch.CONFIG, whisper_model="tiny"))
    try:
        result = _run(five_segments, transcript=True)
    except (OSError, ConnectionError) as exc:  # the model download needs the network
        pytest.skip(f"whisper model unavailable offline: {exc}")
    assert result["words_path"] and Path(result["words_path"]).is_file()
    assert Path(result["segments_path"]).is_file()


# ------------------------------------------------------------------ get_frames

def test_get_frames_crop_dimensions(five_segments: Path) -> None:
    out = watch.get_frames(str(five_segments), [0.5, 2.0], crop=[0.25, 0.25, 0.5, 0.5])
    summary = _text(out)
    assert len(out) == 3 and all(isinstance(i, Image) for i in out[1:])
    assert [e["size"] for e in summary["images"]] == [[90, 160], [90, 160]]
    assert [e["t"] for e in summary["images"]] == [0.5, 2.0]
    for entry in summary["images"]:
        with PILImage.open(entry["path"]) as view:
            assert view.size == (90, 160)
        with PILImage.open(entry["full_path"]) as full:
            assert full.size == (90, 160)
    with PILImage.open(summary["images"][1]["full_path"]) as img:  # t=2.0 s is in the cyan segment
        r, g, b = img.convert("RGB").getpixel((45, 80))
    assert r < 60 and g > 200 and b > 200


def test_get_frames_without_crop_is_full_frame_and_respects_max_side(five_segments: Path) -> None:
    summary = _text(watch.get_frames(str(five_segments), [1.0], max_side=100))
    entry = summary["images"][0]
    assert entry["size"] == [180, 320]
    with PILImage.open(entry["path"]) as view:
        assert max(view.size) == 100 and view.size == (56, 100)
    assert summary["crop"] is None


def test_get_frames_caps_the_number_of_times(five_segments: Path) -> None:
    times = [0.1 * k for k in range(1, 11)]
    out = watch.get_frames(str(five_segments), times)
    summary = _text(out)
    assert len(summary["images"]) == watch.GET_FRAMES_MAX_TIMES == len(out) - 1
    assert summary["skipped_times"] == pytest.approx(times[8:])
    assert "at most 8" in summary["note"]


def test_get_frames_rejects_bad_input(five_segments: Path) -> None:
    src = str(five_segments)
    with pytest.raises(ValueError, match="crop"):
        watch.get_frames(src, [1.0], crop=[0.5, 0.5, 0.8, 0.8])
    with pytest.raises(ValueError, match="crop"):
        watch.get_frames(src, [1.0], crop=[0.1, 0.1])
    with pytest.raises(ValueError, match="outside the video"):
        watch.get_frames(src, [99.0])
    with pytest.raises(ValueError, match="empty"):
        watch.get_frames(src, [])
    with pytest.raises(ValueError, match="max_side"):
        watch.get_frames(src, [1.0], max_side=5)


def test_get_frames_at_the_very_end_is_clamped(five_segments: Path) -> None:
    summary = _text(watch.get_frames(str(five_segments), [6.0]))
    assert summary["images"][0]["size"] == [180, 320]


def test_get_frames_stores_files_in_the_project_work_folder(five_segments: Path) -> None:
    proj = project.project_dir("clips")
    inside = proj / "refs" / "five.mp4"
    shutil.copy(five_segments, inside)
    summary = _text(watch.get_frames(str(inside), [1.0]))
    assert Path(summary["images"][0]["full_path"]).parent == proj / ".work" / "frames"

    summary = _text(watch.get_frames(str(five_segments), [1.0]))
    assert Path(summary["images"][0]["full_path"]).parent == watch.CONFIG.output_dir / ".work" / "frames"


# ------------------------------------------------------------------ server

def test_server_registers_watch_tools_and_drops_analyze_reference() -> None:
    names = server._registered_tool_names()
    assert "watch_video" in names and "get_frames" in names
    assert "analyze_reference" not in names
    assert not (Path(watch.__file__).parent / "reference.py").exists()

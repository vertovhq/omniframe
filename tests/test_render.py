"""render_video: request validation, public dir, stills comparison, final post-processing, engine e2e.

Everything runs offline on synthetic media (ffmpeg lavfi). The tests marked `needs_engine`
start the real Remotion engine and are skipped when `engine/node_modules` is missing.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import jobs, project  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.ffmpeg import probe, stream_info  # noqa: E402
from argus.media_out import Image  # noqa: E402
from argus.tools import kinetic, qa, render  # noqa: E402

ENGINE = Path(__file__).resolve().parents[1] / "engine"
needs_engine = pytest.mark.skipif(
    not (ENGINE / "node_modules").is_dir(), reason="engine/node_modules is missing (run npm install in engine/)"
)
WAIT = 300  # a worker is a fresh Python process, and it bundles the engine


@pytest.fixture(autouse=True)
def render_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Own output dir per test: projects, renders and jobs never leak between tests."""
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (jobs, project, render):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield
    for proc in list(jobs._PROCS.values()):
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    jobs._PROCS.clear()


@pytest.fixture
def root() -> Path:
    return project.project_dir("t")


def _ffmpeg(*args: str) -> None:
    subprocess.run([CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error", *args], check=True, capture_output=True)


def _tone(path: Path, seconds: float = 3.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-ar", "48000", str(path))
    return path


def _reference_video(path: Path, seconds: float = 4.0) -> Path:
    _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc=size=270x480:rate=30:duration={seconds}", "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", str(path),
    )
    return path


def _plan(**extra) -> dict:
    return {
        "version": 2, "format": "9:16", "duration": 3, "style": "dark",
        "scenes": [{"kind": "big", "at": 0, "text": "ARGUS"}], **extra,
    }


def _prepare(plan, root: Path, **kw):
    args = {"mode": "stills", "times": None, "compare": None, "format": None, "name": "video", **kw}
    return render.prepare_render(plan, root, **args)


# ------------------------------------------------------------------ validation (no engine)

def test_invalid_plan_returns_every_error_and_starts_no_render(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a, **k):
        raise AssertionError("an invalid plan must not start a job")

    monkeypatch.setattr(jobs, "run_or_detach", boom)
    bad = _plan(scenes=[{"kind": "stamp", "at": 0, "text": "x"}, {"kind": "big", "at": 1, "txt": "y"}])
    out = render.render_video(bad, "t")
    assert out["valid"] is False
    errors = out["errors"]
    assert any(e.startswith("scenes[0].kind:") and "stamp" in e for e in errors), errors
    assert any(e.startswith("scenes[1].txt:") for e in errors), errors
    assert not list((project.project_dir("t") / "renders").glob("*"))
    assert not jobs.jobs_root().exists() or not list(jobs.jobs_root().iterdir())


def test_unknown_mode_format_and_unreadable_plan_file_are_reported(root: Path) -> None:
    payload, errors = _prepare(_plan(), root, mode="draft", format="4:3")
    assert payload is None
    assert any(e.startswith("mode:") for e in errors) and any(e.startswith("format:") for e in errors)
    payload, errors = _prepare("no-such-plan.json", root)
    assert payload is None and errors[0].startswith("plan: file not found")


def test_plan_can_be_a_json_file_and_relative_paths_use_the_project(root: Path) -> None:
    (root / "plan.in.json").write_text(json.dumps(_plan()), encoding="utf-8")
    payload, errors = _prepare("plan.in.json", root)
    assert errors == [] and payload is not None
    assert payload["plan"]["duration"] == 3 and payload["mode"] == "stills"


def test_missing_files_are_reported_with_their_plan_path(root: Path) -> None:
    plan = _plan(
        style={
            "colors": {"bg": "#000", "text": "#fff", "muted": "#888", "accent": "#f80"},
            "fonts": {"display": {"family": "X", "src": "fonts/none.ttf"}, "body": {"family": "Inter"}},
        },
        scenes=[{"kind": "card", "at": 0, "media": "shots/none.jpg"}],
        audio={"voice": {"src": "audio/voice.mp3"}, "sfx": [{"at": 1, "src": "audio/none.wav"}]},
    )
    payload, errors = _prepare(plan, root, mode="final")
    assert payload is None
    wheres = {e.split(":")[0] for e in errors}
    assert {"style.fonts.display.src", "scenes[0].media", "audio.voice.src", "audio.sfx[0].src"} <= wheres

    # a still has no sound, so audio files are not needed for it
    payload, errors = _prepare(plan, root, mode="stills")
    assert {e.split(":")[0] for e in errors} == {"style.fonts.display.src", "scenes[0].media"}


def test_builtin_sfx_names_need_no_file(root: Path) -> None:
    plan = _plan(audio={"sfx": [{"at": 1, "src": "sfx/whoosh.mp3"}, {"at": 2, "src": "hit.wav"}]})
    payload, errors = _prepare(plan, root, mode="final")
    assert errors == [] and payload is not None


def test_times_defaults_limits_and_range(root: Path) -> None:
    payload, errors = _prepare(_plan(), root)
    assert errors == [] and payload["times"] == [0.5, 1.5, 2.5]  # a default spread, one per second up to 6

    payload, errors = _prepare(_plan(), root, times=[0.5, 99, "x", -1])
    assert payload is None
    assert [e.split(":")[0] for e in errors] == ["times[1]", "times[2]", "times[3]"]

    payload, errors = _prepare(_plan(), root, times=[0.1] * (render.MAX_STILLS + 1))
    assert payload is None and errors[0].startswith("times:")


def test_compare_needs_matching_times_and_a_readable_video(root: Path, tmp_path: Path) -> None:
    ref = _reference_video(tmp_path / "ref.mp4", 4.0)
    ok = {"video": str(ref), "times": [0.5, 3.5]}
    payload, errors = _prepare(_plan(), root, times=[0.5, 1.5], compare=ok)
    assert errors == [] and payload["compare"] == {"video": str(ref.resolve()), "times": [0.5, 3.5]}

    _, errors = _prepare(_plan(), root, times=[0.5, 1.5], compare={"video": str(ref), "times": [0.5]})
    assert any(e.startswith("compare.times:") and "must match" in e for e in errors)
    _, errors = _prepare(_plan(), root, times=[0.5], compare={"video": str(ref), "times": [9.0]})
    assert any(e.startswith("compare.times[0]:") for e in errors)
    _, errors = _prepare(_plan(), root, times=[0.5], compare={"video": "nope.mp4", "times": [0.5]})
    assert any(e.startswith("compare.video:") for e in errors)
    _, errors = _prepare(_plan(), root, compare=ok)
    assert any(e.startswith("times:") for e in errors)
    _, errors = _prepare(_plan(), root, mode="preview", compare=ok)
    assert any(e.startswith("compare:") and "stills" in e for e in errors)


def test_caption_words_from_file_inline_and_remap(root: Path) -> None:
    words = [{"w": "hello", "s": 0.0, "e": 0.4}, {"w": "big", "s": 0.5, "e": 0.8}, {"w": "world", "s": 4.0, "e": 4.5}]
    (root / "audio" / "voice.words.json").write_text(json.dumps(words), encoding="utf-8")

    payload, errors = _prepare(_plan(captions={"words": "audio/voice.words.json"}), root)
    assert errors == [] and [w["w"] for w in payload["caption_words"]] == ["hello", "big", "world"]

    payload, errors = _prepare(_plan(captions={"words": [{"w": "x", "s": 0.2, "e": 0.5}]}), root)
    assert payload["caption_words"] == [{"w": "x", "s": 0.2, "e": 0.5}]

    # footage transcript: only the kept range [3.9, 4.6] stays, moved to the start of the output
    footage = _reference_video(root / "refs" / "talk.mp4", 5.0)
    plan = _plan(
        duration=None,
        clips=[{"src": str(footage), "at": 0.0, "in": 3.9, "out": 4.6}],
        captions={"words": {"source": "audio/voice.words.json", "remap": "clips"}},
    )
    payload, errors = _prepare(plan, root)
    assert errors == [], errors
    assert [(w["w"], w["s"]) for w in payload["caption_words"]] == [("world", 0.1)]
    assert payload["plan"]["duration"] == pytest.approx(2.6)  # the scene (at 0 + 2 s) is the last thing, plus the tail
    assert not any("clips" in w for w in payload["warnings"])  # the engine draws clips since task 14

    plan["clips"][0].update({"in": 1.0, "out": 3.0})  # no word in that range
    _, errors = _prepare(plan, root)
    assert any(e.startswith("captions.words:") and "falls inside" in e for e in errors)


def test_warning_for_unducked_music(root: Path) -> None:
    _tone(root / "audio" / "m.wav")
    plan = _plan(audio={"music": {"src": "audio/m.wav", "duck": 0.3}})
    payload, errors = _prepare(plan, root, mode="final")
    assert errors == []
    assert "duck" in " ".join(payload["warnings"])


def test_example_plan_reports_the_files_it_needs(root: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "plans" / "reference_style_9x16.json"
    payload, errors = _prepare(str(example), root, mode="final")
    assert payload is None
    assert {e.split(":")[0] for e in errors} >= {"captions.words", "audio.voice.src", "audio.music.src"}


# ------------------------------------------------------------------ public dir

def test_public_dir_links_files_and_rewrites_paths(root: Path, tmp_path: Path) -> None:
    img = tmp_path / "pic one.png"
    PILImage.new("RGB", (8, 8), "red").save(img)
    voice = _tone(root / "audio" / "voice.wav")
    plan = _plan(
        scenes=[{"kind": "card", "at": 0, "media": str(img)}],
        captions={"words": [{"w": "x", "s": 0, "e": 1}]},
        audio={"voice": {"src": "audio/voice.wav"}, "sfx": [{"at": 1, "src": "sfx/whoosh.mp3"}]},
    )
    payload, errors = _prepare(plan, root, mode="final")
    assert errors == []
    public = render._PublicDir(root / ".work" / "pub", [Path(b) for b in payload["bases"]])
    props = render._engine_props(payload["plan"], payload["caption_words"], public, with_audio=True)

    card = props["scenes"][0]["media"]
    assert card.startswith("m/") and " " not in card
    assert os.path.samefile(public.root / card, img)  # a hardlink, not a copy
    assert os.path.samefile(public.root / props["audio"]["voice"]["src"], voice)
    assert (public.root / props["audio"]["sfx"][0]["src"]).is_file()
    assert (public.root / "fonts" / "InterDisplay-Bold.otf").is_file()
    assert props["captions"]["words"] == [{"w": "x", "s": 0.0, "e": 1.0}]

    bare = render._engine_props(payload["plan"], payload["caption_words"], public, with_audio=False)
    assert "audio" not in bare  # stills carry no sound


# ------------------------------------------------------------------ stills comparison

def test_side_by_side_puts_reference_left_and_render_right(tmp_path: Path) -> None:
    ref = tmp_path / "ref.png"
    shot = tmp_path / "shot.png"
    PILImage.new("RGB", (270, 480), (200, 30, 30)).save(ref)
    PILImage.new("RGB", (1080, 1920), (30, 30, 200)).save(shot)
    out = render.compose_side_by_side(ref, shot, tmp_path / "cmp.jpg", "REFERENCE 00:01.0", "RENDER 00:01.0")
    with PILImage.open(out) as img:
        width, height = img.size
        assert height == render.COMPARE_MAX_HEIGHT + render.COMPARE_LABEL_H
        assert width == 2 * 540 + render.COMPARE_GAP
        r, _, b = img.getpixel((width // 4, height // 2))
        assert r > 150 and b < 90  # reference on the left
        r, _, b = img.getpixel((3 * width // 4, height // 2))
        assert b > 150 and r < 90  # render on the right
        label = img.crop((0, 0, width, render.COMPARE_LABEL_H))
        assert label.getextrema() != ((18, 18), (18, 18), (22, 22))  # text was drawn


def test_side_by_side_of_wide_frames_fits_the_width_budget(tmp_path: Path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    PILImage.new("RGB", (1920, 1080), "gray").save(a)
    PILImage.new("RGB", (1920, 1080), "white").save(b)
    out = render.compose_side_by_side(a, b, tmp_path / "wide.jpg", "A", "B")
    with PILImage.open(out) as img:
        assert img.width <= render.COMPARE_MAX_WIDTH + 2


# ------------------------------------------------------------------ final post-processing

def _video_with_audio(path: Path, volume: float, seconds: float = 4.0) -> Path:
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c=black:s=180x320:r=30:d={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
        "-af", f"volume={volume}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    )
    return path


def test_finalize_normalises_loudness_tags_and_keeps_the_video(tmp_path: Path) -> None:
    raw = _video_with_audio(tmp_path / "raw.mp4", volume=0.05)
    out = tmp_path / "final.mp4"
    info = render.finalize_video(raw, out)
    assert info["loudness_before"] < -25
    assert abs(info["loudness_after"] - CONFIG.loudness_target) <= 1.0, info
    meta = probe(out)
    assert meta["format"]["tags"]["comment"].startswith("Made with ARGUS Studio v")
    vids = [s for s in meta["streams"] if s["codec_type"] == "video"]
    assert vids[0]["codec_name"] == "h264" and (vids[0]["width"], vids[0]["height"]) == (180, 320)
    # faststart: the moov box comes before the media data
    head = out.read_bytes()
    assert head.find(b"moov") < head.find(b"mdat")


def test_finalize_without_audio_only_tags(tmp_path: Path) -> None:
    raw = tmp_path / "silent.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=180x320:r=30:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw))
    info = render.finalize_video(raw, tmp_path / "out.mp4")
    assert info["note"] == "no audio to normalise" and not stream_info(tmp_path / "out.mp4").has_audio


# ------------------------------------------------------------------ shared helpers

def test_kinetic_still_shares_the_moved_helpers() -> None:
    assert kinetic._find_browser is render._find_browser
    assert kinetic.engine_dir is render.engine_dir
    assert kinetic._ensure_default_sfx is render._ensure_default_sfx
    assert kinetic.DEFAULT_SFX == render.DEFAULT_SFX


def test_server_registers_render_video() -> None:
    from argus import server

    assert "render_video" in server._registered_tool_names()


# ------------------------------------------------------------------ engine e2e

def _images(out) -> tuple[dict, list]:
    assert isinstance(out, list) and isinstance(out[0], str), out
    return json.loads(out[0]), [x for x in out[1:] if isinstance(x, Image)]


@needs_engine
@pytest.mark.parametrize("fmt, size", [("9:16", (1080, 1920)), ("16:9", (1920, 1080))])
def test_stills_in_both_formats_return_images(fmt: str, size: tuple[int, int]) -> None:
    plan = _plan(format=fmt, captions={"words": [{"w": "ARGUS", "s": 0.2, "e": 0.9}], "mode": "word"})
    out = render.render_video(plan, "t", mode="stills", times=[0.4, 1.5], wait_s=WAIT)
    summary, images = _images(out)
    assert len(images) == 2, summary
    assert [e["t"] for e in summary["images"]] == [0.4, 1.5]
    assert (summary["width"], summary["height"]) == size
    for entry in summary["stills"]:
        with PILImage.open(entry) as img:
            assert img.size == size
    # the work folder is gone after a successful job
    assert not list((project.project_dir("t") / ".work").glob("render-*"))


@needs_engine
def test_stills_with_compare_are_side_by_side(tmp_path: Path) -> None:
    ref = _reference_video(tmp_path / "ref.mp4")
    out = render.render_video(
        _plan(), "t", mode="stills", times=[0.5, 1.5],
        compare={"video": str(ref), "times": [1.0, 3.0]}, wait_s=WAIT,
    )
    summary, images = _images(out)
    assert len(images) == 2 and all(e["reference_t"] in (1.0, 3.0) for e in summary["images"])
    with PILImage.open(summary["images"][0]["path"]) as img:
        assert img.width > img.height * 0.9  # two portrait panels next to each other


@needs_engine
def test_final_render_of_three_seconds_passes_qa() -> None:
    _tone(project.project_dir("t") / "audio" / "tone.wav", 3.0)
    plan = _plan(audio={"voice": {"src": "audio/tone.wav"}})
    out = render.render_video(plan, "t", mode="final", name="clip", wait_s=WAIT)
    assert isinstance(out, dict) and "output" in out, out
    video = Path(out["output"])
    assert video.name == "clip-final-9x16.mp4" and video.parent.name == "renders"
    assert (out["output_width"], out["output_height"]) == (1080, 1920)
    assert abs(out["output_duration"] - 3.0) < 0.2
    assert (project.project_dir("t") / "plan.json").is_file()
    report = qa.verify_video(video)
    assert report["passed"], (report["hard_failures"], report["checks"])
    assert probe(video)["format"]["tags"]["comment"].startswith("Made with ARGUS Studio")


@needs_engine
def test_preview_is_half_size() -> None:
    out = render.render_video(_plan(duration=1), "t", mode="preview", wait_s=WAIT)
    assert isinstance(out, dict) and "output" in out, out
    assert (out["output_width"], out["output_height"]) == (540, 960)
    assert out["output"].endswith("video-preview-9x16.mp4")

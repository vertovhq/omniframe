"""Clips track: media prep (proxies), request checks, engine props, and engine renders.

Offline, on synthetic media made with ffmpeg `lavfi`. Tests marked `needs_engine` start the
real Remotion engine and are skipped when `engine/node_modules` is missing.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs, project  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.ffmpeg import probe, stream_info  # noqa: E402
from omniframe.media_out import Image  # noqa: E402
from omniframe.tools import media_prep, render  # noqa: E402

ENGINE = Path(__file__).resolve().parents[1] / "engine"
needs_engine = pytest.mark.skipif(
    not (ENGINE / "node_modules").is_dir(), reason="engine/node_modules is missing (run npm install in engine/)"
)
WAIT = 300


@pytest.fixture(autouse=True)
def render_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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


def _video_stream(path: Path) -> dict:
    return next(s for s in probe(path)["streams"] if s["codec_type"] == "video")


def _cfr_source(path: Path, seconds: float = 4.0, audio: bool = True) -> Path:
    """Constant-rate H.264, 30 fps, with a tone."""
    args = ["-f", "lavfi", "-i", f"testsrc=size=320x180:rate=30:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}", "-c:a", "aac", "-shortest"]
    _ffmpeg(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(path))
    return path


def _vfr_source(path: Path) -> Path:
    """H.264 with variable timing: 30 fps for 1 s, then 10 fps. Base rate 30, average about 15."""
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=4",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=4",
        "-vf", "setpts='if(lt(N,30),N/30,1+(N-30)/10)/TB'", "-fps_mode", "vfr",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path),
    )
    return path


def _colors_source(path: Path) -> Path:
    """2 s red, 2 s green, 1 s blue, with a tone."""
    parts = ["-f", "lavfi", "-i", "color=c=0xFF0000:s=320x180:r=30:d=2",
             "-f", "lavfi", "-i", "color=c=0x00FF00:s=320x180:r=30:d=2",
             "-f", "lavfi", "-i", "color=c=0x0000FF:s=320x180:r=30:d=1",
             "-f", "lavfi", "-i", "sine=frequency=300:duration=5"]
    _ffmpeg(*parts, "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-c:a", "aac", str(path))
    return path


def _box_source(path: Path, seconds: float = 3.0) -> Path:
    """Black 16:9 picture with a white square in the middle (20% of the width), no audio."""
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c=black:s=640x360:r=30:d={seconds}",
        "-vf", "drawbox=x=iw*0.4:y=ih*0.4:w=iw*0.2:h=ih*0.2:color=white:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(path),
    )
    return path


def _plan(**extra) -> dict:
    return {"version": 2, "format": "16:9", "style": "dark", **extra}


def _prepare(plan, root: Path, **kw):
    args = {"mode": "stills", "times": None, "compare": None, "format": None, "name": "video", **kw}
    return render.prepare_render(plan, root, **args)


# ------------------------------------------------------------------ media prep

def test_vfr_source_gets_a_constant_rate_proxy_in_the_project_cache(root: Path) -> None:
    src = _vfr_source(root / "refs" / "vfr.mp4")
    meta = _video_stream(src)
    assert meta["r_frame_rate"] != meta["avg_frame_rate"]  # the fixture really is variable-rate

    cache = root / "cache" / "proxies"
    media = media_prep.prepare_clip(src, cache, fps=30)
    assert media.proxied and media.path.parent == cache and media.path.suffix == ".mp4"
    assert any("variable frame rate" in r for r in media.reasons)

    proxy = _video_stream(media.path)
    assert proxy["codec_name"] == "h264"
    num, den = proxy["avg_frame_rate"].split("/")
    assert float(num) / float(den) == pytest.approx(30, abs=0.5)
    assert proxy["r_frame_rate"] == "30/1"
    assert stream_info(media.path).has_audio
    assert media.length == pytest.approx(4.0, abs=0.1)  # the length of the source file, not of the proxy


def test_proxy_is_reused_and_rebuilt_when_the_source_or_fps_changes(root: Path) -> None:
    src = _vfr_source(root / "refs" / "vfr.mp4")
    cache = root / "cache" / "proxies"
    first = media_prep.prepare_clip(src, cache, fps=30)
    stamp = first.path.stat().st_mtime_ns
    again = media_prep.prepare_clip(src, cache, fps=30)
    assert again.path == first.path and again.path.stat().st_mtime_ns == stamp  # not converted twice

    other_fps = media_prep.prepare_clip(src, cache, fps=25)
    assert other_fps.path != first.path
    assert float(_video_stream(other_fps.path)["r_frame_rate"].split("/")[0]) == 25

    _vfr_source(src)  # same path, new file: size or modification time differs
    src.touch()
    rebuilt = media_prep.prepare_clip(src, cache, fps=30)
    assert rebuilt.path != first.path
    assert not list(cache.glob("*.part.mp4"))  # no half-written leftovers


def test_constant_rate_h264_is_used_as_it_is(root: Path) -> None:
    src = _cfr_source(root / "refs" / "ok.mp4")
    media = media_prep.prepare_clip(src, root / "cache" / "proxies", fps=30)
    assert not media.proxied and media.path == src and media.reasons == ()
    assert not list((root / "cache" / "proxies").glob("*"))
    assert media.length == pytest.approx(4.0, abs=0.1)


def test_other_codec_gets_a_proxy(root: Path) -> None:
    src = root / "refs" / "mpeg4.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=2", "-c:v", "mpeg4", str(src))
    media = media_prep.prepare_clip(src, root / "cache" / "proxies", fps=30)
    assert media.proxied and any("mpeg4" in r for r in media.reasons)
    assert _video_stream(media.path)["codec_name"] == "h264"


def test_clean_audio_makes_a_proxy_that_keeps_the_picture(root: Path) -> None:
    src = _cfr_source(root / "refs" / "talk.mp4")
    cache = root / "cache" / "proxies"
    plain = media_prep.prepare_clip(src, cache, fps=30, clean_audio=False)
    cleaned = media_prep.prepare_clip(src, cache, fps=30, clean_audio=True)
    assert not plain.proxied
    assert cleaned.proxied and cleaned.reasons == ("clean_audio",)
    assert _video_stream(cleaned.path)["codec_name"] == "h264"
    assert stream_info(cleaned.path).has_audio

    # a source without sound has nothing to clean
    silent = _cfr_source(root / "refs" / "silent.mp4", audio=False)
    assert not media_prep.prepare_clip(silent, cache, fps=30, clean_audio=True).proxied


def test_images_need_no_prep(root: Path) -> None:
    img = root / "refs" / "pic.png"
    PILImage.new("RGB", (16, 16), "red").save(img)
    media = media_prep.prepare_clip(img, root / "cache" / "proxies", fps=30, clean_audio=True)
    assert not media.proxied and media.length is None


def test_unreadable_file_names_the_clip(root: Path) -> None:
    bad = root / "refs" / "broken.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(RuntimeError, match=r"clips\[0\]\.src: cannot prepare broken\.mp4"):
        media_prep.prepare_clips([(bad, False)], root / "cache" / "proxies", fps=30)


# ------------------------------------------------------------------ request checks and props

def test_clip_ranges_must_lie_inside_the_file(root: Path) -> None:
    src = _cfr_source(root / "refs" / "talk.mp4", 4.0)
    _, errors = _prepare(_plan(clips=[{"src": str(src), "at": 0, "in": 5.0}]), root)
    assert any(e.startswith("clips[0].in:") and "past the end" in e for e in errors), errors
    _, errors = _prepare(_plan(clips=[{"src": str(src), "at": 0, "in": 1.0, "out": 9.0}]), root)
    assert any(e.startswith("clips[0].out:") and "past the end" in e for e in errors), errors
    payload, errors = _prepare(_plan(clips=[{"src": str(src), "at": 0, "in": 1.0, "out": 4.0}]), root)
    assert errors == [] and payload is not None


def test_duration_follows_a_clip_without_out_and_nothing_says_clips_are_not_drawn(root: Path) -> None:
    src = _cfr_source(root / "refs" / "talk.mp4", 4.0)
    payload, errors = _prepare(_plan(clips=[{"src": str(src), "at": 1.0, "in": 1.5}]), root)
    assert errors == [], errors
    assert payload["plan"]["duration"] == pytest.approx(1.0 + 2.5 + 0.3, abs=0.15)
    assert not any("clips" in w for w in payload["warnings"])


def test_an_image_clip_needs_no_probe_and_shows_until_the_end(root: Path) -> None:
    img = root / "refs" / "pic.png"
    PILImage.new("RGB", (16, 16), "red").save(img)
    plan = _plan(duration=4, clips=[{"src": str(img), "at": 1.0}])
    payload, errors = _prepare(plan, root)
    assert errors == [] and payload["plan"]["duration"] == 4


def test_engine_props_use_the_proxy_and_give_open_clips_a_length(root: Path) -> None:
    src = _vfr_source(root / "refs" / "vfr.mp4")
    plan = _plan(clips=[{"src": str(src), "at": 0, "in": 1.0}, {"src": str(src), "at": 5, "in": 0.5, "out": 1.5}])
    payload, errors = _prepare(plan, root)
    assert errors == [], errors
    resolved = render.Plan.model_validate(payload["plan"])
    bases = [Path(b) for b in payload["bases"]]
    media = render._prepare_clip_media(resolved, bases, root, with_audio=True, report=lambda *a, **k: None)
    assert all(m.proxied for m in media) and media[0].path == media[1].path  # one proxy for both clips

    public = render._PublicDir(root / ".work" / "pub", bases)
    props = render._engine_props(payload["plan"], None, public, with_audio=True, clip_media=media)
    first, second = props["clips"]
    assert first["src"] == second["src"] and first["src"].startswith("m/")
    assert (public.root / first["src"]).is_file()
    assert first["length"] == pytest.approx(3.0, abs=0.1) and "length" not in second  # `out` already says it
    assert first["in"] == 1.0  # the proxy keeps the timeline of the source


def test_stills_do_not_clean_audio(root: Path) -> None:
    src = _cfr_source(root / "refs" / "talk.mp4")
    plan = _plan(duration=3, clips=[{"src": str(src), "at": 0, "clean_audio": True}])
    payload, _ = _prepare(plan, root)
    resolved = render.Plan.model_validate(payload["plan"])
    bases = [Path(b) for b in payload["bases"]]
    quiet = render._prepare_clip_media(resolved, bases, root, with_audio=False, report=lambda *a, **k: None)
    assert not quiet[0].proxied
    loud = render._prepare_clip_media(resolved, bases, root, with_audio=True, report=lambda *a, **k: None)
    assert loud[0].reasons == ("clean_audio",)


# ------------------------------------------------------------------ engine

def _images(out) -> tuple[dict, list[Image]]:
    assert isinstance(out, list), out
    import json

    return json.loads(out[0]), [x for x in out[1:] if isinstance(x, Image)]


def _still(path: str) -> np.ndarray:
    with PILImage.open(path) as img:
        return np.asarray(img.convert("RGB")).astype(int)


@needs_engine
def test_clip_with_in_and_out_renders_the_right_part_and_duration(root: Path) -> None:
    src = _colors_source(root / "refs" / "colors.mp4")
    # green is 2.0-4.0 s in the source; take 2.5-3.5 and put it at 0.5-1.5 on the timeline
    plan = _plan(clips=[{"src": str(src), "at": 0.5, "in": 2.5, "out": 3.5}])

    out = render.render_video(plan, "t", mode="final", name="cut", wait_s=WAIT)
    assert isinstance(out, dict) and "output" in out, out
    assert out["duration"] == pytest.approx(1.5 + 0.3, abs=0.05)  # clip end (1.5 s) plus the tail
    assert out["output_duration"] == pytest.approx(out["duration"], abs=0.25)
    assert out["has_audio"]  # the clip's own sound plays

    out = render.render_video(plan, "t", mode="stills", times=[0.2, 1.0, 1.8], wait_s=WAIT)
    summary, images = _images(out)
    assert len(images) == 1 and len(summary["images"][0]["cells"]) == 3  # one contact sheet
    before, inside, after = (_still(e) for e in summary["stills"])
    cx, cy = before.shape[1] // 2, before.shape[0] // 2
    assert before[cy, cx].max() < 60  # before `at`: only the dark background
    r, g, b = inside[cy, cx]
    assert g > 200 and r < 60 and b < 60  # inside: the green part of the source, not red or blue
    assert after[cy, cx].max() < 60  # after the clip: background again


@needs_engine
def test_clip_without_out_plays_to_the_end_of_the_file(root: Path) -> None:
    src = _colors_source(root / "refs" / "colors.mp4")
    plan = _plan(clips=[{"src": str(src), "at": 0, "in": 3.0}])  # the last 2 s: 1 s green, 1 s blue
    out = render.render_video(plan, "t", mode="stills", times=[0.5, 1.5, 2.3], wait_s=WAIT)
    summary, _ = _images(out)
    assert summary["duration"] == pytest.approx(2.3, abs=0.1)  # the 2.0 s clip plus TAIL_S 0.3
    a, b, c = (_still(e) for e in summary["stills"])
    cy, cx = a.shape[0] // 2, a.shape[1] // 2
    assert a[cy, cx][1] > 200 and b[cy, cx][2] > 200
    assert c[cy, cx].max() < 60  # past the end of the file: background (the tail)


def _white_box_width(frame: np.ndarray) -> int:
    """Width in pixels of the white square in the middle row."""
    row = frame[frame.shape[0] // 2]
    white = np.where(row.min(axis=1) > 200)[0]
    assert white.size, "no white pixels in the middle row"
    return int(white.max() - white.min() + 1)


@needs_engine
def test_zoom_keyframes_are_visible_in_stills(root: Path) -> None:
    src = _box_source(root / "refs" / "box.mp4", 3.0)
    plan = _plan(clips=[{
        "src": str(src), "at": 0, "out": 3.0, "fit": "cover",
        "zoom": [{"t": 0, "scale": 1.0}, {"t": 2.0, "scale": 2.0, "x": 0.5, "y": 0.5}],
    }])
    out = render.render_video(plan, "t", mode="stills", times=[0.05, 1.0, 2.5], wait_s=WAIT)
    summary, images = _images(out)
    assert len(images) == 1 and len(summary["images"][0]["cells"]) == 3  # one contact sheet
    start, middle, held = (_white_box_width(_still(e)) for e in summary["stills"])
    full = 1920 * 0.2  # the square is 20% of the frame width at scale 1
    assert start == pytest.approx(full, rel=0.06)
    assert middle == pytest.approx(full * 1.5, rel=0.06)  # half way, eased: scale 1.5
    assert held == pytest.approx(full * 2.0, rel=0.06)  # after the last key the zoom holds


@needs_engine
def test_zoom_around_a_focus_point_keeps_that_point_in_place(root: Path) -> None:
    src = _box_source(root / "refs" / "box.mp4", 2.0)
    plan = _plan(clips=[{
        "src": str(src), "at": 0, "out": 2.0,
        "zoom": [{"t": 0, "scale": 2.0, "x": 0.4, "y": 0.4, "ease": "linear"}],
    }])
    out = render.render_video(plan, "t", mode="stills", times=[0.5], wait_s=WAIT)
    summary, _ = _images(out)
    frame = _still(summary["stills"][0])
    white = np.argwhere(frame.min(axis=2) > 200)
    top, left = white.min(axis=0)
    # the square starts at 40% of the frame; zoomed around (0.4, 0.4) its corner does not move
    assert left == pytest.approx(0.4 * 1920, abs=12) and top == pytest.approx(0.4 * 1080, abs=12)


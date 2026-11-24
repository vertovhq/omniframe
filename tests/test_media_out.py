"""Images for the model: downscaling and the `[summary, Image, ...]` result shape."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe.media_out import Image, prepare_image, tool_result  # noqa: E402


def _png(path: Path, size: tuple[int, int], mode: str = "RGB") -> Path:
    PILImage.new(mode, size, (200, 30, 30, 255) if mode == "RGBA" else (200, 30, 30)).save(path)
    return path


def test_prepare_image_downscales_to_jpeg_next_to_source(tmp_path: Path) -> None:
    src = _png(tmp_path / "frame.png", (2000, 1000))
    view = prepare_image(src)
    assert view == (tmp_path / "frame.view.jpg").resolve()
    with PILImage.open(view) as img:
        assert img.format == "JPEG"
        assert img.size == (1024, 512)
    with PILImage.open(src) as original:
        assert original.size == (2000, 1000)  # the source is untouched


def test_prepare_image_portrait_uses_height_as_longest_side(tmp_path: Path) -> None:
    view = prepare_image(_png(tmp_path / "p.png", (1080, 1920)), max_side=640)
    with PILImage.open(view) as img:
        assert img.size == (360, 640)


def test_prepare_image_does_not_upscale_and_drops_alpha(tmp_path: Path) -> None:
    view = prepare_image(_png(tmp_path / "small.png", (300, 200), mode="RGBA"))
    with PILImage.open(view) as img:
        assert img.size == (300, 200)
        assert img.mode == "RGB"


def test_prepare_image_reuses_fresh_copy_and_rebuilds_stale_one(tmp_path: Path) -> None:
    src = _png(tmp_path / "f.png", (2000, 1000))
    view = prepare_image(src)
    stamp = view.stat().st_mtime_ns
    assert prepare_image(src) == view
    assert view.stat().st_mtime_ns == stamp  # reused, not rewritten

    # a different size request must not return the cached 1024 px copy
    with PILImage.open(prepare_image(src, max_side=256)) as img:
        assert max(img.size) == 256

    # source newer than the copy -> rebuilt from the new pixels
    _png(src, (1000, 4000))
    later = view.stat().st_mtime + 5
    os.utime(src, (later, later))
    with PILImage.open(prepare_image(src)) as img:
        assert img.size == (256, 1024)


def test_prepare_image_keeps_small_view_file_as_is(tmp_path: Path) -> None:
    view = prepare_image(_png(tmp_path / "x.png", (1500, 900)))
    assert prepare_image(view) == view  # no x.view.view.jpg
    assert not list(tmp_path.glob("*.view.view.jpg"))


def test_prepare_image_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        prepare_image(tmp_path / "nope.png")


def test_tool_result_list_shape(tmp_path: Path) -> None:
    a = _png(tmp_path / "a.png", (2000, 1000))
    b = _png(tmp_path / "b.png", (800, 600))
    out = tool_result({"video": "v.mp4", "images": [{"t": 1.5}, {"t": 7.0}]}, [a, b])

    assert isinstance(out, list) and len(out) == 3
    assert isinstance(out[0], str)
    assert all(isinstance(item, Image) for item in out[1:])

    summary = json.loads(out[0])
    assert summary["video"] == "v.mp4"
    assert summary["engine"].startswith("OmniFrame ")
    assert [e["t"] for e in summary["images"]] == [1.5, 7.0]
    # same order as the Image items, and the paths are the files that were sent
    assert [e["path"] for e in summary["images"]] == [str(img.path) for img in out[1:]]
    assert all(Path(e["path"]).is_file() for e in summary["images"])
    with PILImage.open(out[1].path) as first:
        assert max(first.size) <= 1024


def test_tool_result_without_given_entries_and_content_conversion(tmp_path: Path) -> None:
    a = _png(tmp_path / "a.png", (640, 360))
    summary_in = {"note": "ok"}
    out = tool_result(summary_in, [a])
    assert summary_in == {"note": "ok"}  # input not modified
    assert json.loads(out[0])["images"] == [{"path": str((tmp_path / "a.view.jpg").resolve())}]
    content = out[1].to_image_content()
    assert content.mime_type == "image/jpeg" and content.data

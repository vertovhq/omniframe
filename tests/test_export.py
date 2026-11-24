"""export_package (requirement 13): final folder, covers, post.md, text limits, QA refusal, cleanup.

The masters are synthetic: lavfi pictures and a 440 Hz tone, loudness set the way a final render
sets it, so QA passes them unless a test breaks one on purpose.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs, project, server  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.ffmpeg import stream_info  # noqa: E402
from omniframe.media_out import Image  # noqa: E402
from omniframe.tools import export, qa  # noqa: E402
from omniframe.tools.render import finalize_video  # noqa: E402

MB = 1024 * 1024
PICTURE = {
    "motion": "testsrc=size={size}:rate=30:duration={d}",
    "black": "color=c=black:size={size}:rate=30:duration={d}",
}
TEXTS = {
    "tiktok": {"caption": "Morning walk, four minutes", "hashtags": ["walk", "#morning"]},
    "shorts": {"title": "Morning walk", "description": "Four minutes before work.", "hashtags": ["#shorts"]},
    "youtube": {
        "title": "Morning walk through the city",
        "description": "The full walk, no cuts.",
        "tags": ["walk", "morning walk"],
    },
}


def _ffmpeg(args: list[str]) -> None:
    subprocess.run([CONFIG.ffmpeg, "-hide_banner", "-y", *args], check=True, capture_output=True)


def _master(path: Path, size: str, *, gap: bool = False) -> Path:
    """A 4 s clip that passes QA. With `gap`, 1.5 s of black sits in the middle (a hard failure)."""
    picture = [("motion", 1.25), ("black", 1.5), ("motion", 1.25)] if gap else [("motion", 4.0)]
    args: list[str] = []
    for kind, seconds in picture:
        args += ["-f", "lavfi", "-i", PICTURE[kind].format(size=size, d=seconds)]
    graph = "".join(f"[{i}:v]" for i in range(len(picture)))
    graph += f"concat=n={len(picture)}:v=1:a=0,format=yuv420p[v]"
    tone = len(picture)
    args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=4"]
    raw = path.with_name(f"{path.stem}.raw.mp4")
    _ffmpeg([
        *args, "-filter_complex", graph, "-map", "[v]", "-map", f"{tone}:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(raw),
    ])
    finalize_video(raw, path)
    return path


@pytest.fixture(scope="module")
def masters(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("masters")
    return {
        "9:16": _master(folder / "vertical.mp4", "1080x1920"),
        "16:9": _master(folder / "wide.mp4", "1920x1080"),
    }


@pytest.fixture(scope="module")
def gap_master(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _master(tmp_path_factory.mktemp("gap") / "gap.mp4", "1080x1920", gap=True)


@pytest.fixture
def out_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """OMNIFRAME_OUTPUT_DIR of this test: projects, jobs and QA frames go under tmp_path."""
    output = tmp_path / "out"
    for module in (project, jobs, qa):
        monkeypatch.setattr(module, "CONFIG", dataclasses.replace(module.CONFIG, output_dir=output))
    return output


def _stage(name: str, sources: dict[str, Path]) -> tuple[Path, dict[str, str]]:
    """A project whose renders folder holds each source, named the way `render_video` names them."""
    root = project.project_dir(name)
    videos: dict[str, str] = {}
    for fmt, src in sources.items():
        target = root / "renders" / f"{root.name}-final-{fmt.replace(':', 'x')}.mp4"
        shutil.copy(src, target)
        videos[fmt] = str(target)
    return root, videos


def _top_level_boxes(data: bytes) -> list[str]:
    """Names of the top-level MP4 boxes in file order. `moov` before `mdat` means faststart."""
    boxes: list[str] = []
    pos = 0
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        if size < header:
            break
        boxes.append(kind.decode("latin-1"))
        pos += size
    return boxes


def _quiet(*args: object, **kwargs: object) -> None:
    """Progress callback for calls that do not show progress."""


def test_export_writes_videos_covers_and_post(out_dir: Path, masters: dict[str, Path]) -> None:
    root, videos = _stage("Morning Walk", masters)
    (root / ".work" / "leftover.txt").write_text("scratch", encoding="utf-8")

    result = export.export_package("Morning Walk", videos, TEXTS, cover_times={"16:9": 2.0}, wait_s=300)
    assert isinstance(result, list), result  # [summary json, image, image] when the export is done
    summary, *images = result
    data = json.loads(summary)

    assert data["exported"] is True
    assert data["removed_work"] is True
    assert not (root / ".work").exists()
    assert data["covers"]["16:9"]["t"] == 2.0
    assert 0 < data["covers"]["9:16"]["t"] < 4

    final = root / "final"
    assert sorted(p.name for p in final.iterdir()) == [
        "morning-walk_16x9.mp4",
        "morning-walk_9x16.mp4",
        "morning-walk_cover_16x9.jpg",
        "morning-walk_cover_9x16.jpg",
        "post.md",
    ]
    for fmt, size in (("9:16", (1080, 1920)), ("16:9", (1920, 1080))):
        video = final / f"morning-walk_{fmt.replace(':', 'x')}.mp4"
        info = stream_info(video)
        assert (info.width, info.height) == size
        assert info.has_audio
        boxes = _top_level_boxes(video.read_bytes())
        assert boxes.index("moov") < boxes.index("mdat")

    for name, size in (("morning-walk_cover_9x16.jpg", (1080, 1920)), ("morning-walk_cover_16x9.jpg", (1280, 720))):
        cover = final / name
        with PILImage.open(cover) as picture:
            assert picture.format == "JPEG"
            assert picture.size == size
        assert cover.stat().st_size < 2 * MB

    post = (final / "post.md").read_text(encoding="utf-8")
    assert "## TikTok" in post and "## YouTube Shorts" in post and "## YouTube" in post
    assert "Morning walk, four minutes" in post
    assert "#walk #morning" in post
    assert "Four minutes before work.\n\n#shorts" in post
    assert "Tags: walk, morning walk" in post
    assert "Over the limit" not in post

    assert len(images) == 2 and all(isinstance(item, Image) for item in images)
    assert all(Path(entry["path"]).is_file() for entry in data["images"])


def test_export_refuses_on_a_hard_qa_failure(out_dir: Path, masters: dict[str, Path], gap_master: Path) -> None:
    root, videos = _stage("Gap Test", {"9:16": gap_master, "16:9": masters["16:9"]})
    payload, errors = export.prepare_export(root, videos, TEXTS)
    assert errors == []

    result = export.run_job(payload, report=_quiet)

    assert result["exported"] is False
    assert ("9:16", "black") in [(item["format"], item["check"]) for item in result["hard_failures"]]
    assert not (root / "final" / "gap-test_9x16.mp4").exists()
    assert not (root / "final" / "post.md").exists()
    assert (root / ".work").exists()  # kept: the export did not succeed


def test_text_over_a_limit_is_reported_and_marked(out_dir: Path, masters: dict[str, Path]) -> None:
    root, videos = _stage("Limits", {"9:16": masters["9:16"]})
    texts = {
        "shorts": {"title": "x" * 101, "description": "Short text.", "hashtags": []},
        "youtube": {"title": "Fine", "description": "я" * 2501, "tags": ["morning walk"]},
    }
    payload, errors = export.prepare_export(root, videos, texts)
    assert errors == []

    result = export.run_job(payload, report=_quiet)

    assert result["exported"] is True  # the files are written; the violations are reported
    assert {(item["platform"], item["field"]) for item in result["violations"]} == {
        ("shorts", "title"), ("youtube", "description"),
    }
    post = (root / "final" / "post.md").read_text(encoding="utf-8")
    assert "> Over the limit: title is 101 characters; the limit is 100." in post
    assert "> Over the limit: description is 5002 bytes; the limit is 5000." in post
    assert "Video: none in this export" in post


def test_server_registers_export_package() -> None:
    assert "export_package" in server._registered_tool_names()


def test_invalid_request_starts_no_job(out_dir: Path, masters: dict[str, Path]) -> None:
    _, videos = _stage("Bad Request", masters)

    result = export.export_package(
        "Bad Request",
        {"1:1": videos["9:16"]},
        {"instagram": {}, "youtube": {"title": "", "description": "", "tags": []}},
        cover_times={"4:3": 1.0},
        name="!!!",
    )

    assert result["valid"] is False
    errors = "\n".join(result["errors"])
    for expected in (
        "videos.1:1: unknown format",
        "texts.instagram: unknown platform",
        "texts.youtube.title: required",
        "cover_times.4:3: unknown format",
        "name:",
    ):
        assert expected in errors
    assert not jobs.jobs_root().exists()


def test_cover_time_must_fall_inside_the_video(out_dir: Path, masters: dict[str, Path]) -> None:
    root, videos = _stage("Cover Range", masters)

    payload, errors = export.prepare_export(root, videos, TEXTS, {"9:16": 99.0, "16:9": "soon"})

    assert payload is None
    assert any(e.startswith("cover_times.9:16: 99.0 is outside the video") for e in errors)
    assert any(e.startswith("cover_times.16:9: 'soon' is not a number") for e in errors)


def _yt(*, title: str = "t", description: str = "", tags: tuple[str, ...] = ()) -> dict:
    return {"youtube": {"title": title, "description": description, "tags": list(tags)}}


def test_tiktok_caption_is_counted_in_utf16_units_with_hashtags() -> None:
    fits = {"tiktok": {"caption": "😀" * 1100, "hashtags": []}}  # 1100 characters = 2200 UTF-16 units
    assert export.text_violations(fits) == []

    [over] = export.text_violations({"tiktok": {"caption": "😀" * 1101, "hashtags": []}})
    assert (over["platform"], over["field"], over["length"], over["limit"]) == ("tiktok", "caption", 2202, 2200)

    # the hashtags are pasted after the caption and count too: 2190 + 2 + 9 = 2201
    [with_tags] = export.text_violations({"tiktok": {"caption": "a" * 2190, "hashtags": ["#" + "b" * 8]}})
    assert with_tags["length"] == 2201


def test_youtube_description_is_counted_in_utf8_bytes() -> None:
    assert export.text_violations(_yt(description="я" * 2500)) == []  # 5000 bytes

    [over] = export.text_violations(_yt(description="я" * 2501))
    assert over["length"] == 5002
    assert over["unit"] == "bytes"


def test_youtube_tags_count_commas_and_the_quotation_marks_of_spaced_tags() -> None:
    # 494 + 5 (a tag with a space: three letters and two quotation marks) + 1 comma = 500
    assert export.text_violations(_yt(tags=("a" * 494, "b c"))) == []

    [over] = export.text_violations(_yt(tags=("a" * 495, "b c")))
    assert over["length"] == 501


def test_titles_are_limited_to_100_characters() -> None:
    assert export.text_violations(_yt(title="т" * 100)) == []

    [over] = export.text_violations(_yt(title="т" * 101))
    assert (over["field"], over["length"], over["limit"]) == ("title", 101, 100)


def test_check_texts_strips_adds_hash_and_names_bad_fields() -> None:
    clean, errors = export.check_texts({
        "tiktok": {"caption": "  hi  ", "hashtags": ["ai", "#video", " "]},
        "instagram": {},
        "youtube": {"title": "T", "description": "d", "tags": ["x"], "extra": 1},
    })

    assert clean["tiktok"] == {"caption": "hi", "hashtags": ["#ai", "#video"]}
    assert "texts.instagram: unknown platform (expected tiktok, shorts or youtube)" in errors
    assert "texts.tiktok.hashtags[2]: empty" in errors
    assert "texts.youtube.extra: unknown field (expected title, description, tags)" in errors
    assert len(errors) == 3

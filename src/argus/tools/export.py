"""`export_package`: the finished folder for one video (design §12, requirement 13).

The job (kind `export`, `run_job`):
1. QA on each video (`qa.verify_video`). A hard failure refuses the export: nothing is
   written and the failures come back.
2. `<project>/final/<base>_9x16.mp4` and `<base>_16x9.mp4`: stream copy with the index at
   the front (`+faststart`), no re-encoding.
3. Covers: `<base>_cover_9x16.jpg` (1080x1920) and `<base>_cover_16x9.jpg` (1280x720), JPEG
   under 2 MB. The frame is `cover_times[format]`, else the first evenly spread QA frame that
   is not black.
4. `final/post.md`: the texts per platform. A text over its platform limit is marked under
   its field.
4b. With `save_to_library` (task 20.11: a list, one item per reusable element, saved without asking after
   a final passes QA): each item's components go to the style library with a card and a 512 px poster
   taken from the final. A name that exists makes the next version (`tools/library.py`).
5. `<project>/.work/` is removed. Covers come back as images from small copies in
   `<project>/cache/export/`, so `final/` holds only the deliverables.

Length limits are reported, not enforced. The files are still written, so the text can be
shortened in `post.md` or the export can run again.
"""

from __future__ import annotations

import math
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageStat

from .. import __version__, jobs
from ..ffmpeg import FFmpegError, run_ffmpeg, stream_info, temp_sibling
from ..plan import FORMAT_SIZES
from ..project import project_dir, slugify
from . import library, qa

# Cover sizes. The 9:16 cover is the video's own frame size. The 16:9 cover is a YouTube
# thumbnail: 1280x720, JPG or PNG, under 2 MB. The 2 MB cap is the limit for uploads from the
# phone app; the desktop limit is 50 MB (https://support.google.com/youtube/answer/72431).
COVER_SIZES: dict[str, tuple[int, int]] = {"9:16": (1080, 1920), "16:9": (1280, 720)}
COVER_MAX_BYTES = 2 * 1024 * 1024
JPEG_QUALITIES = (92, 85, 75, 65, 50, 35)
COVER_MIN_BRIGHTNESS = 16.0     # mean grey level (0-255) below which a QA frame counts as black
VIEW_MAX_SIDE = 1024            # the model sees pictures at the default size (requirement 4.2)
VIEW_QUALITY = 85

# Which platforms publish which video: 9:16 for TikTok and Shorts, 16:9 for YouTube.
FORMAT_PLATFORMS: dict[str, tuple[str, ...]] = {"9:16": ("tiktok", "shorts"), "16:9": ("youtube",)}

# Fields per platform. "text" is one string, "hashtags" is a list that gets a leading "#",
# "tags" is a plain list (YouTube tags).
PLATFORM_FIELDS: dict[str, dict[str, str]] = {
    "tiktok": {"caption": "text", "hashtags": "hashtags"},
    "shorts": {"title": "text", "description": "text", "hashtags": "hashtags"},
    "youtube": {"title": "text", "description": "text", "tags": "tags"},
}

# Length limits per platform.field: (limit, how it is measured, what the reader sees).
# Checked on 2026-11-17 against:
# - TikTok caption: "The maximum length is 2200 in UTF-16 runes" (Content Posting API, direct
#   post, post_info.title), https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
#   Hashtags are part of the caption, so the caption is measured together with them.
# - YouTube title: "maximum length of 100 characters" (videos, snippet.title), and Shorts use the
#   same title. https://developers.google.com/youtube/v3/docs/videos
# - YouTube description: "maximum length of 5000 bytes" (videos, snippet.description), same page.
#   Bytes are UTF-8, so one Cyrillic letter counts as two.
# - YouTube tags: "maximum length of 500 characters", counting the commas between tags, and a
#   tag with a space counts two more for the quotation marks (videos, snippet.tags[]), same page.
TEXT_LIMITS: dict[str, tuple[int, str, str]] = {
    "tiktok.caption": (2200, "utf16", "caption with hashtags"),
    "shorts.title": (100, "chars", "title"),
    "shorts.description": (5000, "utf8", "description with hashtags"),
    "youtube.title": (100, "chars", "title"),
    "youtube.description": (5000, "utf8", "description"),
    "youtube.tags": (500, "tags", "tags together"),
}
UNIT_NAMES = {"utf16": "UTF-16 units", "utf8": "bytes", "chars": "characters", "tags": "characters"}


# ------------------------------------------------------------------ texts

def _with_hashtags(text: str, hashtags: list[str]) -> str:
    """The text as it is pasted into a platform: the body, a blank line, then the hashtags."""
    return "\n\n".join(part for part in (text, " ".join(hashtags)) if part)


def check_texts(texts: Any) -> tuple[dict, list[str]]:
    """Check the shape of `texts`, strip the strings and add `#` to hashtags.

    Returns `(clean texts, errors)`. Length limits are not checked here. Every error is a
    `path: message` string; the clean dict is only usable when there are no errors.
    """
    if not isinstance(texts, dict) or not texts:
        return {}, ["texts: give an object with tiktok, shorts and/or youtube"]
    errors = [
        f"texts.{platform}: unknown platform (expected tiktok, shorts or youtube)"
        for platform in texts if platform not in PLATFORM_FIELDS
    ]
    clean: dict[str, dict] = {}
    for platform, fields in PLATFORM_FIELDS.items():
        if platform not in texts:
            continue
        where = f"texts.{platform}"
        block = texts[platform]
        if not isinstance(block, dict):
            errors.append(f"{where}: give an object with {', '.join(fields)}")
            continue
        errors += [f"{where}.{key}: unknown field (expected {', '.join(fields)})"
                   for key in block if key not in fields]
        out: dict[str, Any] = {}
        for key, kind in fields.items():
            path = f"{where}.{key}"
            if key not in block:
                errors.append(f"{path}: required")
            elif kind == "text":
                if not isinstance(block[key], str):
                    errors.append(f"{path}: must be a string")
                    continue
                out[key] = block[key].strip()
                if key == "title" and not out[key]:
                    errors.append(f"{path}: required, the title must not be empty")
            elif not isinstance(block[key], list) or not all(isinstance(item, str) for item in block[key]):
                errors.append(f"{path}: must be a list of strings")
            else:
                words: list[str] = []
                for i, item in enumerate(block[key]):
                    word = item.strip()
                    if kind == "hashtags":
                        word = "#" + word.lstrip("#").strip()
                    if not word.lstrip("#"):
                        errors.append(f"{path}[{i}]: empty")
                    else:
                        words.append(word)
                out[key] = words
        clean[platform] = out
    return clean, errors


def _measure(kind: str, value: Any) -> int:
    if kind == "utf16":
        return len(value.encode("utf-16-le")) // 2
    if kind == "utf8":
        return len(value.encode("utf-8"))
    if kind == "chars":
        return len(value)
    # tags: a comma between two tags, and quotation marks around a tag with a space
    return sum(len(tag) + (2 if " " in tag else 0) for tag in value) + max(len(value) - 1, 0)


def _measured_fields(texts: dict) -> list[tuple[str, Any]]:
    """`(platform.field, value as it is pasted)` for every field that has a limit."""
    fields: list[tuple[str, Any]] = []
    tiktok = texts.get("tiktok")
    if tiktok:
        fields.append(("tiktok.caption", _with_hashtags(tiktok["caption"], tiktok["hashtags"])))
    shorts = texts.get("shorts")
    if shorts:
        fields.append(("shorts.title", shorts["title"]))
        fields.append(("shorts.description", _with_hashtags(shorts["description"], shorts["hashtags"])))
    youtube = texts.get("youtube")
    if youtube:
        fields += [
            ("youtube.title", youtube["title"]),
            ("youtube.description", youtube["description"]),
            ("youtube.tags", youtube["tags"]),
        ]
    return fields


def text_violations(texts: dict) -> list[dict]:
    """Every text over its platform limit, as `{platform, field, length, limit, unit, message}`."""
    found: list[dict] = []
    for key, value in _measured_fields(texts):
        limit, kind, label = TEXT_LIMITS[key]
        length = _measure(kind, value)
        if length > limit:
            platform, field = key.split(".")
            unit = UNIT_NAMES[kind]
            found.append({
                "platform": platform,
                "field": field,
                "length": length,
                "limit": limit,
                "unit": unit,
                "message": f"{label} is {length} {unit}; the limit is {limit}",
            })
    return found


# ------------------------------------------------------------------ request

def _first_line(exc: Exception) -> str:
    lines = str(exc).strip().splitlines()
    return lines[0] if lines else type(exc).__name__


def prepare_export(
    root: Path,
    videos: Any,
    texts: Any,
    cover_times: Any = None,
    name: str | None = None,
    save_to_library: Any = None,
) -> tuple[dict | None, list[str]]:
    """Validate a request. Returns `(job payload, [])` or `(None, errors)`. Writes nothing."""
    errors: list[str] = []
    base = root.name
    if name is not None:
        try:
            base = slugify(name)
        except ValueError as exc:
            errors.append(f"name: {exc}")

    clean_videos: dict[str, str] = {}
    durations: dict[str, float] = {}
    if not isinstance(videos, dict) or not videos:
        errors.append('videos: give {"9:16": path, "16:9": path}, one or both')
    else:
        for fmt, value in videos.items():
            where = f"videos.{fmt}"
            if fmt not in FORMAT_SIZES:
                errors.append(f"{where}: unknown format (expected 9:16 or 16:9)")
            elif not isinstance(value, str) or not value.strip():
                errors.append(f"{where}: the path of the video file")
            elif not Path(value).expanduser().is_file():
                errors.append(f"{where}: file not found: {value}")
            else:
                path = Path(value).expanduser().resolve()
                try:
                    durations[fmt] = stream_info(path).duration
                except FFmpegError as exc:
                    errors.append(f"{where}: cannot read the file ({_first_line(exc)})")
                    continue
                clean_videos[fmt] = str(path)

    clean_texts, text_errors = check_texts(texts)
    errors += text_errors

    clean_cover: dict[str, float] = {}
    if cover_times is not None and not isinstance(cover_times, dict):
        errors.append('cover_times: give {"9:16": seconds, "16:9": seconds}, or leave it out')
    elif cover_times:
        for fmt, value in cover_times.items():
            where = f"cover_times.{fmt}"
            if fmt not in FORMAT_SIZES:
                errors.append(f"{where}: unknown format (expected 9:16 or 16:9)")
            elif fmt not in clean_videos:
                errors.append(f"{where}: no {fmt} video in this export")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"{where}: {value!r} is not a number of seconds")
            elif not 0 <= value < durations[fmt]:
                errors.append(f"{where}: {value} is outside the video (0..{durations[fmt]:.2f} s)")
            else:
                clean_cover[fmt] = float(value)

    clean_library: dict | None = None
    if save_to_library is not None:
        poster_format = _poster_format(clean_videos)
        clean_library, library_errors = library.validate_save(
            save_to_library, root, library.project_library_dir(root), durations.get(poster_format or "")
        )
        errors += library_errors

    if errors:
        return None, errors
    payload = {
        "project": str(root),
        "base": base,
        "videos": clean_videos,
        "texts": clean_texts,
        "cover_times": clean_cover,
    }
    if clean_library is not None:
        payload["library"] = clean_library
    return payload, []


# ------------------------------------------------------------------ worker

def _tag(fmt: str) -> str:
    return fmt.replace(":", "x")


def _poster_format(videos: dict) -> str | None:
    """The video a library poster is taken from: the 9:16 one when there is one, else the first."""
    if "9:16" in videos:
        return "9:16"
    return next(iter(videos), None)


def _strictest_platform(fmt: str, texts: dict) -> str | None:
    """The platform with the shortest duration limit among those whose texts use this format."""
    used = [platform for platform in FORMAT_PLATFORMS[fmt] if platform in texts]
    return min(used, key=lambda platform: qa.PLATFORM_LIMITS[platform][0]) if used else None


def _step(report: Callable[..., None], start: float, end: float, index: int, count: int) -> Callable[..., None]:
    """Progress callback for item `index` of `count`, which takes the share start..end of the job."""
    width = (end - start) / count
    first = start + index * width

    def say(progress: float, note: str | None = None) -> None:
        report(first + width * float(progress), note)

    return say


def _copy_faststart(src: Path, out: Path) -> None:
    """Copy the video and audio streams into `out` without re-encoding, index first."""
    staged = temp_sibling(out, ".export.mp4")
    try:
        run_ffmpeg([
            "-i", str(src), "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-movflags", "+faststart",
            str(staged),
        ])
        os.replace(staged, out)
    finally:
        staged.unlink(missing_ok=True)


def _mean_grey(path: Path) -> float:
    with PILImage.open(path) as img:
        return float(ImageStat.Stat(img.convert("L")).mean[0])


def _default_cover_time(qa_result: dict) -> float:
    """Time of the first evenly spread QA frame that is not black, else of the first one."""
    spread = [image for image in qa_result.get("images", []) if image.get("reason") == "evenly spread"]
    for image in spread:
        if _mean_grey(Path(image["path"])) >= COVER_MIN_BRIGHTNESS:
            return float(image["t"])
    if spread:
        return float(spread[0]["t"])
    return float(qa_result["duration"]) / 2


def _write_cover(src: Path, at: float, size: tuple[int, int], out: Path, scratch: Path) -> None:
    """A JPEG of exactly `size` from the frame at `at` seconds, under COVER_MAX_BYTES."""
    scratch.mkdir(parents=True, exist_ok=True)
    frame = scratch / f"{out.stem}.png"
    frame.unlink(missing_ok=True)
    try:
        run_ffmpeg(["-ss", f"{at:.3f}", "-i", str(src), "-map", "0:v:0", "-frames:v", "1", str(frame)])
        with PILImage.open(frame) as grab:
            picture = grab.convert("RGB")
        if picture.size != size:
            picture = picture.resize(size, PILImage.Resampling.LANCZOS)
        staged = temp_sibling(out, ".jpg")
        try:
            for quality in JPEG_QUALITIES:
                picture.save(staged, format="JPEG", quality=quality, optimize=True)
                if staged.stat().st_size < COVER_MAX_BYTES:
                    break
            os.replace(staged, out)
        finally:
            staged.unlink(missing_ok=True)
    finally:
        frame.unlink(missing_ok=True)


def _write_view(cover: Path, view: Path) -> None:
    """A JPEG copy of the cover for the model, at most VIEW_MAX_SIDE px on the longest side."""
    view.parent.mkdir(parents=True, exist_ok=True)
    with PILImage.open(cover) as img:
        picture = img.convert("RGB")
    picture.thumbnail((VIEW_MAX_SIDE, VIEW_MAX_SIDE), PILImage.Resampling.LANCZOS)
    staged = temp_sibling(view, ".jpg")
    try:
        picture.save(staged, format="JPEG", quality=VIEW_QUALITY, optimize=True)
        os.replace(staged, view)
    finally:
        staged.unlink(missing_ok=True)


def _file_line(label: str, entry: dict | None, fmt: str) -> str:
    if entry is None:
        return f"{label}: none in this export (no {fmt} file was given)"
    return f"{label}: `{Path(entry['path']).name}`"


def _post_markdown(
    base: str,
    videos: dict[str, dict],
    covers: dict[str, dict],
    texts: dict,
    violations: list[dict],
) -> str:
    over = {(item["platform"], item["field"]): item["message"] for item in violations}

    def flag(platform: str, field: str) -> list[str]:
        message = over.get((platform, field))
        return ["", f"> Over the limit: {message}."] if message else []

    lines = [f"# {base}", "", "Files in this folder:", ""]
    for fmt, size in FORMAT_SIZES.items():
        if fmt in videos:
            video = videos[fmt]
            lines.append(f"- `{Path(video['path']).name}`: video {size[0]}x{size[1]}, {video['duration']:.1f} s")
        if fmt in covers:
            lines.append(f"- `{Path(covers[fmt]['path']).name}`: cover {covers[fmt]['size']}")
    if "tiktok" in texts:
        block = texts["tiktok"]
        lines += ["", "## TikTok", "", _file_line("Video", videos.get("9:16"), "9:16"),
                  _file_line("Cover", covers.get("9:16"), "9:16"), "", "Caption:", "", block["caption"]]
        if block["hashtags"]:
            lines += ["", " ".join(block["hashtags"])]
        lines += flag("tiktok", "caption")
    if "shorts" in texts:
        block = texts["shorts"]
        lines += ["", "## YouTube Shorts", "", _file_line("Video", videos.get("9:16"), "9:16"),
                  _file_line("Cover", covers.get("9:16"), "9:16"), "", f"Title: {block['title']}"]
        lines += flag("shorts", "title")
        lines += ["", "Description:", "", _with_hashtags(block["description"], block["hashtags"])]
        lines += flag("shorts", "description")
    if "youtube" in texts:
        block = texts["youtube"]
        lines += ["", "## YouTube", "", _file_line("Video", videos.get("16:9"), "16:9"),
                  _file_line("Thumbnail", covers.get("16:9"), "16:9"), "", f"Title: {block['title']}"]
        lines += flag("youtube", "title")
        lines += ["", "Description:", "", block["description"]]
        lines += flag("youtube", "description")
        lines += ["", f"Tags: {', '.join(block['tags'])}"]
        lines += flag("youtube", "tags")
    return "\n".join(lines) + "\n"


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Worker side of `export_package` (job kind `export`)."""
    root = Path(payload["project"])
    base = str(payload["base"])
    texts: dict = payload["texts"]
    videos = {fmt: Path(path) for fmt, path in payload["videos"].items()}
    cover_times = {fmt: float(at) for fmt, at in payload.get("cover_times", {}).items()}
    final = root / "final"
    fmts = list(videos)

    qa_results: dict[str, dict] = {}
    hard: list[dict] = []
    warnings: list[dict] = []
    for index, fmt in enumerate(fmts):
        result = qa.verify_video(
            videos[fmt],
            format=fmt,
            target=_strictest_platform(fmt, texts),
            frames=qa.DEFAULT_FRAMES,
            report=_step(report, 0.0, 0.5, index, len(fmts)),
        )
        qa_results[fmt] = result
        hard += [{**item, "format": fmt} for item in result["hard_failures"]]
        warnings += [{**item, "format": fmt} for item in result["warnings"]]
    if hard:
        return {
            "exported": False,
            "hard_failures": hard,
            "warnings": warnings,
            "note": "QA found hard failures, so nothing was written to final/. Fix them, then export again.",
        }

    final.mkdir(parents=True, exist_ok=True)
    videos_out: dict[str, dict] = {}
    for index, fmt in enumerate(fmts):
        report(0.5 + 0.1 * index / len(fmts), f"copying the {fmt} video")
        out = final / f"{base}_{_tag(fmt)}.mp4"
        _copy_faststart(videos[fmt], out)
        size = FORMAT_SIZES[fmt]
        videos_out[fmt] = {
            "path": str(out),
            "size": f"{size[0]}x{size[1]}",
            "duration": qa_results[fmt]["duration"],
            "bytes": out.stat().st_size,
        }

    covers_out: dict[str, dict] = {}
    images: list[dict] = []
    for index, fmt in enumerate(fmts):
        report(0.6 + 0.3 * index / len(fmts), f"making the {fmt} cover")
        at = cover_times[fmt] if fmt in cover_times else _default_cover_time(qa_results[fmt])
        size = COVER_SIZES[fmt]
        out = final / f"{base}_cover_{_tag(fmt)}.jpg"
        _write_cover(videos[fmt], at, size, out, root / ".work" / "export")
        view = root / "cache" / "export" / f"{base}_cover_{_tag(fmt)}.view.jpg"
        _write_view(out, view)
        covers_out[fmt] = {
            "path": str(out),
            "t": round(at, 3),
            "size": f"{size[0]}x{size[1]}",
            "bytes": out.stat().st_size,
        }
        images.append({
            "path": str(view),
            "t": round(at, 3),
            "reason": f"{fmt} cover {size[0]}x{size[1]} at {at:.2f} s",
        })

    library_out: dict | None = None
    requests = payload.get("library")
    if requests:
        report(0.92, "saving to the style library")
        fmt = _poster_format(videos)
        assert fmt is not None  # a request has at least one video
        entries: list[dict] = []
        for request in requests:
            at = request["poster_time"] if request.get("poster_time") is not None else covers_out[fmt]["t"]
            try:
                entries.append({"saved": True, **library.save_entry(
                    request, root, library.project_library_dir(root), videos[fmt], float(at))})
            except (OSError, FFmpegError, ValueError) as exc:
                # The export itself worked; say that only this library step failed.
                entries.append({"saved": False, "entry": request["entry"], "error": _first_line(exc)})
        library_out = {"saved": all(e["saved"] for e in entries), "entries": entries}
        first = next((e for e in entries if e["saved"]), None)
        if first is not None:  # one poster picture confirms the saved frame; the others are listed by name
            view = root / "cache" / "export" / f"{base}_library_poster.view.jpg"
            _write_view(Path(first["poster"]), view)
            images.append({"path": str(view), "t": first["poster_t"], "reason": f"library poster of {first['entry']}"})

    report(0.95, "writing post.md")
    violations = text_violations(texts)
    post = final / "post.md"
    post.write_text(_post_markdown(base, videos_out, covers_out, texts, violations), encoding="utf-8")

    from .. import economy  # local import: the reply-size log of every tool call so far

    # The log lives in .work, so the totals are read before .work is removed.
    economy_totals = economy.totals(root.name)
    shutil.rmtree(root / ".work", ignore_errors=True)
    result = {
        "exported": True,
        "final_dir": str(final),
        "post": str(post),
        "videos": videos_out,
        "covers": covers_out,
        "violations": violations,
        "warnings": warnings,
        "removed_work": not (root / ".work").exists(),
        "images": images,
    }
    if library_out is not None:
        result["library"] = library_out
    # What the project's renders cost so far (seconds, from the kept render jobs' `timing`).
    result["render_timing"] = jobs.project_render_totals(root)
    result["economy"] = economy_totals
    return result


# ------------------------------------------------------------------ tool

def export_package(
    project: str,
    videos: Any,
    texts: Any,
    cover_times: Any = None,
    name: str | None = None,
    save_to_library: Any = None,
    wait_s: float = jobs.DEFAULT_WAIT_S,
) -> dict | list:
    """Tool logic of `export_package`: validate, then run the `export` job.

    An invalid request returns `{"valid": false, "errors": [...]}` and starts nothing.
    Jobs with the same final file name never run twice at once.
    """
    root = project_dir(project)
    payload, errors = prepare_export(root, videos, texts, cover_times, name, save_to_library)
    if payload is None:
        return {
            "engine": f"ARGUS {__version__}",
            "valid": False,
            "errors": errors,
            "note": "nothing was exported; fix the listed problems and call again",
        }
    return jobs.run_or_detach("export", payload, key=str(root / "final" / payload["base"]), wait_s=wait_s)

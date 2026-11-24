"""Media prep for the clips track (design §9 step 4).

Remotion cuts video by frame number, so a source it cannot seek exactly gives wrong
frames: phone footage is often variable frame rate (VFR), and the engine's frame
extractor is built around H.264. Such a file is converted once into a proxy,
`<project>/cache/proxies/<hash>.mp4`: constant frame rate at the plan's fps, H.264 `crf 18`,
AAC audio. `clean_audio` also goes through a proxy, with a high-pass and a noise
reduction on the audio.

The proxy covers the whole source file and keeps its timeline, so every clip made from
that file (different `in`/`out`) shares one proxy, and `in`/`out` stay valid. The name is
a hash of the source path, size, modification time, fps and the clean flag, so a changed
source or plan setting makes a new proxy and an unchanged one is reused.

Images need no prep. A source that is already constant-rate H.264 is used as it is.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..ffmpeg import FFmpegError, probe, run_ffmpeg, temp_sibling

IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
PROXY_CRF = 18
PROXY_AUDIO_BITRATE = "192k"
PROXY_AUDIO_RATE = "48000"
CLEAN_AUDIO_CHAIN = "highpass=f=80,afftdn"   # design §9 step 4
CFR_TOLERANCE = 0.005                        # r_frame_rate vs avg_frame_rate, relative
PROXY_VERSION = "1"                          # bump when the proxy recipe changes


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


@dataclass(frozen=True)
class ClipMedia:
    """The file the engine plays for one clip."""

    path: Path                                          # the source, or its proxy
    source: Path
    reasons: tuple[str, ...] = field(default_factory=tuple)  # why a proxy was made; empty = none
    length: float | None = None                         # seconds of the source file (None for images)

    @property
    def proxied(self) -> bool:
        return self.path != self.source


def _rate(value: str | None) -> float | None:
    """`"30000/1001"` -> 29.97; None when missing or `0/0`."""
    if not value:
        return None
    try:
        num, _, den = value.partition("/")
        n, d = float(num), float(den or 1)
    except ValueError:
        return None
    return n / d if d else None


def proxy_reasons(meta: dict, *, clean_audio: bool) -> list[str]:
    """Why this file needs a proxy; an empty list means the file can be used as it is.

    `meta` is the ffprobe JSON of the file (`ffmpeg.probe`).
    """
    streams = meta.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    if video is None:
        return []
    reasons: list[str] = []
    codec = video.get("codec_name")
    if codec != "h264":
        reasons.append(f"codec {codec or 'unknown'} is not H.264")
    r, avg = _rate(video.get("r_frame_rate")), _rate(video.get("avg_frame_rate"))
    if r and avg and abs(r - avg) / r > CFR_TOLERANCE:
        reasons.append(f"variable frame rate ({avg:.2f} fps average, {r:.2f} fps base)")
    if clean_audio and has_audio:
        reasons.append("clean_audio")
    return reasons


def proxy_path(source: Path, cache_dir: Path, *, fps: int, clean_audio: bool) -> Path:
    """Where the proxy of `source` lives for these settings."""
    stat = source.stat()
    key = f"{PROXY_VERSION}|{source}|{stat.st_size}|{stat.st_mtime_ns}|{fps}|{int(clean_audio)}"
    return cache_dir / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}.mp4"


def make_proxy(source: Path, dst: Path, *, fps: int, clean_audio: bool, copy_video: bool = False) -> None:
    """Write the proxy of `source` to `dst` (atomically: a half-written file is never left there).

    `copy_video` keeps the video stream as it is (used when only the audio needs work).
    """
    meta = probe(source)
    has_audio = any(s.get("codec_type") == "audio" for s in meta.get("streams", []))
    args = ["-i", str(source), "-map", "0:v:0"]
    if has_audio:
        args += ["-map", "0:a:0"]
    if copy_video:
        args += ["-c:v", "copy"]
    else:
        args += ["-c:v", "libx264", "-crf", str(PROXY_CRF), "-preset", "fast", "-pix_fmt", "yuv420p",
                 "-r", str(fps), "-fps_mode", "cfr"]
    if has_audio:
        if clean_audio:
            args += ["-af", CLEAN_AUDIO_CHAIN]
        args += ["-c:a", "aac", "-b:a", PROXY_AUDIO_BITRATE, "-ar", PROXY_AUDIO_RATE]
    args += ["-movflags", "+faststart"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    staged = temp_sibling(dst, ".part.mp4")
    try:
        run_ffmpeg([*args, str(staged)])
        os.replace(staged, dst)
    finally:
        staged.unlink(missing_ok=True)


def prepare_clip(
    source: Path,
    cache_dir: Path,
    *,
    fps: int,
    clean_audio: bool = False,
) -> ClipMedia:
    """The file to play for a clip made from `source`; builds (or reuses) a proxy when needed.

    Raises `FFmpegError` when the file cannot be read or converted.
    """
    if is_image(source):
        return ClipMedia(path=source, source=source)
    meta = probe(source)
    length = float(meta.get("format", {}).get("duration") or 0.0) or None
    reasons = proxy_reasons(meta, clean_audio=clean_audio)
    if not reasons:
        return ClipMedia(path=source, source=source, length=length)
    dst = proxy_path(source, cache_dir, fps=fps, clean_audio=clean_audio)
    if not dst.is_file() or dst.stat().st_size == 0:
        # Only the audio needs work: keep the picture untouched (no second encode).
        only_audio = reasons == ["clean_audio"]
        make_proxy(source, dst, fps=fps, clean_audio=clean_audio, copy_video=only_audio)
    return ClipMedia(path=dst, source=source, reasons=tuple(reasons), length=length)


def prepare_clips(
    sources: list[tuple[Path, bool]],
    cache_dir: Path,
    *,
    fps: int,
    report: Callable[[str], None] | None = None,
) -> list[ClipMedia]:
    """`prepare_clip` for `[(source, clean_audio), ...]`, in order.

    `report(note)` is called before each file that is converted, so the job status can
    say what takes the time.
    """
    out: list[ClipMedia] = []
    for index, (source, clean_audio) in enumerate(sources):
        if report is not None and not is_image(source):
            report(f"preparing clip {index + 1} of {len(sources)}")
        try:
            out.append(prepare_clip(source, cache_dir, fps=fps, clean_audio=clean_audio))
        except FFmpegError as exc:
            first = str(exc).splitlines()[0] if str(exc) else "ffmpeg failed"
            raise RuntimeError(f"clips[{index}].src: cannot prepare {source.name} ({first})") from exc
    return out

"""Thin, reliable wrappers around ffmpeg / ffprobe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import CONFIG


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe invocation fails."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        proc = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError as exc:
        raise FFmpegError(
            f"'{cmd[0]}' not found. Install ffmpeg (https://ffmpeg.org) "
            "or set ARGUS_FFMPEG/ARGUS_FFPROBE in .env."
        ) from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
        raise FFmpegError(f"{cmd[0]} failed (exit {proc.returncode}):\n" + "\n".join(tail))
    return proc


def run_ffmpeg(args: list[str]) -> None:
    """Run `ffmpeg <args>` (input/output args without the binary name)."""
    _run([CONFIG.ffmpeg, "-hide_banner", "-y", *args])


def probe(path: str | Path) -> dict:
    """Return ffprobe JSON metadata for a media file."""
    proc = _run([
        CONFIG.ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ])
    return json.loads(proc.stdout.decode("utf-8", "replace"))


@dataclass(frozen=True)
class StreamInfo:
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    pix_fmt: str | None
    field_order: str | None
    has_video: bool
    has_audio: bool


def stream_info(path: str | Path) -> StreamInfo:
    """Summarize the first video/audio streams of a file."""
    meta = probe(path)
    videos = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in meta.get("streams", []) if s.get("codec_type") == "audio"]
    v = videos[0] if videos else {}
    fps = None
    num, den = (v.get("r_frame_rate") or "0/0").split("/")
    if float(den):
        fps = round(float(num) / float(den), 3)
    duration = float(meta.get("format", {}).get("duration") or v.get("duration") or 0.0)
    return StreamInfo(
        duration=duration,
        width=v.get("width"),
        height=v.get("height"),
        fps=fps,
        pix_fmt=v.get("pix_fmt"),
        field_order=v.get("field_order"),
        has_video=bool(videos),
        has_audio=bool(audios),
    )


def measure_loudness(path: str | Path) -> dict:
    """Measure integrated loudness (LUFS) via the loudnorm filter."""
    proc = _run([
        CONFIG.ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i", str(path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ])
    stderr = proc.stderr.decode("utf-8", "replace")
    # loudnorm prints its JSON report as the last {...} block on stderr.
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1:
        raise FFmpegError("loudnorm produced no JSON report")
    report = json.loads(stderr[start:end + 1])
    return {
        "input_i": float(report["input_i"]) if report.get("input_i") else None,
        "input_tp": float(report["input_tp"]) if report.get("input_tp") else None,
        "input_lra": float(report["input_lra"]) if report.get("input_lra") else None,
    }


def detect_pauses(
    path: str | Path,
    noise_db: float = -35.0,
    min_silence: float = 0.18,
) -> list[tuple[float, float]]:
    """Find speech pauses: returns [(silence_start, silence_end), ...]."""
    proc = _run([
        CONFIG.ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i", str(path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ])
    stderr = proc.stderr.decode("utf-8", "replace")
    starts: list[float] = []
    ends: list[float] = []
    for line in stderr.splitlines():
        line = line.strip()
        if "silence_start:" in line:
            starts.append(float(line.rsplit(":", 1)[1].strip().rstrip("|")))
        elif "silence_end:" in line:
            ends.append(float(line.split("silence_end:")[1].split("|")[0].strip()))
    return list(zip(starts, ends))


def escape_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter argument."""
    text = str(path).replace("\\", "/").replace(":", "\\:")
    return text.replace("'", r"\'")


def temp_sibling(target: str | Path, suffix: str) -> Path:
    """A temp file next to `target` (same filesystem => atomic rename later)."""
    fd, name = tempfile.mkstemp(suffix=suffix, dir=Path(target).parent)
    os.close(fd)  # close the handle or Windows will lock the file against ffmpeg
    return Path(name)


def tool_available(name: str) -> bool:
    return bool(shutil.which(name))

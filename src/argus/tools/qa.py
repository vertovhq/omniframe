"""Technical QA for finished videos (design §11, requirement 12).

`qa_verify_video` checks what a machine can measure and never judges the creative work:
frame size for the format, frame rate, scan type, audio presence, integrated loudness and
true peak (EBU R128 through ffmpeg `loudnorm`), the length difference between the tracks,
black gaps, a frozen picture, long silences, and the duration against one platform's limit
when `target` is given. Each problem carries timecodes in seconds. Hard failures make
`passed` false; warnings do not. The result also has images: evenly spread frames, plus one
frame for each black gap or frozen picture.

The analysis runs as a `qa` job (`jobs.run_or_detach`), because decoding a long video can
take longer than a tool call may wait.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import __version__, jobs
from ..config import CONFIG
from ..ffmpeg import FFmpegError, detect_pauses, measure_loudness, probe, run_ffmpeg, run_ffmpeg_stderr, stream_info
from ..plan import FORMAT_SIZES

# --- thresholds (design §11) ---
ACCEPTED_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)
LUFS_TOLERANCE = 1.5           # LU either side of CONFIG.loudness_target
TRUE_PEAK_MAX_DB = -1.0        # dBTP
TRACK_LENGTH_TOLERANCE_S = 0.5
BLACK_MIN_S = 0.5              # shorter black is not reported (blackdetect d)
BLACK_HARD_S = 1.0             # black this long in the middle of the video is a hard failure
# blackdetect pix_th: a pixel is black at or below 0.03 * 255 (about 8 of 255). At 0.10 (about 25)
# the `dark` style background (#0A0A12, lifted to about 13-25 by glow and grain) counted as black,
# so a caption on it made a 1.5 s "black gap" in every dark video (task 13).
BLACK_PIXEL_THRESHOLD = 0.03
FREEZE_MIN_S = 3.0             # freezedetect d
FREEZE_NOISE_DB = -60.0        # freezedetect n
SILENCE_MIN_S = 2.0            # silencedetect d; only silences in the middle count
SILENCE_NOISE_DB = -45.0       # silencedetect n
EDGE_TOLERANCE_S = 0.1         # a gap this close to the start or the end is "at the edge"
INTERLACED_ORDERS = ("tt", "bb", "tb", "bt")  # ffprobe field_order values of interlaced video

# Platform duration limits, used for warnings only. Checked 2026-11-17:
# - shorts: YouTube Shorts up to 3 minutes, https://support.google.com/youtube/answer/15424877
# - youtube: 15 minutes by default, 12 hours with a verified account,
#   https://support.google.com/youtube/answer/71673
# - tiktok: TikTok's own support pages could not be read. Third-party guides give 10 minutes
#   for most accounts and up to 60 minutes for uploads from TikTok Studio on the web. The
#   lower figure is used. Re-check https://support.tiktok.com before changing it.
PLATFORM_LIMITS: dict[str, tuple[float, str]] = {
    "tiktok": (600.0, "10 minutes for most accounts"),
    "shorts": (180.0, "3 minutes"),
    "youtube": (900.0, "15 minutes (12 hours with a verified account)"),
}

# A preview from render_video (mode "preview") is named `<name>-preview-<format>.mp4`. It is half
# size and not mastered, so these checks report as warnings on it (Known issue 32).
PREVIEW_MARK = "-preview-"
PREVIEW_SOFT_CHECKS = frozenset({"resolution", "loudness", "true_peak"})
PREVIEW_NOTE = (
    "this file is a preview (half size, not mastered): size, loudness and true peak are "
    "warnings here; the other checks still fail the file"
)

DEFAULT_FRAMES = 4
MAX_IMAGES = 8                 # evenly spread frames and issue frames together

_BLACK_RE = re.compile(r"black_start:\s*([-+0-9.eE]+)\s+black_end:\s*([-+0-9.eE]+)")
_FREEZE_RE = re.compile(r"freeze_(start|end):\s*([-+0-9.eE]+)")


# ------------------------------------------------------------------ results

@dataclass(frozen=True)
class _Finding:
    """A problem a check found. Times are seconds on the video's timeline."""

    check: str
    severity: str                   # "hard" fails the video, "warning" does not
    message: str
    start: float | None = None
    end: float | None = None
    picture_t: float | None = None  # a frame at this time shows the problem (black and freeze)

    def entry(self) -> dict:
        out: dict = {"check": self.check, "message": self.message}
        if self.start is not None:
            out["start"] = round(self.start, 3)
        if self.end is not None:
            out["end"] = round(self.end, 3)
        return out


class _Checks:
    """Check results by name, and the findings behind the failed ones."""

    def __init__(self, soft: frozenset[str] = frozenset()) -> None:
        self.results: dict[str, dict] = {}
        self.findings: list[_Finding] = []
        self.soft = soft  # check names whose failures are warnings for this file (previews)

    def result(self, name: str, passed: bool, measured: object, expected: str) -> None:
        self.results[name] = {"passed": bool(passed), "measured": measured, "expected": expected}

    def expect(
        self,
        name: str,
        passed: bool,
        measured: object,
        expected: str,
        message: str,
        severity: str = "hard",
    ) -> None:
        """A check with one value. A failure adds one finding."""
        self.result(name, passed, measured, expected)
        if not passed:
            level = "warning" if name in self.soft else severity
            self.findings.append(_Finding(name, level, message))

    def detection(self, name: str, found: list[_Finding], expected: str) -> None:
        """A check that can find several problems (black, freeze, silence)."""
        self.result(name, not found, len(found), expected)
        self.findings.extend(found)


# ------------------------------------------------------------------ helpers

def _no_progress(progress: float, note: str) -> None:
    """Progress callback for callers that do not show progress."""


def _check_format(value: str | None) -> str | None:
    if value is None or value in FORMAT_SIZES:
        return value
    raise ValueError(f"format must be one of {', '.join(FORMAT_SIZES)}, got {value!r}")


def _check_target(value: str | None) -> str | None:
    if value is None or value in PLATFORM_LIMITS:
        return value
    raise ValueError(f"target must be one of {', '.join(PLATFORM_LIMITS)}, got {value!r}")


def _check_frames(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_IMAGES:
        raise ValueError(f"frames must be a whole number from 0 to {MAX_IMAGES}, got {value!r}")
    return value


def _format_of(width: int | None, height: int | None) -> str | None:
    """"9:16" or "16:9" when the frame has exactly that shape (at any size), else None."""
    if not width or not height:
        return None
    if 16 * width == 9 * height:
        return "9:16"
    if 9 * width == 16 * height:
        return "16:9"
    return None


def _last_line(exc: Exception) -> str:
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    return lines[-1] if lines else type(exc).__name__


def _finite(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _track_seconds(streams: list[dict], kind: str) -> float | None:
    for stream in streams:
        if stream.get("codec_type") == kind:
            value = stream.get("duration")
            return float(value) if value else None
    return None


# ------------------------------------------------------------------ checks

def _check_frame_size(checks: _Checks, width: int | None, height: int | None, fmt: str | None) -> None:
    measured = f"{width}x{height}"
    if fmt is None:
        expected = " or ".join(f"{w}x{h} ({name})" for name, (w, h) in FORMAT_SIZES.items())
        checks.expect("resolution", False, measured, expected,
                      f"frame is {measured}, which is neither 9:16 nor 16:9")
        return
    want_w, want_h = FORMAT_SIZES[fmt]
    expected = f"{want_w}x{want_h} ({fmt})"
    checks.expect("resolution", (width, height) == (want_w, want_h), measured, expected,
                  f"frame is {measured}, expected {expected}")


def _check_frame_rate_and_scan(checks: _Checks, fps: float | None, field_order: str | None) -> None:
    expected_fps = ", ".join(f"{rate:g}" for rate in ACCEPTED_FPS)
    checks.expect("fps", fps in ACCEPTED_FPS, fps, f"one of {expected_fps}",
                  f"frame rate is {fps} fps, expected one of {expected_fps}")
    interlaced = field_order in INTERLACED_ORDERS
    checks.expect("scan", not interlaced, field_order or "not reported", "progressive",
                  f"video is interlaced (field order {field_order})")


def _check_loudness(checks: _Checks, src: Path) -> None:
    target = CONFIG.loudness_target
    expected = f"{target:g} ±{LUFS_TOLERANCE:g} LUFS"
    error: str | None = None
    try:
        levels = measure_loudness(src)
    except FFmpegError as exc:
        levels, error = {}, f"the audio could not be measured: {_last_line(exc)}"
    lufs = _finite(levels.get("input_i"))
    if error:
        lufs_message = error
    elif lufs is None:
        lufs_message = f"no integrated loudness value (is the audio silent?), expected {expected}"
    else:
        lufs_message = f"integrated loudness is {lufs:.1f} LUFS, expected {expected}"
    checks.expect("loudness", lufs is not None and abs(lufs - target) <= LUFS_TOLERANCE,
                  None if lufs is None else round(lufs, 1), expected, lufs_message)

    peak = _finite(levels.get("input_tp"))
    expected_peak = f"at most {TRUE_PEAK_MAX_DB:g} dBTP"
    if error:
        peak_message = error
    elif peak is None:
        peak_message = f"no true peak value (is the audio silent?), expected {expected_peak}"
    else:
        peak_message = f"true peak is {peak:.2f} dBTP, expected {expected_peak}"
    checks.expect("true_peak", peak is not None and peak <= TRUE_PEAK_MAX_DB,
                  None if peak is None else round(peak, 2), expected_peak, peak_message)


def _check_track_lengths(checks: _Checks, info, streams: list[dict]) -> None:
    # A track without a duration of its own is measured by the container duration.
    video = _track_seconds(streams, "video") or info.duration
    audio = _track_seconds(streams, "audio") or info.duration
    gap = abs(video - audio)
    checks.expect(
        "stream_lengths", gap <= TRACK_LENGTH_TOLERANCE_S,
        f"video {video:.2f} s, audio {audio:.2f} s",
        f"within {TRACK_LENGTH_TOLERANCE_S:g} s of each other",
        f"video and audio differ by {gap:.2f} s",
    )


def _check_silences(checks: _Checks, src: Path, duration: float) -> None:
    expected = f"no silence of {SILENCE_MIN_S:g} s or more in the middle of the video"
    try:
        pauses = detect_pauses(src, noise_db=SILENCE_NOISE_DB, min_silence=SILENCE_MIN_S)
    except FFmpegError as exc:
        checks.expect("silence", False, None, expected, f"the audio could not be scanned: {_last_line(exc)}")
        return
    found = [
        _Finding("silence", "warning",
                 f"silence of {end - start:.2f} s in the middle of the video ({start:.2f}-{end:.2f} s)",
                 start, end)
        for start, end in pauses
        if start > EDGE_TOLERANCE_S and end < duration - EDGE_TOLERANCE_S
    ]
    checks.detection("silence", found, expected)


def _black_finding(start: float, end: float, duration: float) -> _Finding | None:
    length = end - start
    if length < BLACK_MIN_S:
        return None
    span = f"{start:.2f}-{end:.2f} s"
    if start <= EDGE_TOLERANCE_S or end >= duration - EDGE_TOLERANCE_S:
        message, severity = f"black for {length:.2f} s at the edge of the video ({span})", "warning"
    elif length >= BLACK_HARD_S:
        message = (f"black for {length:.2f} s in the middle of the video ({span}); "
                   f"{BLACK_HARD_S:.1f} s or more is a hard failure")
        severity = "hard"
    else:
        message = (f"black for {length:.2f} s in the middle of the video ({span}); "
                   f"under {BLACK_HARD_S:.1f} s is a warning")
        severity = "warning"
    return _Finding("black", severity, message, start, end, picture_t=(start + end) / 2)


def _freeze_spans(text: str, duration: float) -> list[tuple[float, float]]:
    """(start, end) of each frozen stretch. A freeze that lasts to the end logs no end: it ends with the file."""
    spans: list[tuple[float, float]] = []
    start: float | None = None
    for kind, value in _FREEZE_RE.findall(text):
        if kind == "start":
            start = float(value)
        elif start is not None:
            spans.append((start, float(value)))
            start = None
    if start is not None:
        spans.append((start, max(duration, start)))
    return spans


def _check_black_and_freeze(checks: _Checks, src: Path, duration: float) -> None:
    black_expected = (f"no black gap of {BLACK_MIN_S:g} s or more "
                      f"({BLACK_HARD_S:.1f} s or more in the middle is a hard failure)")
    freeze_expected = f"no frozen picture of {FREEZE_MIN_S:g} s or more"
    try:
        text = run_ffmpeg_stderr([
            "-i", str(src), "-map", "0:v:0", "-an",
            "-vf", (f"blackdetect=d={BLACK_MIN_S:g}:pix_th={BLACK_PIXEL_THRESHOLD:g},"
                    f"freezedetect=n={FREEZE_NOISE_DB:g}dB:d={FREEZE_MIN_S:g}"),
            "-f", "null", "-",
        ])
    except FFmpegError as exc:
        error = f"the picture could not be scanned: {_last_line(exc)}"
        checks.expect("black", False, None, black_expected, error)
        checks.expect("freeze", False, None, freeze_expected, error)
        return

    blacks: list[_Finding] = []
    for start_text, end_text in _BLACK_RE.findall(text):
        finding = _black_finding(float(start_text), float(end_text), duration)
        if finding is not None:
            blacks.append(finding)
    checks.detection("black", blacks, black_expected)
    freezes = [
        _Finding("freeze", "warning", f"picture frozen for {end - start:.2f} s ({start:.2f}-{end:.2f} s)",
                 start, end, picture_t=(start + end) / 2)
        for start, end in _freeze_spans(text, duration)
    ]
    checks.detection("freeze", freezes, freeze_expected)


def _check_platform_duration(checks: _Checks, duration: float, platform: str) -> None:
    limit, label = PLATFORM_LIMITS[platform]
    expected = f"at most {limit:g} s for {platform}"
    checks.expect("platform_duration", duration <= limit, round(duration, 2), expected,
                  f"{duration:.1f} s is longer than the {platform} limit: {label}", severity="warning")


# ------------------------------------------------------------------ frames

def _frames_dir(src: Path) -> Path:
    """`<project>/.work/qa/<key>` for a file in a project folder, else `<output>/.work/qa/<key>`.

    The folder is emptied at the start of each run, so a rerun never mixes old frames in.
    """
    projects = (CONFIG.output_dir / "projects").resolve()
    base = CONFIG.output_dir
    try:
        parts = src.relative_to(projects).parts
    except ValueError:
        parts = ()
    if len(parts) > 1:  # parts[0] is the project folder, the rest is the file inside it
        base = projects / parts[0]
    stat = src.stat()
    key = hashlib.sha256(f"{src}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:12]
    folder = base / ".work" / "qa" / key
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _grab(src: Path, t: float, out: Path) -> bool:
    """One frame at `t` seconds into `out` (JPEG). False when ffmpeg wrote nothing."""
    out.unlink(missing_ok=True)
    try:
        run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(src), "-map", "0:v:0", "-frames:v", "1", "-q:v", "2", str(out)])
    except FFmpegError:
        return False
    return out.is_file() and out.stat().st_size > 0


def _frame_images(
    src: Path,
    duration: float,
    count: int,
    findings: list[_Finding],
) -> tuple[list[dict], str | None]:
    """`count` evenly spread frames, then one frame per black or freeze finding (hard ones first)."""
    spread = [((i + 0.5) * max(duration, 0.0) / count, "evenly spread") for i in range(count)]
    issues = sorted(
        (f for f in findings if f.picture_t is not None),
        key=lambda f: (f.severity != "hard", f.picture_t),
    )
    picked = issues[: MAX_IMAGES - len(spread)]
    picks = spread + [
        (f.picture_t, f"{f.check} {f.start:.2f}-{f.end:.2f} s ({f.severity})") for f in picked
    ]
    note = None
    if len(issues) > len(picked):
        note = (f"{len(issues) - len(picked)} more black or freeze finding(s) have no frame "
                f"(at most {MAX_IMAGES} images); their times are in the failures and warnings")
    if not picks:
        return [], note

    folder = _frames_dir(src)
    images: list[dict] = []
    for index, (t, reason) in enumerate(picks):
        t = min(max(t, 0.0), max(duration - 0.05, 0.0))
        out = folder / f"frame_{index:02d}.jpg"
        if _grab(src, t, out):
            images.append({"t": round(t, 3), "reason": reason, "path": str(out)})
    return images, note


# ------------------------------------------------------------------ entry points

def _result(
    src: Path,
    fmt: str | None,
    checks: _Checks,
    duration: float,
    images: list[dict],
    note: str | None,
) -> dict:
    hard = [f.entry() for f in checks.findings if f.severity == "hard"]
    warnings = [f.entry() for f in checks.findings if f.severity == "warning"]
    out = {
        "engine": f"ARGUS {__version__}",
        "source": str(src),
        "format": fmt,
        "passed": not hard,
        "hard_failures": hard,
        "warnings": warnings,
        "checks": checks.results,
        "duration": round(duration, 3),
        "images": images,
    }
    if note:
        out["images_note"] = note
    return out


def verify_video(
    video_path: str | Path,
    *,
    format: str | None = None,
    target: str | None = None,
    frames: int = DEFAULT_FRAMES,
    report: Callable[..., None] | None = None,
) -> dict:
    """Run every check on `video_path`. `report(progress, note)` is called between the steps.

    Images in the result are file paths; the tool returns them as picture content.
    """
    src = Path(video_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"video not found: {src}")
    wanted = _check_format(format)
    platform = _check_target(target)
    count = _check_frames(frames)
    say = report or _no_progress

    is_preview = PREVIEW_MARK in src.name
    checks = _Checks(PREVIEW_SOFT_CHECKS if is_preview else frozenset())
    say(0.02, "reading streams")
    try:
        info = stream_info(src)
        streams = probe(src).get("streams", [])
    except FFmpegError as exc:
        checks.findings.append(_Finding("readable", "hard", f"the file cannot be read: {_last_line(exc)}"))
        return _result(src, wanted, checks, 0.0, [], None)

    fmt = wanted or _format_of(info.width, info.height)
    if info.has_video:
        _check_frame_size(checks, info.width, info.height, fmt)
        _check_frame_rate_and_scan(checks, info.fps, info.field_order)
    else:
        checks.expect("video_stream", False, "none", "a video stream", "the file has no video stream")
    checks.expect("audio_present", info.has_audio, "yes" if info.has_audio else "no",
                  "an audio track", "the file has no audio track")
    if info.has_audio:
        say(0.10, "measuring loudness")
        _check_loudness(checks, src)
        if info.has_video:
            _check_track_lengths(checks, info, streams)
        say(0.30, "looking for silences")
        _check_silences(checks, src, info.duration)
    if info.has_video:
        say(0.50, "scanning for black and frozen frames")
        _check_black_and_freeze(checks, src, info.duration)
    if platform:
        _check_platform_duration(checks, info.duration, platform)
    say(0.80, "taking frames")
    images, note = _frame_images(src, info.duration, count, checks.findings)
    out = _result(src, fmt, checks, info.duration, images, note)
    if is_preview:
        out["preview"] = PREVIEW_NOTE
    return out


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Worker side of `qa_verify_video` (called by `argus.jobs` for kind `qa`)."""
    return verify_video(
        payload["path"],
        format=payload.get("format"),
        target=payload.get("target"),
        frames=int(payload.get("frames", DEFAULT_FRAMES)),
        report=report,
    )


def qa_verify_video(
    video_path: str,
    format: str | None = None,
    frames: int = DEFAULT_FRAMES,
    target: str | None = None,
    wait_s: float = jobs.DEFAULT_WAIT_S,
) -> dict | list:
    """Tool logic of `qa_verify_video`: validate, then run the `qa` job.

    A quick check comes back inline with its images. After `wait_s` seconds the call returns a
    job_id instead; poll `job_status` for the same result.
    """
    src = Path(video_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"video not found: {src}")
    payload = {
        "path": str(src),
        "format": _check_format(format),
        "target": _check_target(target),
        "frames": _check_frames(frames),
    }
    return jobs.run_or_detach("qa", payload, wait_s=wait_s)

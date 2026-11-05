"""QA verification: is this master actually broadcast-ready?"""

from __future__ import annotations

from pathlib import Path

from ..config import CONFIG
from ..ffmpeg import measure_loudness, probe, stream_info

ACCEPTED_FPS = {23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0}
LUFS_TOLERANCE = 2.0


def qa_verify_video(
    video_path: str | Path,
    frames_dir: str | Path | None = None,
    *,
    strict_resolution: bool = True,
) -> dict:
    """Verify format, scan type, loudness and optionally export frames."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    info = stream_info(path)
    checks: dict[str, dict] = {}

    ok_res = info.width == CONFIG.width and info.height == CONFIG.height
    ok_ar = info.width and info.height and abs(info.width / info.height - 9 / 16) < 0.01
    checks["resolution"] = {
        "passed": ok_res or (not strict_resolution and ok_ar),
        "measured": f"{info.width}x{info.height}",
        "expected": f"{CONFIG.width}x{CONFIG.height}" + ("" if strict_resolution else " (or any 9:16)"),
    }
    checks["fps"] = {
        "passed": info.fps in ACCEPTED_FPS,
        "measured": info.fps,
        "expected": sorted(ACCEPTED_FPS),
    }
    progressive = info.field_order in (None, "progressive", "Progressive")
    checks["scan"] = {"passed": bool(progressive), "measured": info.field_order or "progressive"}
    checks["audio_present"] = {"passed": info.has_audio}

    loudness = None
    if info.has_audio:
        # дорожки не должны расходиться: видео короче аудио = обрыв в темноту
        meta = probe(path)
        vdur = next((float(s.get("duration") or 0) for s in meta.get("streams", []) if s.get("codec_type") == "video"), 0)
        adur = next((float(s.get("duration") or 0) for s in meta.get("streams", []) if s.get("codec_type") == "audio"), 0)
        if vdur and adur:
            checks["stream_lengths"] = {
                "passed": abs(vdur - adur) <= 0.5,
                "measured": f"video {vdur:.1f}s / audio {adur:.1f}s",
                "expected": "|diff| <= 0.5s",
            }
        loudness = measure_loudness(path)
        lufs = loudness["input_i"]
        checks["loudness"] = {
            "passed": lufs is not None
            and (CONFIG.loudness_target - LUFS_TOLERANCE) <= lufs <= (CONFIG.loudness_target + LUFS_TOLERANCE),
            "measured": lufs,
            "expected": f"{CONFIG.loudness_target:+.0f} ±{LUFS_TOLERANCE:.0f} LUFS",
        }

    frames: list[str] = []
    if frames_dir:
        out_dir = Path(frames_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        step = max(info.duration / 3.0, 0.1)
        from ..ffmpeg import run_ffmpeg

        for i in range(3):
            ts = min(step * i + step / 2, max(info.duration - 0.1, 0.0))
            frame_path = out_dir / f"qa_frame_{i}.jpg"
            run_ffmpeg(["-ss", f"{ts:.3f}", "-i", str(path), "-frames:v", "1", "-q:v", "2", str(frame_path)])
            frames.append(str(frame_path))

    return {
        "passed": all(c["passed"] for c in checks.values()),
        "checks": checks,
        "duration": round(info.duration, 3),
        "frames": frames,
    }

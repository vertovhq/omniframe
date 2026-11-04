"""Assemble the final master: clips + voiceover + music + subtitles."""

from __future__ import annotations

from pathlib import Path

from ..config import CONFIG
from ..ffmpeg import escape_filter_path, run_ffmpeg, stream_info, temp_sibling


def _norm_chain() -> str:
    w, h, fps = CONFIG.width, CONFIG.height, CONFIG.fps
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps},setsar=1"
    )


def _burn_subtitles(video: Path, ass_path: Path, output: Path) -> None:
    run_ffmpeg([
        "-i", str(video),
        "-vf", f"ass=filename='{escape_filter_path(ass_path)}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output),
    ])


def assemble_master_video(
    clips: list[str],
    voiceover: str,
    output_path: str,
    *,
    subtitles_ass: str | None = None,
    music: str | None = None,
    music_gain_db: float = -18.0,
    loudness_target: float | None = None,
) -> dict:
    """Concatenate clips, mix voiceover (+ optional music bed), burn subs.

    Steps:
      1. Normalize every clip to the master grid (1080x1920 @ fps, SAR 1).
      2. Concatenate and mix audio: voiceover at 0 dB + music bed (ducked).
      3. Loudness-normalize the mixed track to the ARGUS target.
      4. Burn the ASS karaoke subtitles as the final render pass.
    """
    if not clips:
        raise ValueError("no clips provided")

    work = Path(output_path).resolve().parent
    work.mkdir(parents=True, exist_ok=True)

    # --- 1/2-3: video concat + audio mix + loudnorm in one filter graph ----
    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    inputs += ["-i", str(voiceover)]

    norm = _norm_chain()
    n = len(clips)
    fc_parts = [f"[{i}:v]{norm}[v{i}]" for i in range(n)]
    concat_in = "".join(f"[v{i}]" for i in range(n))
    fc_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[cat]")

    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        # input n = voiceover, input n+1 = music bed (ducked under the voice)
        fc_parts.append(
            f"[{n + 1}:a]volume={music_gain_db}dB[m];"
            f"[{n}:a][m]amix=inputs=2:duration=first:dropout_transition=3[mix]"
        )
        mix_label = "[mix]"
    else:
        fc_parts.append(f"[{n}:a]anull[vo]")
        mix_label = "[vo]"

    lufs = loudness_target if loudness_target is not None else CONFIG.loudness_target
    fc_parts.append(
        f"{mix_label}loudnorm=I={lufs}:TP=-1.5:LRA=11[outa]"
    )
    filter_complex = ";".join(fc_parts)

    staged = temp_sibling(Path(output_path).resolve(), ".stage.mp4")
    try:
        run_ffmpeg([
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[cat]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(staged),
        ])

        # --- 4: burn subtitles as a separate, idempotent pass --------------
        final = Path(output_path).resolve()
        if subtitles_ass:
            _burn_subtitles(staged, Path(subtitles_ass), final)
            staged.unlink(missing_ok=True)
        else:
            final.unlink(missing_ok=True)
            staged.replace(final)

        info = stream_info(final)
        return {
            "output": str(final),
            "clips": len(clips),
            "music": bool(music),
            "subtitles": bool(subtitles_ass),
            "duration": round(info.duration, 3),
            "resolution": f"{info.width}x{info.height}",
        }
    finally:
        staged.unlink(missing_ok=True)

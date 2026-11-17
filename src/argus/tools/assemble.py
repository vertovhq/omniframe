"""Assemble the final master: clips + voiceover + music + subtitles."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..config import CONFIG
from .. import __version__
from ..ffmpeg import escape_filter_path, stream_info, temp_sibling
from .subtitles import FONTS_DIR

# Client MCP bridges commonly cut tool calls at ~30s; assembly of many clips
# runs minutes. The job therefore runs detached and the tool returns
# immediately with a status file the caller can poll via qa_verify_video or a
# plain file check.
ASYNC_NOTICE = (
    "assembly runs in background (ffmpeg needs minutes for many clips; "
    "client tool-call timeouts would kill it). Poll the status file / output "
    "file until it appears, then call qa_verify_video."
)


def _norm_chain() -> str:
    w, h, fps = CONFIG.width, CONFIG.height, CONFIG.fps
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps},setsar=1"
    )


def _burn_subtitles(video: Path, ass_path: Path, output: Path) -> None:
    _run_detached_ffmpeg([
        "-i", str(video),
        "-vf", f"ass=filename='{escape_filter_path(ass_path)}':fontsdir='{escape_filter_path(FONTS_DIR)}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-metadata", f"comment=Made with ARGUS Studio v{__version__}",
        str(output),
    ])


def _run_detached_ffmpeg(args: list[str]) -> None:
    """Start ffmpeg without waiting - survives short client tool timeouts."""
    ffmpeg = CONFIG.ffmpeg
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    subprocess.Popen(
        [ffmpeg, "-hide_banner", "-y", "-loglevel", "error", *args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


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

    ASYNC by design: the ffmpeg job runs detached and this call returns
    immediately (client MCP bridges kill calls at ~30s; a multi-clip assembly
    needs minutes). Writes a `.status.json` next to the output; poll the
    status file (or the output file) until state is "done" | "error", then
    qa_verify_video. Re-calling with the same arguments is safe: a running
    job for the same output is not started twice (stale jobs are detected
    by pid liveness and age).

    Steps executed by the background job:
      1. Normalize every clip to the master grid (1080x1920 @ fps, SAR 1).
      2. Concatenate and mix audio: voiceover at 0 dB + music bed (ducked).
      3. Loudness-normalize the mixed track to the ARGUS target.
      4. Burn the ASS karaoke subtitles as the final render pass.
    """
    if not clips:
        raise ValueError("no clips provided")

    out = Path(output_path).resolve()
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)
    status_path = out.with_suffix(".status.json")

    # --- single-flight: never run two ffmpeg jobs on the same output -------
    if status_path.exists():
        try:
            prev = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
        if prev.get("state") == "running":
            pid = prev.get("pid")
            age = time.time() - float(prev.get("started", 0))
            alive = False
            if pid:
                try:
                    os.kill(pid, 0)  # signal 0 = existence probe
                    alive = True
                except OSError:
                    alive = False
            if alive and age < 1800:
                return {
                    "engine": f"ARGUS {__version__}",
                    "state": "running",
                    "output": str(out),
                    "status_file": str(status_path),
                    "note": ASYNC_NOTICE,
                    "started_by_previous_call": True,
                }
        # stale/crashed previous run -> fall through and restart

    missing = [c for c in clips if not Path(c).exists()]
    if missing:
        raise FileNotFoundError(f"clips not found: {missing}")
    if not Path(voiceover).exists():
        raise FileNotFoundError(f"voiceover not found: {voiceover}")
    if subtitles_ass and not Path(subtitles_ass).exists():
        raise FileNotFoundError(f"subtitles not found: {subtitles_ass}")
    if music and not Path(music).exists():
        raise FileNotFoundError(f"music not found: {music}")

    # --- build the command for the detached worker --------------------------
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
        fc_parts.append(
            f"[{n + 1}:a]volume={music_gain_db}dB[m];"
            f"[{n}:a][m]amix=inputs=2:duration=first:dropout_transition=3[mix]"
        )
        mix_label = "[mix]"
    else:
        fc_parts.append(f"[{n}:a]anull[vo]")
        mix_label = "[vo]"

    lufs = loudness_target if loudness_target is not None else CONFIG.loudness_target
    fc_parts.append(f"{mix_label}loudnorm=I={lufs}:TP=-1.5:LRA=11[outa]")

    video_dur = sum(stream_info(c).duration for c in clips)
    voice_dur = stream_info(voiceover).duration
    pad = max(0.0, voice_dur - video_dur) + 0.3
    if pad > 0.3:
        fc_parts.append("[cat]tpad=stop_mode=clone:stop_duration=" + f"{pad:.3f}[catp]")
        video_out = "[catp]"
    else:
        video_out = "[cat]"
    filter_complex = ";".join(fc_parts)

    staged = temp_sibling(out, ".stage.mp4")
    stage_args = [
        *inputs,
        "-filter_complex", filter_complex,
        "-map", video_out, "-map", "[outa]",
        "-shortest",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-metadata", f"comment=Made with ARGUS Studio v{__version__}",
        str(staged),
    ]

    # worker: a tiny python child that runs ffmpeg stages and maintains status
    worker = work / "_argus_assemble_worker.py"
    worker.write_text(_WORKER_TEMPLATE, encoding="utf-8")
    payload = json.dumps({
        "ffmpeg": CONFIG.ffmpeg,
        "stage_args": stage_args,
        "staged": str(staged),
        "final": str(out),
        "subtitles_ass": subtitles_ass,
        "fonts_dir": str(FONTS_DIR),
        "status_file": str(status_path),
        "loudness_target": lufs,
        "version": __version__,
    })
    payload_path = temp_sibling(out, ".assemble_job.json")
    payload_path.write_text(payload, encoding="utf-8")

    status_path.write_text(json.dumps({
        "state": "running",
        "output": str(out),
        "pid": None,
        "started": time.time(),
        "steps": ["queued"],
    }, ensure_ascii=False), encoding="utf-8")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [sys.executable, "-I", str(worker), str(payload_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    # patch the pid into the status for single-flight probes
    try:
        st = json.loads(status_path.read_text(encoding="utf-8"))
        st["pid"] = proc.pid
        status_path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return {
        "engine": f"ARGUS {__version__}",
        "state": "running",
        "output": str(out),
        "status_file": str(status_path),
        "clips": len(clips),
        "music": bool(music),
        "subtitles": bool(subtitles_ass),
        "note": ASYNC_NOTICE,
    }


_WORKER_TEMPLATE = '''"""Background assembler worker (spawned by assemble_master_video)."""
import json, os, subprocess, sys, time
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
status_path = Path(payload["status_file"])
ffmpeg = payload["ffmpeg"]


def set_status(**kw):
    try:
        st = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    st.update(kw)
    status_path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


try:
    set_status(steps=["assemble+mix+loudnorm"], started=time.time())
    r = subprocess.run([ffmpeg, "-hide_banner", "-y", "-loglevel", "error",
                        *payload["stage_args"]], capture_output=True, text=True)
    if r.returncode != 0:
        set_status(state="error", step="assemble", error=r.stderr[-1500:])
        sys.exit(1)

    staged = Path(payload["staged"])
    final = Path(payload["final"])

    if payload.get("subtitles_ass"):
        set_status(steps=["assemble", "burn_subtitles"])
        fonts_escaped = (payload["fonts_dir"].replace("\\\\", "/")
                         .replace(":", "\\:").replace("'", "\\'"))
        ass_escaped = (payload["subtitles_ass"].replace("\\\\", "/")
                       .replace(":", "\\\\:").replace("'", "\\\\'"))
        r2 = subprocess.run(
            [ffmpeg, "-hide_banner", "-y", "-loglevel", "error",
             "-i", str(staged),
             "-vf", "ass=filename='{}':fontsdir='{}'".format(ass_escaped, fonts_escaped),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "copy",
             "-movflags", "+faststart",
             "-metadata", "comment=Made with ARGUS Studio v" + payload["version"],
             str(final)], capture_output=True, text=True)
        if r2.returncode != 0:
            set_status(state="error", step="burn_subtitles", error=r2.stderr[-1500:])
            sys.exit(1)
        staged.unlink(missing_ok=True)
    else:
        final.unlink(missing_ok=True)
        staged.replace(final)

    set_status(state="done", finished=time.time(),
               output=str(final))
except Exception as e:
    set_status(state="error", error=str(e)[:1500])
    sys.exit(1)
'''

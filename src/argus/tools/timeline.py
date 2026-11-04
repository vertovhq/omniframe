"""Acoustic timeline: snap scene cuts to real speech boundaries.

The video must never cut mid-word, so every scene cut point is
snapped to the middle of the nearest detected speech pause.
"""

from __future__ import annotations

from pathlib import Path

from ..ffmpeg import detect_pauses, stream_info


def _sentences(script_text: str) -> list[str]:
    """Split a script into sentences, keeping text usable for captions."""
    parts: list[str] = []
    buffer: list[str] = []
    terminators = {".", "!", "?", "…"}
    for token in script_text.replace("\n", " ").split(" "):
        buffer.append(token)
        if token and token[-1] in terminators:
            sentence = " ".join(buffer).strip()
            if sentence:
                parts.append(sentence)
            buffer = []
    tail = " ".join(buffer).strip()
    if tail:
        parts.append(tail)
    return parts


def _snap_to_pause(t: float, pauses: list[tuple[float, float]]) -> tuple[float, bool]:
    """Return the centre of the pause nearest to `t` (or `t` unchanged)."""
    best_t, best_dist = t, float("inf")
    for start, end in pauses:
        centre = (start + end) / 2.0
        dist = abs(centre - t)
        if dist < best_dist:
            best_t, best_dist = centre, dist
    return best_t, best_dist < 1.0  # "snapped" only if within 1s of a pause


def calculate_acoustic_timeline(
    audio_path: str | Path,
    script_text: str,
    target_scene_count: int = 7,
) -> dict:
    """Compute scene cut points aligned to sentence & pause boundaries."""
    info = stream_info(audio_path)
    if not info.has_audio:
        raise ValueError(f"{audio_path} has no audio stream")
    duration = info.duration
    if duration <= 0:
        raise ValueError("could not determine audio duration")

    target_scene_count = max(1, target_scene_count)
    sentences = _sentences(script_text) or [script_text.strip()]

    pauses = detect_pauses(audio_path)
    raw_cuts = [duration * i / target_scene_count for i in range(1, target_scene_count)]
    cuts, snapped_flags = [], []
    for t in raw_cuts:
        snapped, ok = _snap_to_pause(t, pauses)
        cuts.append(round(snapped, 3))
        snapped_flags.append(ok)

    # Build scenes from the (deduplicated, sorted) cut points.
    bounds = [0.0, *(c for i, c in enumerate(cuts) if i == 0 or c > cuts[i - 1] + 0.05), duration]
    per_scene = max(1, round(len(sentences) / len(bounds[1:])))
    scenes = []
    for i, (start, end) in enumerate(zip(bounds, bounds[1:])):
        chunk = sentences[i * per_scene: (i + 1) * per_scene] or [""]
        scenes.append({
            "index": i,
            "start": round(start, 3),
            "end": round(end, 3),
            "sentence": " ".join(chunk),
        })

    return {
        "duration": round(duration, 3),
        "scene_count": len(scenes),
        "scenes": scenes,
        "cut_points": cuts,
        "snapped_ratio": round(sum(snapped_flags) / max(1, len(snapped_flags)), 2),
        "pauses_found": len(pauses),
    }

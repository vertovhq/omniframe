"""Veo clip generation, two providers:

  api  — official Gemini API (stable, paid: Veo has no free API tier)
  flow — your own logged-in Google Flow browser session (free monthly
         credits; log in once via flow_login, no cookie files ever)

Default provider comes from ARGUS_VEO_PROVIDER (default "api").
"""

from __future__ import annotations

import time
from pathlib import Path

from ..config import CONFIG

POLL_INTERVAL_S = 10.0


def _client():
    if not CONFIG.gemini_api_key:
        raise RuntimeError(
            "No Gemini API key configured. Copy .env.example to .env and set "
            "ARGUS_GEMINI_API_KEY (get one free at https://aistudio.google.com/apikey), "
            "or switch to provider='flow' to use your Google Flow browser session."
        )
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed: pip install argus-studio") from exc
    return genai.Client(api_key=CONFIG.gemini_api_key)


def generate_veo_clip(
    prompt: str,
    output_path: str,
    *,
    aspect_ratio: str = "9:16",
    model: str | None = None,
    negative_prompt: str | None = None,
    max_wait_s: float = 600.0,
    provider: str | None = None,
) -> dict:
    """Generate one vertical Veo clip and save it to `output_path`.

    provider: "api" (official Gemini API, paid) or "flow" (your logged-in
    Google Flow browser session, free credits — run flow_login once first).
    Default: ARGUS_VEO_PROVIDER, then "api". Renders take 1–3 minutes.
    Prompts are passed to the model exactly as given — no content-policy
    workarounds are applied, keep prompts clean.
    """
    chosen = (provider or CONFIG.veo_provider or "api").strip().lower()
    if chosen == "flow":
        from .flow_browser import flow_generate

        return flow_generate(prompt, output_path, max_wait_s=max_wait_s)
    if chosen != "api":
        raise ValueError(f"unknown Veo provider: {chosen!r} (use 'api' or 'flow')")

    client = _client()
    model = model or CONFIG.veo_model

    from google.genai import types

    config = types.GenerateVideosConfig(
        aspect_ratio=aspect_ratio,
        number_of_videos=1,
        **({"negative_prompt": negative_prompt} if negative_prompt else {}),
    )
    operation = client.models.generate_videos(model=model, prompt=prompt, config=config)

    started = time.monotonic()
    while not operation.done:
        if time.monotonic() - started > max_wait_s:
            raise TimeoutError(f"Veo render exceeded {max_wait_s:.0f}s; try again or use a fast model")
        time.sleep(POLL_INTERVAL_S)
        operation = client.operations.get(operation)

    videos = getattr(operation.response, "generated_videos", None) or []
    if not videos:
        raise RuntimeError(f"Veo returned no video (model={model}). Check prompt & quota.")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    video = videos[0]
    data = getattr(video.video, "video_bytes", None)
    if data:
        out.write_bytes(data if isinstance(data, bytes) else data.getvalue())
    else:
        client.files.download(file=video.video)
        data = getattr(video.video, "video_bytes", None)
        if not data:
            raise RuntimeError("could not download the generated clip")
        out.write_bytes(data if isinstance(data, bytes) else data.getvalue())

    return {
        "output": str(out),
        "model": model,
        "aspect_ratio": aspect_ratio,
        "elapsed_s": round(time.monotonic() - started, 1),
    }

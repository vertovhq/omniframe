"""Veo clip generation, two routes:

  api  — official Gemini API. Refused: Veo 3.1 Preview was shut down there on 2026-10-22
         (https://aistudio.google.com/docs/video). Task 20.8b replaces it with Omni (Interactions API).
  flow — your own logged-in Google Flow browser session (free monthly
         credits; log in once via flow_login, no cookie files ever)

Default route comes from ARGUS_VEO_PROVIDER (default "api").
"""

from __future__ import annotations

from ..config import CONFIG
from .model_catalog import VEO_API_SHUTDOWN_MESSAGE


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

    provider: "flow" (your logged-in Google Flow browser session, free credits — run flow_login
    once first). "api" (the Gemini API) is refused: Veo 3.1 Preview was shut down there on
    2026-10-22, and the error says so. Default: ARGUS_VEO_PROVIDER, then "api", so set "flow"
    or ARGUS_VEO_PROVIDER=flow until the Omni route is built.
    Renders take 1–3 minutes. Prompts are passed to the model exactly as given — no content-policy
    workarounds are applied, keep prompts clean.
    """
    chosen = (provider or CONFIG.veo_provider or "api").strip().lower()
    if chosen == "flow":
        from .flow_browser import flow_generate

        return flow_generate(prompt, output_path, max_wait_s=max_wait_s)
    if chosen != "api":
        raise ValueError(f"unknown Veo provider: {chosen!r} (use 'api' or 'flow')")
    raise RuntimeError(VEO_API_SHUTDOWN_MESSAGE)

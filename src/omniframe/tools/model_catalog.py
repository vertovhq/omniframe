"""Which Gemini models the key can use: Gemini text-to-speech (task 20.8).

OmniFrame does not type model ids into code. An id comes from the provider's own list, unless the
user set one in `.env` (OMNIFRAME_TTS_MODEL). ElevenLabs models are listed in
`voiceover.py`, next to the ElevenLabs HTTP helper. "Newest" means the highest version numbers in the id
(gemini-3.8 > gemini-3.1 > gemini-2.5), because neither API returns a release date.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ..config import CONFIG

# google-genai: `client.models.list()` iterates over every page of models
#   https://googleapis.github.io/python-genai/
# Model ids and what each is for: https://aistudio.google.com/docs/models

_NUMBER = re.compile(r"\d+")


def version_key(model_id: str) -> tuple:
    """Sort key: the numbers in the id, then no 'lite', then no 'preview' (True sorts above False)."""
    numbers = tuple(int(n) for n in _NUMBER.findall(model_id))
    return (numbers, "lite" not in model_id, "preview" not in model_id)


def newest_first(models: list[dict]) -> list[dict]:
    """Models with an "id" key, newest first. Equal keys keep the provider's order (sorted is stable)."""
    return sorted(models, key=lambda model: version_key(model["id"]), reverse=True)


def is_tts(model: dict) -> bool:
    return "tts" in model["id"] and "live" not in model["id"]


def gemini_model_list() -> list[dict]:
    """Every model the Gemini key lists, as `[{id, name}]`. Raises RuntimeError with the reason."""
    if not CONFIG.gemini_api_key:
        raise RuntimeError("no Gemini key: set OMNIFRAME_GEMINI_API_KEY in .env (free key: https://aistudio.google.com/apikey)")
    try:
        from google import genai

        client = genai.Client(api_key=CONFIG.gemini_api_key)
        models: list[dict] = []
        for model in client.models.list():
            model_id = str(model.name or "").removeprefix("models/")
            if model_id:
                models.append({"id": model_id, "name": model.display_name or model_id})
    except Exception as exc:  # the message names the cause; the key is never part of it
        raise RuntimeError(f"could not list Gemini models: {str(exc)[:300]}") from exc
    return models


def _pick(configured: str, keep: Callable[[dict], bool], env_name: str, what: str) -> str:
    """The configured id, or the newest listed model that `keep` accepts. Names the env variable on failure."""
    if configured:
        return configured
    try:
        found = [model for model in newest_first(gemini_model_list()) if keep(model)]
    except RuntimeError as exc:
        raise RuntimeError(f"{exc}; set {env_name} in .env to a {what} model id to skip the list") from exc
    if not found:
        raise RuntimeError(f"the Gemini key lists no {what} model; set {env_name} in .env to a model id")
    return found[0]["id"]


def tts_model_id() -> str:
    """The Gemini text-to-speech model: OMNIFRAME_TTS_MODEL when set, else the newest TTS model listed."""
    return _pick(CONFIG.tts_model, is_tts, "OMNIFRAME_TTS_MODEL", "text-to-speech")


def options(errors: dict[str, str]) -> list[dict]:
    """Gemini TTS models the key lists, newest first.

    Each row is `{id, name, use, default}`; `default` marks the id OmniFrame uses when the user picks none.
    A failed list goes into `errors["gemini_models"]` and returns no rows.
    """
    try:
        listed = newest_first(gemini_model_list())
    except RuntimeError as exc:
        errors["gemini_models"] = str(exc)[:300]
        return []
    kind = [model for model in listed if is_tts(model)]
    default = CONFIG.tts_model or (kind[0]["id"] if kind else None)
    return [{"id": m["id"], "name": m["name"], "use": "text to speech", "default": m["id"] == default} for m in kind]

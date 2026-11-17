"""`studio_guide`: the working method, what is available now, the user's preferences.

The guide text ships with the package (`argus/STUDIO_GUIDE.md`). Capabilities are
computed per call from the registered tools, the config and import checks, so the
model never plans around a provider that is not there. Preferences are the tail of
the knowledge base file that `learn_and_record_memory` appends to.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

from ..config import CONFIG, ArgusConfig
from .flow_browser import _profile_dir as _flow_profile_dir

# Upper bound for the preferences text, in characters, so a long file cannot flood the context.
PREFERENCES_LIMIT = 4000


def read_guide() -> str:
    """The packaged guide text."""
    return resources.files("argus").joinpath("STUDIO_GUIDE.md").read_text(encoding="utf-8")


def read_preferences(path: Path, limit: int = PREFERENCES_LIMIT) -> tuple[str, bool]:
    """Last `limit` characters of the knowledge base file -> (text, truncated).

    The cut moves forward to the next entry heading (`## `) when one starts in the
    first quarter of the window, otherwise to the next line, so the text does not
    open in the middle of a sentence. The result is never longer than `limit`.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # missing file = no preferences saved yet
        return "", False
    text = text.strip()
    if len(text) <= limit:
        return text, False

    tail = text[-limit:]
    heading = tail.find("\n## ")
    if 0 <= heading <= limit // 4:
        tail = tail[heading + 1 :]
    else:
        newline = tail.find("\n")
        if newline >= 0:
            tail = tail[newline + 1 :]
    return tail.strip(), True


def _importable(module: str) -> bool:
    """True when `module` can be imported, without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _provider(available: bool, note: str) -> dict:
    return {"available": available, "note": note}


def providers(cfg: ArgusConfig) -> dict:
    """Which voice, transcript and video providers work right now."""
    eleven = bool(cfg.elevenlabs_api_key)
    gemini = bool(cfg.gemini_api_key)
    edge = _importable("edge_tts")
    whisper = _importable("faster_whisper")
    flow = _flow_profile_dir(None).exists()
    return {
        "elevenlabs": _provider(
            eleven,
            f"voice, model {cfg.eleven_model}" if eleven else "no key: set ELEVENLABS_API_KEY in .env",
        ),
        "gemini": _provider(
            gemini,
            "voice (Gemini TTS) and Veo API" if gemini else "no key: set ARGUS_GEMINI_API_KEY in .env",
        ),
        "edge": _provider(
            edge,
            "free voices, no key" if edge else "not installed: pip install edge-tts",
        ),
        "faster_whisper": _provider(
            whisper,
            f"transcripts and word timings, model {cfg.whisper_model}" if whisper
            else "not installed: pip install 'argus-studio[asr]'; no transcripts until then",
        ),
        "veo_api": _provider(
            gemini,
            f"generate_veo_clip provider=api, model {cfg.veo_model}" if gemini else "needs the Gemini key",
        ),
        "flow_session": _provider(
            flow,
            "logged-in Google Flow profile found (generate_veo_clip provider=flow)" if flow
            else "no session: run flow_login once to use provider=flow",
        ),
    }


def studio_guide(tool_names: Iterable[str], config: ArgusConfig | None = None) -> dict:
    """Guide + capabilities + preferences, as returned by the `studio_guide` tool."""
    cfg = CONFIG if config is None else config
    preferences, truncated = read_preferences(cfg.knowledge_base)
    return {
        "guide": read_guide(),
        "capabilities": {
            "tools": sorted(tool_names),
            "providers": providers(cfg),
        },
        "preferences": preferences,
        "preferences_truncated": truncated,
    }

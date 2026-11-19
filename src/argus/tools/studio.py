"""`studio_guide`: the working method, what is available now, the user's preferences.

The guide text ships with the package (`argus/STUDIO_GUIDE.md`). Capabilities are
computed per call from the registered tools, the config and import checks, so the
model never plans around a provider that is not there. Preferences are the tail of
the knowledge base file that `learn_and_record_memory` appends to.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

from ..config import CONFIG, ArgusConfig
from ..media_out import Image
from . import library
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


def read_kit() -> str:
    """The motion kit catalogue (`engine/src/kit/KIT.md`), or a note when the engine folder lacks it."""
    from .render import engine_dir  # imported here: render pulls in the whole renderer

    path = engine_dir() / "src" / "kit" / "KIT.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"The motion kit catalogue is missing ({path}). Read the files in engine/src/kit/ instead."


def studio_guide(tool_names: Iterable[str], config: ArgusConfig | None = None, *, custom_scenes: bool = False) -> dict:
    """Guide + capabilities + preferences, as returned by the `studio_guide` tool.

    With `custom_scenes` the result also has `motion_kit`, the catalogue of the kit blocks.
    """
    cfg = CONFIG if config is None else config
    preferences, truncated = read_preferences(cfg.knowledge_base)
    out = {
        "guide": read_guide(),
        "capabilities": {
            "tools": sorted(tool_names),
            "providers": providers(cfg),
        },
        "preferences": preferences,
        "preferences_truncated": truncated,
    }
    out["library"] = library.overview(library.library_dir(cfg.output_dir))
    if custom_scenes:
        out["motion_kit"] = read_kit()
    return out


def result_for_model(result: dict) -> dict | list:
    """`studio_guide` as a tool return value: `[json, Image, ...]` when the library has posters.

    The posters are the newest entries' `poster.jpg` files (512 px, at most `library.MAX_POSTERS`),
    in the order of `library.posters`. They are returned as they are: `media_out.prepare_image`
    would write a `.view.jpg` copy into the entry folder.
    """
    posters = result.get("library", {}).get("posters") or []
    paths = [Path(p["path"]) for p in posters]
    if not paths or not all(p.is_file() for p in paths):
        return result
    return [json.dumps(result, ensure_ascii=False, indent=2, default=str), *[Image(path=p) for p in paths]]

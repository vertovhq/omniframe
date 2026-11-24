"""`studio_guide`: the working method, what is available now, the user's preferences.

The guide text ships with the package (`argus/STUDIO_GUIDE.md`). Capabilities are
computed per call from the registered tools, the config and import checks, so the
model never plans around a provider that is not there. Preferences are the tail of
the knowledge base file that `learn_and_record_memory` appends to.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

from .. import __version__, state
from ..config import CONFIG, ArgusConfig
from ..media_out import Image
from . import kit_preview, library, sounds

# Upper bound for the preferences text, in characters, so a long file cannot flood the context.
PREFERENCES_LIMIT = 4000

# Digest of what each guide read returned during this server run (task 20.10 item 15).
_SENT: dict[str, str] = {}


def once(key: str, result: dict, full: bool = False) -> dict:
    """`result`, or a one-line answer when the same content already went out in this server run.

    The first read of a guide or kit group returns the full text; a repeated read with the same
    content returns its hash only, and `full=True` asks for the text again. The state lives in
    the server process, so a new chat on the same server gets the one line too: it must pass
    `full=true` to see the text.
    """
    digest = hashlib.sha256(
        json.dumps(result, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    if not full and _SENT.get(key) == digest:
        return {
            "engine": f"ARGUS {__version__}",
            "unchanged": True,
            "hash": digest,
            "note": f"unchanged since your last read, hash {digest}; pass full=true to get it again",
        }
    _SENT[key] = digest
    return result


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
    return {
        "elevenlabs": _provider(
            eleven,
            f"voice, model {cfg.eleven_model or 'newest text-to-speech model of the key (see voice_options)'}"
            if eleven else "no key: set ELEVENLABS_API_KEY in .env",
        ),
        "gemini": _provider(
            gemini,
            "voice (Gemini TTS)" if gemini else "no key: set ARGUS_GEMINI_API_KEY in .env",
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
    }


def read_kit() -> str:
    """The motion kit index (`engine/src/kit/KIT.md`: one line per group), or a note when the engine folder lacks it."""
    from .render import engine_dir  # imported here: render pulls in the whole renderer

    path = engine_dir() / "src" / "kit" / "KIT.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"The motion kit catalogue is missing ({path}). Read the files in engine/src/kit/ instead."


SECTION_HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


def guide_sections(text: str) -> dict[str, tuple[str, str]]:
    """`{number: (title, body)}` for every `## N. Title` section of the guide text, in order."""
    matches = list(SECTION_HEADING.finditer(text))
    out: dict[str, tuple[str, str]] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match.group(1)] = (match.group(2).strip(), text[match.end():end].strip())
    return out


def core_text(text: str) -> str:
    """The guide core: the title, section 0 (look, order, budget rules), and an index of the other sections."""
    sections = guide_sections(text)
    first = SECTION_HEADING.search(text)
    head = text[: first.start()].strip() if first else ""
    core = sections.get("0")
    core_part = f"{core[0]}\n\n{core[1]}" if core else ""
    index = "\n".join(
        f'- section {num} "{title}": studio_guide(section="{num}")'
        for num, (title, _) in sections.items() if num != "0"
    )
    return "\n\n".join(part for part in (head, core_part, "Other sections:\n" + index) if part)


def find_section(sections: dict[str, tuple[str, str]], key: str) -> str | None:
    """The number of the section named `key`: its number, `core`, or a word of its title (case-insensitive)."""
    key = key.strip().lower()
    if key == "core":
        key = "0"
    if key in sections:
        return key
    for num, (title, _) in sections.items():
        if key and key in title.lower():
            return num
    return None


def section_for_model(section: str, full: bool = False) -> dict:
    """`studio_guide(section=...)`: one section of the guide. An unknown name lists the valid ones."""
    sections = guide_sections(read_guide())
    head = {"engine": f"ARGUS {__version__}"}
    num = find_section(sections, section)
    if num is None:
        names = [f"{n} {title}" for n, (title, _) in sections.items()]
        return {**head, "error": f"unknown section {section!r}", "sections": names}
    title, body = sections[num]
    return once(f"section:{num}", {**head, "section": num, "title": title, "text": body}, full)


def studio_guide(
    tool_names: Iterable[str],
    config: ArgusConfig | None = None,
    *,
    custom_scenes: bool = False,
    project: str | None = None,
) -> dict:
    """Guide core + capabilities + preferences, as returned by the `studio_guide` tool.

    With `custom_scenes` the result also has `motion_kit`, the index of the kit groups
    (one group's text and strip: `kit_group_result`). With `project` it has `resume`, at most
    5 lines of the project's stage (`state.resume_lines`).
    """
    cfg = CONFIG if config is None else config
    preferences, truncated = read_preferences(cfg.knowledge_base)
    out = {
        "guide": core_text(read_guide()),
        "capabilities": {
            "tools": sorted(tool_names),
            "providers": providers(cfg),
        },
        "preferences": preferences,
        "preferences_truncated": truncated,
    }
    out["library"] = library.overview(library.library_dir(cfg.output_dir))
    sfx_lines = sounds.library_lines(library.library_dir(cfg.output_dir))
    if sfx_lines:
        out["library"]["sfx"] = sfx_lines  # one line per saved sound; copy its recipe into audio.sounds
    if custom_scenes:
        out["motion_kit"] = read_kit()
    if project:
        resume = state.resume_lines(project)
        if resume:
            out["resume"] = resume
    return out


def kit_group_result(group: str) -> dict:
    """One kit group for `studio_guide(kit_group=...)`: its text and its contact strip, not the whole guide.

    `strip` is `{"path", "blocks"}` when the image is cached, or `{"state": "building", "job_id", ...}`
    while a background job renders it (see `kit_preview.strip_for_guide`). An unknown group gets the list of groups.
    """
    names = kit_preview.group_names()
    head = {"engine": f"ARGUS {__version__}"}
    if group == "sfx":
        return {**head, **sfx_group(), "groups": [*names, "sfx"]}
    if group not in names:
        return {**head, "error": f"unknown kit group {group!r}", "groups": names}
    return {**head, "kit_group": group, "text": kit_preview.group_doc(group), "groups": names, **kit_preview.strip_for_guide(group)}


def sfx_group() -> dict:
    """`studio_guide(kit_group="sfx")`: the starting sound recipes, one line each, and their sheet image."""
    return {
        "kit_group": "sfx",
        "text": (
            "Sound recipes. Each line is a starting point: write it into audio.sounds with \"from\" and the "
            "fields you change (for example {\"from\": \"whoosh\", \"pitch_end\": 300, \"length\": 0.6}), or a full sound "
            "with length and layers (up to 4 layers: source, pitch sweep, envelope, filter, drive, bits, pan). "
            "Place it with audio.sfx {at: seconds | \"cue:name\" | \"cut:n\", sound, align: start|peak|end, vary}. "
            "Check the timeline image of render_video(mode=\"audio\") before the preview."
        ),
        "recipes": sounds.starting_lines(),
        "strip": {"path": str(sounds.ensure_starting_sheet(CONFIG.output_dir))},
    }


def kit_group_for_model(group: str, full: bool = False) -> dict | list:
    """`kit_group_result` as a tool return value: `[json, Image]` when the strip is cached.

    A group read again with the same content answers with one line (`once`).
    """
    result = once(f"kit:{group}", kit_group_result(group), full)
    if result.get("unchanged"):
        return result
    path = result.get("strip", {}).get("path")
    if path and Path(path).is_file():
        return [json.dumps(result, ensure_ascii=False, indent=2), Image(path=Path(path))]
    return result


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

"""The style library: scenes, characters, plates and caption styles that worked, kept for the next video.

Where: `<OMNIFRAME_OUTPUT_DIR>/library/<entry>/`, per user, never in the repo. One entry holds

- the component files (`.tsx`), copied from `<project>/components/` as they are;
- `card.md`: what it is, when it fits, its props, the source project, the files and how to import them;
- `poster.jpg`: a frame of the final video, longest side 512 px.

`library/index.md` is generated from the cards, one line per entry. The cards are the source of
truth: the index is rebuilt from them on every save and on every `studio_guide` call, so an entry
that is deleted or edited by hand is reflected the next time.

Saving has no tool of its own: `export_package(save_to_library=...)` calls `validate_save` before
the export starts and `save_entry` when the export succeeded (design: the poster comes from the
final). The model offers it after a good final and passes it only after the user agreed.

Using an entry: a project component imports one of its files as
`import Boat from './library/<entry>/<File>'` (`tools/components.py` copies the files a render
needs). Whether an entry fits a new reference is the model's call; nothing here scores it.
"""

from __future__ import annotations

import datetime
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from ..ffmpeg import run_ffmpeg, temp_sibling
from ..project import slugify
from .components import COMPONENTS_DIR, LIBRARY_DIR, NAME_RE, collect_files

CARD = "card.md"
POSTER = "poster.jpg"
INDEX = "index.md"
POSTER_SIDE = 512             # longest side of a poster, in px
POSTER_QUALITY = 85
MAX_POSTERS = 8               # posters that `studio_guide` returns as images
# `style.ts` and `kit.ts` are the re-export files next to the entries inside a render.
RESERVED_ENTRIES = frozenset({"style", "kit"})

# Characters. `what` and `fits_when` form the one-line index entry that `studio_guide` returns.
FIELD_LIMITS = {"what": 200, "fits_when": 250, "props": 600}
SAVE_KEYS = ("name", "components", "what", "fits_when", "props", "replace", "poster_time")

_CARD_FIELDS = {
    "What": "what",
    "Fits when": "fits_when",
    "Props": "props",
    "Source project": "source",
    "Files": "files",
    "Saved": "saved",
}
_CARD_LINE = re.compile(r"^\*\*(?P<label>[^*:]+):\*\*[ \t]*(?P<value>.*)$", re.M)


# ------------------------------------------------------------------ paths

def library_dir(output_dir: Path) -> Path:
    """`<OMNIFRAME_OUTPUT_DIR>/library`."""
    return Path(output_dir) / LIBRARY_DIR


def project_library_dir(project_root: Path) -> Path:
    """The library that belongs to a project folder (`<output>/projects/<slug>` -> `<output>/library`)."""
    return library_dir(Path(project_root).parent.parent)


# ------------------------------------------------------------------ cards and the index

def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def card_text(entry: str, fields: dict[str, Any]) -> str:
    """The text of `card.md` for an entry."""
    files: list[str] = fields["files"]
    first = Path(files[0]).stem
    lines = [
        f"# {entry}",
        "",
        f"**What:** {_one_line(fields['what'])}",
        f"**Fits when:** {_one_line(fields['fits_when'])}",
        f"**Props:** {_one_line(fields.get('props') or '(none given)')}",
        f"**Source project:** {fields['source']}",
        f"**Files:** {', '.join(files)}",
        f"**Saved:** {fields['saved']}",
        "",
        "Use it from a project component:",
        "",
        "```tsx",
        f"import {first} from './{LIBRARY_DIR}/{entry}/{first}';",
        "```",
        "",
        f"`poster.jpg` is a frame of the final video of `{fields['source']}`.",
        "",
    ]
    return "\n".join(lines)


def read_card(folder: Path) -> dict[str, Any] | None:
    """The fields of `<folder>/card.md`, or None when the folder is not an entry."""
    path = folder / CARD
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields: dict[str, Any] = {"name": folder.name, "mtime": path.stat().st_mtime_ns}
    for match in _CARD_LINE.finditer(text):
        key = _CARD_FIELDS.get(match["label"].strip())
        if key:
            fields[key] = match["value"].strip()
    fields["files"] = [f.strip() for f in str(fields.get("files", "")).split(",") if f.strip()]
    poster = folder / POSTER
    fields["poster"] = poster if poster.is_file() else None
    return fields


def read_cards(library_root: Path) -> list[dict[str, Any]]:
    """Every entry of the library, sorted by name. Folders without a card are ignored."""
    if not library_root.is_dir():
        return []
    cards = [read_card(p) for p in sorted(library_root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    return [card for card in cards if card is not None]


def index_line(card: dict[str, Any]) -> str:
    parts = [f"- **{card['name']}**: {card.get('what', '')}", f"Fits when: {card.get('fits_when', '')}"]
    if card.get("files"):
        parts.append("Files: " + ", ".join(Path(f).stem for f in card["files"]))
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts)


def build_index(library_root: Path) -> str:
    """The text of `index.md`: a short header, then one line per entry."""
    cards = read_cards(library_root)
    lines = [
        "# ARGUS style library",
        "",
        f"One line per entry; `<entry>/{CARD}` has the details and `<entry>/{POSTER}` is a frame of its video. "
        f"Import a file in a project component as `import X from './{LIBRARY_DIR}/<entry>/<File>'`.",
        "",
    ]
    lines += [index_line(card) for card in cards] or ["(no entries yet)"]
    return "\n".join(lines) + "\n"


def write_index(library_root: Path) -> Path:
    library_root.mkdir(parents=True, exist_ok=True)
    path = library_root / INDEX
    staged = temp_sibling(path, ".md")
    try:
        staged.write_text(build_index(library_root), encoding="utf-8", newline="\n")
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)
    return path


def overview(library_root: Path, max_posters: int = MAX_POSTERS) -> dict[str, Any]:
    """What `studio_guide` shows: the index and the posters of the newest entries.

    `posters` is `[{"entry": name, "path": poster.jpg}]`, newest first, at most `max_posters`.
    """
    cards = read_cards(library_root)
    out: dict[str, Any] = {"dir": str(library_root), "entries": len(cards)}
    if not cards:
        return out
    newest = sorted((c for c in cards if c["poster"] is not None), key=lambda c: c["mtime"], reverse=True)
    out["index"] = build_index(library_root)
    out["posters"] = [{"entry": c["name"], "path": str(c["poster"])} for c in newest[:max_posters]]
    return out


# ------------------------------------------------------------------ saving

def validate_save(
    spec: Any,
    project_root: Path,
    library_root: Path,
    poster_duration: float | None = None,
) -> tuple[dict | None, list[str]]:
    """Check a `save_to_library` request. Returns `(clean request, [])` or `(None, errors)`. Writes nothing.

    The clean request has `entry`, `components` (the names asked for), `files` (those plus every
    file they import, as file names in `<project>/components/`), `what`, `fits_when`, `props`,
    `replace`, `poster_time` and `source` (the project name).
    """
    where = "save_to_library"
    if not isinstance(spec, dict) or not spec:
        return None, [f"{where}: give {{name, components, what, fits_when}}"]
    errors = [f"{where}.{key}: unknown field (expected {', '.join(SAVE_KEYS)})" for key in spec if key not in SAVE_KEYS]

    entry = ""
    if not isinstance(spec.get("name"), str):
        errors.append(f"{where}.name: required, the entry name")
    else:
        try:
            entry = slugify(spec["name"])
        except ValueError as exc:
            errors.append(f"{where}.name: {exc}")
        else:
            if entry in RESERVED_ENTRIES:
                errors.append(f"{where}.name: {entry!r} is reserved, pick another name")

    texts: dict[str, str] = {}
    for key, limit in FIELD_LIMITS.items():
        value = spec.get(key)
        if key == "props" and value is None:
            texts[key] = ""
        elif not isinstance(value, str) or (key != "props" and not value.strip()):
            errors.append(f"{where}.{key}: required, a short text" if key != "props" else f"{where}.props: must be a string")
        elif len(_one_line(value)) > limit:
            errors.append(f"{where}.{key}: {len(_one_line(value))} characters; at most {limit}")
        else:
            texts[key] = _one_line(value)

    replace = spec.get("replace", False)
    if not isinstance(replace, bool):
        errors.append(f"{where}.replace: true or false")
    if entry and (library_root / entry).exists() and replace is not True:
        errors.append(f"{where}.name: the library already has {entry!r}; set replace=true to overwrite it or pick another name")

    at: float | None = None
    poster_time = spec.get("poster_time")
    if poster_time is not None:
        if isinstance(poster_time, bool) or not isinstance(poster_time, (int, float)) or not math.isfinite(poster_time):
            errors.append(f"{where}.poster_time: {poster_time!r} is not a number of seconds")
        elif poster_duration is not None and not 0 <= poster_time < poster_duration:
            errors.append(f"{where}.poster_time: {poster_time} is outside the video (0..{poster_duration:.2f} s)")
        else:
            at = float(poster_time)

    names = spec.get("components")
    files: list[str] = []
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        errors.append(f"{where}.components: give the component names of <project>/components, e.g. [\"Art\", \"Scenes\"]")
    else:
        bad = [n for n in names if not NAME_RE.fullmatch(n)]
        errors += [f"{where}.components: {n!r} is not a component name" for n in bad]
        missing = [n for n in names if n not in bad and not any(
            (project_root / COMPONENTS_DIR / f"{n}{ext}").is_file() for ext in (".tsx", ".ts"))]
        errors += [f"{where}.components: file not found: {COMPONENTS_DIR}/{n}.tsx in {project_root}" for n in missing]
        if not bad and not missing:
            found, scan_errors, _ = collect_files(project_root, names, library_root)
            errors += [f"{where}: {e}" for e in scan_errors]
            for item in found:
                if item.rel.startswith(f"{LIBRARY_DIR}/"):
                    errors.append(
                        f"{where}.components: {item.path.parent.name}/{item.path.name} comes from the library, not from "
                        f"this project. Save components that do not import library files"
                    )
                else:
                    files.append(item.rel)

    if errors:
        return None, errors
    return {
        "entry": entry,
        "components": list(names),
        "files": files,
        "replace": replace is True,
        "poster_time": at,
        "source": project_root.name,
        **texts,
    }, []


def write_poster(video: Path, at: float, out: Path, scratch: Path) -> None:
    """A JPEG of the frame at `at` seconds, longest side `POSTER_SIDE` px (never scaled up)."""
    scratch.mkdir(parents=True, exist_ok=True)
    frame = scratch / "poster-frame.png"
    frame.unlink(missing_ok=True)
    try:
        run_ffmpeg(["-ss", f"{at:.3f}", "-i", str(video), "-map", "0:v:0", "-frames:v", "1", str(frame)])
        with PILImage.open(frame) as grab:
            picture = grab.convert("RGB")
        picture.thumbnail((POSTER_SIDE, POSTER_SIDE), PILImage.Resampling.LANCZOS)
        staged = temp_sibling(out, ".jpg")
        try:
            picture.save(staged, format="JPEG", quality=POSTER_QUALITY, optimize=True)
            os.replace(staged, out)
        finally:
            staged.unlink(missing_ok=True)
    finally:
        frame.unlink(missing_ok=True)


def save_entry(request: dict, project_root: Path, library_root: Path, video: Path, at: float) -> dict:
    """Write one entry (the files, `card.md`, `poster.jpg` from `video` at `at` s) and rebuild `index.md`.

    The entry is built in a hidden folder first, so a failure leaves the library as it was.
    """
    entry: str = request["entry"]
    dest = library_root / entry
    staging = library_root / f".saving-{entry}"
    library_root.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        for name in request["files"]:
            shutil.copy2(project_root / COMPONENTS_DIR / name, staging / name)
        write_poster(video, at, staging / POSTER, staging)
        saved = datetime.date.today().isoformat()
        (staging / CARD).write_text(
            card_text(entry, {**request, "saved": saved}), encoding="utf-8", newline="\n"
        )
        replaced = dest.exists()
        if replaced:
            shutil.rmtree(dest)
        os.replace(staging, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    index = write_index(library_root)
    return {
        "entry": entry,
        "dir": str(dest),
        "files": list(request["files"]),
        "card": str(dest / CARD),
        "poster": str(dest / POSTER),
        "poster_t": round(at, 3),
        "index": str(index),
        "replaced": replaced,
    }

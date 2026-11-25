"""The style library: looks (background, palette, fonts, caption and plate look, transitions) saved from finished videos, kept for the next video.

Where: `<OMNIFRAME_OUTPUT_DIR>/library/<entry>/`, per user, never in the repo. One entry holds

- the component files (`.tsx`), copied from `<project>/components/` as they are;
- `card.md`: what it is, when it fits, its props, the source project, the files and how to import them;
- `poster.jpg`: a frame of the final video, longest side 512 px.

`library/index.md` is generated from the cards, one line per entry. The cards are the source of
truth: the index is rebuilt from them on every save and on every `studio_guide` call, so an entry
that is deleted or edited by hand is reflected the next time.

Saving has no tool of its own: `export_package(save_to_library=[...])` calls `validate_save` before
the export starts and `save_entry` for each item when the export succeeded (the poster comes from
the final). The model offers to save the style of a final that passes QA, and passes `save_to_library` only when the user agreed.

Versions: saving a name that exists makes the next version. `<entry>/` always holds the newest
files; older files move to `<entry>/versions/v<n>/`, and `card.md` lists every version with one
line on what changed. `card.md` also counts `times used`: `count_use` adds one each time a render
imports the entry.

Starter styles: `src/omniframe/starter_library/` ships a few styles in the wheel. The first time a
library folder is reached (`library_dir`), the starter styles it lacks are copied in, and the
folder gets the marker file `.starter_copied`. With the marker present nothing is copied again,
so a starter style the user deleted stays deleted. Deleting the marker brings them back on the
next access. Nothing already in the folder is overwritten.

Using an entry: a project component imports one of its files as
`import Boat from './library/<entry>/<File>'` (`tools/components.py` copies the files a render
needs). Whether an entry fits a new reference is the model's call; nothing here scores it.

Composed entries: a component that imports other entries can be saved too. Its card lists them
under `Uses` with the version each one had at save time (`**Uses:** neon-octopus v1, neon-bg v1`), and
the saved file imports them as `../<entry>/<File>`. Only the saved component's own files are kept
in the entry. Importing a composed entry copies the used files at the pinned versions, so an
older version stays usable after a newer one is saved. One level only: an entry that uses other
entries cannot be used by another entry or by a saved component.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from ..ffmpeg import run_ffmpeg, temp_sibling
from ..project import slugify
from .components import COMPONENTS_DIR, LIBRARY_DIR, NAME_RE, SourceFile, collect_files, scan_source

CARD = "card.md"
POSTER = "poster.jpg"
INDEX = "index.md"
USAGE = "usage.json"          # `library/usage.json`: {entry: how many renders imported it}
VERSIONS = "versions"         # `<entry>/versions/v<n>/`: the files of the older versions
POSTER_SIDE = 512             # longest side of a poster, in px
POSTER_QUALITY = 85
MAX_POSTERS = 8               # posters that `studio_guide` returns as images
# `style.ts` and `kit.ts` are the re-export files next to the entries inside a render.
RESERVED_ENTRIES = frozenset({"style", "kit"})

# Characters. `what` and `fits_when` form the one-line index entry that `studio_guide` returns.
FIELD_LIMITS = {"what": 200, "fits_when": 250, "props": 600, "changed": 200}
SAVE_KEYS = ("name", "components", "what", "fits_when", "props", "changed", "poster_time")
MAX_SAVES = 12                # items in one `save_to_library` list
VERSIONS = "versions"         # folder inside an entry that keeps the older versions
FIRST_SAVE = "first save"
OPTIONAL_FIELDS = frozenset({"props", "changed"})

_CARD_FIELDS = {
    "What": "what",
    "Fits when": "fits_when",
    "Props": "props",
    "Source project": "source",
    "Files": "files",
    "Uses": "uses",
    "Saved": "saved",
    "Version": "version",
    "Times used": "times_used",
}
_CARD_LINE = re.compile(r"^\*\*(?P<label>[^*:]+):\*\*[ \t]*(?P<value>.*)$", re.M)
_HISTORY_LINE = re.compile(r"^- v(?P<version>\d+) \((?P<when>[^,]*), from (?P<source>[^)]*)\): (?P<what>.*)$", re.M)
_USE_ITEM = re.compile(r"(?P<entry>[a-z0-9][a-z0-9-]*) v(?P<version>\d+)")
# `from './library/<entry>/<File>'` in a project component, and the same import as a saved entry keeps it.
_LIBRARY_IMPORT_TEXT = re.compile(
    r"""(?P<q>['"])\./library/(?P<entry>[a-z0-9][a-z0-9-]*)/(?P<file>[A-Za-z][A-Za-z0-9_]*)(?P=q)"""
)


# ------------------------------------------------------------------ paths

PACKAGED_STARTERS = Path(__file__).resolve().parents[1] / "starter_library"  # shipped in the wheel
STARTER_MARK = ".starter_copied"  # written into the library folder once the starter styles were copied


def starter_dir() -> Path:
    """The folder of starter styles. `OMNIFRAME_STARTER_DIR` replaces it.

    The variable is read from the environment, not patched in code, because `export_package` runs
    in a worker process that a monkeypatch in the test process cannot reach.
    """
    override = os.environ.get("OMNIFRAME_STARTER_DIR", "").strip()
    return Path(override) if override else PACKAGED_STARTERS


def library_dir(output_dir: Path) -> Path:
    """`<OMNIFRAME_OUTPUT_DIR>/library`. The first access copies in the starter styles, once (see `seed_starter_styles`)."""
    path = Path(output_dir) / LIBRARY_DIR
    try:
        seed_starter_styles(path)
    except OSError:
        pass  # a read-only library still works, just without the starter styles
    return path


def seed_starter_styles(library_root: Path) -> list[str]:
    """Copy the starter styles that `library_root` lacks, then write the marker `STARTER_MARK`.

    With the marker present this does nothing, so a starter style the user deleted stays deleted.
    An existing folder is never touched. A copy is made under a hidden name and renamed into place,
    so an interrupted copy leaves no half entry, and no marker: the next access finishes the job.
    Returns the names copied.
    """
    source_root = starter_dir()
    mark = library_root / STARTER_MARK
    if mark.exists() or not source_root.is_dir():
        return []
    library_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in sorted(source_root.iterdir()):
        target = library_root / source.name
        if not source.is_dir() or target.exists():
            continue
        staging = library_root / f".{source.name}.partial"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(source, staging)
        staging.rename(target)
        copied.append(source.name)
    mark.write_text("Starter styles were copied here once. Delete this file to copy them again.\n", encoding="utf-8")
    if copied:
        write_index(library_root)
    return copied


def project_library_dir(project_root: Path) -> Path:
    """The library that belongs to a project folder (`<output>/projects/<slug>` -> `<output>/library`)."""
    return library_dir(Path(project_root).parent.parent)


# ------------------------------------------------------------------ cards and the index

def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _uses_text(uses: list[dict[str, Any]]) -> str:
    return ", ".join(f"{use['entry']} v{use['version']}" for use in uses)


def card_text(entry: str, fields: dict[str, Any]) -> str:
    """The text of `card.md` for an entry. `history` lists the versions; the newest is the current files.

    `uses` lists the other entries whose files the entry imports, each at the version it pins.
    """
    files: list[str] = fields.get("files") or []
    uses: list[dict[str, Any]] = fields.get("uses") or []
    first = Path(files[0]).stem if files else entry
    history = fields.get("history") or [
        {"version": 1, "when": fields.get("saved", ""), "source": fields.get("source", ""), "what": FIRST_SAVE}
    ]
    lines = [
        f"# {entry}",
        "",
        f"**What:** {_one_line(fields.get('what', ''))}",
        f"**Fits when:** {_one_line(fields.get('fits_when', ''))}",
        f"**Props:** {_one_line(fields.get('props') or '(none given)')}",
        f"**Source project:** {fields.get('source', '')}",
        f"**Files:** {', '.join(files)}",
        *([f"**Uses:** {_uses_text(uses)}"] if uses else []),
        f"**Version:** {fields.get('version', 1)}",
        f"**Times used:** {fields.get('times_used', 0)}",
        f"**Saved:** {fields.get('saved', '')}",
        "",
        "## Versions",
        "",
        *[f"- v{h['version']} ({h['when']}, from {h['source']}): {_one_line(h['what'])}" for h in history],
        "",
        "Use it from a project component (the newest version):",
        "",
        "```tsx",
        f"import {first} from './{LIBRARY_DIR}/{entry}/{first}';",
        "```",
        "",
        f"`poster.jpg` is a frame of the final video of `{fields.get('source', '')}`.",
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
    fields: dict[str, Any] = {"name": folder.name}
    for match in _CARD_LINE.finditer(text):
        key = _CARD_FIELDS.get(match["label"].strip())
        if key:
            fields[key] = match["value"].strip()
    fields["files"] = [f.strip() for f in str(fields.get("files", "")).split(",") if f.strip()]
    fields["uses"] = [
        {"entry": m["entry"], "version": int(m["version"])}
        for m in (_USE_ITEM.fullmatch(part.strip()) for part in str(fields.get("uses", "")).split(","))
        if m is not None
    ]
    fields["version"] = _number(fields.get("version"), 1)
    fields["times_used"] = _number(fields.get("times_used"), 0)
    fields["history"] = [
        {"version": int(m["version"]), "when": m["when"].strip(), "source": m["source"].strip(), "what": m["what"].strip()}
        for m in _HISTORY_LINE.finditer(text)
    ] or [{"version": 1, "when": fields.get("saved", ""), "source": fields.get("source", ""), "what": FIRST_SAVE}]
    poster = folder / POSTER
    fields["poster"] = poster if poster.is_file() else None
    # Ordering for `studio_guide` posters: the poster changes on every save, the card also on every use.
    fields["mtime"] = (poster if poster.is_file() else path).stat().st_mtime_ns
    return fields


def _number(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def read_cards(library_root: Path) -> list[dict[str, Any]]:
    """Every entry of the library, sorted by name. Folders without a card are ignored."""
    if not library_root.is_dir():
        return []
    cards = [read_card(p) for p in sorted(library_root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    return [card for card in cards if card is not None]


def index_line(card: dict[str, Any]) -> str:
    times = card.get("times_used", 0)
    head = f"- **{card['name']}** (v{card.get('version', 1)}, used {times} {'time' if times == 1 else 'times'}): "
    parts = [head + card.get("what", ""), f"Fits when: {card.get('fits_when', '')}"]
    if card.get("files"):
        parts.append("Files: " + ", ".join(Path(f).stem for f in card["files"]))
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts)


def build_index(library_root: Path) -> str:
    """The text of `index.md`: a short header, then one line per entry."""
    cards = read_cards(library_root)
    lines = [
        "# OmniFrame style library",
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
) -> tuple[list[dict] | None, list[str]]:
    """Check a `save_to_library` request: one item, or a list of items (at most `MAX_SAVES`).

    Returns `(clean items, [])` or `(None, errors)`. Writes nothing. Each clean item has `entry`,
    `components` (the names asked for), `files` (the project files they need, the components and the
    project files they import, as file names in
    `<project>/components/`), `uses` (the entries the components import, at their current versions),
    `what`, `fits_when`, `props`, `changed`, `poster_time`, `exists` (the entry is already in the
    library, so this save makes a new version) and `source` (the project name).
    """
    if isinstance(spec, list):
        if not spec or len(spec) > MAX_SAVES:
            return None, [f"save_to_library: give a list of 1 to {MAX_SAVES} items"]
        items, numbered = spec, True
    else:
        items, numbered = [spec], False
    clean: list[dict] = []
    errors: list[str] = []
    entries: set[str] = set()
    for i, item in enumerate(items):
        where = f"save_to_library[{i}]" if numbered else "save_to_library"
        # checked before the item's other fields, so a clash is listed even when that item has other errors
        name = _entry_name(item)
        if name is not None:
            if name in entries:
                errors.append(f"{where}.name: {name!r} appears twice in one save")
            entries.add(name)
        request, item_errors = _validate_one(item, project_root, library_root, poster_duration, where)
        errors += item_errors
        if request is not None:
            clean.append(request)
    return (None, errors) if errors else (clean, [])


def _entry_name(item: Any) -> str | None:
    """The entry name a save item asks for (slugged), or None when the name is missing or not a valid name."""
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        return None
    try:
        return slugify(item["name"])
    except ValueError:
        return None


def _validate_one(
    spec: Any,
    project_root: Path,
    library_root: Path,
    poster_duration: float | None,
    where: str,
) -> tuple[dict | None, list[str]]:
    """Check one save item; `where` prefixes every message (`save_to_library` or `save_to_library[2]`)."""
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
        if key in OPTIONAL_FIELDS and value is None:
            texts[key] = ""
        elif not isinstance(value, str) or (key not in OPTIONAL_FIELDS and not value.strip()):
            errors.append(f"{where}.{key}: must be a string" if key in OPTIONAL_FIELDS else f"{where}.{key}: required, a short text")
        elif len(_one_line(value)) > limit:
            errors.append(f"{where}.{key}: {len(_one_line(value))} characters; at most {limit}")
        else:
            texts[key] = _one_line(value)

    exists = bool(entry) and (library_root / entry).exists()
    if exists and not texts.get("changed"):
        errors.append(f"{where}.changed: required, one line on what changed from the saved {entry!r} (it becomes the next version)")

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
    uses: list[dict[str, Any]] = []
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
                if not item.rel.startswith(f"{LIBRARY_DIR}/"):
                    files.append(item.rel)
            uses, use_errors = _direct_uses(found, project_root, library_root, where)
            errors += use_errors

    if errors:
        return None, errors
    return {
        "entry": entry,
        "components": list(names),
        "files": files,
        "uses": uses,
        "exists": exists,
        "poster_time": at,
        "source": project_root.name,
        **texts,
    }, []


def _direct_uses(
    found: list[SourceFile], project_root: Path, library_root: Path, where: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """The entries the saved components import themselves, each at its current version (the Uses line).

    Entries that those entries import are not listed: they come with the entry they belong to.
    An entry that uses other entries cannot be imported by a saved component (one level only).
    """
    uses: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in found:
        if item.rel.startswith(f"{LIBRARY_DIR}/"):
            continue
        _, _, local = scan_source(item.path, project_root, library_root)
        for dep in local:
            if not dep.rel.startswith(f"{LIBRARY_DIR}/"):
                continue
            name = dep.rel.split("/")[1]
            card = read_card(library_root / name)
            if card is None:
                errors.append(f"{where}.components: {name} is not an entry of the library")
            elif card["uses"]:
                errors.append(
                    f"{where}.components: {name} uses other entries itself; chains are one level deep, "
                    "so a saved component cannot import it"
                )
            elif all(use["entry"] != name for use in uses):
                uses.append({"entry": name, "version": card["version"]})
    return uses, errors


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


def _keep_previous_version(dest: Path, previous: dict, staging: Path) -> None:
    """Copy the older versions and the files of the newest version into `staging/versions/`."""
    if (dest / VERSIONS).is_dir():
        shutil.copytree(dest / VERSIONS, staging / VERSIONS)
    archive = staging / VERSIONS / f"v{previous['version']}"
    archive.mkdir(parents=True, exist_ok=True)
    for name in [*previous["files"], POSTER, CARD]:
        if (dest / name).is_file():
            shutil.copy2(dest / name, archive / name)


def _saved_source(text: str) -> str:
    """A project component as the entry keeps it: `./library/<entry>/<File>` becomes `../<entry>/<File>`.

    Inside the library every entry is a sibling folder, so a used entry is reached that way in a render.
    Other text is kept as it is.
    """
    return _LIBRARY_IMPORT_TEXT.sub(lambda m: f"{m['q']}../{m['entry']}/{m['file']}{m['q']}", text)


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
        previous = read_card(dest)  # None for a new entry
        history = list(previous["history"]) if previous else []
        version = previous["version"] + 1 if previous else 1
        times_used = previous["times_used"] if previous else 0
        if previous:
            _keep_previous_version(dest, previous, staging)
        for name in request["files"]:
            source = (project_root / COMPONENTS_DIR / name).read_text(encoding="utf-8")
            (staging / name).write_text(_saved_source(source), encoding="utf-8", newline="\n")
        write_poster(video, at, staging / POSTER, staging)
        saved = datetime.date.today().isoformat()
        history.append({
            "version": version,
            "when": saved,
            "source": request["source"],
            "what": FIRST_SAVE if version == 1 else request["changed"],
        })
        fields = {**request, "saved": saved, "version": version, "times_used": times_used, "history": history}
        (staging / CARD).write_text(card_text(entry, fields), encoding="utf-8", newline="\n")
        replaced = previous is not None
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
        "version": version,
        "times_used": times_used,
    }


def count_use(library_root: Path, entries: list[str]) -> None:
    """Add one to `times used` in the card of each entry a render imported, then rebuild `index.md`.

    Called once per render job (components.py), so a render that uses an entry counts once.
    """
    changed = False
    for entry in entries:
        card = read_card(library_root / entry)
        if card is None:
            continue
        card["times_used"] += 1
        (library_root / entry / CARD).write_text(card_text(entry, card), encoding="utf-8", newline="\n")
        changed = True
    if changed:
        write_index(library_root)

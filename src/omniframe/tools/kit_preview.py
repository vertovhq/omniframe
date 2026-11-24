"""Contact strips of the motion kit: one rendered frame per block, so the model sees a block before it picks it.

`studio_guide(kit_group="hud")` returns the group's text (`engine/src/kit/groups/hud.md`) and its
strip. A strip is built once per kit version: `engine/src/custom/previews/<group>.tsx` lists the
blocks (`{name: 'Block', at: seconds, node: ...}`, one `SLOT_S` slot each), a throw-away project
plays them as one custom scene, one still per block is rendered (16:9) and the stills are laid out
in a grid with the block names under them. The image is cached in `<OMNIFRAME_OUTPUT_DIR>/kit_previews/`
under a hash of the preview files and the kit sources, so a change to the kit rebuilds it.

Building takes a minute or two (the engine is bundled), so `strip_for_guide` starts it as a
detached job (`kit_preview`) when the image is not cached yet and the model polls `job_status`.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import jobs
from ..config import CONFIG
from ..project import project_dir

PREVIEW_PROJECT = "kit-preview"
PREVIEW_COMPONENT = "KitPreview"
SHEET_COMPONENT = "KitSheet"
SLOT_S = 2.0                     # seconds per block; must equal SLOT in engine/src/custom/previews/KitSheet.tsx
TAIL_S = 1.0                     # after the last slot, so the scene's fade-out does not touch the last still
COLUMNS = 3
TILE_W = 384                     # a 16:9 tile; three columns stay under 1.3k px wide
GAP = 6
CAPTION_H = 30
STRIP_QUALITY = 82
STRIP_MAX_SIDE = 1600            # `image_max_side` of the job result: the strip is taller than one frame
LAYOUT_VERSION = "1"             # bump when the tile layout changes, so cached strips are rebuilt
GROUP_ORDER = ("core", "backgrounds", "transitions", "energy", "hud", "type", "bursts", "depth", "camera", "info")

# `{name: 'Block', at: 1.2, ...` in a preview file; `at` is the second inside the slot the still is taken at.
_BLOCK_RE = re.compile(r"\{name: '(?P<name>\w+)', at: (?P<at>\d+(?:\.\d+)?)")

Report = Callable[..., None]


# ------------------------------------------------------------------ files

def _engine_src() -> Path:
    from .render import engine_dir  # imported here: render pulls in the whole renderer

    return engine_dir() / "src"


def groups_dir() -> Path:
    return _engine_src() / "kit" / "groups"


def previews_dir() -> Path:
    return _engine_src() / "custom" / "previews"


def cache_dir() -> Path:
    return Path(CONFIG.output_dir) / "kit_previews"


def group_names() -> list[str]:
    """The kit groups that have a text file, in catalogue order."""
    found = {p.stem for p in groups_dir().glob("*.md")} if groups_dir().is_dir() else set()
    return [g for g in GROUP_ORDER if g in found] + sorted(found - set(GROUP_ORDER))


def group_doc(group: str) -> str:
    """The text file of one kit group."""
    return (groups_dir() / f"{group}.md").read_text(encoding="utf-8")


def preview_blocks(group: str) -> list[tuple[str, float]]:
    """`(block name, seconds into its slot)` of a group's preview, in order."""
    text = (previews_dir() / f"{group}.tsx").read_text(encoding="utf-8")
    return [(m["name"], float(m["at"])) for m in _BLOCK_RE.finditer(text)]


def signature(group: str) -> str:
    """Short hash of everything a strip depends on: the preview files, the kit sources and the layout."""
    digest = hashlib.sha256(LAYOUT_VERSION.encode())
    files = [previews_dir() / f"{SHEET_COMPONENT}.tsx", previews_dir() / f"{group}.tsx"]
    files += sorted((_engine_src() / "kit").glob("*.ts*"))
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:12]


def strip_path(group: str) -> Path:
    return cache_dir() / f"{group}-{signature(group)}.jpg"


def cached_strip(group: str) -> Path | None:
    path = strip_path(group)
    return path if path.is_file() else None


# ------------------------------------------------------------------ the image

def compose_strip(frames: list[Path], names: list[str], out: Path) -> Path:
    """Lay the frames out in a grid with the block names under them and save a JPEG at `out`."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=17)
    except TypeError:  # Pillow before 10.1 has no sized default font
        font = ImageFont.load_default()
    tiles = []
    for path in frames:
        with Image.open(path) as img:
            tiles.append(img.convert("RGB").resize((TILE_W, round(TILE_W * img.height / img.width)), Image.Resampling.LANCZOS))
    tile_h = max(t.height for t in tiles)
    rows = -(-len(tiles) // COLUMNS)
    cell_h = tile_h + CAPTION_H
    sheet = Image.new("RGB", (COLUMNS * TILE_W + (COLUMNS + 1) * GAP, rows * cell_h + (rows + 1) * GAP), (18, 20, 28))
    draw = ImageDraw.Draw(sheet)
    for i, (tile, name) in enumerate(zip(tiles, names)):
        x = GAP + (i % COLUMNS) * (TILE_W + GAP)
        y = GAP + (i // COLUMNS) * (cell_h + GAP)
        sheet.paste(tile, (x, y))
        draw.text((x + 6, y + tile_h + 5), name, fill=(235, 238, 245), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    sheet.save(tmp, format="JPEG", quality=STRIP_QUALITY)
    tmp.replace(out)
    return out


def build_strip(group: str, report: Report | None = None) -> Path:
    """Render the stills of a group and compose its strip (blocks until done; use inside a job)."""
    from . import render

    if group not in group_names():
        raise ValueError(f"unknown kit group {group!r} (groups: {', '.join(group_names())})")
    blocks = preview_blocks(group)
    if not blocks:
        raise ValueError(f"engine/src/custom/previews/{group}.tsx lists no blocks")
    note = report or (lambda *args, **kwargs: None)
    root = project_dir(PREVIEW_PROJECT)
    components = root / "components"
    components.mkdir(parents=True, exist_ok=True)
    for name, source in ((SHEET_COMPONENT, SHEET_COMPONENT), (PREVIEW_COMPONENT, group)):
        text = (previews_dir() / f"{source}.tsx").read_text(encoding="utf-8")
        (components / f"{name}.tsx").write_text(text, encoding="utf-8")
    plan: dict[str, Any] = {
        "version": 2,
        "format": "16:9",
        "duration": len(blocks) * SLOT_S + TAIL_S,
        "style": "dark",
        "scenes": [{"kind": "custom", "at": 0, "component": PREVIEW_COMPONENT}],
    }
    times = [round(i * SLOT_S + at, 3) for i, (_, at) in enumerate(blocks)]
    payload, errors = render.prepare_render(
        plan, root, mode="stills", times=[times[0]], compare=None, format="16:9", name=f"strip-{group}",
    )
    if payload is None:
        raise RuntimeError("the kit preview plan was refused: " + "; ".join(errors))
    payload["times"] = times  # more than `MAX_STILLS`: the cap is for what a model asks, not for this job
    result = render.run_job(payload, note)
    if result.get("valid") is False:
        raise RuntimeError("the kit preview did not compile: " + "; ".join(result.get("errors", [])[:6]))
    frames = [Path(p) for p in result["stills"]]
    note(0.97, "composing the strip")
    out = strip_path(group)
    for old in out.parent.glob(f"{group}-*.jpg"):
        old.unlink(missing_ok=True)
    compose_strip(frames, [name for name, _ in blocks], out)
    for frame in frames:
        frame.unlink(missing_ok=True)
    shutil.rmtree(root / ".work", ignore_errors=True)
    return out


def run_job(payload: dict, report: Report) -> dict:
    """Worker side (job kind `kit_preview`): build the strip of `payload["group"]`."""
    group = str(payload["group"])
    out = build_strip(group, report)
    names = [name for name, _ in preview_blocks(group)]
    return {
        "group": group,
        "blocks": names,
        "images": [{"path": str(out)}],
        "image_max_side": STRIP_MAX_SIDE,
        "note": f"contact strip of the `{group}` kit group, one frame per block in the order: {', '.join(names)}",
    }


# ------------------------------------------------------------------ for studio_guide

def strip_for_guide(group: str) -> dict:
    """The strip of a group for `studio_guide`: its file when cached, else a detached build to poll.

    Returns `{"strip": {"path": ..., "blocks": [...]}}` or `{"strip": {"state": "building", "job_id": ...}}`.
    """
    names = [name for name, _ in preview_blocks(group)]
    cached = cached_strip(group)
    if cached is not None:
        return {"strip": {"path": str(cached), "blocks": names}}
    job_id = jobs.start("kit_preview", {"group": group}, key=f"kit-preview-{group}-{signature(group)}")
    return {
        "strip": {
            "state": "building",
            "job_id": job_id,
            "blocks": names,
            "note": "the contact strip is rendered once per kit version (about a minute); read the text now, "
                    "call job_status with this job_id to get the image, or call studio_guide again later",
        }
    }

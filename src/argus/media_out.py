"""Pictures for the model (design §4).

`prepare_image` makes a small JPEG copy of a frame, `tool_result` packs a JSON summary
plus those copies into the list that MCP clients render as text + image content.
The summary always lists every image path, so a client that does not show image
content still lets the model open the files with its own file tools.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageOps

try:
    # mcp >= 2.x
    from mcp.server.mcpserver.utilities.types import Image
except ImportError:  # pragma: no cover
    # mcp 1.x (FastMCP era), same helper class
    from mcp.server.fastmcp.utilities.types import Image  # type: ignore[no-redef]

from . import __version__
from .ffmpeg import temp_sibling

DEFAULT_MAX_SIDE = 1024
DEFAULT_QUALITY = 85
VIEW_SUFFIX = ".view.jpg"
_EXIF_ORIENTATION = 0x0112
_EXIF_SWAPS_AXES = (5, 6, 7, 8)  # transposed / rotated by 90 degrees

__all__ = ["DEFAULT_MAX_SIDE", "Image", "prepare_image", "tool_result"]


def _target_size(size: tuple[int, int], max_side: int) -> tuple[int, int]:
    """`size` scaled down so the longest side is at most `max_side` (never scaled up)."""
    width, height = size
    longest = max(width, height)
    if longest <= max_side:
        return width, height
    scale = max_side / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def prepare_image(path: str | Path, max_side: int = DEFAULT_MAX_SIDE, quality: int = DEFAULT_QUALITY) -> Path:
    """Downscaled JPEG copy of `path`, saved next to it as `<name>.view.jpg`.

    The longest side becomes at most `max_side` px (smaller images keep their size).
    An existing copy is reused when it is at least as new as the source and has the
    size this call would produce. A source that already is a small `.view.jpg` is
    returned as is.
    """
    if max_side < 1:
        raise ValueError(f"max_side must be >= 1, got {max_side}")
    src = Path(path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"image not found: {src}")

    with PILImage.open(src) as probe:
        size = probe.size
        if probe.getexif().get(_EXIF_ORIENTATION) in _EXIF_SWAPS_AXES:
            size = (size[1], size[0])  # the view is rotated upright, so width and height swap
        target = _target_size(size, max_side)
        unchanged = size == target

    if src.name.lower().endswith(VIEW_SUFFIX) and unchanged:
        return src

    view = src.with_name(src.name.rsplit(".", 1)[0] + VIEW_SUFFIX)
    if view.is_file() and view.stat().st_mtime >= src.stat().st_mtime:
        try:
            with PILImage.open(view) as cached:
                if cached.size == target:
                    return view
        except OSError:  # unreadable leftovers are rebuilt below
            pass

    with PILImage.open(src) as img:
        img = ImageOps.exif_transpose(img)
        if img.size != target:
            img = img.convert("RGB").resize(target, PILImage.Resampling.LANCZOS)
        elif img.mode != "RGB":
            img = img.convert("RGB")
        # write to a temp file first so a reader never sees a half-written JPEG
        staged = temp_sibling(view, ".tmp")
        try:
            img.save(staged, format="JPEG", quality=quality, optimize=True)
            os.replace(staged, view)
        finally:
            staged.unlink(missing_ok=True)
    return view


def tool_result(
    summary: dict,
    images: Sequence[str | Path],
    *,
    max_side: int = DEFAULT_MAX_SIDE,
) -> list:
    """`[summary_json_text, Image, Image, ...]`: what a tool returns when it has pictures.

    Each image is downscaled with `prepare_image`. `summary["images"]` lists one
    `{"path": ...}` entry per image in the same order as the Image items. When the
    caller already put a list of the same length under `summary["images"]` (for
    example `{"t": 12.5}` per frame), those entries are kept and only `path` is set.
    `summary` gets `"engine"` if it has none. The input dict is not modified.
    """
    views = [prepare_image(p, max_side=max_side) for p in images]
    given = summary.get("images")
    entries: list[dict] = []
    for i, view in enumerate(views):
        base = given[i] if isinstance(given, list) and len(given) == len(views) and isinstance(given[i], dict) else {}
        entries.append({**base, "path": str(view)})

    out = {"engine": f"ARGUS {__version__}", **summary, "images": entries}
    return [json.dumps(out, ensure_ascii=False, indent=2, default=str), *[Image(path=v) for v in views]]

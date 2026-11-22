"""Reply-size log (20.10 item 19).

Every MCP tool reply that names a project appends one JSON line to
`<project>/.work/economy.jsonl`: the tool, the characters of text, the pictures with their
pixel sizes, and the seconds ARGUS spent. ARGUS writes the log and the model never reads it,
so the log costs no tokens. `totals` sums it for `export_package`.
"""

from __future__ import annotations

import functools
import inspect
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from .config import CONFIG
from .media_out import Image
from .project import slugify

LOG_NAME = "economy.jsonl"


def _pixels(image: Any) -> list[int] | None:
    """`[width, height]` of an MCP image, read from its file when it has one."""
    path = getattr(image, "path", None)
    try:
        if path is not None:
            with PILImage.open(path) as opened:
                return list(opened.size)
    except OSError:
        return None
    return None


def measure(reply: Any) -> tuple[int, list[list[int] | None]]:
    """Characters of text in a reply and the pixel size of each picture it carries."""
    items = reply if isinstance(reply, list) else [reply]
    chars = 0
    sizes: list[list[int] | None] = []
    for item in items:
        if isinstance(item, Image):
            sizes.append(_pixels(item))
        elif isinstance(item, str):
            chars += len(item)
        else:
            chars += len(json.dumps(item, ensure_ascii=False, default=str))
    return chars, sizes


def log_path(project: str) -> Path:
    """`<output_dir>/projects/<slug>/.work/economy.jsonl` (no folder is created)."""
    return CONFIG.output_dir / "projects" / slugify(project) / ".work" / LOG_NAME


def record(project: str, tool: str, reply: Any, seconds: float) -> None:
    """Append one line for `tool`. Logging never raises: a failed write must not fail the tool."""
    try:
        chars, sizes = measure(reply)
        path = log_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"tool": tool, "chars": chars, "images": sizes, "seconds": round(seconds, 2)}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    except (OSError, ValueError, TypeError):
        return


def totals(project: str) -> dict:
    """Sum of the project's log: calls, characters, pictures, seconds."""
    path = log_path(project)
    out = {"calls": 0, "chars": 0, "images": 0, "seconds": 0.0}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        out["calls"] += 1
        out["chars"] += int(line.get("chars", 0))
        out["images"] += len(line.get("images", []))
        out["seconds"] += float(line.get("seconds", 0.0))
    out["seconds"] = round(out["seconds"], 1)
    return out


def measured(fn: Callable) -> Callable:
    """Wrap a tool so that each reply with a `project` argument is logged."""

    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        started = time.monotonic()
        reply = fn(*args, **kwargs)
        bound = signature.bind_partial(*args, **kwargs).arguments
        project = bound.get("project")
        if isinstance(project, str) and project.strip():
            record(project, fn.__name__, reply, time.monotonic() - started)
        return reply

    return wrapper

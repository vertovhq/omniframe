"""Project stage in `<project>/.work/state.json` (task 20.10 item 24).

Tools write the stage of a project here (the plan, the last render, the voice files, the last export),
so that after context compaction or in a new chat `studio_guide(project=...)` can add a resume of at
most `MAX_RESUME_LINES` lines. The model never writes this file and never has to read it.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .config import CONFIG
from .project import slugify

STATE_NAME = "state.json"
MAX_RESUME_LINES = 5


def state_path(project: str) -> Path:
    """`<output_dir>/projects/<slug>/.work/state.json` (no folder is created)."""
    return CONFIG.output_dir / "projects" / slugify(project) / ".work" / STATE_NAME


def load(project: str) -> dict:
    """The project's state, or {} when it is missing or unreadable."""
    path = state_path(project)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(project: str, **fields: Any) -> None:
    """Merge `fields` into the project's state. A failed write is ignored: state must never fail a tool."""
    try:
        data = load(project)
        data.update(fields)
        path = state_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, path)
    except (OSError, ValueError, TypeError):
        return


def resume_lines(project: str) -> list[str]:
    """At most `MAX_RESUME_LINES` lines that say where the project stands. Empty when nothing is recorded."""
    data = load(project)
    lines: list[str] = []
    if data.get("plan"):
        lines.append(f"plan: {data['plan']}")
    render = data.get("last_render")
    if isinstance(render, dict):
        job = f", job {render['job_id']}" if render.get("job_id") else ""
        lines.append(f"last render: {render.get('mode', '?')}{job}; {render.get('summary', '')}".rstrip("; "))
    if data.get("voice"):
        lines.append(f"voice: {data['voice']}")
    if data.get("last_export"):
        lines.append(f"last export: {data['last_export']}")
    return lines[:MAX_RESUME_LINES]

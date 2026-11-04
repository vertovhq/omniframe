"""Durable production memory: append verified lessons to KNOWLEDGE_BASE.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import CONFIG


def learn_and_record_memory(
    lesson_title: str,
    user_directive: str,
    technical_rule: str,
    knowledge_base_path: str | Path | None = None,
) -> dict:
    """Record a verified lesson so it survives across sessions."""
    path = Path(knowledge_base_path) if knowledge_base_path else CONFIG.knowledge_base
    path.parent.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {lesson_title.strip()}\n"
        f"- **Recorded:** {stamp}\n"
        f"- **User directive:** {user_directive.strip()}\n"
        f"- **Technical rule:** {technical_rule.strip()}\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        if path.stat().st_size == 0:
            fh.write("# ARGUS — Production Knowledge Base\n")
        fh.write(entry)

    return {"recorded": str(path), "lesson": lesson_title.strip()}

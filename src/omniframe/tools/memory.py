"""User preferences that survive across sessions (the knowledge base file).

`learn_and_record_memory` appends one entry; `studio_guide` returns the tail of
the same file at the start of the next session (see `tools/studio.py`).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import CONFIG
from .. import __version__

HEADER = "# OmniFrame — user preferences\n"


def learn_and_record_memory(
    lesson_title: str,
    user_directive: str,
    technical_rule: str,
    knowledge_base_path: str | Path | None = None,
) -> dict:
    """Append one lasting user preference or correction to the knowledge base file.

    A new file starts with the header `# OmniFrame — user preferences`.
    """
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
            fh.write(HEADER)
        fh.write(entry)

    return {"engine": f"OmniFrame {__version__}", "recorded": str(path), "lesson": lesson_title.strip()}

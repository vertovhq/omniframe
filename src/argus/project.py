"""Per-project folders under OMNIFRAME_OUTPUT_DIR (design §3).

Layout: `<output_dir>/projects/<slug>/` with the folders in `PROJECT_FOLDERS`.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .config import CONFIG

PROJECT_FOLDERS = ("refs", "audio", "components", "cache", "renders", "final", ".work")
MAX_SLUG_LEN = 48

# Cyrillic -> Latin, so Russian project names keep a readable folder name.
_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(name: str) -> str:
    """Folder-safe slug matching `[a-z0-9-]{1,48}`.

    Raises ValueError when the name has no letters or digits left.
    """
    text = "".join(_CYRILLIC.get(ch, ch) for ch in name.strip().lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:MAX_SLUG_LEN].rstrip("-")
    if not text:
        raise ValueError(f"project name {name!r} has no letters or digits to build a folder name")
    return text


def project_dir(name: str) -> Path:
    """Return `<output_dir>/projects/<slug>` and create its folders if missing."""
    root = CONFIG.output_dir / "projects" / slugify(name)
    for folder in PROJECT_FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root

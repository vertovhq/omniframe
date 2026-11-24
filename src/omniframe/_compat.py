"""Support for the old ARGUS names. The project is now called OmniFrame.

- `ARGUS_*` environment variables still work. Each one is copied to its
  `OMNIFRAME_*` name when that name is not set. The package runs this on import,
  and config runs it again after it reads the `.env` file.
- The home folder is `~/.omniframe`. A user who has only `~/.argus` keeps using it.
"""

from __future__ import annotations

import os
from pathlib import Path

NEW_PREFIX = "OMNIFRAME_"
OLD_PREFIX = "ARGUS_"


def mirror_legacy_env() -> None:
    """Copy each set `ARGUS_<name>` to `OMNIFRAME_<name>` when the new name is empty or missing."""
    for key in list(os.environ):
        if not key.startswith(OLD_PREFIX):
            continue
        new_key = NEW_PREFIX + key[len(OLD_PREFIX):]
        if not os.environ.get(new_key, "").strip():
            os.environ[new_key] = os.environ[key]


def omniframe_home() -> Path:
    """`~/.omniframe`, or `~/.argus` when only the old folder exists."""
    new = Path.home() / ".omniframe"
    old = Path.home() / ".argus"
    if not new.exists() and old.exists():
        return old
    return new

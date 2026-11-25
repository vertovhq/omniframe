"""Shared test setup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def no_starter_styles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with an empty library: the starter folder is a path that does not exist.

    It is set in the environment, not patched in code, because `export_package` runs in a worker
    process and that process must see the same setting. Only the starter-library tests point the
    variable at the real folder.
    """
    monkeypatch.setenv("OMNIFRAME_STARTER_DIR", str(tmp_path / "no-starter-styles"))

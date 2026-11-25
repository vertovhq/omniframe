"""The starter styles: copied into a library on first access, once, and an existing entry is never overwritten.

All offline: temporary folders only. The real starter folder is read, never written.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe.tools import library  # noqa: E402

REAL_STARTER_DIR = Path(__file__).resolve().parents[1] / "src" / "omniframe" / "starter_library"
STARTERS = ("style-kraft-collage", "style-neon-space", "style-tech-telemetry")


@pytest.fixture
def real_starters(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OMNIFRAME_STARTER_DIR", str(REAL_STARTER_DIR))
    return REAL_STARTER_DIR


def test_first_access_copies_every_starter_style(real_starters: Path, tmp_path: Path) -> None:
    lib = library.library_dir(tmp_path / "out")

    for name in STARTERS:
        for file in ("card.md", "poster.jpg", "StyleKit.tsx"):
            copied = lib / name / file
            assert copied.read_bytes() == (real_starters / name / file).read_bytes()
    assert sorted(p.name for p in lib.iterdir() if p.is_dir()) == sorted(STARTERS)
    assert all(not p.name.endswith(".partial") for p in lib.iterdir())
    assert all(f"**{name}**" in (lib / "index.md").read_text(encoding="utf-8") for name in STARTERS)
    assert (lib / library.STARTER_MARK).is_file()


def test_an_existing_entry_is_not_overwritten(real_starters: Path, tmp_path: Path) -> None:
    lib = tmp_path / "library"
    mine = lib / "style-neon-space"
    mine.mkdir(parents=True)
    (mine / "card.md").write_text("my own card", encoding="utf-8")
    (mine / "StyleKit.tsx").write_text("// my own file", encoding="utf-8")

    copied = library.seed_starter_styles(lib)

    assert sorted(copied) == ["style-kraft-collage", "style-tech-telemetry"]
    assert (mine / "card.md").read_text(encoding="utf-8") == "my own card"
    assert (mine / "StyleKit.tsx").read_text(encoding="utf-8") == "// my own file"
    assert not (mine / "poster.jpg").exists()  # the starter poster is not added to the user's folder


def test_a_deleted_starter_style_stays_deleted_when_the_marker_is_there(real_starters: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    lib = library.library_dir(out)
    assert (lib / library.STARTER_MARK).is_file()
    shutil.rmtree(lib / "style-neon-space")

    library.library_dir(out)  # the same process, a later access
    assert library.seed_starter_styles(lib) == []  # a later process, the same
    assert not (lib / "style-neon-space").exists()


def test_deleting_the_marker_brings_the_starter_styles_back(real_starters: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    lib = library.library_dir(out)
    shutil.rmtree(lib / "style-neon-space")
    (lib / library.STARTER_MARK).unlink()

    assert library.seed_starter_styles(lib) == ["style-neon-space"]
    assert (lib / "style-neon-space" / "card.md").is_file()

"""Task 20.10 item 5(c): a stills job lists every missing media file at once, as text, and draws nothing.
Preview and final renders still stop at the first missing file.

Offline: exercises `_PublicDir`, the part of the job that resolves media names.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.tools import render  # noqa: E402


def test_stills_collect_every_missing_file(tmp_path: Path) -> None:
    public = render._PublicDir(tmp_path / "public", [tmp_path], collect=True)

    assert public.add("a.png", "scenes[0].media") == "a.png"
    assert public.add("b.mp3", "audio.sfx[1].src") == "b.mp3"

    assert public.missing == [
        "scenes[0].media: file not found: a.png",
        "audio.sfx[1].src: file not found: b.mp3",
    ]


def test_other_renders_still_raise_on_the_first_missing_file(tmp_path: Path) -> None:
    public = render._PublicDir(tmp_path / "public", [tmp_path])

    with pytest.raises(FileNotFoundError, match="scenes\\[0\\].media: file not found: a.png"):
        public.add("a.png", "scenes[0].media")

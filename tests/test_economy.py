"""Task 20.10 economy items: short tool texts, one contact sheet by default, unchanged pictures and guide
reads are not sent again, a summary sentence on every job reply, and the `then` steps of a final render.

Offline. The render cases use a temporary output folder and no engine.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs, project  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.tools import render, studio, watch  # noqa: E402

TOOL_TEXT_LIMIT = 14000  # all tool descriptions together (was 23,296 before task 20.10 item 14)


@pytest.fixture(autouse=True)
def economy_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (jobs, project, render, studio):
        monkeypatch.setattr(module, "CONFIG", cfg)


# ------------------------------------------------------------------ item 14: tool texts

def test_tool_descriptions_stay_under_the_limit() -> None:
    from omniframe import server

    total = sum(len(inspect.getdoc(getattr(server, name)) or "") for name in server._registered_tool_names())
    assert total <= TOOL_TEXT_LIMIT, total


# ------------------------------------------------------------------ item 15: a guide read once per run

def test_a_repeated_guide_read_is_one_line_until_full_is_asked() -> None:
    studio._SENT.pop("guide-test", None)
    first = studio.once("guide-test", {"guide": "text"})
    assert first == {"guide": "text"}
    again = studio.once("guide-test", {"guide": "text"})
    assert again["unchanged"] is True and "pass full=true" in again["note"]
    assert studio.once("guide-test", {"guide": "text"}, full=True) == {"guide": "text"}
    assert studio.once("guide-test", {"guide": "changed"})["guide"] == "changed"  # new content goes out in full


def test_guide_and_kit_reads_have_their_own_keys() -> None:
    studio._SENT.pop("kit:hud", None)
    studio.once("kit:hud", {"text": "hud"})
    assert studio.once("guide", {"guide": "g"}) == {"guide": "g"}  # another key is not affected


# ------------------------------------------------------------------ item 8: a summary on every job reply

def test_summary_says_what_runs_and_what_is_left() -> None:
    text = jobs.summarize({"kind": "render", "state": "running", "progress": 0.5, "note": "frames", "eta_s": 90})
    assert text == "render is running at 50 % (frames), about 1 min 30 s left."


def test_summary_of_a_failure_names_the_cause() -> None:
    text = jobs.summarize({"kind": "voiceover", "state": "error", "error": "ElevenLabs HTTP 429: slow down\nmore"})
    assert text.startswith("voiceover failed: ElevenLabs HTTP 429: slow down.")
    assert "\n" not in text


def test_done_summary_is_short() -> None:
    assert jobs.summarize({"kind": "export", "state": "done"}) == "export finished."


# ------------------------------------------------------------------ items 1 and 2: one sheet of 12 frames

def test_watch_default_is_one_sheet_of_twelve_frames() -> None:
    assert watch.DEFAULT_MAX_FRAMES == 12
    assert watch.TILES_PER_SHEET == 12
    cols, rows, tile_w, tile_h = watch._sheet_layout(1080, 1920)
    assert (cols, rows) == (3, 4)
    sheet_h = rows * tile_h + (rows + 1) * watch.SHEET_GAP
    assert sheet_h <= 1280 and watch.SHEET_MAX_SIDE == 1280
    cols, rows, tile_w, tile_h = watch._sheet_layout(1920, 1080)
    assert (cols, rows) == (4, 3)


# ------------------------------------------------------------------ item 16: pictures already sent are not sent again

def test_unchanged_picture_is_listed_by_hash_and_drawn_as_a_grey_cell(tmp_path: Path) -> None:
    red = tmp_path / "red.png"
    PILImage.new("RGB", (90, 160), (200, 10, 10)).save(red)
    assert render._file_hash(red) == render._file_hash(red)
    stored = tmp_path / "stills-sent.json"
    render._write_hashes(stored, [render._file_hash(red)])
    assert render._read_hashes(stored) == {render._file_hash(red)}
    assert render._read_hashes(tmp_path / "missing.json") == set()

    out = tmp_path / "sheet.jpg"
    render.build_contact_sheet([(red, "t 1.00 s"), (None, "t 2.00 s")], out)
    with PILImage.open(out) as sheet:
        cw = sheet.width // 2
        grey = sheet.getpixel((cw + cw // 2, sheet.height // 3))
    assert all(abs(a - b) <= 3 for a, b in zip(grey, (44, 44, 52)))


# ------------------------------------------------------------------ item 5: `then` steps of a final render

def _plan() -> dict:
    return {"version": 2, "format": "9:16", "duration": 3, "style": "dark",
            "scenes": [{"kind": "big", "at": 0, "text": "OmniFrame"}]}


def test_then_accepts_only_qa_and_only_on_a_final() -> None:
    bad_step = render.render_video(_plan(), "t", mode="final", then=["export"])
    assert bad_step["valid"] is False and "export" in bad_step["errors"][0]
    not_final = render.render_video(_plan(), "t", mode="preview", then=["qa"])
    assert not_final["valid"] is False and "final" in not_final["errors"][0]

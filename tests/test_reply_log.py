"""Task 20.10 item 19: every tool reply with a project adds one line to `<project>/.work/economy.jsonl`,
and `export_package` returns the totals as `economy`.

Offline. Uses a temporary output folder.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import economy  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.media_out import Image  # noqa: E402


@pytest.fixture(autouse=True)
def log_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(economy, "CONFIG", dataclasses.replace(CONFIG, output_dir=tmp_path / "out"))


def _lines(project: str) -> list[dict]:
    path = economy.log_path(project)
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines()]


def test_dict_reply_is_logged_with_chars_and_no_images() -> None:
    @economy.measured
    def tool(project: str) -> dict:
        return {"summary": "done", "n": 3}

    tool(project="demo")
    (line,) = _lines("demo")
    assert line["tool"] == "tool"
    assert line["chars"] == len(json.dumps({"summary": "done", "n": 3}, ensure_ascii=False))
    assert line["images"] == []
    assert line["seconds"] >= 0


def test_picture_sizes_are_logged(tmp_path: Path) -> None:
    picture = tmp_path / "frame.png"
    PILImage.new("RGB", (640, 360)).save(picture)

    @economy.measured
    def tool(project: str) -> list:
        return ["summary text", Image(path=picture)]

    tool(project="demo")
    (line,) = _lines("demo")
    assert line["chars"] == len("summary text")
    assert line["images"] == [[640, 360]]


def test_calls_without_a_project_are_not_logged() -> None:
    @economy.measured
    def tool(path: str) -> dict:
        return {"ok": True}

    tool(path="x.mp4")
    assert not economy.log_path("x").exists()


def test_totals_add_up_over_calls() -> None:
    @economy.measured
    def tool(project: str, text: str) -> dict:
        return {"text": text}

    tool(project="demo", text="a" * 10)
    tool(project="demo", text="b" * 20)
    totals = economy.totals("demo")
    assert totals["calls"] == 2
    assert totals["chars"] == len('{"text": "' + "a" * 10 + '"}') + len('{"text": "' + "b" * 20 + '"}')
    assert totals["images"] == 0


def test_a_failed_log_write_does_not_fail_the_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    monkeypatch.setattr(economy, "log_path", lambda project: blocker / "economy.jsonl")

    @economy.measured
    def tool(project: str) -> dict:
        return {"ok": True}

    assert tool(project="demo") == {"ok": True}


def test_server_tools_are_wrapped_and_keep_their_names() -> None:
    from argus import server

    names = server._registered_tool_names()
    assert "render_video" in names and "export_package" in names
    assert server.render_video.__name__ == "render_video"

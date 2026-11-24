"""Task 20.10 item 20: the tool surface sent on every turn (descriptions plus input schemas) stays small,
and the merged tool is gone: `download_sfx` is `search_sfx(download=[...], out_dir=...)`.

Offline: reads the registered tools of the server, no calls.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import server  # noqa: E402

SURFACE_LIMIT = 9200  # descriptions + input schemas of all tools, characters (20.10 item 20; 9000 before the voice overwrite flag)


def _tools() -> list:
    return list(server.mcp._tool_manager.list_tools())


def _schema(tool) -> dict:
    return getattr(tool, "parameters", None) or getattr(tool, "inputSchema", None) or {}


def surface_size() -> int:
    return sum(
        len(tool.description or "") + len(json.dumps(_schema(tool), separators=(",", ":"), ensure_ascii=False))
        for tool in _tools()
    )


def test_descriptions_and_schemas_stay_under_the_limit() -> None:
    assert surface_size() <= SURFACE_LIMIT, surface_size()


def test_merged_tools_are_gone_and_their_options_exist() -> None:
    names = {tool.name for tool in _tools()}
    assert "download_sfx" not in names
    assert "download" in inspect.signature(server.search_sfx).parameters


def test_voiceover_overwrite_is_an_optional_flag_with_a_description() -> None:
    tool = next(t for t in _tools() if t.name == "synthesize_voiceover")
    prop = _schema(tool)["properties"]["overwrite"]
    assert prop["type"] == "boolean" and prop["default"] is False
    assert 0 < len(prop["description"]) <= 80


def test_every_parameter_description_is_short() -> None:
    for tool in _tools():
        for prop in (_schema(tool).get("properties") or {}).values():
            assert len(prop.get("description", "")) <= 80, tool.name

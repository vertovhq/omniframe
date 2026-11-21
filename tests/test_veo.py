"""generate_veo_clip routes (task 20.8): the API route is refused with the shutdown message; Flow is unchanged. No network."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.config import CONFIG  # noqa: E402
from argus.tools import flow_browser, veo  # noqa: E402

SHUTDOWN = (
    "Veo 3.1 Preview in the Gemini API was shut down on 2026-10-22 (https://aistudio.google.com/docs/video). "
    "Use the Flow route or wait for the Omni update."
)


@pytest.fixture
def route(monkeypatch: pytest.MonkeyPatch):
    """Set the default route; the Flow call is replaced so nothing opens a browser."""
    def set_default(provider: str) -> None:
        monkeypatch.setattr(veo, "CONFIG", dataclasses.replace(CONFIG, veo_provider=provider, gemini_api_key="g"))

    calls: list[tuple] = []

    def fake_flow(prompt, output_path, *, max_wait_s):
        calls.append((prompt, output_path, max_wait_s))
        return {"output": output_path, "route": "flow"}

    monkeypatch.setattr(flow_browser, "flow_generate", fake_flow)
    set_default.calls = calls
    return set_default


def test_the_api_route_says_the_veo_shutdown(route, tmp_path) -> None:
    route("api")
    with pytest.raises(RuntimeError) as raised:
        veo.generate_veo_clip("a clip", str(tmp_path / "clip.mp4"), provider="api")
    assert str(raised.value) == SHUTDOWN


def test_the_default_route_is_refused_the_same_way(route, tmp_path) -> None:
    route("api")
    with pytest.raises(RuntimeError) as raised:
        veo.generate_veo_clip("a clip", str(tmp_path / "clip.mp4"))
    assert str(raised.value) == SHUTDOWN


def test_the_flow_route_still_generates(route, tmp_path) -> None:
    route("api")
    result = veo.generate_veo_clip("a clip", str(tmp_path / "clip.mp4"), provider="flow", max_wait_s=90)
    assert result == {"output": str(tmp_path / "clip.mp4"), "route": "flow"}
    assert route.calls == [("a clip", str(tmp_path / "clip.mp4"), 90)]


def test_flow_as_the_default_route_needs_no_provider_argument(route, tmp_path) -> None:
    route("flow")
    result = veo.generate_veo_clip("a clip", str(tmp_path / "clip.mp4"))
    assert result["route"] == "flow"


def test_an_unknown_route_is_a_value_error(route, tmp_path) -> None:
    route("api")
    with pytest.raises(ValueError, match="unknown Veo provider"):
        veo.generate_veo_clip("a clip", str(tmp_path / "clip.mp4"), provider="carrier-pigeon")

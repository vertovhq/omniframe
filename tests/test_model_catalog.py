"""Model catalog (task 20.8): newest-first order, env overrides, failed lists. No network."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe.config import CONFIG  # noqa: E402
from omniframe.tools import model_catalog  # noqa: E402


@pytest.fixture
def cfg(monkeypatch: pytest.MonkeyPatch):
    """Config with no pinned model ids, so each test decides what is set."""
    config = dataclasses.replace(CONFIG, gemini_api_key="g", tts_model="")
    monkeypatch.setattr(model_catalog, "CONFIG", config)
    return config


def _listing(monkeypatch: pytest.MonkeyPatch, models: list[dict]) -> None:
    monkeypatch.setattr(model_catalog, "gemini_model_list", lambda: list(models))


def _refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused():
        raise AssertionError("the list must not be read when the id is set")

    monkeypatch.setattr(model_catalog, "gemini_model_list", refused)


def test_version_numbers_order_the_models_not_the_text() -> None:
    ids = ["gemini-2.5-flash-tts", "gemini-3.8-flash-tts", "gemini-3.1-flash-tts", "gemini-10.0-flash-tts"]
    ordered = [m["id"] for m in model_catalog.newest_first([{"id": i} for i in ids])]
    assert ordered == ["gemini-10.0-flash-tts", "gemini-3.8-flash-tts", "gemini-3.1-flash-tts", "gemini-2.5-flash-tts"]


def test_lite_and_preview_lose_a_tie_and_equal_ids_keep_the_provider_order() -> None:
    ids = ["x-2-lite", "x-2-preview", "x-2", "x-2-plain"]
    assert [m["id"] for m in model_catalog.newest_first([{"id": i} for i in ids])] == [
        "x-2", "x-2-plain", "x-2-preview", "x-2-lite"]


def test_tts_is_the_newest_listed_text_to_speech_model(monkeypatch, cfg) -> None:
    _listing(monkeypatch, [
        {"id": "gemini-3.8-flash", "name": "chat"},
        {"id": "gemini-3.8-flash-tts", "name": "tts"},
        {"id": "gemini-3.8-live-tts", "name": "live, not for us"},
        {"id": "gemini-2.5-flash-preview-tts", "name": "old"},
    ])
    assert model_catalog.tts_model_id() == "gemini-3.8-flash-tts"


def test_a_pinned_tts_model_is_used_without_listing(monkeypatch, cfg) -> None:
    monkeypatch.setattr(model_catalog, "CONFIG", dataclasses.replace(cfg, tts_model="pinned-tts"))
    _refuse(monkeypatch)
    assert model_catalog.tts_model_id() == "pinned-tts"


def test_no_tts_model_in_the_list_names_the_variable(monkeypatch, cfg) -> None:
    _listing(monkeypatch, [{"id": "gemini-3.8-flash", "name": "chat"}])
    with pytest.raises(RuntimeError, match="OMNIFRAME_TTS_MODEL"):
        model_catalog.tts_model_id()


def test_a_failed_list_names_the_variable_and_adds_no_id(monkeypatch, cfg) -> None:
    def refused():
        raise RuntimeError("could not list Gemini models: 401 UNAUTHENTICATED")

    monkeypatch.setattr(model_catalog, "gemini_model_list", refused)
    with pytest.raises(RuntimeError) as raised:
        model_catalog.tts_model_id()
    message = str(raised.value)
    assert "401" in message and "OMNIFRAME_TTS_MODEL" in message and "gemini-" not in message


def test_options_mark_the_default_only_once(monkeypatch, cfg) -> None:
    _listing(monkeypatch, [{"id": "gemini-3.8-flash-tts", "name": "t"}, {"id": "gemini-3.1-flash-tts", "name": "u"},
                           {"id": "gemini-3.8-flash", "name": "chat"}])
    rows = model_catalog.options({})
    assert [(r["id"], r["use"], r["default"]) for r in rows] == [
        ("gemini-3.8-flash-tts", "text to speech", True),
        ("gemini-3.1-flash-tts", "text to speech", False),
    ]


def test_a_pinned_id_is_the_default_even_when_the_list_has_a_newer_one(monkeypatch, cfg) -> None:
    monkeypatch.setattr(model_catalog, "CONFIG", dataclasses.replace(cfg, tts_model="gemini-3.1-flash-tts"))
    _listing(monkeypatch, [{"id": "gemini-3.8-flash-tts", "name": "t"}, {"id": "gemini-3.1-flash-tts", "name": "u"}])
    rows = model_catalog.options({})
    assert [(r["id"], r["default"]) for r in rows] == [("gemini-3.8-flash-tts", False), ("gemini-3.1-flash-tts", True)]


def test_a_missing_key_is_reported_before_any_call(monkeypatch) -> None:
    monkeypatch.setattr(model_catalog, "CONFIG", dataclasses.replace(CONFIG, gemini_api_key=""))
    with pytest.raises(RuntimeError, match="OMNIFRAME_GEMINI_API_KEY"):
        model_catalog.gemini_model_list()

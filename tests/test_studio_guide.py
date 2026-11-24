"""studio_guide: guide + capabilities + preferences, and the preference round trip."""

from __future__ import annotations

import dataclasses
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import server  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.tools import kit_preview, memory, studio  # noqa: E402

PROVIDER_KEYS = {"elevenlabs", "gemini", "edge", "faster_whisper"}
HEADER = "# ARGUS — user preferences"


@pytest.fixture
def kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A knowledge base inside tmp_path, wired into both the reader and the writer."""
    path = tmp_path / "KNOWLEDGE_BASE.md"
    # output_dir too: the style library lives there, and the real one must not leak into the tests
    cfg = dataclasses.replace(CONFIG, knowledge_base=path, output_dir=tmp_path / "out")
    monkeypatch.setattr(studio, "CONFIG", cfg)
    monkeypatch.setattr(memory, "CONFIG", cfg)
    monkeypatch.setattr(kit_preview, "CONFIG", cfg)  # the strip cache lives under output_dir too
    return path


def test_returns_guide_capabilities_and_preferences(kb: Path) -> None:
    kb.write_text(f"{HEADER}\n\n## Language\n- always narrate in Russian\n", encoding="utf-8")

    result = server.studio_guide()

    assert result["guide"].startswith("# ARGUS Studio Guide")
    tools = result["capabilities"]["tools"]
    assert "studio_guide" in tools and "learn_and_record_memory" in tools
    assert "story_guide" not in tools and "validate_beats" not in tools
    providers = result["capabilities"]["providers"]
    assert set(providers) == PROVIDER_KEYS
    assert all(isinstance(p["available"], bool) and p["note"] for p in providers.values())
    assert "always narrate in Russian" in result["preferences"]
    assert result["preferences_truncated"] is False


def test_guide_text_has_no_percentage_rules() -> None:
    assert "%" not in studio.read_guide()


def test_providers_follow_config_and_imports(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(studio, "_importable", lambda module: module == "edge_tts")

    keyed = studio.providers(dataclasses.replace(CONFIG, elevenlabs_api_key="e", gemini_api_key="g"))
    assert all(keyed[name]["available"] for name in ("elevenlabs", "gemini", "edge"))
    assert not keyed["faster_whisper"]["available"]

    keyless = studio.providers(dataclasses.replace(CONFIG, elevenlabs_api_key="", gemini_api_key=""))
    assert not any(keyless[name]["available"] for name in ("elevenlabs", "gemini"))
    assert keyless["edge"]["available"]
    assert "ELEVENLABS_API_KEY" in keyless["elevenlabs"]["note"]


@pytest.mark.parametrize("seed", range(8))
def test_preferences_are_capped_and_keep_the_newest_entries(kb: Path, seed: int) -> None:
    rng = random.Random(seed)
    entries = [
        f"## Rule {i}\n- **User directive:** {'x' * rng.randint(20, 900)} end-{i}\n"
        for i in range(rng.randint(1, 80))
    ]
    kb.write_text(f"{HEADER}\n\n" + "\n".join(entries), encoding="utf-8")
    text = kb.read_text(encoding="utf-8").strip()

    result = studio.studio_guide([])
    prefs = result["preferences"]

    assert len(prefs) <= studio.PREFERENCES_LIMIT
    assert text.endswith(prefs)  # the tail of the file: newest entries survive
    assert result["preferences_truncated"] == (len(text) > studio.PREFERENCES_LIMIT)
    if result["preferences_truncated"]:
        assert prefs.startswith("## ")  # cut at an entry boundary, not mid-sentence
    else:
        assert prefs == text


def test_preferences_cap_holds_for_one_huge_line(kb: Path) -> None:
    kb.write_text("y" * 10_000, encoding="utf-8")

    prefs, truncated = studio.read_preferences(kb)

    assert truncated and len(prefs) == studio.PREFERENCES_LIMIT


def test_recorded_preference_appears_in_the_next_call(kb: Path) -> None:
    assert server.studio_guide()["preferences"] == ""  # no file yet

    server.learn_and_record_memory("Narration language", "always narrate in Russian", "use language ru")
    assert kb.read_text(encoding="utf-8").startswith(HEADER)
    first = server.studio_guide()["preferences"]
    assert "Narration language" in first and "always narrate in Russian" in first

    server.learn_and_record_memory("Handle", "my handle is @doc", "put @doc on the end card")
    second = server.studio_guide()["preferences"]
    assert second.index("Narration language") < second.index("Handle")
    assert second.count(HEADER) == 1  # header is written once, not per entry


def test_motion_kit_index_is_returned_only_for_custom_scenes(kb: Path) -> None:
    assert "motion_kit" not in server.studio_guide()
    kit = server.studio_guide(custom_scenes=True)["motion_kit"]
    assert kit.startswith("# Motion kit") and len(kit) < 5000
    for group in kit_preview.group_names():
        assert f"**{group}**" in kit  # one line per group
    guide = studio.read_guide()
    assert "custom_scenes=true" in guide and "kit_group" in guide  # the guide tells where the catalogue is


def _fake_strip(path: Path) -> Path:
    from PIL import Image as PILImage

    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.new("RGB", (600, 300), (30, 60, 90)).save(path)
    return path


def test_kit_group_returns_the_group_text_and_its_cached_strip(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    started: list[tuple] = []
    monkeypatch.setattr(kit_preview.jobs, "start", lambda *a, **k: started.append((a, k)) or "job1")
    cached = _fake_strip(kit_preview.strip_path("hud"))

    result = server.studio_guide(kit_group="hud")

    assert isinstance(result, list) and len(result) == 2 and hasattr(result[1], "path")
    info = json.loads(result[0])
    assert info["kit_group"] == "hud" and "HudLayer" in info["text"] and "guide" not in info
    assert info["strip"]["path"] == str(cached) and "Timecode" in info["strip"]["blocks"]
    assert set(info["groups"]) >= {"hud", "type", "bursts", "depth", "camera", "energy", "transitions"}
    assert started == [], "a cached strip must not start a render"


def test_kit_group_without_a_strip_starts_one_background_job(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple] = []
    monkeypatch.setattr(kit_preview.jobs, "start", lambda *a, **k: started.append((a, k)) or "job42")

    result = server.studio_guide(kit_group="bursts")

    assert isinstance(result, dict) and "SpeedLines" in result["text"]
    assert result["strip"]["state"] == "building" and result["strip"]["job_id"] == "job42"
    assert started[0][0][:2] == ("kit_preview", {"group": "bursts"})
    server.studio_guide(kit_group="bursts")  # asking again reuses the same job key
    assert started[1][1]["key"] == started[0][1]["key"]


def test_unknown_kit_group_lists_the_groups(kb: Path) -> None:
    result = server.studio_guide(kit_group="sparkles")

    assert "sparkles" in result["error"] and "hud" in result["groups"]

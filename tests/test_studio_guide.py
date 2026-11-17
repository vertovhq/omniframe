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
from argus.tools import memory, studio  # noqa: E402

PROVIDER_KEYS = {"elevenlabs", "gemini", "edge", "faster_whisper", "veo_api", "flow_session"}
HEADER = "# ARGUS — user preferences"


@pytest.fixture
def kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A knowledge base inside tmp_path, wired into both the reader and the writer."""
    path = tmp_path / "KNOWLEDGE_BASE.md"
    cfg = dataclasses.replace(CONFIG, knowledge_base=path)
    monkeypatch.setattr(studio, "CONFIG", cfg)
    monkeypatch.setattr(memory, "CONFIG", cfg)
    monkeypatch.setenv("ARGUS_FLOW_PROFILE", str(tmp_path / "no-flow-profile"))
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


def test_providers_follow_config_imports_and_flow_profile(
    kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow_dir = tmp_path / "flow"
    flow_dir.mkdir()
    monkeypatch.setenv("ARGUS_FLOW_PROFILE", str(flow_dir))
    monkeypatch.setattr(studio, "_importable", lambda module: module == "edge_tts")

    keyed = studio.providers(dataclasses.replace(CONFIG, elevenlabs_api_key="e", gemini_api_key="g"))
    assert all(keyed[name]["available"] for name in ("elevenlabs", "gemini", "veo_api", "edge", "flow_session"))
    assert not keyed["faster_whisper"]["available"]

    keyless = studio.providers(dataclasses.replace(CONFIG, elevenlabs_api_key="", gemini_api_key=""))
    assert not any(keyless[name]["available"] for name in ("elevenlabs", "gemini", "veo_api"))
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

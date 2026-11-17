"""voice_options tests: own + library voices, edge defaults, provider status. No network."""

from __future__ import annotations

import dataclasses
import io
import json
import sys
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.config import CONFIG  # noqa: E402
from argus.tools import voiceover  # noqa: E402

OWN = {"voices": [
    {"voice_id": "ownVoiceAAAAAAAAAAAA", "name": "Brian", "category": "premade", "description": "deep, resonant narrator",
     "labels": {"gender": "male", "age": "middle_aged", "accent": "american", "use_case": "narration", "language": "en"},
     "preview_url": "https://example.test/brian.mp3"},
    {"voice_id": "ownVoiceBBBBBBBBBBBB", "name": "Sasha", "category": "cloned", "description": "warm Russian voice",
     "labels": {"gender": "female", "age": "young", "language": "ru"}},
    {"voice_id": "ownVoiceCCCCCCCCCCCC", "name": "Boris", "category": "professional",
     "labels": {"gender": "male"}, "verified_languages": [{"language": "ru", "model_id": "eleven_v3"}]},
], "has_more": False}

LIBRARY = {"voices": [
    {"public_owner_id": "o1", "voice_id": "libVoiceAAAAAAAAAAAA", "name": "Lena", "gender": "female", "age": "young",
     "accent": "russian", "use_case": "social_media", "language": "ru",
     "description": "Bright and fast. " + "long " * 80, "preview_url": "https://example.test/lena.mp3"},
]}

MODELS = [
    {"model_id": "eleven_v3", "name": "Eleven v3", "can_do_text_to_speech": True, "maximum_text_length_per_request": 5000},
    {"model_id": "eleven_multilingual_v2", "name": "Multilingual v2", "can_do_text_to_speech": True,
     "maximum_text_length_per_request": 10000},
    {"model_id": "eleven_multilingual_sts_v2", "name": "STS", "can_do_text_to_speech": False},
]


class Reply:
    def __init__(self, payload: object) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "Reply":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeApi:
    def __init__(self, library: object = LIBRARY, fail_library: int | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.library = library
        self.fail_library = fail_library

    def __call__(self, request, timeout=None):
        parsed = urlparse(request.full_url)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.calls.append((parsed.path, query))
        if parsed.path == "/v2/voices":
            return Reply(OWN)
        if parsed.path == "/v1/shared-voices":
            if self.fail_library:
                raise urllib.error.HTTPError(request.full_url, self.fail_library, "no", {}, io.BytesIO(b'{"detail":"paid plan"}'))
            return Reply(self.library)
        if parsed.path == "/v1/models":
            return Reply(MODELS)
        raise AssertionError(f"unexpected request {request.full_url}")


def _config(monkeypatch: pytest.MonkeyPatch, **changes) -> None:
    monkeypatch.setattr(voiceover, "CONFIG", dataclasses.replace(CONFIG, **changes))


@pytest.fixture
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _config(monkeypatch, elevenlabs_api_key="", gemini_api_key="")
    monkeypatch.delenv("ARGUS_TTS_PROVIDER", raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("no key: voice_options must not call ElevenLabs")

    monkeypatch.setattr("urllib.request.urlopen", no_network)


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> FakeApi:
    _config(monkeypatch, elevenlabs_api_key="sk_test", gemini_api_key="")
    monkeypatch.delenv("ARGUS_TTS_PROVIDER", raising=False)
    api = FakeApi()
    monkeypatch.setattr("urllib.request.urlopen", api)
    return api


def test_without_keys_only_edge_defaults_and_status_are_returned(no_keys) -> None:
    result = voiceover.voice_options(language="ru")

    assert result["default_provider"] == "edge"
    assert result["providers"]["elevenlabs"]["available"] is False
    assert "ELEVENLABS_API_KEY" in result["providers"]["elevenlabs"]["note"]
    assert result["providers"]["gemini"]["available"] is False
    assert result["own_voices"] == [] and result["library_voices"] == []
    assert [v["id"] for v in result["edge_voices"]] == ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"]
    assert result["edge_voices"][0]["gender"] == "male" and result["edge_voices"][0]["languages"] == ["ru-RU"]


def test_edge_filters_by_gender_query_and_unknown_language(no_keys) -> None:
    female = voiceover.voice_options(language="Russian", gender="f")["edge_voices"]
    assert [v["name"] for v in female] == ["Svetlana"]
    assert [v["name"] for v in voiceover.voice_options(query="guy")["edge_voices"]] == ["Guy"]

    unknown = voiceover.voice_options(language="sw")
    assert unknown["edge_voices"] == [] and any("edge-tts --list-voices" in n for n in unknown["notes"])


def test_providers_follow_the_configured_keys(monkeypatch: pytest.MonkeyPatch, no_keys) -> None:
    assert "Charon" in voiceover.voice_options()["gemini_voices"]
    _config(monkeypatch, elevenlabs_api_key="", gemini_api_key="g")
    status = voiceover.voice_options()["providers"]
    assert status["gemini"]["available"] is True and status["gemini"]["model"] == CONFIG.tts_model
    assert voiceover.voice_options()["default_provider"] == "edge"  # a Gemini key alone does not change the default
    assert set(status) == {"elevenlabs", "gemini", "edge", "faster_whisper"}


def test_own_voices_filter_by_gender_and_put_the_requested_language_first(keyed) -> None:
    result = voiceover.voice_options(language="ru")
    assert result["default_provider"] == "elevenlabs"
    assert [v["name"] for v in result["own_voices"]] == ["Sasha", "Boris", "Brian"]  # ru first, then the rest
    assert [v["language_match"] for v in result["own_voices"]] == [True, True, False]

    men = voiceover.voice_options(gender="male")["own_voices"]
    assert [v["name"] for v in men] == ["Brian", "Boris"]
    brian = men[0]
    assert brian["id"] == "ownVoiceAAAAAAAAAAAA" and brian["source"] == "premade"
    assert (brian["gender"], brian["age"], brian["accent"], brian["use_case"]) == (
        "male", "middle_aged", "american", "narration")
    assert brian["preview_url"] == "https://example.test/brian.mp3"

    assert [v["name"] for v in voiceover.voice_options(query="resonant")["own_voices"]] == ["Brian"]


def test_library_search_sends_the_filters_and_trims_long_descriptions(keyed) -> None:
    result = voiceover.voice_options(language="Russian", gender="Female", query="young energetic", limit=5)

    path, params = next(c for c in keyed.calls if c[0] == "/v1/shared-voices")
    assert params == {"page_size": "5", "language": "ru", "gender": "female",
                      "search": "young energetic", "sort": "trending"}
    lena = result["library_voices"][0]
    assert lena["id"] == "libVoiceAAAAAAAAAAAA" and lena["source"] == "library"
    assert lena["languages"] == ["ru"] and len(lena["description"]) <= 160


def test_models_report_how_each_one_wants_delivery_written(keyed) -> None:
    models = {m["id"]: m for m in voiceover.voice_options()["elevenlabs_models"]}
    assert set(models) == {"eleven_v3", "eleven_multilingual_v2"}  # speech-to-speech is not a voice model
    assert models["eleven_v3"]["max_chars"] == 5000 and "audio tags" in models["eleven_v3"]["delivery"]
    assert "SSML" in models["eleven_multilingual_v2"]["delivery"]


def test_limit_caps_every_list(keyed) -> None:
    result = voiceover.voice_options(limit=1)
    assert len(result["own_voices"]) == 1 and len(result["edge_voices"]) == 1 and len(result["gemini_voices"]) == 1
    assert len(voiceover.voice_options(limit=500)["gemini_voices"]) == 30  # the cap is 50, Gemini has 30


def test_a_refused_library_search_does_not_hide_own_voices(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    api = FakeApi(fail_library=402)
    monkeypatch.setattr("urllib.request.urlopen", api)
    result = voiceover.voice_options()
    assert len(result["own_voices"]) == 3 and result["library_voices"] == []
    assert "402" in result["errors"]["library_voices"] and "sk_test" not in json.dumps(result)


def test_with_one_working_provider_there_is_nothing_to_ask(no_keys) -> None:
    choice = voiceover.voice_options()["provider_choice"]
    assert choice["recommended"] == "edge" and choice["ask_user"] is False
    available = [o["provider"] for o in choice["options"] if o["available"]]
    assert available == ["edge"]
    elevenlabs = next(o for o in choice["options"] if o["provider"] == "elevenlabs")
    assert "ELEVENLABS_API_KEY" in elevenlabs["to_enable"]


def test_with_several_providers_elevenlabs_is_recommended_and_the_user_is_asked(monkeypatch, keyed) -> None:
    _config(monkeypatch, elevenlabs_api_key="sk_test", gemini_api_key="g")
    choice = voiceover.voice_options()["provider_choice"]
    assert choice["recommended"] == "elevenlabs" and choice["ask_user"] is True
    assert choice["options"][0]["provider"] == "elevenlabs"  # the recommendation comes first
    assert {o["provider"] for o in choice["options"] if o["available"]} == {"elevenlabs", "gemini", "edge"}
    assert "ask the user" in choice["instruction"] and "mid-project" in choice["instruction"]


def test_an_installed_local_provider_shows_up_as_a_choice(monkeypatch, keyed) -> None:
    class Local:
        name, raw_suffix, blurb = "voicestudio", ".wav", "local voices on this machine, offline"

        def available(self) -> bool:
            return True

    monkeypatch.setitem(voiceover.PROVIDERS, "voicestudio", Local())
    options = {o["provider"]: o for o in voiceover.voice_options()["provider_choice"]["options"]}
    assert options["voicestudio"]["available"] is True and "offline" in options["voicestudio"]["about"]


def test_env_override_decides_the_recommendation(monkeypatch, keyed) -> None:
    _config(monkeypatch, elevenlabs_api_key="sk_test", gemini_api_key="g")
    monkeypatch.setenv("ARGUS_TTS_PROVIDER", "gemini")
    assert voiceover.voice_options()["provider_choice"]["recommended"] == "gemini"


def test_delivery_vocabulary_comes_with_a_key_and_matches_the_model(monkeypatch, keyed) -> None:
    delivery = voiceover.voice_options()["delivery"]
    assert delivery["model"] == "eleven_v3" and "[whispers]" in delivery["audio_tags"]
    assert any("stability" in rule for rule in delivery["rules"])

    _config(monkeypatch, elevenlabs_api_key="sk_test", eleven_model="eleven_multilingual_v2")
    v2 = voiceover.voice_options()["delivery"]
    assert "audio_tags" not in v2 and "<break" in v2["rules"][0]


def test_no_key_means_no_elevenlabs_delivery_guide(no_keys) -> None:
    assert "delivery" not in voiceover.voice_options()


def test_the_decision_stays_with_the_model(no_keys) -> None:
    """v2 returns options, not an instruction to ask the user (design §7, requirement 7.2)."""
    assert "decision_hint" not in voiceover.voice_options()

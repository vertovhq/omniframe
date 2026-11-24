"""voice_options tests: own + library voices, edge defaults, provider status, compact answer. No network."""

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

from omniframe.config import CONFIG  # noqa: E402
from omniframe.tools import model_catalog, voiceover  # noqa: E402

# Gemini models as the google-genai list returns them (test data; ids are chosen to exercise the sort)
GEMINI_LISTED = [
    {"id": "gemini-3.1-flash-tts-preview", "name": "Gemini 3.1 Flash TTS"},
    {"id": "gemini-3.8-flash-lite-tts", "name": "Gemini 3.8 Flash-Lite TTS"},
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
    {"id": "gemini-3.8-flash-tts", "name": "Gemini 3.8 Flash TTS"},
]

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
    {"public_owner_id": "o1", "voice_id": "libVoiceAAAAAAAAAAAA", "name": "Lena", "gender": "Female", "age": "young",
     "accent": "russian", "use_case": "social_media", "language": "ru", "free_users_allowed": True,
     "description": "Bright and fast. " + "long " * 80, "preview_url": "https://example.test/lena.mp3"},
    {"public_owner_id": "o2", "voice_id": "libVoiceBBBBBBBBBBBB", "name": "Pavel", "gender": "Male",
     "age": "middle_aged", "accent": "russian", "language": "ru", "free_users_allowed": False,
     "description": "Deep baritone for documentaries"},
    {"public_owner_id": "o3", "voice_id": "libVoiceCCCCCCCCCCCC", "name": "Maks", "gender": "Male",
     "age": "old", "language": "ru", "description": "Calm storyteller"},  # no free_users_allowed field
]}

MODELS = [
    {"model_id": "eleven_v3", "name": "Eleven v3", "can_do_text_to_speech": True, "maximum_text_length_per_request": 5000},
    {"model_id": "eleven_multilingual_v2", "name": "Multilingual v2", "can_do_text_to_speech": True,
     "maximum_text_length_per_request": 10000},
    {"model_id": "eleven_multilingual_sts_v2", "name": "STS", "can_do_text_to_speech": False},
]

BIG_OWN = {"voices": [
    {"voice_id": f"own{i:03d}" + "X" * 14, "name": f"Voice {i}", "category": "professional",
     "description": "word " * 60, "labels": {"gender": "male", "age": "young", "accent": "american", "language": "en"}}
    for i in range(100)
]}
BIG_LIBRARY = {"voices": [
    {"voice_id": f"lib{i:03d}" + "Y" * 14, "name": f"Library {i}", "gender": "Female", "age": "young",
     "accent": "british", "language": "en", "free_users_allowed": i % 2 == 0, "description": "text " * 60}
    for i in range(50)
]}


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
    """Fake ElevenLabs API. `pages`: a list of voice lists served one page per `next_page_token` ("0", "1", ...)."""

    def __init__(self, library: object = LIBRARY, own: object = OWN, fail_library: int | None = None,
                 tier: str = "creator", plan_error: bool = False, pages: list[list[dict]] | None = None,
                 models: object = None, fail_models: int | None = None,
                 fail_voices: int | None = None, voices_error: object = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.library = library
        self.own = own
        self.fail_library = fail_library
        self.tier = tier
        self.plan_error = plan_error
        self.pages = pages
        self.models = MODELS if models is None else models
        self.fail_models = fail_models
        self.fail_voices = fail_voices
        self.voices_error = voices_error

    def __call__(self, request, timeout=None):
        parsed = urlparse(request.full_url)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.calls.append((parsed.path, query))
        if parsed.path == "/v1/user/subscription":
            if self.plan_error:
                raise urllib.error.HTTPError(request.full_url, 500, "no", {}, io.BytesIO(b'{"detail":"down"}'))
            return Reply({"tier": self.tier})
        if parsed.path == "/v2/voices":
            if self.fail_voices:
                raise urllib.error.HTTPError(request.full_url, self.fail_voices, "no", {},
                                             io.BytesIO(json.dumps(self.voices_error).encode("utf-8")))
            if self.pages is not None:
                index = int(query.get("next_page_token", "0"))
                last = index == len(self.pages) - 1
                return Reply({
                    "voices": self.pages[index],
                    "has_more": not last,
                    "next_page_token": None if last else str(index + 1),
                })
            return Reply(self.own)
        if parsed.path == "/v1/shared-voices":
            if self.fail_library:
                raise urllib.error.HTTPError(request.full_url, self.fail_library, "no", {}, io.BytesIO(b'{"detail":"paid plan"}'))
            return Reply(self.library)
        if parsed.path == "/v1/models":
            if self.fail_models:
                raise urllib.error.HTTPError(request.full_url, self.fail_models, "no", {},
                                             io.BytesIO(b'{"detail":"invalid api key"}'))
            return Reply(self.models)
        raise AssertionError(f"unexpected request {request.full_url}")

    def paths(self) -> list[str]:
        return [path for path, _ in self.calls]


def _config(monkeypatch: pytest.MonkeyPatch, **changes) -> None:
    """Replace the config in both modules that read it. Model ids are empty unless a test sets them."""
    changes.setdefault("eleven_model", "")
    changes.setdefault("tts_model", "")
    monkeypatch.setattr(voiceover, "CONFIG", dataclasses.replace(CONFIG, **changes))
    monkeypatch.setattr(model_catalog, "CONFIG", dataclasses.replace(CONFIG, **changes))


@pytest.fixture(autouse=True)
def gemini_list(monkeypatch: pytest.MonkeyPatch):
    """No test reaches Google: the Gemini model list is canned. A test may replace it."""
    listed = {"value": list(GEMINI_LISTED)}
    monkeypatch.setattr(model_catalog, "gemini_model_list", lambda: list(listed["value"]))
    return listed


def _size(result: dict) -> int:
    """Characters of the answer as the MCP client gets it: JSON with indent 2, no \\u escapes."""
    return len(json.dumps(result, ensure_ascii=False, indent=2))


def _no_elevenlabs_call(*args, **kwargs):
    raise AssertionError("ElevenLabs must not be called without a key")


@pytest.fixture
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _config(monkeypatch, elevenlabs_api_key="", gemini_api_key="")
    monkeypatch.delenv("OMNIFRAME_TTS_PROVIDER", raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("no key: voice_options must not call ElevenLabs")

    monkeypatch.setattr("urllib.request.urlopen", no_network)


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> FakeApi:
    _config(monkeypatch, elevenlabs_api_key="sk_test", gemini_api_key="")
    monkeypatch.delenv("OMNIFRAME_TTS_PROVIDER", raising=False)
    api = FakeApi()
    monkeypatch.setattr("urllib.request.urlopen", api)
    return api


# ------------------------------------------------------------------ edge, gemini, providers

def test_without_keys_only_edge_defaults_and_status_are_returned(no_keys) -> None:
    result = voiceover.voice_options(language="ru")

    assert result["default_provider"] == "edge"
    assert result["providers"]["elevenlabs"]["available"] is False
    assert "ELEVENLABS_API_KEY" in result["providers"]["elevenlabs"]["note"]
    assert result["providers"]["gemini"]["available"] is False
    assert result["own_voices"] == [] and result["library_voices"] == []
    assert [v["id"] for v in result["edge_voices"]] == ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"]
    assert result["edge_voices"][0] == {"id": "ru-RU-DmitryNeural", "name": "Dmitry", "gender": "male", "language": "ru-RU"}


def test_edge_filters_by_gender_query_and_unknown_language(no_keys) -> None:
    female = voiceover.voice_options(language="Russian", gender="f")["edge_voices"]
    assert [v["name"] for v in female] == ["Svetlana"]
    assert [v["name"] for v in voiceover.voice_options(query="guy")["edge_voices"]] == ["Guy"]

    unknown = voiceover.voice_options(language="sw")
    assert unknown["edge_voices"] == [] and any("edge-tts --list-voices" in n for n in unknown["notes"])


def test_query_matches_any_word_in_any_case_for_edge_and_gemini_voices(no_keys) -> None:
    result = voiceover.voice_options(query="SVETLANA guy")
    assert [v["name"] for v in result["edge_voices"]] == ["Svetlana", "Guy"]

    gemini = voiceover.voice_options(query="charon, ZEPHYR; nobody")["gemini_voices"]
    assert sorted(gemini) == ["Charon", "Zephyr"]
    assert voiceover.voice_options(query="nobody zzz")["gemini_voices"] == []


def test_providers_follow_the_configured_keys(monkeypatch: pytest.MonkeyPatch, no_keys) -> None:
    assert "Charon" in voiceover.voice_options()["gemini_voices"]
    _config(monkeypatch, elevenlabs_api_key="", gemini_api_key="g")
    status = voiceover.voice_options()["providers"]
    assert status["gemini"]["available"] is True and "newest text-to-speech" in status["gemini"]["model"]
    assert voiceover.voice_options()["default_provider"] == "edge"  # a Gemini key alone does not change the default
    assert set(status) == {"elevenlabs", "gemini", "edge", "faster_whisper"}


# ------------------------------------------------------------------ own voices

def test_own_voices_are_compact_filter_by_gender_and_put_the_requested_language_first(keyed) -> None:
    result = voiceover.voice_options(language="ru")
    assert result["default_provider"] == "elevenlabs"
    assert [v["name"] for v in result["own_voices"]] == ["Sasha", "Boris", "Brian"]  # ru first, then the rest
    assert [v["language"] for v in result["own_voices"]] == ["ru", "ru", "en"]

    men = voiceover.voice_options(gender="male")["own_voices"]
    assert [v["name"] for v in men] == ["Brian", "Boris"]
    assert men[0] == {
        "id": "ownVoiceAAAAAAAAAAAA", "name": "Brian", "gender": "male", "age": "middle_aged",
        "accent": "american", "language": "en", "description": "deep, resonant narrator",
    }
    # empty fields are left out; nothing but the seven fields is ever returned
    assert men[1] == {"id": "ownVoiceCCCCCCCCCCCC", "name": "Boris", "gender": "male", "language": "ru"}


def test_a_language_without_own_voices_is_explained(keyed) -> None:
    result = voiceover.voice_options(language="de")
    assert len(result["own_voices"]) == 3
    assert any("no own voice is labelled 'de'" in note for note in result["notes"])


def test_query_searches_name_description_accent_and_labels_by_any_word_in_any_case(keyed) -> None:
    def names(query: str) -> list[str]:
        return [v["name"] for v in voiceover.voice_options(query=query)["own_voices"]]

    assert names("resonant") == ["Brian"]                  # description
    assert names("AMERICAN") == ["Brian"]                  # accent label, upper case
    assert names("Young") == ["Sasha"]                     # age label
    assert names("narration") == ["Brian"]                 # use case label
    assert names("Russian") == ["Sasha"]                   # description of another voice
    assert names("deep young") == ["Brian", "Sasha"]       # any word is enough
    assert names("boris, professional!") == ["Boris"]      # punctuation is not part of a word
    assert names("warm american") == ["Brian", "Sasha"]    # one word each, the account's order on a tie
    assert names("nothing matches this") == []


def test_voices_matching_more_query_words_come_first(keyed) -> None:
    # Sasha: "warm" + "russian" (description) + "young" (age); Brian: "deep"
    assert [v["name"] for v in voiceover.voice_options(query="deep young warm russian")["own_voices"]] == ["Sasha", "Brian"]


# ------------------------------------------------------------------ library voices

def test_library_search_runs_once_per_word_and_splits_off_the_paid_plan_voices(keyed) -> None:
    result = voiceover.voice_options(language="Russian", gender="Female", query="Young ENERGETIC!", limit=5)

    searches = [params for path, params in keyed.calls if path == "/v1/shared-voices"]
    assert searches == [
        {"page_size": "5", "language": "ru", "gender": "female", "search": word, "sort": "trending"}
        for word in ("young", "energetic")
    ]
    lena, maks = result["library_voices"]
    assert lena["id"] == "libVoiceAAAAAAAAAAAA" and maks["name"] == "Maks"  # Lena matches "young"; Maks matches nothing
    assert set(lena) == {"id", "name", "gender", "age", "accent", "language", "description"}
    assert (lena["gender"], lena["language"]) == ("female", "ru")
    assert len(lena["description"]) == voiceover.VOICE_DESCRIPTION_CHARS and lena["description"].endswith("…")
    assert "preview_url" not in lena and "source" not in lena

    paid = result["library_voices_paid_plan_only"]
    assert [v["name"] for v in paid["voices"]] == ["Pavel"]
    assert "paid ElevenLabs plan" in paid["note"] and "free_users_allowed=false" in paid["note"]
    assert "Pavel" not in json.dumps(result["library_voices"])


def test_without_a_query_the_library_is_searched_once(keyed) -> None:
    result = voiceover.voice_options(language="ru")
    assert [path for path in keyed.paths() if path == "/v1/shared-voices"] == ["/v1/shared-voices"]
    assert [v["name"] for v in result["library_voices"]] == ["Lena", "Maks"]


def test_there_is_no_paid_list_when_every_library_voice_is_free(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(library={"voices": LIBRARY["voices"][:1]}))
    result = voiceover.voice_options()
    assert [v["name"] for v in result["library_voices"]] == ["Lena"]
    assert "library_voices_paid_plan_only" not in result


def test_a_refused_library_search_does_not_hide_own_voices(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    api = FakeApi(fail_library=402)
    monkeypatch.setattr("urllib.request.urlopen", api)
    result = voiceover.voice_options()
    assert len(result["own_voices"]) == 3 and result["library_voices"] == []
    assert "402" in result["errors"]["library_voices"] and "sk_test" not in json.dumps(result)


MISSING_VOICES_READ = {"detail": {"status": "missing_permissions",
                                  "message": "The API key you used is missing the permission voices_read to execute this operation."}}


def test_a_refused_voice_list_names_the_http_code_and_the_missing_key_permission(monkeypatch, keyed) -> None:
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(fail_voices=401, voices_error=MISSING_VOICES_READ))
    result = voiceover.voice_options(language="ru")

    assert result["own_voices"] == []
    text = result["errors"]["own_voices"]
    assert "HTTP 401 on GET /v2/voices" in text
    assert "lacks the permission voices_read" in text and "API keys" in text
    assert "sk_test" not in json.dumps(result)
    assert [v["name"] for v in result["edge_voices"]] == ["Dmitry", "Svetlana"]  # the other providers still answer
    assert not any("no voice fits" in note for note in result.get("notes", []))


def test_a_key_refused_as_invalid_is_told_to_check_the_env_variable(monkeypatch, keyed) -> None:
    invalid = {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(fail_voices=401, voices_error=invalid))
    text = voiceover.voice_options()["errors"]["own_voices"]
    assert "HTTP 401" in text and "Invalid API key" in text and "ELEVENLABS_API_KEY" in text


def test_when_the_rest_of_the_answer_fills_the_room_the_note_says_no_voice_fits(monkeypatch, keyed) -> None:
    # provider_choice and providers alone are about 1750 characters, so 1500 leaves no room for any voice
    monkeypatch.setattr(voiceover, "VOICE_RESPONSE_MAX_CHARS", 1500)
    result = voiceover.voice_options(language="ru")

    assert result["own_voices"] == [] and result["edge_voices"] == [] and result["gemini_voices"] == []
    assert result["library_voices"] == [] and "library_voices_paid_plan_only" not in result
    assert any(note.startswith("no voice fits") and "VOICE_RESPONSE_MAX_CHARS" in note for note in result["notes"])


def test_a_filter_that_matches_no_voice_is_said_not_left_empty(no_keys) -> None:
    result = voiceover.voice_options(query="глубокий мужской голос")

    assert result["edge_voices"] == [] and result["gemini_voices"] == []
    assert any(note.startswith("no voice matches") and "глубокий" in note for note in result["notes"])


# ------------------------------------------------------------------ size and details

def test_free_plan_moves_non_premade_and_library_voices_to_the_paid_list(monkeypatch: pytest.MonkeyPatch,
                                                                         keyed) -> None:
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(tier="free"))
    result = voiceover.voice_options()
    assert result["plan"] == {"tier": "free"}
    assert [v["name"] for v in result["own_voices"]] == ["Brian"]  # premade only
    assert result["library_voices"] == []
    paid = result["library_voices_paid_plan_only"]
    assert paid["note"] == voiceover.FREE_PLAN_NOTE
    assert {v["name"] for v in paid["voices"]} == {"Sasha", "Boris", "Lena", "Pavel", "Maks"}


def test_paid_plan_keeps_each_voice_where_it_was(keyed) -> None:
    result = voiceover.voice_options()
    assert result["plan"] == {"tier": "creator"}
    assert [v["name"] for v in result["own_voices"]] == ["Brian", "Sasha", "Boris"]
    paid = result["library_voices_paid_plan_only"]
    assert paid["note"] == voiceover.LIBRARY_PAID_NOTE
    assert [v["name"] for v in paid["voices"]] == ["Pavel"]  # only free_users_allowed=false


def test_unreadable_plan_is_said_and_no_voice_is_marked(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(plan_error=True))
    result = voiceover.voice_options()
    assert result["plan"]["tier"] is None
    assert "could not read the ElevenLabs plan" in result["plan"]["note"]
    assert "plan" in result["errors"]
    assert [v["name"] for v in result["own_voices"]] == ["Brian", "Sasha", "Boris"]  # nothing refused


def test_models_are_listed_newest_first_and_the_default_is_marked(keyed) -> None:
    plain = voiceover.voice_options()
    assert "/v1/models" in keyed.paths()  # the list is read on every call, details or not
    assert "delivery" not in plain and "elevenlabs_models" not in plain
    assert any("details=True" in note for note in plain["notes"])

    rows = plain["models"]["elevenlabs"]
    assert [m["id"] for m in rows] == ["eleven_v3", "eleven_multilingual_v2"]  # v3 is the higher version; STS is not TTS
    assert rows[0] == {"id": "eleven_v3", "name": "Eleven v3", "use": "text to speech", "max_chars": 5000,
                       "default": True}
    assert rows[1]["default"] is False


def test_details_adds_the_delivery_rules_of_the_default_model(keyed) -> None:
    full = voiceover.voice_options(details=True)
    assert "details=True" not in " ".join(full.get("notes", []))
    assert full["delivery"]["model"] == "eleven_v3" and "[whispers]" in full["delivery"]["audio_tags"]
    assert "audio tags" in full["delivery"]["style"]


def test_delivery_vocabulary_matches_the_model(monkeypatch, keyed) -> None:
    delivery = voiceover.voice_options(details=True)["delivery"]
    assert any("stability" in rule for rule in delivery["rules"])

    # a pinned model (OMNIFRAME_ELEVEN_MODEL) is the default and drives the delivery rules
    _config(monkeypatch, elevenlabs_api_key="sk_test", eleven_model="eleven_multilingual_v2")
    result = voiceover.voice_options(details=True)
    assert [m["default"] for m in result["models"]["elevenlabs"]] == [False, True]
    v2 = result["delivery"]
    assert "audio_tags" not in v2 and "<break" in v2["rules"][0]


def test_the_newest_elevenlabs_model_is_picked_from_the_list(monkeypatch, keyed) -> None:
    assert voiceover.eleven_model_id() == "eleven_v3"
    keyed.models = [{"model_id": "eleven_v4", "name": "Eleven v4", "can_do_text_to_speech": True},
                    {"model_id": "eleven_v3", "name": "Eleven v3", "can_do_text_to_speech": True},
                    {"model_id": "eleven_alpha", "name": "Alpha", "can_do_text_to_speech": True,
                     "requires_alpha_access": True}]
    assert voiceover.eleven_model_id() == "eleven_v4"  # a newer version from the list, no code change
    assert [m["id"] for m in voiceover.voice_options()["models"]["elevenlabs"]] == ["eleven_v4", "eleven_v3"]


def test_the_env_variable_pins_the_elevenlabs_model_without_a_list_call(monkeypatch, keyed) -> None:
    _config(monkeypatch, elevenlabs_api_key="sk_test", eleven_model="pinned_model_x")
    assert voiceover.eleven_model_id() == "pinned_model_x"
    assert "/v1/models" not in keyed.paths()


def test_a_failed_elevenlabs_model_list_names_the_variable_and_no_old_id(monkeypatch, keyed) -> None:
    api = FakeApi(fail_models=401)
    monkeypatch.setattr("urllib.request.urlopen", api)

    with pytest.raises(RuntimeError) as raised:
        voiceover.eleven_model_id()
    assert "OMNIFRAME_ELEVEN_MODEL" in str(raised.value) and "HTTP 401" in str(raised.value)
    assert "eleven_v3" not in str(raised.value)

    result = voiceover.voice_options()
    assert "elevenlabs" not in result.get("models", {})  # no list, so no model at all
    assert "HTTP 401" in result["errors"]["models"] and "sk_test" not in json.dumps(result)
    assert "eleven_v3" not in json.dumps(result.get("models", {}))


def test_voices_are_read_from_every_page(monkeypatch, keyed) -> None:
    pages = [
        [{"voice_id": "pageOneAAAAAAAAAAA", "name": "First", "category": "premade", "labels": {"gender": "male"}}],
        [{"voice_id": "pageTwoBBBBBBBBBBB", "name": "Second", "category": "professional", "labels": {"gender": "male"}}],
        [{"voice_id": "pageThreeCCCCCCCCC", "name": "Third", "category": "cloned", "labels": {"gender": "female"}}],
    ]
    api = FakeApi(pages=pages, library={"voices": []})
    monkeypatch.setattr("urllib.request.urlopen", api)

    result = voiceover.voice_options(limit=50)
    assert [v["name"] for v in result["own_voices"]] == ["First", "Second", "Third"]
    voice_calls = [params for path, params in api.calls if path == "/v2/voices"]
    assert [c.get("next_page_token") for c in voice_calls] == [None, "1", "2"]  # first page has no token
    assert all(c["include_total_count"] == "false" and c["page_size"] == "100" for c in voice_calls)


def test_free_plan_marking_applies_to_voices_on_later_pages(monkeypatch, keyed) -> None:
    pages = [
        [{"voice_id": "pageOneAAAAAAAAAAA", "name": "First", "category": "premade", "labels": {"gender": "male"}}],
        [{"voice_id": "pageTwoBBBBBBBBBBB", "name": "Second", "category": "cloned", "labels": {"gender": "male"}}],
    ]
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(pages=pages, tier="free", library={"voices": []}))

    result = voiceover.voice_options(limit=50)
    assert [v["name"] for v in result["own_voices"]] == ["First"]
    assert [v["name"] for v in result["library_voices_paid_plan_only"]["voices"]] == ["Second"]


def test_a_voice_list_that_never_ends_is_stopped(monkeypatch, keyed) -> None:
    class Endless(FakeApi):
        def __call__(self, request, timeout=None):
            if urlparse(request.full_url).path == "/v2/voices":
                return Reply({"voices": [], "has_more": True, "next_page_token": "again"})
            return super().__call__(request, timeout)

    monkeypatch.setattr(voiceover, "ELEVEN_VOICE_MAX_PAGES", 3)
    monkeypatch.setattr("urllib.request.urlopen", Endless(library={"voices": []}))
    result = voiceover.voice_options()
    assert result["own_voices"] == []
    assert "did not end after 3 pages" in result["errors"]["own_voices"]


def test_gemini_models_come_newest_first_with_a_default_for_each_use(monkeypatch, keyed) -> None:
    _config(monkeypatch, elevenlabs_api_key="", gemini_api_key="g")
    monkeypatch.setattr("urllib.request.urlopen", _no_elevenlabs_call)
    result = voiceover.voice_options()

    rows = result["models"]["gemini"]
    tts = [(m["id"], m["default"]) for m in rows if m["use"] == "text to speech"]
    # 3.8 before 3.1; the plain flash beats its lite sibling; the preview id loses to the final one
    assert tts == [("gemini-3.8-flash-tts", True), ("gemini-3.8-flash-lite-tts", False),
                   ("gemini-3.1-flash-tts-preview", False)]
    assert "gemini_models" not in result.get("errors", {})


def test_a_failed_gemini_list_is_reported_and_no_model_is_guessed(monkeypatch, keyed) -> None:
    _config(monkeypatch, elevenlabs_api_key="", gemini_api_key="g")
    monkeypatch.setattr("urllib.request.urlopen", _no_elevenlabs_call)

    def refused():
        raise RuntimeError("could not list Gemini models: 403 PERMISSION_DENIED")

    monkeypatch.setattr(model_catalog, "gemini_model_list", refused)
    result = voiceover.voice_options()
    assert "models" not in result
    assert "403" in result["errors"]["gemini_models"]

    with pytest.raises(RuntimeError, match="OMNIFRAME_TTS_MODEL"):
        model_catalog.tts_model_id()


def test_no_key_means_no_elevenlabs_delivery_guide_even_with_details(no_keys) -> None:
    result = voiceover.voice_options(details=True)
    assert "delivery" not in result and "elevenlabs_models" not in result


def test_limit_caps_every_list(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    result = voiceover.voice_options(limit=1)
    assert len(result["own_voices"]) == 1 and len(result["edge_voices"]) == 1 and len(result["gemini_voices"]) == 1
    assert len(result["library_voices"]) == 1 and len(result["library_voices_paid_plan_only"]["voices"]) == 1

    # `limit` itself is capped at 50 (checked with the size cap out of the way)
    monkeypatch.setattr(voiceover, "VOICE_RESPONSE_MAX_CHARS", 10**6)
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(own=BIG_OWN))
    assert len(voiceover.voice_options(limit=500)["own_voices"]) == 50


def test_the_answer_stays_under_9000_characters_and_says_what_was_left_out(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(library=BIG_LIBRARY, own=BIG_OWN))
    result = voiceover.voice_options(limit=50)

    assert _size(result) <= voiceover.VOICE_RESPONSE_MAX_CHARS == 9000
    assert any("left out" in note and "language, gender or query" in note for note in result["notes"])
    assert result["own_voices"][0]["id"].startswith("own000")  # the best-ranked voices are the ones kept
    kept = [*result["own_voices"], *result["library_voices"], *result["library_voices_paid_plan_only"]["voices"]]
    assert kept and all(len(v["description"]) <= 80 for v in kept)
    assert len(result["own_voices"]) < 50  # something really was dropped


def test_details_come_on_top_of_the_voices_and_the_answer_still_fits(monkeypatch: pytest.MonkeyPatch, keyed) -> None:
    monkeypatch.setattr("urllib.request.urlopen", FakeApi(library=BIG_LIBRARY, own=BIG_OWN))
    plain = voiceover.voice_options(limit=50)
    full = voiceover.voice_options(limit=50, details=True)

    assert _size(full) <= 9000
    assert "delivery" in full and len(full["models"]["elevenlabs"]) == 2  # the rules are never the part that is cut
    assert len(full["own_voices"]) < len(plain["own_voices"])  # the room they take comes out of the voices
    assert any("left out" in note for note in full["notes"])


def test_a_small_answer_has_no_left_out_note(keyed) -> None:
    result = voiceover.voice_options()
    assert _size(result) <= 9000
    assert not any("left out" in note for note in result.get("notes", []))


def test_the_answer_without_a_key_is_small_too(no_keys) -> None:
    assert _size(voiceover.voice_options(limit=50)) <= 9000


# ------------------------------------------------------------------ provider choice

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
    monkeypatch.setenv("OMNIFRAME_TTS_PROVIDER", "gemini")
    assert voiceover.voice_options()["provider_choice"]["recommended"] == "gemini"


def test_the_decision_stays_with_the_model(no_keys) -> None:
    """v2 returns options, not an instruction to ask the user (design §7, requirement 7.2)."""
    assert "decision_hint" not in voiceover.voice_options()


def test_the_tool_passes_details_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from omniframe import server

    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(voiceover, "voice_options", fake)
    server.voice_options(language="ru", query="calm", details=True)
    assert seen == {"language": "ru", "gender": None, "query": "calm", "limit": 10, "details": True}
    server.voice_options()
    assert seen["details"] is False

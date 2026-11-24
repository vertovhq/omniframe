"""Voice v2 tests (design §7): providers, word timings, chunking, fallbacks.

All offline: ElevenLabs HTTP is mocked at `urllib.request.urlopen`, edge-tts is a fake module,
Gemini and faster-whisper are patched. Audio is real (synthetic wav, ffmpeg masters it).
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import math
import struct
import sys
import types
import urllib.error
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs, project  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.ffmpeg import stream_info  # noqa: E402
from omniframe.tools import voiceover, watch  # noqa: E402

TAGGED = "[whispers] Hello, brave world. [excited] We start now!"


# ------------------------------------------------------------------ fixtures and fakes

@pytest.fixture(autouse=True)
def voice_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Own output dir per test, one ElevenLabs key, nothing else; no provider override from the environment."""
    cfg = dataclasses.replace(
        CONFIG, output_dir=tmp_path / "out", elevenlabs_api_key="sk_test_key", gemini_api_key="",
        eleven_model="eleven_v3",
    )
    for module in (jobs, project, voiceover, watch):
        monkeypatch.setattr(module, "CONFIG", cfg)
    monkeypatch.delenv("OMNIFRAME_TTS_PROVIDER", raising=False)
    monkeypatch.setattr(voiceover, "_model_limits", {})
    return {"cfg": cfg, "monkeypatch": monkeypatch}


def wav_bytes(seconds: float, rate: int = 24000) -> bytes:
    """A quiet 220 Hz tone of exactly `seconds`, as a wav file."""
    frames = b"".join(
        struct.pack("<h", int(6000 * math.sin(2 * math.pi * 220 * n / rate))) for n in range(int(seconds * rate))
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames)
    return buf.getvalue()


def alignment_for(text: str, step: float = 0.1) -> dict:
    """What ElevenLabs returns: one entry per character, `step` seconds each."""
    chars = list(text)
    return {
        "characters": chars,
        "character_start_times_seconds": [round(i * step, 3) for i in range(len(chars))],
        "character_end_times_seconds": [round((i + 1) * step, 3) for i in range(len(chars))],
    }


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeEleven:
    """Stands in for `urllib.request.urlopen`; answers by URL and records every request."""

    def __init__(self, durations: list[float] | None = None, alignment: bool = True, step: float = 0.1) -> None:
        self.durations = durations or [1.0]
        self.alignment = alignment
        self.step = step  # seconds per character in the alignment
        self.requests: list[dict] = []
        self.speeches = 0

    def __call__(self, request, timeout=None):
        url = request.full_url
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.requests.append({
            "url": url, "method": request.get_method(), "body": body,
            "key": request.get_header("Xi-api-key"),
        })
        if "/with-timestamps" in url:
            seconds = self.durations[min(self.speeches, len(self.durations) - 1)]
            self.speeches += 1
            reply = {"audio_base64": base64.b64encode(wav_bytes(seconds)).decode("ascii")}
            reply["alignment"] = alignment_for(body["text"], self.step) if self.alignment else None
            return FakeResponse(reply)
        raise AssertionError(f"unexpected request {request.get_method()} {url}")


def payload(text: str = TAGGED, **extra) -> dict:
    return {"text": text, "project": "t", **extra}


def run(**kw) -> dict:
    return voiceover.run_job(payload(**kw), lambda *a, **k: None)


def read_words(result: dict) -> list[dict]:
    return json.loads(Path(result["words_path"]).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ alignment -> words

def test_alignment_becomes_words_with_audio_tags_stripped() -> None:
    words = voiceover.words_from_alignment(alignment_for(TAGGED))
    assert [w["w"] for w in words] == ["Hello,", "brave", "world.", "We", "start", "now!"]
    first = TAGGED.index("Hello,")
    assert words[0] == {"w": "Hello,", "s": round(first * 0.1, 3), "e": round((first + 6) * 0.1, 3)}
    assert all(w["e"] > w["s"] for w in words)


def test_tags_glued_to_words_and_ssml_breaks_are_not_part_of_words() -> None:
    text = '[sighs]Yes <break time="1.0s" /> no[laughs]!'
    words = voiceover.words_from_alignment(alignment_for(text))
    assert [w["w"] for w in words] == ["Yes", "no", "!"]


def test_alignment_offset_is_added_and_empty_alignment_gives_no_words() -> None:
    words = voiceover.words_from_alignment(alignment_for("Hi there"), offset=2.0)
    assert words[0]["s"] == 2.0
    assert voiceover.words_from_alignment({"characters": []}) == []


def test_edge_boundaries_convert_ticks_to_seconds() -> None:
    events = [
        {"offset": 5_000_000, "duration": 3_000_000, "text": "Привет"},
        {"offset": 10_000_000, "duration": 4_500_000, "text": " мир "},
        {"offset": 20_000_000, "duration": 1, "text": "  "},
    ]
    assert voiceover.words_from_boundaries(events, offset=1.0) == [
        {"w": "Привет", "s": 1.5, "e": 1.8},
        {"w": "мир", "s": 2.0, "e": 2.45},
    ]


# ------------------------------------------------------------------ chunking

def test_short_text_is_one_chunk_and_empty_text_none() -> None:
    assert voiceover.split_text("One line.", 100) == ["One line."]
    assert voiceover.split_text("   ", 100) == []


def test_chunks_respect_the_limit_and_keep_all_text() -> None:
    paragraphs = [f"Paragraph {n}. " + "word " * 12 for n in range(6)]
    text = "\n\n".join(p.strip() for p in paragraphs)
    chunks = voiceover.split_text(text, 150)
    assert len(chunks) > 1 and all(len(c) <= 150 for c in chunks)
    assert " ".join("\n\n".join(chunks).split()) == " ".join(text.split())


def test_over_long_paragraph_is_cut_at_sentences_then_spaces_and_never_inside_a_tag() -> None:
    sentences = " ".join(f"Sentence number {n} is here." for n in range(10))
    cut = voiceover.split_text(sentences, 60)
    assert all(len(c) <= 60 for c in cut) and all(c.endswith(".") for c in cut)

    tagged = "alpha beta [speaks in a very low and slow voice] gamma delta"
    tag_chunks = voiceover.split_text(tagged, 45)
    assert tag_chunks == ["alpha beta", "[speaks in a very low and slow voice] gamma", "delta"]
    no_spaces = voiceover.split_text("x" * 25, 10)
    assert no_spaces == ["x" * 10, "x" * 10, "x" * 5]


# ------------------------------------------------------------------ ElevenLabs

def test_elevenlabs_keeps_the_text_unchanged_and_returns_provider_timings(voice_env) -> None:
    fake = FakeEleven(durations=[2.0])
    voice_env["monkeypatch"].setattr("urllib.request.urlopen", fake)

    result = run(voice="Brian", settings={"stability": 0.5, "speed": 1.1})

    assert len(fake.requests) == 1
    sent = fake.requests[0]
    assert sent["method"] == "POST" and sent["key"] == "sk_test_key"
    assert sent["url"].startswith(
        "https://api.elevenlabs.io/v1/text-to-speech/nPczCjzI2devNBz1zQrb/with-timestamps")
    assert sent["body"]["text"] == TAGGED  # delivery markup passes through untouched
    assert sent["body"]["model_id"] == "eleven_v3"
    assert sent["body"]["voice_settings"] == {"stability": 0.5, "speed": 1.1}

    assert result["provider"] == "elevenlabs" and result["words_source"] == "provider"
    assert result["model"] == "eleven_v3" and result["parts"] == 1
    assert "audio tags" in result["delivery"]
    words = read_words(result)
    assert [w["w"] for w in words][:2] == ["Hello,", "brave"]
    assert not any("[" in w["w"] for w in words)
    audio = Path(result["audio"])
    assert audio == voice_env["cfg"].output_dir / "projects" / "t" / "audio" / "voice.mp3"
    assert abs(stream_info(audio).duration - 2.0) < 0.15 and abs(result["duration"] - 2.0) < 0.15
    assert result["words_path"].endswith("voice.words.json")
    assert not list((audio.parent.parent / ".work").iterdir()), "work files must be removed"


def test_long_text_chunks_are_joined_and_word_times_follow_chunk_durations(voice_env) -> None:
    fake = FakeEleven(durations=[1.0, 1.5, 0.9], step=0.05)  # each chunk's timings fit inside its audio
    voice_env["monkeypatch"].setattr("urllib.request.urlopen", fake)
    voice_env["monkeypatch"].setitem(voiceover.ELEVEN_CHAR_LIMITS, "eleven_v3", 20)
    text = "First part here.\n\nSecond part here.\n\nThird part here."

    result = run(text=text)

    assert result["parts"] == 3 and len(fake.requests) == 3
    assert [r["body"]["text"] for r in fake.requests] == ["First part here.", "Second part here.", "Third part here."]
    words = read_words(result)
    firsts = [w for w in words if w["w"] in ("First", "Second", "Third")]
    assert [w["s"] for w in firsts] == pytest.approx([0.0, 1.0, 2.5], abs=0.02)
    assert words == sorted(words, key=lambda w: w["s"])
    assert abs(result["duration"] - 3.4) < 0.2
    assert words[-1]["e"] <= result["duration"] + 0.05


def test_missing_alignment_falls_back_to_whisper_or_reports_none(voice_env) -> None:
    mp = voice_env["monkeypatch"]
    mp.setattr("urllib.request.urlopen", FakeEleven(alignment=False))
    mp.setattr(watch, "whisper_available", lambda: False)
    result = run()
    assert result["words_source"] == "none" and result["words_path"] is None
    assert "faster-whisper" in result["captions_note"]


def test_http_error_names_the_status_and_never_leaks_the_key(voice_env) -> None:
    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail": "bad key"}'))

    voice_env["monkeypatch"].setattr("urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError) as err:
        run(voice="nPczCjzI2devNBz1zQrb")
    assert "401" in str(err.value) and "sk_test_key" not in str(err.value)


def test_library_voice_refused_gets_a_plain_explanation(voice_env) -> None:
    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 402, "Payment Required", {}, io.BytesIO(b"{}"))

    voice_env["monkeypatch"].setattr("urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="paid ElevenLabs plan"):
        run(voice="21m00Tcm4TlvDq8ikWAM")


def test_voice_name_is_looked_up_among_the_account_voices(voice_env) -> None:
    class Lookup(FakeEleven):
        def __call__(self, request, timeout=None):
            if "/v2/voices" in request.full_url:
                self.requests.append({"url": request.full_url, "method": "GET", "body": None, "key": None})
                return FakeResponse({"voices": [{"voice_id": "abcDEF123456789xyzQQ", "name": "Aria"}]})
            return super().__call__(request, timeout)

    fake = Lookup()
    voice_env["monkeypatch"].setattr("urllib.request.urlopen", fake)
    run(voice="aria")
    assert "/v1/text-to-speech/abcDEF123456789xyzQQ/with-timestamps" in fake.requests[-1]["url"]

    with pytest.raises(ValueError, match="unknown ElevenLabs voice"):
        run(voice="Nobody Here")


# ------------------------------------------------------------------ edge-tts

class FakeCommunicate:
    instances: list["FakeCommunicate"] = []

    def __init__(self, text: str, voice: str = "", **options) -> None:
        self.text, self.voice, self.options = text, voice, options
        FakeCommunicate.instances.append(self)

    async def stream(self):
        yield {"type": "audio", "data": wav_bytes(1.0)}
        yield {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_000_000, "text": "Hello"}
        yield {"type": "WordBoundary", "offset": 4_000_000, "duration": 3_000_000, "text": "world"}


@pytest.fixture
def fake_edge(voice_env):
    module = types.ModuleType("edge_tts")
    module.Communicate = FakeCommunicate
    FakeCommunicate.instances = []
    voice_env["monkeypatch"].setitem(sys.modules, "edge_tts", module)
    return FakeCommunicate


def test_edge_word_boundaries_become_the_words_file(fake_edge) -> None:
    result = run(text="[whispers] Hello world", provider="edge", voice="en-US-GuyNeural",
                 settings={"rate": "+10%"})

    spoken = fake_edge.instances[0]
    assert spoken.text == "Hello world" and spoken.voice == "en-US-GuyNeural"
    assert spoken.options["boundary"] == "WordBoundary" and spoken.options["rate"] == "+10%"
    assert read_words(result) == [{"w": "Hello", "s": 0.1, "e": 0.3}, {"w": "world", "s": 0.4, "e": 0.7}]
    assert result["provider"] == "edge" and result["words_source"] == "provider" and result["model"] is None
    assert "removed" in result["note"]


def test_edge_default_voice_follows_the_language_of_the_text(fake_edge) -> None:
    run(text="Привет, мир", provider="edge")
    run(text="Hello there", provider="edge")
    assert [c.voice for c in fake_edge.instances] == ["ru-RU-DmitryNeural", "en-US-GuyNeural"]


def test_without_any_key_the_default_provider_is_edge(voice_env, fake_edge) -> None:
    cfg = dataclasses.replace(voice_env["cfg"], elevenlabs_api_key="", gemini_api_key="")
    for module in (jobs, project, voiceover, watch):
        voice_env["monkeypatch"].setattr(module, "CONFIG", cfg)

    assert voiceover.default_provider() == "edge"
    result = run(text="Hello world")
    assert result["provider"] == "edge" and result["voice"] == "en-US-GuyNeural"


def test_elevenlabs_key_makes_elevenlabs_the_default_and_the_env_can_override(voice_env) -> None:
    assert voiceover.default_provider() == "elevenlabs"
    voice_env["monkeypatch"].setenv("OMNIFRAME_TTS_PROVIDER", "gemini")
    assert voiceover.default_provider() == "gemini"


# ------------------------------------------------------------------ gemini and alignment

@pytest.fixture
def gemini(voice_env):
    cfg = dataclasses.replace(voice_env["cfg"], gemini_api_key="g-test")
    for module in (jobs, project, voiceover, watch):
        voice_env["monkeypatch"].setattr(module, "CONFIG", cfg)
    calls: list[tuple] = []

    def fake_pcm(self, text, voice, model):
        calls.append((text, voice, model))
        return b"".join(struct.pack("<h", int(5000 * math.sin(n / 9))) for n in range(24000))  # 1 s

    voice_env["monkeypatch"].setattr(voiceover.GeminiProvider, "_pcm", fake_pcm)
    return calls


def test_gemini_without_whisper_has_no_words(voice_env, gemini) -> None:
    voice_env["monkeypatch"].setattr(watch, "whisper_available", lambda: False)
    stale = voice_env["cfg"].output_dir / "projects" / "t" / "audio" / "voice.words.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("[{\"w\": \"old\", \"s\": 0, \"e\": 1}]", encoding="utf-8")

    result = run(provider="gemini", voice="Kore")

    assert gemini[0][:2] == (TAGGED, "Kore")  # the text reaches Gemini unchanged
    assert result["provider"] == "gemini" and result["voice"] == "Kore"
    assert result["words_source"] == "none" and result["words_path"] is None
    assert "captions" in result["captions_note"] and "faster-whisper" in result["captions_note"]
    assert abs(result["duration"] - 1.0) < 0.15
    assert not stale.exists(), "a words file from an earlier take must not stay next to new audio"


def test_gemini_with_whisper_aligns_the_finished_audio(voice_env, gemini) -> None:
    seen: dict = {}

    def fake_transcribe(src, language, duration, report):
        seen.update(src=Path(src), language=language, duration=duration)
        return {"language": "en", "words": [{"w": "hello", "s": 0.1, "e": 0.4}], "segments": []}

    voice_env["monkeypatch"].setattr(watch, "whisper_available", lambda: True)
    voice_env["monkeypatch"].setattr(watch, "transcribe", fake_transcribe)

    result = run(provider="gemini", settings={"language": "en"})

    assert result["words_source"] == "faster-whisper"
    assert read_words(result) == [{"w": "hello", "s": 0.1, "e": 0.4}]
    assert seen["src"] == Path(result["audio"]) and seen["language"] == "en"


def test_failing_whisper_keeps_the_voiceover_and_says_why(voice_env, gemini) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("model download failed")

    voice_env["monkeypatch"].setattr(watch, "whisper_available", lambda: True)
    voice_env["monkeypatch"].setattr(watch, "transcribe", broken)
    result = run(provider="gemini")
    assert Path(result["audio"]).is_file() and result["words_source"] == "none"
    assert "model download failed" in result["captions_note"]


# ------------------------------------------------------------------ provider layer

def test_unavailable_or_unknown_provider_is_an_error_not_a_silent_switch() -> None:
    with pytest.raises(RuntimeError, match="OMNIFRAME_GEMINI_API_KEY"):
        voiceover.resolve_provider("gemini")
    with pytest.raises(ValueError, match="unknown voice provider"):
        voiceover.resolve_provider("siri")


def test_a_local_provider_plugs_in_without_changing_the_tool(voice_env) -> None:
    class Local:
        name = "voicestudio"
        raw_suffix = ".wav"

        def available(self) -> bool:
            return True

        def unavailable_hint(self) -> str:
            return ""

        def max_chars(self, model) -> int:
            return 1000

        def default_voice(self, text, settings) -> str:
            return "local-1"

        def default_model(self):
            return None

        def synthesize(self, text, voice, model, settings, out_audio):
            out_audio.write_bytes(wav_bytes(1.0))
            return [{"w": "local", "s": 0.0, "e": 0.5}]

    voice_env["monkeypatch"].setitem(voiceover.PROVIDERS, "voicestudio", Local())
    result = run(provider="voicestudio")
    assert result["provider"] == "voicestudio" and result["voice"] == "local-1"
    assert read_words(result) == [{"w": "local", "s": 0.0, "e": 0.5}]


def test_tool_logic_validates_then_starts_a_job(voice_env) -> None:
    started: list[tuple] = []

    def fake_run_or_detach(kind, data, key=None, wait_s=20.0):
        started.append((kind, data, wait_s))
        return {"state": "running", "job_id": "voiceover-x"}

    voice_env["monkeypatch"].setattr(jobs, "run_or_detach", fake_run_or_detach)
    out = voiceover.synthesize_voiceover("Hello", "My Video", voice="Brian", name="Intro Take", wait_s=5)

    assert out["job_id"] == "voiceover-x"
    kind, data, wait_s = started[0]
    assert kind == "voiceover" and wait_s == 5
    assert data == {"text": "Hello", "project": "My Video", "provider": None, "voice": "Brian",
                    "model": None, "name": "Intro Take", "settings": {}, "project_holds": []}

    with pytest.raises(ValueError, match="empty text"):
        voiceover.synthesize_voiceover("  ", "p")
    with pytest.raises(ValueError, match="settings"):
        voiceover.synthesize_voiceover("Hi", "p", settings=["stability"])  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="not available"):
        voiceover.synthesize_voiceover("Hi", "p", provider="gemini")
    assert len(started) == 1


def test_the_job_kind_resolves_to_this_module() -> None:
    assert jobs._resolve("voiceover") is voiceover.run_job


def test_delivery_style_tells_v3_from_v2() -> None:
    assert "audio tags" in voiceover.delivery_style("eleven_v3")
    assert "audio tags" in voiceover.delivery_style("eleven_v4")
    assert "SSML" in voiceover.delivery_style("eleven_multilingual_v2")
    assert "no SSML" in voiceover.delivery_style("eleven_v3")


# ------------------------------------------------------------------ a name that already holds a voice

@pytest.fixture
def direct_jobs(voice_env) -> list:
    """Runs each voiceover job at once in this process, ElevenLabs mocked; returns the started payloads."""
    started: list[dict] = []

    def run_now(kind, data, key=None, wait_s=20.0):
        started.append(data)
        return voiceover.run_job(data, lambda *a, **k: None)

    voice_env["monkeypatch"].setattr(jobs, "run_or_detach", run_now)
    return started


CLASH = "voice.mp3 already exists in project octopus-hearts with other text; pass overwrite=true or another name"


def test_other_text_under_the_same_name_is_refused_and_the_files_stay(voice_env, direct_jobs) -> None:
    voice_env["monkeypatch"].setattr("urllib.request.urlopen", FakeEleven())
    first = voiceover.synthesize_voiceover("First text.", "octopus-hearts", name="voice", wait_s=5)
    audio, words = Path(first["audio"]), Path(first["words_path"])
    audio_before, words_before = audio.read_bytes(), words.read_bytes()

    out = voiceover.synthesize_voiceover("Another text.", "Octopus Hearts", name="voice", wait_s=5)

    assert out["summary"] == CLASH and out["error"] == CLASH
    assert audio.read_bytes() == audio_before and words.read_bytes() == words_before
    assert len(direct_jobs) == 1  # the refused call started no job


def test_overwrite_true_replaces_the_voice(voice_env, direct_jobs) -> None:
    fake = FakeEleven(durations=[1.0])
    voice_env["monkeypatch"].setattr("urllib.request.urlopen", fake)
    first = voiceover.synthesize_voiceover("First text.", "octopus-hearts", name="voice", wait_s=5)
    audio = Path(first["audio"])
    audio_before = audio.read_bytes()

    fake.durations = [2.0]  # a longer take, so the new audio differs
    second = voiceover.synthesize_voiceover("Another text.", "octopus-hearts", name="voice", overwrite=True, wait_s=5)

    assert "error" not in second and second["duration"] > 1.5  # the first take was 1 s
    assert audio.read_bytes() != audio_before
    assert read_words(second)[0]["w"] == "Another"
    assert len(direct_jobs) == 2


def test_same_text_under_the_same_name_is_a_repeat_and_goes_through(voice_env, direct_jobs) -> None:
    voice_env["monkeypatch"].setattr("urllib.request.urlopen", FakeEleven())
    voiceover.synthesize_voiceover("Same text.", "octopus-hearts", name="voice", wait_s=5)

    second = voiceover.synthesize_voiceover("Same text.", "octopus-hearts", name="voice", wait_s=5)

    assert "error" not in second and "audio" in second
    assert len(direct_jobs) == 2


def test_a_file_with_no_text_record_counts_as_other_text(voice_env, direct_jobs) -> None:
    audio = project.project_dir("octopus-hearts") / "audio"
    (audio / "voice.mp3").write_bytes(b"made before the text record")

    out = voiceover.synthesize_voiceover("Any text.", "octopus-hearts", name="voice", wait_s=5)

    assert out["summary"] == CLASH
    assert (audio / "voice.mp3").read_bytes() == b"made before the text record"
    assert direct_jobs == []

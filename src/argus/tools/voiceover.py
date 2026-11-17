"""Voice v2: providers, chunking, word timings, radio-grade mastering (design §7).

`synthesize_voiceover` turns the model's text (with its delivery markup, unchanged) into
`<project>/audio/<name>.mp3` plus `<name>.words.json` (`[{w, s, e}]`, seconds).

Providers share one small protocol (`VoiceProvider`), so a local provider (Voice Studio)
can be added with `register_provider` without changing a tool signature:

* `elevenlabs`: default when a key is configured; word timings come from the API.
* `edge`: default without keys (edge-tts); word timings come from WordBoundary events.
* `gemini`: opt-in (`provider="gemini"`); no timings, so faster-whisper aligns when installed.

Pipeline: split long text on paragraph boundaries -> one provider call per chunk ->
decode every chunk to 48 kHz wav -> concatenate -> offset word timings by the exact chunk
durations -> master (60 Hz highpass, 110 Hz body EQ, 3.2 kHz presence EQ, compressor,
loudnorm) -> mp3. Anything that can take longer than ~20 s runs through `argus.jobs`.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .. import __version__, jobs
from ..config import CONFIG
from ..ffmpeg import run_ffmpeg, stream_info
from ..project import project_dir, slugify
from . import watch

# ------------------------------------------------------------------ constants

# ElevenLabs API reference (checked 2026-11-16):
#   text to speech with timestamps: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
#     POST /v1/text-to-speech/{voice_id}/with-timestamps -> {audio_base64, alignment, normalized_alignment};
#     alignment = {characters, character_start_times_seconds, character_end_times_seconds}
#   models:                       https://elevenlabs.io/docs/api-reference/models/list      GET /v1/models
#   own voices (search/filter):   https://elevenlabs.io/docs/api-reference/voices/search    GET /v2/voices
#   Voice Library search:         https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared
#                                 GET /v1/shared-voices
#   Library voices need no "add" step: "You can use voices from the Voice Library directly without
#   saving them to My Voices" (https://elevenlabs.io/docs/product/guides/voices); the same page warns
#   that Voice Library voices are not available via the API to free tier users. So ARGUS never adds
#   voices to the account; it reports a plain-language error instead.
ELEVEN_HOST = "https://api.elevenlabs.io"
ELEVEN_OUTPUT_FORMAT = "mp3_44100_128"  # allowed on every plan; 192 kbps needs Creator+ (same page as above)

# Per-request character limits: https://elevenlabs.io/docs/overview/models ("Character limits").
# The live value is `maximum_text_length_per_request` in GET /v1/models; this table is the
# offline answer, 5000 (the smallest in the table) is the answer for an unknown model.
ELEVEN_CHAR_LIMITS = {
    "eleven_v4": 10000,
    "eleven_v3": 5000,
    "eleven_flash_v2_5": 40000,
    "eleven_flash_v2": 30000,
    "eleven_multilingual_v2": 10000,
}
ELEVEN_DEFAULT_CHAR_LIMIT = 5000

# https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices : Eleven v4 and v3 take
# audio tags ([whispers], [excited]) and punctuation; SSML <break> works on the v2 family only.
ELEVEN_TAG_MODEL_PREFIXES = ("eleven_v3", "eleven_v4")

# ElevenLabs preset voices (subset): name -> voice_id. A raw voice_id or an own voice name works too.
ELEVEN_VOICES = {
    "Brian": "nPczCjzI2devNBz1zQrb",  # deep, resonant, comforting narrator
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
}
_ELEVEN_ID_RE = re.compile(r"[A-Za-z0-9_-]{15,40}")
_ELEVEN_VOICE_SETTINGS = ("stability", "similarity_boost", "style", "speed", "use_speaker_boost")
ELEVEN_HTTP_TIMEOUT_S = 300
VOICE_LIST_TIMEOUT_S = 15

# Gemini TTS (https://ai.google.dev/gemini-api/docs/speech-generation): bracketed tags such as
# [whispers] steer delivery inline; the output is raw 24 kHz mono 16-bit PCM.
AVAILABLE_VOICES = (
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
)
GEMINI_CHAR_LIMIT = 3000
GEMINI_PCM_RATE = 24000

EDGE_CHAR_LIMIT = 8000
# edge-tts 7.x defaults to sentence boundaries; word boundaries must be asked for.
EDGE_BOUNDARY = "WordBoundary"
EDGE_TICKS_PER_S = 10_000_000  # WordBoundary offset/duration are in 100-ns units

# Default edge voice per language: (male, female) ShortNames from `edge-tts --list-voices`.
EDGE_VOICES: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "ru": (("ru-RU-DmitryNeural", "Dmitry"), ("ru-RU-SvetlanaNeural", "Svetlana")),
    "en": (("en-US-GuyNeural", "Guy"), ("en-US-JennyNeural", "Jenny")),
    "uk": (("uk-UA-OstapNeural", "Ostap"), ("uk-UA-PolinaNeural", "Polina")),
    "de": (("de-DE-ConradNeural", "Conrad"), ("de-DE-KatjaNeural", "Katja")),
    "es": (("es-ES-AlvaroNeural", "Alvaro"), ("es-ES-ElviraNeural", "Elvira")),
    "fr": (("fr-FR-HenriNeural", "Henri"), ("fr-FR-DeniseNeural", "Denise")),
    "it": (("it-IT-DiegoNeural", "Diego"), ("it-IT-ElsaNeural", "Elsa")),
    "pt": (("pt-BR-AntonioNeural", "Antonio"), ("pt-BR-FranciscaNeural", "Francisca")),
    "pl": (("pl-PL-MarekNeural", "Marek"), ("pl-PL-ZofiaNeural", "Zofia")),
    "tr": (("tr-TR-AhmetNeural", "Ahmet"), ("tr-TR-EmelNeural", "Emel")),
    "ja": (("ja-JP-KeitaNeural", "Keita"), ("ja-JP-NanamiNeural", "Nanami")),
    "zh": (("zh-CN-YunxiNeural", "Yunxi"), ("zh-CN-XiaoxiaoNeural", "Xiaoxiao")),
    "kk": (("kk-KZ-DauletNeural", "Daulet"), ("kk-KZ-AigulNeural", "Aigul")),
}
_LANGUAGE_NAMES = {
    "russian": "ru", "english": "en", "ukrainian": "uk", "german": "de", "spanish": "es",
    "french": "fr", "italian": "it", "portuguese": "pt", "polish": "pl", "turkish": "tr",
    "japanese": "ja", "chinese": "zh", "kazakh": "kk",
}

MAX_VOICE_LIST = 50
VOICE_DESCRIPTION_CHARS = 80      # a voice's description in `voice_options`
VOICE_RESPONSE_MAX_CHARS = 6000   # `voice_options` without `details`, measured as JSON with indent=2 (what the client gets)
MAX_QUERY_WORDS = 4               # Voice Library search runs once per query word
# https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared : `free_users_allowed` (boolean) says
# whether free users may use a library voice. Those with false go to their own list, marked as paid-plan only.
LIBRARY_PAID_NOTE = (
    "Voice Library voices with free_users_allowed=false: through the API they work only on a paid ElevenLabs plan "
    "(a free plan gets HTTP 402/403). Pick from own_voices and library_voices unless the user has a paid plan."
)
_TAG_RE = re.compile(r"\[[^\[\]]*\]|<[^<>]*>")  # [audio tags] and <ssml/> markup
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")
_noop: Callable[..., None] = lambda *args, **kwargs: None  # noqa: E731


def mastering_chain(loudness_target: float) -> str:
    """The fixed ARGUS radio-master ffmpeg filter chain."""
    return ",".join([
        "highpass=f=60",
        "equalizer=f=110:t=q:w=1:g=2",
        "equalizer=f=3200:t=q:w=2:g=3",
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=120",
        f"loudnorm=I={loudness_target}:TP=-1.5:LRA=11",
    ])


# ------------------------------------------------------------------ text helpers

def strip_markup(text: str) -> str:
    """`text` without `[audio tags]` and `<ssml/>` markup (for providers that would read them aloud)."""
    return re.sub(r"[ \t]{2,}", " ", _TAG_RE.sub("", text)).strip()


def _hard_split(piece: str, limit: int) -> list[str]:
    """Cut one over-long sentence at spaces, never inside a `[tag]`."""
    out: list[str] = []
    rest = piece.strip()
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind(" ")
        opened = window.rfind("[", 0, max(cut, 0))
        if cut > 0 and opened > 0 and opened > window.rfind("]", 0, cut):
            cut = opened  # the space is inside an open [tag ...]: cut before the tag
        if cut <= 0:
            cut = limit
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def _split_paragraph(paragraph: str, limit: int) -> list[str]:
    """A paragraph as pieces of at most `limit` characters, cut at sentence ends when it has to be cut."""
    if len(paragraph) <= limit:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END_RE.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_hard_split(sentence, limit))
        elif current and len(current) + 1 + len(sentence) <= limit:
            current += " " + sentence
        else:
            if current:
                pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, limit: int) -> list[str]:
    """Split `text` into chunks of at most `limit` characters, on paragraph boundaries first.

    Paragraphs (blank-line separated) are packed greedily; a paragraph longer than `limit`
    is cut at sentence ends, and a sentence longer than `limit` at spaces. Audio tags stay whole.
    """
    if limit < 1:
        raise ValueError(f"chunk limit must be >= 1, got {limit}")
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    pieces: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if paragraph:
            pieces.extend(_split_paragraph(paragraph, limit))
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 2 + len(piece) <= limit:
            current += "\n\n" + piece
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


# ------------------------------------------------------------------ word timings

def words_from_alignment(alignment: dict, offset: float = 0.0) -> list[dict]:
    """ElevenLabs character alignment -> `[{w, s, e}]` words, with `[audio tags]` / `<ssml/>` dropped.

    A word is a run of non-space characters outside tags; its start is the start of its first
    character and its end the end of its last one. Punctuation stays attached to its word.
    `offset` (seconds) is added to every time.
    """
    chars = list(alignment.get("characters") or [])
    starts = list(alignment.get("character_start_times_seconds") or [])
    ends = list(alignment.get("character_end_times_seconds") or [])
    count = min(len(chars), len(starts), len(ends))
    if count == 0:
        return []
    chars = [str(c) for c in chars[:count]]
    owner: list[int] = []  # text position -> index of the alignment entry it came from
    for index, piece in enumerate(chars):
        owner.extend([index] * len(piece))
    text = "".join(chars)
    skipped = [False] * len(text)
    for match in _TAG_RE.finditer(text):
        for pos in range(match.start(), match.end()):
            skipped[pos] = True

    words: list[dict] = []

    def add(first: int, last: int) -> None:
        words.append({
            "w": text[first:last + 1],
            "s": round(float(starts[owner[first]]) + offset, 3),
            "e": round(float(ends[owner[last]]) + offset, 3),
        })

    begin: int | None = None
    for pos, ch in enumerate(text):
        inside = not skipped[pos] and not ch.isspace()
        if inside and begin is None:
            begin = pos
        elif not inside and begin is not None:
            add(begin, pos - 1)
            begin = None
    if begin is not None:
        add(begin, len(text) - 1)
    return words


def words_from_boundaries(events: list[dict], offset: float = 0.0) -> list[dict]:
    """edge-tts WordBoundary events (`offset`/`duration` in 100-ns ticks) -> `[{w, s, e}]`."""
    words: list[dict] = []
    for event in events:
        word = str(event.get("text", "")).strip()
        if not word:
            continue
        start = float(event["offset"]) / EDGE_TICKS_PER_S
        end = start + float(event.get("duration", 0)) / EDGE_TICKS_PER_S
        words.append({"w": word, "s": round(start + offset, 3), "e": round(end + offset, 3)})
    return words


# ------------------------------------------------------------------ http

def _importable(module: str) -> bool:
    """True when `module` can be imported, without importing it."""
    if module in sys.modules:
        return sys.modules[module] is not None
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _eleven_headers() -> dict[str, str]:
    return {"xi-api-key": CONFIG.elevenlabs_api_key, "Accept": "application/json"}


def _eleven_json(method: str, path: str, params: dict | None = None, body: dict | None = None,
                 timeout: float = ELEVEN_HTTP_TIMEOUT_S) -> dict | list:
    """One ElevenLabs JSON call. Errors carry the HTTP status and a short server message, never the key."""
    url = f"{ELEVEN_HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(
            [(k, str(v)) for k, v in params.items() if v is not None], doseq=True
        )
    headers = _eleven_headers()
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"ElevenLabs HTTP {exc.code} on {method} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ElevenLabs is not reachable: {exc.reason}") from exc


_model_limits: dict[str, int] = {}


def _eleven_char_limit(model: str) -> int:
    """Characters per request for `model`: the table, then the live model list, then the smallest known."""
    if model in ELEVEN_CHAR_LIMITS:
        return ELEVEN_CHAR_LIMITS[model]
    if model not in _model_limits:
        try:
            for entry in _eleven_json("GET", "/v1/models", timeout=VOICE_LIST_TIMEOUT_S):
                if entry.get("model_id") == model and entry.get("maximum_text_length_per_request"):
                    _model_limits[model] = int(entry["maximum_text_length_per_request"])
        except Exception:  # best effort: an offline lookup must not block synthesis
            pass
    return _model_limits.get(model, ELEVEN_DEFAULT_CHAR_LIMIT)


# Delivery vocabulary for Eleven v3/v4, from "Prompting Eleven v4" ("Audio tags", "Punctuation", "Pace") in
# https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices
# This is material for the model; ARGUS never picks or scores emotions itself.
ELEVEN_VOICE_TAGS = (
    "[whispers]", "[sighs]", "[exhales]", "[laughs]", "[laughs harder]", "[starts laughing]", "[wheezing]",
    "[sarcastic]", "[curious]", "[excited]", "[crying]", "[snorts]", "[mischievously]",
)
ELEVEN_DELIVERY_RULES = (
    "put a tag right before the words it colours; match tags to the voice's character (a calm narrator will not shout convincingly)",
    "a tag can be read as a sound effect; describe the voice quality instead of a cue, e.g. [low, gravelly voice]",
    "'...' adds a pause and weight, a dash is a short break, CAPITALS add stress, ordinary punctuation sets the rhythm",
    "settings.speed 0.7..1.2 changes the pace; lower settings.stability gives a wider emotional range, higher gives a steadier read",
    "test the important lines with the chosen voice: tags land more readily when the voice was trained on that delivery",
)

# What each provider offers, for the question to the user. A provider object may set its own `blurb`.
PROVIDER_BLURBS = {
    "elevenlabs": "best quality and the richest emotions (audio tags, voice library); needs an ElevenLabs key; word timings come with the audio",
    "edge": "free, no key; neutral reading that cannot act out tags; word timings come with the audio",
    "gemini": "Google voices (30), follows bracketed tags; needs a Gemini key; no word timings, so captions need faster-whisper",
}


def provider_choice() -> dict:
    """Which providers the user could pick, and whether the model should ask.

    ElevenLabs is the recommendation whenever its key is set (it is also what runs when no provider is passed).
    With two or more usable providers the model asks the user once per project; with one it just uses it.
    """
    options = [
        {
            "provider": name,
            "available": provider.available(),
            "about": getattr(provider, "blurb", None) or PROVIDER_BLURBS.get(name, "custom provider"),
            **({} if provider.available() else {"to_enable": provider.unavailable_hint()}),
        }
        for name, provider in PROVIDERS.items()
    ]
    usable = [o["provider"] for o in options if o["available"]]
    default = default_provider()
    recommended = default if default in usable else (usable[0] if usable else None)
    options.sort(key=lambda o: (o["provider"] != recommended, not o["available"], o["provider"]))
    return {
        "recommended": recommended,
        "ask_user": len(usable) > 1,
        "options": options,
        "instruction": (
            "ask_user=true: before the first voiceover of this project, ask the user (in their language) which "
            "provider they want, one line per available option, and recommend the first one for quality. "
            "Keep the answer for the whole project and do not switch providers mid-project. If the user's "
            "saved preferences already name a provider, use it without asking. ask_user=false: use "
            "`recommended` and tell the user which voice you chose."
            if len(usable) > 1 else
            "Only one provider works: use it and tell the user which voice you chose"
            + ("." if usable else "; none works, tell the user what to enable (see to_enable).")
        ),
    }


def delivery_guide() -> dict:
    """How to write emotion and pacing for the configured ElevenLabs model (empty without a key)."""
    model = CONFIG.eleven_model
    guide: dict = {"model": model, "style": delivery_style(model)}
    if model.startswith(ELEVEN_TAG_MODEL_PREFIXES):
        guide["audio_tags"] = list(ELEVEN_VOICE_TAGS)
        guide["rules"] = list(ELEVEN_DELIVERY_RULES)
    else:
        guide["rules"] = ["SSML <break time=\"1.0s\" /> for pauses (up to 3 s, not many per request); "
                          "'...' and dashes are weaker alternatives"]
    return guide


def delivery_style(model: str) -> str:
    """How `model` wants pauses and emotion written: audio tags (v3/v4) or SSML breaks (v2 family)."""
    if model.startswith(ELEVEN_TAG_MODEL_PREFIXES):
        return "audio tags like [whispers], [excited], [sighs]; punctuation and '...' for pauses; no SSML"
    return "SSML <break time=\"1.0s\" /> for pauses; audio tags are not understood"


# ------------------------------------------------------------------ providers

class VoiceProvider(Protocol):
    """One text-to-speech backend. Register new ones with `register_provider`."""

    name: str
    raw_suffix: str  # file type `synthesize` writes: ".mp3", ".wav"

    def available(self) -> bool: ...

    def unavailable_hint(self) -> str: ...

    def max_chars(self, model: str | None) -> int: ...

    def default_voice(self, text: str, settings: dict) -> str: ...

    def default_model(self) -> str | None: ...

    def synthesize(self, text: str, voice: str | None, model: str | None,
                   settings: dict | None, out_audio: Path) -> list[dict] | None:
        """Write the speech for `text` to `out_audio`; return word timings `[{w, s, e}]` (seconds from the
        start of this audio) or None when the provider has none."""
        ...


class ElevenLabsProvider:
    name = "elevenlabs"
    raw_suffix = ".mp3"

    def available(self) -> bool:
        return bool(CONFIG.elevenlabs_api_key)

    def unavailable_hint(self) -> str:
        return "no ElevenLabs key: set ELEVENLABS_API_KEY in .env (https://elevenlabs.io -> API Keys)"

    def max_chars(self, model: str | None) -> int:
        return _eleven_char_limit(model or CONFIG.eleven_model)

    def default_voice(self, text: str, settings: dict) -> str:
        return "Brian"

    def default_model(self) -> str | None:
        return CONFIG.eleven_model

    def resolve_voice(self, voice: str | None, text: str, settings: dict) -> str:
        """Voice name or id -> voice_id: presets, then a raw id, then an exact name among the account's voices."""
        wanted = (voice or self.default_voice(text, settings)).strip()
        presets = {name.lower(): voice_id for name, voice_id in ELEVEN_VOICES.items()}
        if wanted.lower() in presets:
            return presets[wanted.lower()]
        if _ELEVEN_ID_RE.fullmatch(wanted):
            return wanted
        found = _eleven_json("GET", "/v2/voices", {"search": wanted, "page_size": 20},
                             timeout=VOICE_LIST_TIMEOUT_S)
        for entry in found.get("voices", []):
            if str(entry.get("name", "")).strip().lower() == wanted.lower():
                return str(entry["voice_id"])
        raise ValueError(
            f"unknown ElevenLabs voice {wanted!r}: pass a voice_id or a name from voice_options "
            f"(presets: {', '.join(ELEVEN_VOICES)})"
        )

    def synthesize(self, text: str, voice: str | None, model: str | None,
                   settings: dict | None, out_audio: Path) -> list[dict] | None:
        settings = dict(settings or {})
        voice_id = self.resolve_voice(voice, text, settings)
        body: dict = {"text": text, "model_id": model or CONFIG.eleven_model}
        voice_settings = {k: settings[k] for k in _ELEVEN_VOICE_SETTINGS if k in settings}
        if "speaker_boost" in settings and "use_speaker_boost" not in voice_settings:
            voice_settings["use_speaker_boost"] = settings["speaker_boost"]
        if voice_settings:
            body["voice_settings"] = voice_settings
        for key in ("language_code", "seed"):
            if settings.get(key) is not None:
                body[key] = settings[key]
        try:
            response = _eleven_json(
                "POST", f"/v1/text-to-speech/{voice_id}/with-timestamps",
                {"output_format": ELEVEN_OUTPUT_FORMAT}, body,
            )
        except RuntimeError as exc:
            message = str(exc)
            if any(f"HTTP {code}" in message for code in (401, 402, 403)) and voice_id not in ELEVEN_VOICES.values():
                message += (
                    " (a Voice Library voice needs a paid ElevenLabs plan through the API; "
                    "premade voices and the account's own voices work on every plan)"
                )
            raise RuntimeError(message) from exc
        audio = base64.b64decode(str(response.get("audio_base64") or ""))
        if not audio:
            raise RuntimeError("ElevenLabs returned no audio")
        out_audio.write_bytes(audio)
        alignment = response.get("alignment") or response.get("normalized_alignment")
        return words_from_alignment(alignment) if alignment else None


class EdgeProvider:
    name = "edge"
    raw_suffix = ".mp3"

    def available(self) -> bool:
        return _importable("edge_tts")

    def unavailable_hint(self) -> str:
        return "edge-tts is not installed: pip install edge-tts (or pip install 'argus-studio[voice]')"

    def max_chars(self, model: str | None) -> int:
        return EDGE_CHAR_LIMIT

    def default_model(self) -> str | None:
        return None

    def default_voice(self, text: str, settings: dict) -> str:
        language = str(settings.get("language") or detect_language(text)).lower()[:2]
        male = EDGE_VOICES.get(language, EDGE_VOICES["en"])[0]
        return male[0]

    def synthesize(self, text: str, voice: str | None, model: str | None,
                   settings: dict | None, out_audio: Path) -> list[dict] | None:
        import asyncio

        import edge_tts

        settings = dict(settings or {})
        spoken = strip_markup(text)  # edge-tts would read "[whispers]" aloud
        if not spoken:
            raise ValueError("nothing to speak after removing [audio tags] (edge voices cannot act them out)")
        voice_name = (voice or self.default_voice(text, settings)).strip()
        options = {k: str(settings[k]) for k in ("rate", "volume", "pitch") if settings.get(k) is not None}

        async def run() -> list[dict]:
            communicate = edge_tts.Communicate(spoken, voice_name, boundary=EDGE_BOUNDARY, **options)
            events: list[dict] = []
            audio = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk["data"])
                elif chunk.get("type") == "WordBoundary":
                    events.append(chunk)
            if not audio:
                raise RuntimeError(f"edge-tts returned no audio for voice {voice_name!r}")
            out_audio.write_bytes(bytes(audio))
            return events

        events = asyncio.run(run())
        return words_from_boundaries(events) or None


class GeminiProvider:
    name = "gemini"
    raw_suffix = ".wav"

    def available(self) -> bool:
        return bool(CONFIG.gemini_api_key)

    def unavailable_hint(self) -> str:
        return "no Gemini key: set ARGUS_GEMINI_API_KEY in .env (free key: https://aistudio.google.com/apikey)"

    def max_chars(self, model: str | None) -> int:
        return GEMINI_CHAR_LIMIT

    def default_voice(self, text: str, settings: dict) -> str:
        return CONFIG.default_voice

    def default_model(self) -> str | None:
        return CONFIG.tts_model

    def _pcm(self, text: str, voice: str, model: str) -> bytes:
        """Raw 24 kHz mono 16-bit PCM from Gemini TTS."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=CONFIG.gemini_api_key)
        response = client.models.generate_content(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )
        parts = response.candidates[0].content.parts
        pcm = next((p.inline_data.data for p in parts if p.inline_data), None)
        if not pcm:
            raise RuntimeError("Gemini TTS returned no audio data")
        return pcm

    def synthesize(self, text: str, voice: str | None, model: str | None,
                   settings: dict | None, out_audio: Path) -> list[dict] | None:
        pcm = self._pcm(text, (voice or self.default_voice(text, settings or {})).strip(),
                        model or CONFIG.tts_model)
        _pcm_to_wav(pcm, out_audio, GEMINI_PCM_RATE)
        return None  # Gemini TTS has no timestamps


def _pcm_to_wav(pcm: bytes, wav_path: Path, rate: int = GEMINI_PCM_RATE) -> None:
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


PROVIDERS: dict[str, VoiceProvider] = {}


def register_provider(provider: VoiceProvider) -> None:
    """Add (or replace) a voice provider, e.g. a local Voice Studio backend."""
    PROVIDERS[provider.name] = provider


for _provider in (ElevenLabsProvider(), GeminiProvider(), EdgeProvider()):
    register_provider(_provider)


def default_provider() -> str:
    """`ARGUS_TTS_PROVIDER` if set; else ElevenLabs when its key is configured; else edge."""
    chosen = os.environ.get("ARGUS_TTS_PROVIDER", "").strip().lower()
    if chosen:
        return chosen
    return "elevenlabs" if PROVIDERS["elevenlabs"].available() else "edge"


def resolve_provider(name: str | None) -> VoiceProvider:
    """The provider to use. An unavailable one is an error naming the fix, never a silent switch."""
    wanted = (name or default_provider()).strip().lower()
    if wanted not in PROVIDERS:
        raise ValueError(f"unknown voice provider {wanted!r}; available: {', '.join(sorted(PROVIDERS))}")
    provider = PROVIDERS[wanted]
    if not provider.available():
        raise RuntimeError(f"voice provider {wanted!r} is not available: {provider.unavailable_hint()}")
    return provider


def detect_language(text: str) -> str:
    """Two-letter guess from the script of `text`: ru / uk for Cyrillic, otherwise en."""
    letters = [c for c in text if c.isalpha()]
    if letters and sum("\u0400" <= c <= "\u04ff" for c in letters) > len(letters) / 2:
        return "uk" if any(c in "іїєґІЇЄҐ" for c in letters) else "ru"
    return "en"


# ------------------------------------------------------------------ synthesis pipeline

def _to_wav(raw: Path, wav: Path) -> float:
    """Decode a provider file to 48 kHz stereo wav; the returned duration is what the concatenation will use."""
    run_ffmpeg(["-i", str(raw), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
    return stream_info(wav).duration


def _concat_wavs(wavs: list[Path], out: Path) -> None:
    if len(wavs) == 1:
        shutil.copyfile(wavs[0], out)
        return
    listing = out.with_suffix(".txt")
    listing.write_text(
        "".join("file '{}'\n".format(str(w).replace("\\", "/").replace("'", "'\\''")) for w in wavs),
        encoding="utf-8",
    )
    try:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])
    finally:
        listing.unlink(missing_ok=True)


def _master(src: Path, out: Path) -> None:
    run_ffmpeg([
        "-i", str(src),
        "-af", mastering_chain(CONFIG.loudness_target),
        "-ar", "48000", "-ac", "2", "-codec:a", "libmp3lame", "-b:a", "320k",
        str(out),
    ])


def _align_with_whisper(audio: Path, duration: float, language: str | None) -> tuple[list[dict] | None, str | None]:
    """Word timings from faster-whisper: `(words, None)` or `(None, why_not)`."""
    if not watch.whisper_available():
        return None, ("this provider gives no word timings and faster-whisper is not installed, "
                      "so captions from this voice are unavailable (pip install faster-whisper)")
    try:
        result = watch.transcribe(audio, language, duration, _noop)
    except Exception as exc:  # whisper trouble must not lose the finished voiceover
        return None, f"faster-whisper alignment failed: {str(exc)[:200]}"
    return result["words"], None


def run_job(payload: dict, report: Callable[..., None]) -> dict:
    """Synthesize and master one voiceover (worker side of `synthesize_voiceover`, job kind `voiceover`)."""
    text = str(payload.get("text") or "")
    if not text.strip():
        raise ValueError("empty text")
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object like {\"stability\": 0.5}")
    provider = resolve_provider(payload.get("provider"))
    voice = (payload.get("voice") or "").strip() or None
    model = (payload.get("model") or "").strip() or provider.default_model()
    name = slugify(str(payload.get("name") or "voice"))

    root = project_dir(str(payload["project"]))
    out = root / "audio" / f"{name}.mp3"
    words_path = root / "audio" / f"{name}.words.json"
    chunks = split_text(text, provider.max_chars(model))
    voice_used = voice or provider.default_voice(text, settings)

    work = Path(tempfile.mkdtemp(prefix="voice-", dir=root / ".work"))
    try:
        wavs: list[Path] = []
        timings: list[list[dict] | None] = []
        offsets: list[float] = []
        elapsed = 0.0
        for index, chunk in enumerate(chunks):
            report(0.05 + 0.75 * index / len(chunks), f"speaking part {index + 1} of {len(chunks)}")
            raw = work / f"part{index}.raw{provider.raw_suffix}"
            timings.append(provider.synthesize(chunk, voice, model, settings, raw))
            wav = work / f"part{index}.wav"
            duration = _to_wav(raw, wav)
            wavs.append(wav)
            offsets.append(elapsed)
            elapsed += duration

        report(0.85, "mastering")
        joined = work / "joined.wav"
        _concat_wavs(wavs, joined)
        out.parent.mkdir(parents=True, exist_ok=True)
        _master(joined, out)
        duration = round(stream_info(out).duration, 3)

        words: list[dict] | None
        note: str | None = None
        if all(t is not None for t in timings):
            words = [
                {**w, "s": round(w["s"] + off, 3), "e": round(w["e"] + off, 3)}
                for t, off in zip(timings, offsets) for w in (t or [])
            ]
            source = "provider"
        else:
            report(0.92, "aligning words")
            words, note = _align_with_whisper(out, duration, str(settings.get("language") or "") or None)
            source = "faster-whisper" if words is not None else "none"
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if words is not None:
        words_path.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        words_path.unlink(missing_ok=True)  # an old file under this name would not match the new audio

    result: dict = {
        "audio": str(out),
        "words_path": str(words_path) if words is not None else None,
        "duration": duration,
        "provider": provider.name,
        "voice": voice_used,
        "model": model,
        "words_source": source,
        "words": len(words) if words is not None else 0,
        "parts": len(chunks),
    }
    if provider.name == "elevenlabs":
        result["delivery"] = delivery_style(model or "")
    if provider.name == "edge" and _TAG_RE.search(text):
        result["note"] = "edge voices cannot act out [audio tags] or SSML: they were removed from the spoken text"
    if note:
        result["captions_note"] = note
    return result


def synthesize_voiceover(
    text: str,
    project: str,
    provider: str | None = None,
    voice: str | None = None,
    model: str | None = None,
    name: str = "voice",
    settings: dict | None = None,
    wait_s: float = jobs.DEFAULT_WAIT_S,
) -> dict | list:
    """Tool logic of `synthesize_voiceover`: validate, then run the `voiceover` job.

    Quick results come back inline; after `wait_s` seconds the call returns a job_id instead.
    """
    if not text or not text.strip():
        raise ValueError("empty text")
    slugify(project)  # fail early, with a clear message, on a name that cannot become a folder
    slugify(name)
    if settings is not None and not isinstance(settings, dict):
        raise ValueError("settings must be an object like {\"stability\": 0.5}")
    resolve_provider(provider)  # fail early on an unknown or unavailable provider
    payload = {
        "text": text,
        "project": project,
        "provider": (provider or "").strip().lower() or None,
        "voice": voice,
        "model": model,
        "name": name,
        "settings": settings or {},
    }
    return jobs.run_or_detach("voiceover", payload, wait_s=wait_s)


# ------------------------------------------------------------------ voice_options

def _language_code(language: str | None) -> str | None:
    """`ru`, `ru-RU`, `Russian` -> `ru`."""
    if not language or not language.strip():
        return None
    value = language.strip().lower()
    return _LANGUAGE_NAMES.get(value) or value.replace("_", "-").split("-")[0]


def _gender(gender: str | None) -> str | None:
    if not gender or not gender.strip():
        return None
    value = gender.strip().lower()
    return {"m": "male", "man": "male", "f": "female", "woman": "female"}.get(value, value)


def _shorten(text: object, limit: int = VOICE_DESCRIPTION_CHARS) -> str | None:
    """One line of at most `limit` characters (the last one is `…` when the text was cut)."""
    if not text:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _query_words(query: str | None) -> list[str]:
    """The words of a search text: lower case, no punctuation, no repeats, at most MAX_QUERY_WORDS."""
    words: list[str] = []
    for word in re.findall(r"\w+", (query or "").lower()):
        if word not in words:
            words.append(word)
    return words[:MAX_QUERY_WORDS]


def _word_hits(words: list[str], *fields: object) -> int:
    """How many of `words` occur in the fields (case-insensitive, as part of a word too)."""
    haystack = " ".join(str(f) for f in fields if f).lower()
    return sum(1 for word in words if word in haystack)


def _compact(voice: dict) -> dict:
    """The voice without empty fields: the answer stays short."""
    return {k: v for k, v in voice.items() if v not in (None, "", [])}


def _own_voice(entry: dict) -> tuple[dict, str, set[str]]:
    """(compact voice, text the query searches, language codes) of an account voice."""
    labels = entry.get("labels") or {}
    languages = {str(v.get("language", "")).lower() for v in entry.get("verified_languages") or []}
    if labels.get("language"):
        languages.add(str(labels["language"]).lower())
    languages.discard("")
    voice = _compact({
        "id": entry.get("voice_id"),
        "name": entry.get("name"),
        "gender": labels.get("gender"),
        "age": labels.get("age"),
        "accent": labels.get("accent"),
        "language": ", ".join(sorted(languages)),
        "description": _shorten(entry.get("description")),
    })
    searchable = " ".join(str(x) for x in (
        entry.get("name"), entry.get("description"), entry.get("category"), *labels.values(), *languages) if x)
    return voice, searchable, languages


def _library_voice(entry: dict) -> tuple[dict, str]:
    """(compact voice, text the query searches) of a Voice Library entry."""
    voice = _compact({
        "id": entry.get("voice_id"),
        "name": entry.get("name"),
        "gender": str(entry["gender"]).lower() if entry.get("gender") else None,
        "age": entry.get("age"),
        "accent": entry.get("accent"),
        "language": entry.get("language"),
        "description": _shorten(entry.get("description")),
    })
    searchable = " ".join(str(entry.get(k)) for k in (
        "name", "description", "accent", "gender", "age", "use_case", "descriptive", "language", "category")
        if entry.get(k))
    return voice, searchable


def _library_search(
    words: list[str], code: str | None, sex: str | None, limit: int, errors: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """Voice Library voices for the query, as `(usable, paid_plan_only)`.

    The API search takes one text, so each query word is its own request; the answers are merged
    and the voices matching the most words come first. A failed request is recorded in `errors`.
    """
    found: dict[str, tuple[dict, bool, int]] = {}
    for position, word in enumerate(words or [None]):
        try:
            data = _eleven_json("GET", "/v1/shared-voices", {
                "page_size": limit, "language": code, "gender": sex, "search": word, "sort": "trending",
            }, timeout=VOICE_LIST_TIMEOUT_S)
        except Exception as exc:
            errors.setdefault("library_voices", str(exc)[:300])
            continue
        for entry in data.get("voices", []):
            voice, searchable = _library_voice(entry)
            if not voice.get("id") or voice["id"] in found:
                continue
            # only an explicit false means "not for free users"; a missing field is not held against a voice
            paid_only = entry.get("free_users_allowed") is False
            found[voice["id"]] = (voice, paid_only, _word_hits(words, searchable))
    ranked = sorted(found.values(), key=lambda item: -item[2])  # stable: the API's order breaks ties
    return ([v for v, paid, _ in ranked if not paid][:limit], [v for v, paid, _ in ranked if paid][:limit])


def _edge_voices(code: str | None, gender: str | None, words: list[str], limit: int) -> list[dict]:
    voices: list[dict] = []
    for language, (male, female) in EDGE_VOICES.items():
        if code and language != code:
            continue
        for (voice_id, label), sex in ((male, "male"), (female, "female")):
            if gender and gender != sex:
                continue
            locale = "-".join(voice_id.split("-")[:2])
            if words and not _word_hits(words, voice_id, label, locale, sex):
                continue
            voices.append({"id": voice_id, "name": label, "gender": sex, "language": locale})
    return voices[:limit]


def _json_size(value: object) -> int:
    """Characters of `value` as the client receives it (JSON, indent 2, no \\u escapes)."""
    return len(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _trim_voice_lists(result: dict, max_chars: int) -> int:
    """Drop voices from the longest list until `result` fits `max_chars`. Returns how many were dropped."""
    def lists() -> list[list]:
        found = [result.get(k) for k in ("own_voices", "library_voices", "edge_voices", "gemini_voices")]
        paid = result.get("library_voices_paid_plan_only")
        return [x for x in [*found, paid["voices"] if paid else None] if x]

    dropped = 0
    while _json_size(result) > max_chars:
        candidates = lists()
        if not candidates:
            break
        max(reversed(candidates), key=len).pop()  # on a tie the least important list loses a voice first
        dropped += 1
    paid = result.get("library_voices_paid_plan_only")
    if paid is not None and not paid["voices"]:
        del result["library_voices_paid_plan_only"]
    return dropped


def _provider_status() -> dict:
    eleven = PROVIDERS["elevenlabs"].available()
    gemini = PROVIDERS["gemini"].available()
    edge = PROVIDERS["edge"].available()
    whisper = watch.whisper_available()
    return {
        "elevenlabs": {
            "available": eleven,
            "model": CONFIG.eleven_model,
            "note": ("word timings from the API; voices: own + Voice Library (free_users_allowed=false voices need a paid plan via API)"
                     if eleven else PROVIDERS["elevenlabs"].unavailable_hint()),
        },
        "gemini": {
            "available": gemini,
            "model": CONFIG.tts_model,
            "note": ("opt-in with provider=\"gemini\"; no word timings, captions need faster-whisper"
                     if gemini else PROVIDERS["gemini"].unavailable_hint()),
        },
        "edge": {
            "available": edge,
            "note": "free, no key; word timings from the service; cannot act out audio tags"
                    if edge else PROVIDERS["edge"].unavailable_hint(),
        },
        "faster_whisper": {
            "available": whisper,
            "note": "aligns words for providers without timings" if whisper
                    else "not installed: pip install faster-whisper",
        },
    }


def _eleven_models(errors: dict[str, str]) -> list[dict]:
    """ElevenLabs text-to-speech models with their character limits and how each wants delivery written."""
    models: list[dict] = []
    try:
        for entry in _eleven_json("GET", "/v1/models", timeout=VOICE_LIST_TIMEOUT_S):
            if entry.get("can_do_text_to_speech") and not entry.get("requires_alpha_access"):
                mid = str(entry.get("model_id"))
                models.append({
                    "id": mid, "name": entry.get("name"),
                    "max_chars": entry.get("maximum_text_length_per_request") or ELEVEN_CHAR_LIMITS.get(mid),
                    "delivery": delivery_style(mid),
                })
    except Exception as exc:
        errors["models"] = str(exc)[:300]
    return models


def voice_options(
    language: str | None = None,
    gender: str | None = None,
    query: str | None = None,
    limit: int = 10,
    details: bool = False,
) -> dict:
    """Voices the user can use right now, filtered, plus which providers work.

    Each voice is `{id, name, gender, age, accent, language, description}` (empty fields left out,
    description at most 80 characters). `query` is split into words (at most 4); a voice matches
    when any word occurs, in any case, in its name, description, accent, age, gender, use case,
    language or labels. `own_voices`: the account's voices, matching language first, then the most
    matched words. `library_voices`: Voice Library voices usable on every plan.
    `library_voices_paid_plan_only`: library voices with `free_users_allowed=false`, with a note.
    `edge_voices`, `gemini_voices`: free defaults and Gemini names. Every list is capped at `limit`,
    and the whole answer at VOICE_RESPONSE_MAX_CHARS (the longest lists lose voices first).
    `details=True` adds `elevenlabs_models` and `delivery` (audio tags and pacing rules), which
    leaves room for fewer voices.
    """
    limit = max(1, min(int(limit), MAX_VOICE_LIST))
    code = _language_code(language)
    sex = _gender(gender)
    words = _query_words(query)
    errors: dict[str, str] = {}
    notes: list[str] = []

    own: list[dict] = []
    library: list[dict] = []
    library_paid: list[dict] = []
    models: list[dict] = []
    if PROVIDERS["elevenlabs"].available():
        try:
            data = _eleven_json("GET", "/v2/voices", {"page_size": 100, "include_total_count": "false"},
                                timeout=VOICE_LIST_TIMEOUT_S)
            ranked: list[tuple[bool, int, dict]] = []
            for entry in data.get("voices", []):
                voice, searchable, languages = _own_voice(entry)
                if sex and str(voice.get("gender") or "").lower() != sex:
                    continue
                hits = _word_hits(words, searchable)
                if words and not hits:
                    continue
                ranked.append((not (code and code in languages), -hits, voice))
            ranked.sort(key=lambda item: item[:2])  # matching language first, then the most matched words
            own = [voice for _, _, voice in ranked][:limit]
            if code and ranked and all(item[0] for item in ranked[:limit]):
                notes.append(f"no own voice is labelled {code!r}; v3/v4 voices usually speak other languages fine, try one")
        except Exception as exc:
            errors["own_voices"] = str(exc)[:300]
        library, library_paid = _library_search(words, code, sex, limit, errors)
        if details:
            models = _eleven_models(errors)
    else:
        notes.append(PROVIDERS["elevenlabs"].unavailable_hint() + "; edge voices need no key")

    if code and code not in EDGE_VOICES:
        notes.append(f"no edge default for {code!r}: any ShortName from `edge-tts --list-voices` works as `voice`")
    gemini = [v for v in AVAILABLE_VOICES if not words or _word_hits(words, v)][:limit]
    result: dict = {
        "engine": f"ARGUS {__version__}",
        "default_provider": default_provider(),
        "provider_choice": provider_choice(),
        "providers": _provider_status(),
        "own_voices": own,
        "library_voices": library,
        "edge_voices": _edge_voices(code, sex, words, limit),
        "gemini_voices": gemini,
    }
    if library_paid:
        result["library_voices_paid_plan_only"] = {"note": LIBRARY_PAID_NOTE, "voices": library_paid}
    if PROVIDERS["elevenlabs"].available():
        if details:
            result["delivery"] = delivery_guide()
            if models:
                result["elevenlabs_models"] = models
        else:
            notes.append("call again with details=True for the ElevenLabs models and the delivery rules (audio tags, pacing)")
    if errors:
        result["errors"] = errors
    result["notes"] = notes
    # the cut note is in the answer while it is measured, so the final size is the checked size
    cut_note = (f"some voices were left out to keep the answer under {VOICE_RESPONSE_MAX_CHARS} characters; "
                "narrow it with language, gender or query")
    notes.append(cut_note)
    if not _trim_voice_lists(result, VOICE_RESPONSE_MAX_CHARS):
        notes.remove(cut_note)
    if not notes:
        del result["notes"]
    return result

"""Plan v2: the JSON the model writes and `render_video` renders (design §8).

This module is the source of truth. `engine/src/types.ts` mirrors it; change both together.
Every model forbids unknown fields, so a typo comes back as `path: message`.

Units: times are seconds on the output timeline unless noted. Text sizes in the caption
style are fractions of the frame's short side (0.06 is about 65 px at 1080).
"""

from __future__ import annotations

import difflib
import re
import typing
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    field_validator,
    model_validator,
)

PLAN_VERSION = 2

FORMAT_SIZES: dict[str, tuple[int, int]] = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
FPS_CHOICES = (24, 25, 30, 50, 60)
DEFAULT_FPS = 30

# Fractions of the frame; 9:16 leaves room for the platform UI (design §8).
SAFE_AREA_DEFAULTS: dict[str, dict[str, float]] = {
    "9:16": {"top": 0.08, "bottom": 0.20, "left": 0.06, "right": 0.12},
    "16:9": {"top": 0.06, "bottom": 0.08, "left": 0.05, "right": 0.05},
}

TAIL_S = 0.6          # silence/hold after the last thing in the plan
SCENE_MIN_S = 2.0     # assumed length of a scene without `until` when deriving the duration
DEFAULT_GRAIN = 0.05  # grain for custom tokens that do not set one (the `dark` value)

# Values of `getTheme()` in engine/src/theme.ts. `word_base`, `word_active` and
# `card_border` are extra named colors the engine reads for spoken words and cards.
STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "dark": {
        "colors": {
            "bg": "#0A0A12", "text": "#F5F6FA", "muted": "#8A8FA3", "accent": "#7C5CFA",
            "word_base": "rgba(245, 246, 250, 0.72)", "word_active": "#FFFFFF",
            "card_border": "rgba(255, 255, 255, 0.08)",
        },
        "fonts": {"display": {"family": "Inter", "weight": 900}, "body": {"family": "Inter", "weight": 600}},
        "grain": 0.05,
        "vignette": True,
    },
    "light": {
        "colors": {
            "bg": "#F6F7FB", "text": "#0A0A12", "muted": "#6B7080", "accent": "#7C5CFA",
            "word_base": "rgba(10, 10, 18, 0.62)", "word_active": "#0A0A12",
            "card_border": "rgba(10, 10, 18, 0.10)",
        },
        "fonts": {"display": {"family": "Inter", "weight": 900}, "body": {"family": "Inter", "weight": 600}},
        "grain": 0.035,
        "vignette": True,
    },
}

REQUIRED_COLORS = ("bg", "text", "muted", "accent")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# --------------------------------------------------------------------------- style


class FontRef(_Model):
    family: str = Field(min_length=1)
    src: str | None = None  # font file inside the project; the family is registered from it
    weight: int | None = Field(None, ge=100, le=900)


class Fonts(_Model):
    display: FontRef
    body: FontRef
    mono: FontRef | None = None


class SafeArea(_Model):
    """Fractions of the frame that stay free of text on each side."""

    top: float = Field(ge=0, le=0.5)
    bottom: float = Field(ge=0, le=0.5)
    left: float = Field(ge=0, le=0.5)
    right: float = Field(ge=0, le=0.5)

    @model_validator(mode="after")
    def _room_left(self) -> SafeArea:
        if self.left + self.right >= 1 or self.top + self.bottom >= 1:
            raise ValueError("opposite margins must add up to less than 1")
        return self


class SolidBackground(_Model):
    type: Literal["solid"]


class GradientBackground(_Model):
    type: Literal["gradient"]
    stops: list[str] = Field(min_length=2)
    angle: float | None = None  # degrees, CSS convention


class MediaBackground(_Model):
    type: Literal["media"]
    src: str = Field(min_length=1)
    fit: Literal["cover", "contain"] = "cover"


Background = Annotated[
    Union[SolidBackground, GradientBackground, MediaBackground], Field(discriminator="type")
]


class StyleTokens(_Model):
    colors: dict[str, str]
    fonts: Fonts
    text_scale: float = Field(1.0, gt=0, le=4)
    safe_area: SafeArea | None = None  # None: default for the format (`SAFE_AREA_DEFAULTS`)
    background: Background | None = None  # None: solid `colors.bg`
    grain: float | None = Field(None, ge=0, le=1)  # None: `DEFAULT_GRAIN`
    vignette: bool = True

    @field_validator("colors")
    @classmethod
    def _colors(cls, v: dict[str, str]) -> dict[str, str]:
        missing = [k for k in REQUIRED_COLORS if k not in v]
        if missing:
            raise ValueError(f"missing required color(s): {', '.join(missing)}")
        empty = [k for k, c in v.items() if not c.strip()]
        if empty:
            raise ValueError(f"empty color value for: {', '.join(empty)}")
        return v


# --------------------------------------------------------------------------- clips


class ZoomKey(_Model):
    """Zoom/pan keyframe. `t` is seconds from the start of the clip on the timeline."""

    t: float = Field(ge=0)
    scale: float = Field(gt=0)
    x: float | None = None  # focus point, fraction of the frame width
    y: float | None = None  # focus point, fraction of the frame height
    ease: Literal["linear", "inOut"] = "inOut"


class Clip(_Model):
    src: str = Field(min_length=1)
    at: float = Field(ge=0)
    in_: float | None = Field(None, alias="in", ge=0)  # source seconds
    out: float | None = Field(None, ge=0)             # source seconds
    fit: Literal["cover", "contain"] = "cover"
    volume: float = Field(1.0, ge=0)
    muted: bool = False
    zoom: list[ZoomKey] = Field(default_factory=list)
    clean_audio: bool = False

    @model_validator(mode="after")
    def _range(self) -> Clip:
        if self.out is not None and self.out <= (self.in_ or 0.0):
            raise ValueError(f"out ({self.out}) must be greater than in ({self.in_ or 0.0})")
        return self

    @property
    def length(self) -> float | None:
        """Seconds the clip lasts on the timeline, or None when `out` is not set."""
        return None if self.out is None else self.out - (self.in_ or 0.0)


# --------------------------------------------------------------------------- scenes


class _SceneBase(_Model):
    at: float = Field(ge=0)
    until: float | None = Field(None, ge=0)  # default: the next full scene's `at`
    overlay: bool = False                    # transparent, drawn above clips

    @model_validator(mode="after")
    def _until_after_at(self) -> _SceneBase:
        if self.until is not None and self.until <= self.at:
            raise ValueError(f"until ({self.until}) must be greater than at ({self.at})")
        return self


class WordsScene(_SceneBase):
    kind: Literal["words"]
    text: str


class TitleScene(_SceneBase):
    kind: Literal["title"]
    kicker: str | None = None
    text: str


class CardScene(_SceneBase):
    kind: Literal["card"]
    media: str = Field(min_length=1)
    caption: str | None = None
    fit: Literal["cover", "contain"] | None = None


class BigScene(_SceneBase):
    kind: Literal["big"]
    text: str


class CounterScene(_SceneBase):
    kind: Literal["counter"]
    value: float
    suffix: str | None = None
    sub: str | None = None


class ActScene(_SceneBase):
    kind: Literal["act"]
    index: str | None = None
    title: str


class CtaScene(_SceneBase):
    kind: Literal["cta"]
    text: str
    handle: str | None = None


class ChipItem(_Model):
    text: str
    value: str | None = None


class ChipScene(_SceneBase):
    kind: Literal["chip"]
    text: str | None = None
    value: str | None = None
    items: list[ChipItem] | None = None

    @model_validator(mode="after")
    def _has_content(self) -> ChipScene:
        if not self.items and self.text is None:
            raise ValueError("chip needs `text` or a non-empty `items` list")
        return self


class CustomScene(_SceneBase):
    kind: Literal["custom"]
    component: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")  # file name in <project>/components
    props: dict[str, Any] = Field(default_factory=dict)


Scene = Annotated[
    Union[
        WordsScene, TitleScene, CardScene, BigScene, CounterScene,
        ActScene, CtaScene, ChipScene, CustomScene,
    ],
    Field(discriminator="kind"),
]
SCENE_KINDS = ("words", "title", "card", "big", "counter", "act", "cta", "chip", "custom")


# --------------------------------------------------------------------------- hud


class HudRow(_Model):
    label: str
    value: str


class HudAccentChange(_Model):
    at: float = Field(ge=0)
    row: int = Field(ge=0)  # index into `rows`
    value: str


class HudOverlay(_Model):
    at: float = Field(ge=0)
    until: float = Field(ge=0)
    rows: list[HudRow] = Field(min_length=1)
    pos: Literal["top", "bottom"] = "top"
    accent_changes: list[HudAccentChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> HudOverlay:
        if self.until <= self.at:
            raise ValueError(f"until ({self.until}) must be greater than at ({self.at})")
        bad = [
            f"accent_changes[{i}].row {c.row} is out of range (rows: 0..{len(self.rows) - 1})"
            for i, c in enumerate(self.accent_changes)
            if c.row >= len(self.rows)
        ]
        if bad:
            raise ValueError("; ".join(bad))
        return self


# --------------------------------------------------------------------------- captions


class WordTiming(_Model):
    w: str = Field(min_length=1)
    s: float = Field(ge=0)
    e: float = Field(ge=0)

    @model_validator(mode="after")
    def _order(self) -> WordTiming:
        if self.e < self.s:
            raise ValueError(f"e ({self.e}) is before s ({self.s})")
        return self


class WordsRemap(_Model):
    """Words of a footage transcript, moved from source time to output time for the kept clips.

    `source` is the words.json of the transcript (design §10). `media` is the footage file
    it was made from; the clips with that `src` are remapped. Default: the first clip's `src`.
    """

    source: str = Field(min_length=1)
    remap: Literal["clips"]
    media: str | None = None


def _words_tag(value: Any) -> str | None:
    if isinstance(value, str):
        return "path"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, (dict, WordsRemap)):
        return "remap"
    return None


CaptionWords = Annotated[
    Union[
        Annotated[str, Tag("path")],
        Annotated[list[WordTiming], Tag("list")],
        Annotated[WordsRemap, Tag("remap")],
    ],
    Discriminator(_words_tag),
]
WORDS_HINT = "a path to a words.json, a list of {w, s, e} words, or {source, remap: 'clips'}"


class CaptionStyle(_Model):
    font: Literal["display", "body"] | None = None
    size: float | None = Field(None, gt=0, le=0.5)  # fraction of the short side
    color: str | None = None
    active_color: str | None = None
    upcoming_color: str | None = None
    outline: float | None = Field(None, ge=0)  # fraction of the short side
    shadow: float | None = Field(None, ge=0)   # fraction of the short side
    plate: str | None = None                   # background color behind the text
    case: Literal["upper", "as_is"] = "as_is"  # "upper" draws every caption word in capitals


class Captions(_Model):
    words: CaptionWords
    # "headline": big kinetic words in the middle of the frame, slammed in as they are spoken,
    # `accent_words` boxed in the accent colour (engine/src/captions.tsx, HeadlineLineView)
    mode: Literal["word", "phrase", "headline"] = "phrase"
    position: Literal["upper", "center", "lower"] = "lower"
    style: CaptionStyle | None = None
    accent_words: list[str] = Field(default_factory=list)  # exact, "prefix*" or "*"

    @model_validator(mode="after")
    def _headline_sits_in_the_middle(self) -> Captions:
        # a headline belongs in the middle of the frame unless the plan places it somewhere else
        if self.mode == "headline" and "position" not in self.model_fields_set:
            self.position = "center"
        return self

    @field_validator("words")
    @classmethod
    def _not_empty(cls, v: Any) -> Any:
        if isinstance(v, list) and not v:
            raise ValueError("word list is empty")
        return v


# --------------------------------------------------------------------------- audio


class AudioRef(_Model):
    src: str = Field(min_length=1)
    volume: float = Field(1.0, ge=0)


class Music(_Model):
    src: str = Field(min_length=1)
    volume: float = Field(0.12, ge=0, le=1)
    duck: float = Field(1.0, ge=0, le=1)  # volume multiplier while words are spoken; 1 = no ducking
    fade_in: float = Field(0.0, ge=0)
    fade_out: float = Field(1.5, ge=0)


SOUND_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
ANCHOR_RE = re.compile(r"^(cue:[A-Za-z][A-Za-z0-9_]*|cut:\d+)$")
ANCHOR_HINT = "seconds, 'cue:<name>' (a cue in `cues`) or 'cut:<n>' (the start of scene n, counted from 0)"


class SoundLayer(_Model):
    """One source of a synthesized sound. Tonal sources need `freq_start`; filters need `cutoff_start`."""

    source: Literal["sine", "saw", "square", "triangle", "white", "pink", "brown"]
    freq_start: float | None = Field(None, ge=20, le=20000)  # Hz
    freq_end: float | None = Field(None, ge=20, le=20000)    # Hz; default: freq_start (no sweep)
    curve: Literal["linear", "exp"] = "linear"
    amp: float = Field(1.0, ge=0, le=1)
    attack: float = Field(0.005, ge=0, le=5)                 # seconds to full level
    decay: float = Field(0.0, ge=0, le=10)                   # exponential time constant, 0 = no decay
    release: float = Field(0.0, ge=0, le=5)                  # fade-out over the last seconds of the sound
    start: float = Field(0.0, ge=0, le=10)                   # delay inside the sound, seconds
    filter: Literal["lowpass", "highpass", "bandpass"] | None = None
    cutoff_start: float | None = Field(None, ge=20, le=20000)
    cutoff_end: float | None = Field(None, ge=20, le=20000)  # default: cutoff_start
    resonance: float = Field(0.7, ge=0.1, le=10)
    drive: float = Field(0.0, ge=0, le=10)                   # tanh saturation
    bits: int | None = Field(None, ge=1, le=16)              # bit reduction
    pan: float = Field(0.0, ge=-1, le=1)

    @model_validator(mode="after")
    def _needs(self) -> SoundLayer:
        if self.source not in ("white", "pink", "brown") and self.freq_start is None:
            raise ValueError(f"a {self.source} layer needs freq_start (its frequency in Hz)")
        if self.filter is not None and self.cutoff_start is None:
            raise ValueError(f"a {self.filter} filter needs cutoff_start (Hz)")
        return self


class SoundSpec(_Model):
    """A named sound. Either `from` a starting recipe with overrides, or a full sound (`length` and `layers`)."""

    from_: str | None = Field(None, alias="from")
    length: float | None = Field(None, gt=0.02, le=10)
    layers: list[SoundLayer] | None = Field(None, min_length=1, max_length=4)
    reverb: float | None = Field(None, ge=0, le=1)           # wet amount of a synthetic tail
    reverb_decay: float | None = Field(None, ge=0.1, le=5)   # seconds
    reverse: bool | None = None
    pitch_start: float | None = Field(None, ge=20, le=20000)  # Hz, every tonal layer
    pitch_end: float | None = Field(None, ge=20, le=20000)    # Hz, every tonal layer
    peak_db: float | None = Field(None, ge=-12, le=-1)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def _shape(self) -> SoundSpec:
        from .tools.synth import STARTING_NAMES

        if self.from_ is not None:
            if self.from_ not in STARTING_NAMES:
                raise ValueError(f"unknown starting recipe {self.from_!r} (expected {', '.join(STARTING_NAMES)})")
        elif self.length is None or self.layers is None:
            raise ValueError("a full sound needs `length` and `layers`; or start from one with `from`")
        return self


class SfxEvent(_Model):
    """One sound placed in the video.

    `at` is seconds, `cue:<name>` (a cue of the plan) or `cut:<n>` (the start of scene n).
    Exactly one of `src` (a file) and `sound` (a name from `audio.sounds`, or a starting recipe).
    `align` says which part of the sound sits on `at`: its start, its peak or its end.
    `vary` is how much each repeat differs (0 = exact copies); it defaults to 1 for a `sound` and
    to off for a plain file, so an old-form event (`at`, `src`, `volume`) renders as before.
    """

    at: float | str
    src: str | None = Field(None, min_length=1)
    sound: str | None = Field(None, min_length=1)
    volume: float = Field(1.0, ge=0)
    gain_db: float | None = Field(None, ge=-60, le=0)
    pitch: float = Field(0.0, ge=-24, le=24)     # semitones; the speed changes with it
    rate: float = Field(1.0, gt=0.25, le=4)      # speed factor
    pan: float = Field(0.0, ge=-1, le=1)
    reverse: bool = False
    trim: list[float] | None = Field(None, min_length=2, max_length=2)  # [in, out] seconds of the sound
    fade: float | None = Field(None, ge=0, le=5)  # seconds, both ends
    align: Literal["start", "peak", "end"] = "start"
    vary: float | None = Field(None, ge=0, le=1)

    @field_validator("at", mode="before")
    @classmethod
    def _at(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError(f"{v!r} is not a time; use {ANCHOR_HINT}")
        if isinstance(v, (int, float)):
            if v < 0:
                raise ValueError(f"{v} is before the start of the video")
            return float(v)
        if isinstance(v, str):
            if ANCHOR_RE.fullmatch(v.strip()):
                return v.strip()
            try:
                seconds = float(v)
            except ValueError:
                raise ValueError(f"{v!r} is not a time; use {ANCHOR_HINT}") from None
            return seconds
        raise ValueError(f"must be {ANCHOR_HINT}")

    @model_validator(mode="after")
    def _one_source(self) -> SfxEvent:
        if (self.src is None) == (self.sound is None):
            raise ValueError("give exactly one of `src` (a file) and `sound` (a named sound)")
        if "gain_db" in self.model_fields_set and "volume" in self.model_fields_set:
            raise ValueError("give `gain_db` or `volume`, not both")
        if self.trim is not None and not 0 <= self.trim[0] < self.trim[1]:
            raise ValueError(f"trim must be [in, out] with 0 <= in < out, got {self.trim}")
        return self

    @property
    def transforms(self) -> bool:
        """True when the event changes the file (anything but a plain placement of `src`)."""
        return bool(
            self.sound is not None or self.gain_db is not None or self.pitch or self.rate != 1.0
            or self.pan or self.reverse or self.trim is not None or self.fade or self.align != "start"
            or self.vary is not None
        )


class Audio(_Model):
    voice: AudioRef | None = None
    music: Music | None = None
    sounds: dict[str, SoundSpec] = Field(default_factory=dict)  # named sounds the sfx events may use
    sfx: list[SfxEvent] = Field(default_factory=list)

    @field_validator("sounds")
    @classmethod
    def _names(cls, v: dict[str, Any]) -> dict[str, Any]:
        bad = [n for n in v if not SOUND_NAME_RE.fullmatch(n)]
        if bad:
            raise ValueError(
                f"sound names are letters, digits and _, starting with a letter (at most 40): {', '.join(map(repr, bad))}"
            )
        return v


# --------------------------------------------------------------------------- cues


class WordCue(_Model):
    """A moment found in the voice: the start of the `nth` time `word` is spoken, plus `offset`.

    `word` is one word or several in a row ("пятнадцать миллионов"). Case and punctuation are
    ignored; a word ending in `*` matches any word that starts with the rest ("миллион*").
    The words come from `captions.words`. `render_video` resolves the cue to seconds, so a new
    voice moves the cue with it (design §9, Known issue 22).
    """

    word: str = Field(min_length=1)
    nth: int = Field(1, ge=1)
    offset: float = 0.0

    @field_validator("word")
    @classmethod
    def _has_a_word(cls, v: str) -> str:
        if not v.split():
            raise ValueError("word must hold at least one word")
        return v


def _cue_tag(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "seconds"
    if isinstance(value, (dict, WordCue)):
        return "word_cue"
    return None


Cue = Annotated[
    Union[
        Annotated[float, Tag("seconds")],
        Annotated[WordCue, Tag("word_cue")],
    ],
    Discriminator(_cue_tag),
]
CUE_HINT = "seconds on the output timeline, or {word, nth?, offset?} to follow a spoken word"
CUE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


# --------------------------------------------------------------------------- plan


class Plan(_Model):
    version: Literal[2] = 2
    format: Literal["9:16", "16:9"]
    fps: Literal[24, 25, 30, 50, 60] = DEFAULT_FPS
    duration: float | None = Field(None, gt=0, le=3600)  # derived when absent
    style: StyleTokens
    clips: list[Clip] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    hud: HudOverlay | None = None
    captions: Captions | None = None
    audio: Audio | None = None
    cues: dict[str, Cue] = Field(default_factory=dict)  # named moments for custom scenes (kit `useCue`)

    @field_validator("cues")
    @classmethod
    def _cue_names(cls, v: dict[str, Any]) -> dict[str, Any]:
        bad = [n for n in v if not CUE_NAME_RE.fullmatch(n)]
        if bad:
            raise ValueError(f"cue names are letters, digits and _, starting with a letter: {', '.join(map(repr, bad))}")
        for name, cue in v.items():
            if isinstance(cue, float) and cue < 0:
                raise ValueError(f"{name}: {cue} is before the start of the video")
        return v

    @field_validator("style", mode="before")
    @classmethod
    def _expand_preset(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v not in STYLE_PRESETS:
                raise ValueError(
                    f"unknown preset {v!r} (expected {', '.join(STYLE_PRESETS)} or a tokens object)"
                )
            return preset_tokens(v)
        return v

    @model_validator(mode="after")
    def _remap_needs_clips(self) -> Plan:
        if self.captions and isinstance(self.captions.words, WordsRemap) and not self.clips:
            raise ValueError("captions.words: remap 'clips' needs at least one clip")
        return self

    @model_validator(mode="after")
    def _word_cues_need_words(self) -> Plan:
        if self.captions is None:
            named = [n for n, c in self.cues.items() if isinstance(c, WordCue)]
            if named:
                raise ValueError(
                    f"cues.{named[0]}: a cue that follows a spoken word needs `captions` "
                    "(its `words` are the voice timings)"
                )
        return self

    @property
    def size(self) -> tuple[int, int]:
        return FORMAT_SIZES[self.format]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict for the engine and `plan.json` (aliases kept, nulls dropped)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def resolved(
        self,
        *,
        format: str | None = None,
        voice_duration: float | None = None,
        words_end: float | None = None,
        clip_lengths: Mapping[int, float] | None = None,
    ) -> Plan:
        """Copy with the format override applied and every default filled in.

        Fills `style.safe_area` for the format, `style.grain` and, when absent, `duration`
        (see `derive_duration`).
        """
        fmt = format or self.format
        if fmt not in FORMAT_SIZES:
            raise ValueError(f"unknown format {fmt!r} (expected {', '.join(FORMAT_SIZES)})")
        style = self.style.model_copy(update={
            "safe_area": self.style.safe_area or SafeArea(**SAFE_AREA_DEFAULTS[fmt]),
            "grain": DEFAULT_GRAIN if self.style.grain is None else self.style.grain,
        })
        out = self.model_copy(update={"format": fmt, "style": style})
        if out.duration is None:
            out = out.model_copy(update={"duration": derive_duration(
                out, voice_duration=voice_duration, words_end=words_end, clip_lengths=clip_lengths,
            )})
        return out


def preset_tokens(name: str) -> dict[str, Any]:
    """Fresh copy of a preset's tokens (`dark` or `light`)."""
    import copy

    return copy.deepcopy(STYLE_PRESETS[name])


def builtin_preset(style: StyleTokens) -> str | None:
    """The name of the built-in preset (`dark` or `light`) the style equals, else None.

    Compares the colors, fonts, grain and vignette that a preset sets. Changing any of them
    (the accent, a font, the grain) makes the style the plan's own.
    """
    tokens = style.model_dump(mode="json", exclude_none=True)
    for name in STYLE_PRESETS:
        if all(tokens.get(key) == value for key, value in preset_tokens(name).items()):
            return name
    return None


def derive_duration(
    plan: Plan,
    *,
    voice_duration: float | None = None,
    words_end: float | None = None,
    clip_lengths: Mapping[int, float] | None = None,
) -> float:
    """Length of the video when the plan has no `duration` (design §8).

    The largest of: last clip end, last scene end (`until`, else `at` + 2 s), HUD `until`,
    the voice length, the last word end; plus a 0.6 s tail. A clip without `out` counts only
    when its probed length is in `clip_lengths` (clip index -> seconds). `words_end` is the
    end of words loaded from a file; inline caption words are read from the plan.
    """
    ends: list[float] = []
    for i, clip in enumerate(plan.clips):
        length = clip.length if clip.length is not None else (clip_lengths or {}).get(i)
        if length is not None:
            ends.append(clip.at + length)
    for scene in plan.scenes:
        ends.append(scene.until if scene.until is not None else scene.at + SCENE_MIN_S)
    if plan.hud:
        ends.append(plan.hud.until)
    if voice_duration is not None:
        ends.append(voice_duration)
    if words_end is not None:
        ends.append(words_end)
    if plan.captions and isinstance(plan.captions.words, list):
        ends.extend(w.e for w in plan.captions.words)
    return round(max(ends, default=0.0) + TAIL_S, 3)


# --------------------------------------------------------------------------- validation


def validate_plan(data: Any) -> tuple[Plan | None, list[str]]:
    """Validate a plan dict. Returns `(plan, [])` or `(None, ["path: message", ...])`.

    The references inside `audio.sfx` (`sound`, `cue:`, `cut:`) are checked on the raw dict, so
    they are reported together with field errors instead of after them.
    """
    if not isinstance(data, Mapping):
        return None, [f"plan: must be a JSON object, got {type(data).__name__}"]
    references = _sfx_reference_errors(data)
    try:
        plan = Plan.model_validate(dict(data))
    except ValidationError as exc:
        return None, list(dict.fromkeys([*_format_errors(exc, data), *references]))
    return (None, references) if references else (plan, [])


def _sfx_reference_errors(data: Mapping[str, Any]) -> list[str]:
    """`audio.sfx` events that name an unknown sound, cue or scene (`path: message`)."""
    from .tools.synth import STARTING_NAMES

    audio = data.get("audio")
    events = audio.get("sfx") if isinstance(audio, Mapping) else None
    if not isinstance(events, list):
        return []
    sounds_map = audio.get("sounds") if isinstance(audio.get("sounds"), Mapping) else {}
    defined = sorted({*(str(k) for k in sounds_map), *STARTING_NAMES})
    cues = data.get("cues") if isinstance(data.get("cues"), Mapping) else {}
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    problems: list[str] = []
    for i, event in enumerate(events):
        if not isinstance(event, Mapping):
            continue
        sound = event.get("sound")
        if isinstance(sound, str) and sound not in defined:
            problems.append(
                f"audio.sfx[{i}].sound: unknown sound {sound!r} "
                f"(defined: {', '.join(defined)}; a sound of the plan goes in audio.sounds)"
            )
        at = event.get("at")
        if isinstance(at, str):
            kind, _, ref = at.strip().partition(":")
            if kind == "cue" and ref not in cues:
                names = ", ".join(sorted(str(k) for k in cues)) or "none"
                problems.append(f"audio.sfx[{i}].at: unknown cue {ref!r} (cues defined: {names})")
            if kind == "cut" and ref.isdigit() and int(ref) >= len(scenes):
                problems.append(
                    f"audio.sfx[{i}].at: scene {ref} does not exist "
                    f"(the plan has {len(scenes)} scenes, 0..{max(len(scenes) - 1, 0)})"
                )
    return problems


# Union members are named in pydantic's `loc`; these are the names to drop from the path.
_TAGS = frozenset(SCENE_KINDS) | {"solid", "gradient", "media", "path", "list", "remap", "seconds", "word_cue"}
_TAG_CHOICES = {"kind": SCENE_KINDS, "type": ("solid", "gradient", "media")}


def _path_str(path: list[str | int]) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else part)
    return out or "plan"


def _clean_loc(loc: tuple[str | int, ...]) -> list[str | int]:
    """`('scenes', 3, 'card', 'media')` -> `['scenes', 3, 'media']`."""
    path: list[str | int] = []
    skipped_at = -1
    for part in loc:
        slot = (
            (len(path) >= 2 and path[-2] == "scenes" and isinstance(path[-1], int))
            or path[-2:] == ["captions", "words"]
            or path[-2:] == ["style", "background"]
            or (len(path) >= 2 and path[-2] == "cues")
        )
        if isinstance(part, str) and part in _TAGS and slot and skipped_at != len(path):
            skipped_at = len(path)
            continue
        path.append(part)
    return path


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    """BaseModel classes reachable in a type annotation (through Union, list, Annotated...)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for arg in typing.get_args(annotation):
        found.extend(_models_in(arg))
    return found


def _pick_model(candidates: list[type[BaseModel]], data: Any) -> type[BaseModel] | None:
    if len(candidates) == 1:
        return candidates[0]
    if not isinstance(data, dict):
        return None
    for cls in candidates:
        for disc in ("kind", "type"):
            field = cls.model_fields.get(disc)
            if field is not None and data.get(disc) in typing.get_args(field.annotation):
                return cls
    return None


def _model_at(path: list[str | int], data: Any) -> type[BaseModel] | None:
    """The model that describes the object found at `path` inside the raw plan."""
    candidates: list[type[BaseModel]] = [Plan]
    cur = data
    for part in path:
        if isinstance(part, int):
            try:
                cur = cur[part]
            except (IndexError, TypeError, KeyError):
                return None
            continue
        model = _pick_model(candidates, cur)
        field = model.model_fields.get(part) if model else None
        if field is None:
            return None
        candidates = _models_in(field.annotation)
        cur = cur.get(part) if isinstance(cur, dict) else None
        if not candidates:
            return None
    return _pick_model(candidates, cur)


def _field_names(model: type[BaseModel]) -> list[str]:
    return [f.alias or name for name, f in model.model_fields.items()]


def _format_errors(exc: ValidationError, data: Mapping[str, Any]) -> list[str]:
    messages: list[str] = []
    for err in exc.errors(include_url=False):
        path = _clean_loc(err["loc"])
        kind = err["type"]
        ctx = err.get("ctx") or {}
        if kind == "extra_forbidden":
            key = str(path[-1]) if path else "?"
            model = _model_at(path[:-1], data)
            allowed = _field_names(model) if model else []
            hint = ""
            close = difflib.get_close_matches(key, allowed, n=1, cutoff=0.6)
            if close:
                hint = f"did you mean {close[0]!r}? "
            tail = f"{hint}allowed: {', '.join(allowed)}" if allowed else hint.rstrip()
            msg = f"unknown field {key!r}" + (f" ({tail})" if tail else "")
        elif kind in ("union_tag_invalid", "union_tag_not_found"):
            disc = str(ctx.get("discriminator", "")).strip("'\"")
            expected = ", ".join(t.strip(" '\"") for t in str(ctx.get("expected_tags", "")).split(",") if t.strip())
            expected = expected or ", ".join(_TAG_CHOICES.get(disc, ()))
            if re.fullmatch(r"\w+", disc):
                path = path + [disc]
                if kind == "union_tag_invalid":
                    msg = f"unknown {disc} {ctx.get('tag')!r} (expected {expected})"
                else:
                    msg = f"missing (expected {expected})"
            else:
                msg = f"must be {CUE_HINT if '_cue_tag' in disc else WORDS_HINT}"
        elif kind == "missing":
            msg = "required field is missing"
        elif kind == "value_error":
            msg = str(err["msg"]).removeprefix("Value error, ")
        else:
            msg = str(err["msg"])
        if not path and re.match(r"^[\w.\[\]]+: ", msg):
            messages.append(msg)  # a plan-level check that already names its path
        else:
            messages.append(f"{_path_str(path)}: {msg}")
    return list(dict.fromkeys(messages))

"""The built-in look: the `style_note` line on stills and preview answers, and the guide rules."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.plan import builtin_preset, preset_tokens, validate_plan  # noqa: E402
from argus.tools import render, studio  # noqa: E402

DARK_LINE = "style: engine defaults (dark, #7C5CFA, Inter)"
LIGHT_LINE = "style: built-in preset light (#7C5CFA accent, Inter)"


def _plan(style):
    plan, errors = validate_plan({
        "format": "9:16",
        "style": style,
        "scenes": [{"kind": "title", "text": "Hi", "at": 0}],
    })
    assert errors == [] and plan is not None, errors
    return plan.resolved()


def _own_style(**changes) -> dict:
    tokens = copy.deepcopy(preset_tokens("dark"))
    tokens.update(changes)
    return tokens


@pytest.mark.parametrize(("preset", "line"), [("dark", DARK_LINE), ("light", LIGHT_LINE)])
@pytest.mark.parametrize("mode", ["stills", "preview"])
def test_builtin_preset_gets_the_note_on_stills_and_preview(preset: str, line: str, mode: str) -> None:
    plan = _plan(preset)
    assert builtin_preset(plan.style) == preset
    note = render.style_note(mode, plan)
    assert note == render.STYLE_NOTES[preset]
    assert note.startswith(line)
    assert "\n" not in note  # one line


def test_dark_note_is_the_engine_default_line() -> None:
    assert render.STYLE_NOTE == (
        "style: engine defaults (dark, #7C5CFA, Inter). Set your own palette, fonts and layout "
        "from the reference or the user's request."
    )
    assert render.STYLE_NOTES["light"] == render.STYLE_NOTE_LIGHT


def test_preset_written_out_as_tokens_gets_the_note() -> None:
    assert render.style_note("stills", _plan(_own_style())) == render.STYLE_NOTES["dark"]
    light_tokens = copy.deepcopy(preset_tokens("light"))
    assert render.style_note("preview", _plan(light_tokens)) == render.STYLE_NOTES["light"]


def test_own_palette_has_no_note() -> None:
    plan = _plan(_own_style(colors={**preset_tokens("dark")["colors"], "accent": "#FF3B30"}))
    assert builtin_preset(plan.style) is None
    assert render.style_note("stills", plan) is None
    assert render.style_note("preview", plan) is None


def test_own_font_or_grain_has_no_note() -> None:
    font = copy.deepcopy(preset_tokens("dark")["fonts"])
    font["display"] = {"family": "Anton", "weight": 400}
    assert render.style_note("stills", _plan(_own_style(fonts=font))) is None
    assert render.style_note("stills", _plan(_own_style(grain=0.2))) is None


def test_light_preset_with_a_changed_accent_has_no_note() -> None:
    light = copy.deepcopy(preset_tokens("light"))
    light["colors"]["accent"] = "#FF3B30"
    assert render.style_note("stills", _plan(light)) is None


@pytest.mark.parametrize("mode", ["final", "audio"])
@pytest.mark.parametrize("preset", ["dark", "light"])
def test_final_and_audio_answers_have_no_note(mode: str, preset: str) -> None:
    assert render.style_note(mode, _plan(preset)) is None


def test_guide_tells_the_model_to_name_the_look_first() -> None:
    guide = studio.read_guide()
    assert "Name the look first" in guide
    assert "Never ship the engine default" in guide
    assert "parts, not a look" in guide
    assert "plain React" in guide and "SVG" in guide

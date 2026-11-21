"""The built-in look: the `style_note` line on stills and preview answers, and the guide rules."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.plan import is_builtin_style, preset_tokens, validate_plan  # noqa: E402
from argus.tools import render, studio  # noqa: E402

GUIDE_LINE = "style: engine defaults (dark, #7C5CFA, Inter)"


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


def test_default_style_by_name_gets_the_note_on_stills_and_preview() -> None:
    plan = _plan("dark")
    assert is_builtin_style(plan.style)
    for mode in ("stills", "preview"):
        note = render.style_note(mode, plan)
        assert note == render.STYLE_NOTE
    assert GUIDE_LINE in render.STYLE_NOTE
    assert render.STYLE_NOTE.count("\n") == 0  # one line


def test_default_tokens_written_out_get_the_note() -> None:
    plan = _plan(_own_style())
    assert render.style_note("stills", plan) == render.STYLE_NOTE


def test_own_palette_has_no_note() -> None:
    plan = _plan(_own_style(colors={**preset_tokens("dark")["colors"], "accent": "#FF3B30"}))
    assert not is_builtin_style(plan.style)
    assert render.style_note("stills", plan) is None
    assert render.style_note("preview", plan) is None


def test_own_font_or_grain_has_no_note() -> None:
    font = copy.deepcopy(preset_tokens("dark")["fonts"])
    font["display"] = {"family": "Anton", "weight": 400}
    assert render.style_note("stills", _plan(_own_style(fonts=font))) is None
    assert render.style_note("stills", _plan(_own_style(grain=0.2))) is None


def test_light_preset_has_no_note() -> None:
    plan = _plan("light")
    assert not is_builtin_style(plan.style)
    assert render.style_note("stills", plan) is None


@pytest.mark.parametrize("mode", ["final", "audio"])
def test_final_and_audio_answers_have_no_note(mode: str) -> None:
    assert render.style_note(mode, _plan("dark")) is None


def test_guide_tells_the_model_to_name_the_look_first() -> None:
    guide = studio.read_guide()
    assert "Name the look first" in guide
    assert "Never ship the engine default" in guide
    assert "parts, not a look" in guide
    assert "plain React" in guide and "SVG" in guide

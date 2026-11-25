import json
from pathlib import Path

import pytest

from omniframe.plan import (
    FORMAT_SIZES,
    SAFE_AREA_DEFAULTS,
    STYLE_PRESETS,
    TAIL_S,
    derive_duration,
    validate_plan,
)

PLANS_DIR = Path(__file__).resolve().parent.parent / "examples" / "plans"
SAMPLES = sorted(PLANS_DIR.glob("*.json"))


def _base(**extra):
    return {"format": "9:16", "style": "dark", **extra}


def test_all_four_samples_exist():
    assert {p.name for p in SAMPLES} >= {
        "graphics_9x16.json", "graphics_16x9.json", "footage_16x9.json", "reference_style_9x16.json",
    }


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_sample_validates(path):
    plan, errors = validate_plan(json.loads(path.read_text(encoding="utf-8")))
    assert errors == []
    assert plan is not None
    assert plan.format in FORMAT_SIZES


def test_preset_expands_to_tokens():
    plan, errors = validate_plan(_base())
    assert errors == []
    assert plan.style.colors["bg"] == STYLE_PRESETS["dark"]["colors"]["bg"] == "#0A0A12"
    assert plan.style.grain == 0.05
    light, _ = validate_plan({"format": "16:9", "style": "light"})
    assert light.style.colors["bg"] == "#F6F7FB"
    assert light.style.grain == 0.035


def test_unknown_preset_is_reported():
    _, errors = validate_plan(_base(style="neon"))
    assert errors == ["style: unknown preset 'neon' (expected dark, light or a tokens object)"]


def test_typo_field_reports_path_and_suggestion():
    data = _base(scenes=[
        {"kind": "words", "at": 0, "text": "a"},
        {"kind": "title", "at": 1, "text": "b", "kikcer": "x"},
    ])
    plan, errors = validate_plan(data)
    assert plan is None
    assert len(errors) == 1
    assert errors[0].startswith("scenes[1].kikcer: unknown field 'kikcer'")
    assert "did you mean 'kicker'?" in errors[0]


def test_typo_in_clip_and_top_level():
    data = _base(clips=[{"src": "a.mp4", "at": 0, "inn": 1}], captons={})
    _, errors = validate_plan(data)
    assert any(e.startswith("clips[0].inn: unknown field 'inn'") and "'in'" in e for e in errors)
    assert any(e.startswith("captons: unknown field 'captons'") and "'captions'" in e for e in errors)


def test_unknown_scene_kind_and_missing_kind():
    data = _base(scenes=[{"kind": "stamp", "at": 1}, {"at": 2}])
    _, errors = validate_plan(data)
    assert errors[0].startswith("scenes[0].kind: unknown kind 'stamp' (expected words, title,")
    assert errors[1].startswith("scenes[1].kind: missing (expected words, title,")


def test_missing_required_field_has_clean_path():
    _, errors = validate_plan(_base(scenes=[{"kind": "card", "at": 1}]))
    assert errors == ["scenes[0].media: required field is missing"]


def test_every_problem_is_returned_at_once():
    data = {"format": "4:3", "fps": 31, "style": "dark", "scenes": [{"kind": "big", "at": -1, "text": "x"}]}
    _, errors = validate_plan(data)
    paths = [e.split(":")[0] for e in errors]
    assert paths == ["format", "fps", "scenes[0].at"]


def test_cross_field_checks():
    data = _base(
        clips=[{"src": "a.mp4", "at": 0, "in": 5, "out": 3}],
        scenes=[{"kind": "big", "at": 4, "until": 2, "text": "x"}, {"kind": "chip", "at": 1}],
        hud={"at": 0, "until": 3, "rows": [{"label": "a", "value": "1"}],
             "accent_changes": [{"at": 1, "row": 2, "value": "x"}]},
    )
    _, errors = validate_plan(data)
    assert any(e.startswith("clips[0]: out (3.0) must be greater than in (5.0)") for e in errors)
    assert any(e.startswith("scenes[0]: until (2.0) must be greater than at (4.0)") for e in errors)
    assert any(e.startswith("scenes[1]: chip needs") for e in errors)
    assert any(e.startswith("hud: accent_changes[0].row 2 is out of range") for e in errors)


def test_style_tokens_need_core_colors_and_gradient_stops():
    style = {
        "colors": {"bg": "#000"},
        "fonts": {"display": {"family": "X"}, "body": {"family": "X"}},
        "background": {"type": "gradient", "stops": ["#000"]},
    }
    _, errors = validate_plan(_base(style=style))
    assert "style.colors: missing required color(s): text, muted, accent" in errors
    assert any(e.startswith("style.background.stops:") for e in errors)


def test_caption_words_forms():
    ok_path, e1 = validate_plan(_base(captions={"words": "audio/voice.words.json"}))
    ok_list, e2 = validate_plan(_base(captions={"words": [{"w": "hi", "s": 0, "e": 0.4}]}))
    assert e1 == [] and e2 == []
    assert ok_path.captions.mode == "phrase" and ok_list.captions.position == "lower"
    _, e3 = validate_plan(_base(captions={"words": 5}))
    assert e3[0].startswith("captions.words: must be a path")
    _, e4 = validate_plan(_base(captions={"words": [{"w": "hi", "s": 1, "e": 0.5}]}))
    assert e4[0].startswith("captions.words[0]: e (0.5) is before s (1.0)")


def test_headline_caption_mode_sits_in_the_middle_unless_the_plan_places_it():
    words = [{"w": "hi", "s": 0, "e": 0.4}]
    plan, errors = validate_plan(_base(captions={"words": words, "mode": "headline"}))
    assert errors == [] and plan.captions.mode == "headline" and plan.captions.position == "center"
    assert plan.to_dict()["captions"]["position"] == "center"
    placed, errors = validate_plan(_base(captions={"words": words, "mode": "headline", "position": "upper"}))
    assert errors == [] and placed.captions.position == "upper"
    phrase, _ = validate_plan(_base(captions={"words": words, "mode": "phrase"}))
    assert phrase.captions.position == "lower"  # the other modes keep their low default
    _, errors = validate_plan(_base(captions={"words": words, "mode": "huge"}))
    assert any(e.startswith("captions.mode:") for e in errors), errors


def test_caption_case_is_upper_or_as_is():
    words = [{"w": "hi", "s": 0, "e": 0.4}]
    plain, e1 = validate_plan(_base(captions={"words": words}))
    upper, e2 = validate_plan(_base(captions={"words": words, "style": {"case": "upper"}}))
    as_is, e3 = validate_plan(_base(captions={"words": words, "style": {"case": "as_is"}}))
    assert e1 == [] and e2 == [] and e3 == []
    assert plain.captions.style is None  # no style given: the default applies in the engine
    assert upper.captions.style.case == "upper" and as_is.captions.style.case == "as_is"
    _, errors = validate_plan(_base(captions={"words": words, "style": {"case": "lower"}}))
    assert any(e.startswith("captions.style.case:") for e in errors), errors


def test_remap_requires_clips():
    words = {"source": "w.json", "remap": "clips"}
    _, errors = validate_plan(_base(captions={"words": words}))
    assert errors == ["captions.words: remap 'clips' needs at least one clip"]
    plan, errors = validate_plan(_base(captions={"words": words}, clips=[{"src": "a.mp4", "at": 0}]))
    assert errors == []


def test_non_object_plan():
    assert validate_plan([1, 2]) == (None, ["plan: must be a JSON object, got list"])


def test_resolved_fills_safe_area_and_format_override():
    plan, _ = validate_plan(_base(scenes=[{"kind": "big", "at": 0, "text": "x"}]))
    vertical = plan.resolved()
    assert vertical.style.safe_area.model_dump() == SAFE_AREA_DEFAULTS["9:16"]
    wide = plan.resolved(format="16:9")
    assert wide.format == "16:9" and wide.size == (1920, 1080)
    assert wide.style.safe_area.model_dump() == SAFE_AREA_DEFAULTS["16:9"]
    assert plan.style.safe_area is None  # the original is untouched
    with pytest.raises(ValueError):
        plan.resolved(format="1:1")


def test_user_safe_area_is_kept():
    style = {**STYLE_PRESETS["dark"], "safe_area": {"top": 0.1, "bottom": 0.1, "left": 0.1, "right": 0.1}}
    plan, errors = validate_plan({"format": "9:16", "style": style})
    assert errors == []
    assert plan.resolved(format="16:9").style.safe_area.top == 0.1


def test_duration_derivation():
    data = _base(
        clips=[{"src": "a.mp4", "at": 1, "in": 2, "out": 6}, {"src": "b.mp4", "at": 5}],
        scenes=[{"kind": "big", "at": 3, "text": "x"}, {"kind": "big", "at": 6, "until": 7.5, "text": "y"}],
        hud={"at": 0, "until": 9, "rows": [{"label": "a", "value": "1"}]},
    )
    plan, errors = validate_plan(data)
    assert errors == []
    # clip 0 ends at 5; clip 1 has no `out`; scenes end at 5 and 7.5; hud ends at 9
    assert derive_duration(plan) == pytest.approx(9 + TAIL_S)
    assert derive_duration(plan, voice_duration=12.0) == pytest.approx(12 + TAIL_S)
    assert derive_duration(plan, words_end=10.5) == pytest.approx(10.5 + TAIL_S)
    assert derive_duration(plan, clip_lengths={1: 7.0}) == pytest.approx(12 + TAIL_S)


def test_duration_uses_inline_words_and_scene_default():
    plan, _ = validate_plan(_base(
        scenes=[{"kind": "big", "at": 1, "text": "x"}],
        captions={"words": [{"w": "a", "s": 0, "e": 5.0}]},
    ))
    assert derive_duration(plan) == pytest.approx(5.0 + TAIL_S)
    only_scene, _ = validate_plan(_base(scenes=[{"kind": "big", "at": 1, "text": "x"}]))
    assert derive_duration(only_scene) == pytest.approx(3.0 + TAIL_S)


def test_resolved_keeps_explicit_duration_and_derives_missing():
    plan, _ = validate_plan(_base(scenes=[{"kind": "big", "at": 0, "text": "x"}], duration=8))
    assert plan.resolved().duration == 8
    plan2, _ = validate_plan(_base(scenes=[{"kind": "big", "at": 0, "text": "x"}]))
    assert plan2.resolved().duration == pytest.approx(2 + TAIL_S)


def test_to_dict_is_json_with_aliases():
    plan, _ = validate_plan(_base(clips=[{"src": "a.mp4", "at": 0, "in": 1, "out": 2}]))
    out = plan.to_dict()
    assert out["clips"][0]["in"] == 1 and "in_" not in out["clips"][0]
    assert "hud" not in out
    json.dumps(out)


def _gain_plan(**sfx_fields):
    event = {"at": 0.5, "sound": "pop", **sfx_fields}
    return _base(
        scenes=[{"kind": "big", "at": 0, "text": "x"}],
        audio={"sfx": [event]},
    )


def test_a_saved_plan_with_only_gain_db_loads_again():
    """`volume` has a default; a saved plan must not write it back next to `gain_db`."""
    plan, errors = validate_plan(_gain_plan(gain_db=-6))
    assert errors == []
    saved = plan.to_dict()
    assert saved["audio"]["sfx"][0]["gain_db"] == -6.0
    assert "volume" not in saved["audio"]["sfx"][0]
    again, errors = validate_plan(saved)
    assert errors == []
    assert again.audio.sfx[0].gain_db == -6.0


def test_gain_db_and_volume_given_together_are_refused():
    _, errors = validate_plan(_gain_plan(gain_db=-6, volume=0.5))
    assert any("not both" in e for e in errors)

import json

import pytest

from argus.captions import (
    clean_word_timings,
    group_phrases,
    load_words,
    parse_words,
    remap_words_to_clips,
)
from argus.plan import validate_plan


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


WORDS = [
    _w("alpha", 0.0, 0.5),
    _w("um", 0.6, 0.9),        # a stumble the editor cuts out
    _w("beta", 1.0, 1.5),
    _w("gamma", 4.0, 4.5),
    _w("delta", 5.0, 5.5),
    _w("epsilon", 9.0, 9.5),
]


def test_remap_keeps_words_inside_kept_ranges_and_shifts_them():
    clips = [
        {"src": "talk.mp4", "at": 0.0, "in": 0.0, "out": 0.55},   # alpha
        {"src": "talk.mp4", "at": 0.55, "in": 0.95, "out": 1.6},  # beta (um is cut)
        {"src": "talk.mp4", "at": 1.2, "in": 4.0, "out": 5.6},    # gamma, delta
    ]
    out = remap_words_to_clips(WORDS, clips, "talk.mp4")
    assert [w["word"] for w in out] == ["alpha", "beta", "gamma", "delta"]
    by = {w["word"]: w for w in out}
    assert by["alpha"]["start"] == pytest.approx(0.0)
    assert by["beta"]["start"] == pytest.approx(0.6)   # 1.0 - 0.95 + 0.55
    assert by["beta"]["end"] == pytest.approx(1.1)
    assert by["gamma"]["start"] == pytest.approx(1.2)  # 4.0 - 4.0 + 1.2
    assert by["delta"]["start"] == pytest.approx(2.2)
    assert "epsilon" not in by and "um" not in by


def test_remap_does_not_modify_input_and_sorts_output():
    clips = [
        {"src": "a.mp4", "at": 5.0, "in": 0.0, "out": 0.55},
        {"src": "a.mp4", "at": 0.0, "in": 4.0, "out": 5.6},
    ]
    before = [dict(w) for w in WORDS]
    out = remap_words_to_clips(WORDS, clips, "a.mp4")
    assert WORDS == before
    assert [w["word"] for w in out] == ["gamma", "delta", "alpha"]
    assert out[-1]["start"] == pytest.approx(5.0)


def test_remap_ignores_other_sources_and_handles_open_ended_clip():
    clips = [
        {"src": "broll.mp4", "at": 0.0, "in": 0.0, "out": 10.0},
        {"src": "talk.mp4", "at": 2.0, "in": 4.0},  # no `out`: to the end
    ]
    out = remap_words_to_clips(WORDS, clips, "talk.mp4")
    assert [w["word"] for w in out] == ["gamma", "delta", "epsilon"]
    assert out[0]["start"] == pytest.approx(2.0)


def test_remap_clamps_word_that_straddles_a_cut():
    words = [_w("long", 1.0, 2.0)]
    out = remap_words_to_clips(words, [{"src": "a", "at": 10.0, "in": 0.0, "out": 1.8}], "a")
    assert out == [_w("long", 11.0, 11.8)]
    # less than half inside: dropped
    assert remap_words_to_clips(words, [{"src": "a", "at": 0.0, "in": 0.0, "out": 1.2}], "a") == []


def test_remap_accepts_plan_clips():
    plan, errors = validate_plan({
        "format": "16:9", "style": "dark",
        "clips": [{"src": "talk.mp4", "at": 3.0, "in": 1.0, "out": 1.6}],
    })
    assert errors == []
    out = remap_words_to_clips(WORDS, plan.clips, "talk.mp4")
    assert [(w["word"], round(w["start"], 3)) for w in out] == [("beta", 3.0)]


def test_parse_words_accepts_both_shapes(tmp_path):
    assert parse_words([{"w": "a", "s": 0, "e": 1}, {"w": " ", "s": 1, "e": 2}]) == [_w("a", 0.0, 1.0)]
    path = tmp_path / "words.json"
    path.write_text(json.dumps({"words": [_w("b", 1, 2)]}), encoding="utf-8")
    assert load_words(path) == [_w("b", 1.0, 2.0)]
    with pytest.raises(ValueError):
        parse_words([])


def test_clean_and_group():
    glitch = [_w("a", 1.0, 1.6), _w("b", 1.0, 1.6), _w("c", 1.0, 1.6), _w("d", 3.0, 3.4)]
    cleaned, fixed = clean_word_timings(glitch)
    assert fixed >= 3
    starts = [w["start"] for w in cleaned]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    lines = group_phrases([_w("one", 0, 0.3), _w("two.", 0.3, 0.6), _w("three", 0.6, 0.9)])
    assert [[w["word"] for w in ln] for ln in lines] == [["one", "two."], ["three"]]


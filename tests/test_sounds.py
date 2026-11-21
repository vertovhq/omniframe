"""Sound design (task 20.5b): synthesized recipes, event placement, variation, the audio render, the sound library.

All offline: no engine, no network. Synthetic events and plans only.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import project  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.plan import validate_plan  # noqa: E402
from argus.tools import render, sounds, studio, synth  # noqa: E402

TOLERANCE_S = 1.0 / 30.0


@pytest.fixture(autouse=True)
def sound_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (project, render, studio):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield cfg


@pytest.fixture
def root() -> Path:
    return project.project_dir("sound-t")


def _scene_plan(duration: float = 3.0, **extra) -> dict:
    return {
        "version": 2, "format": "9:16", "duration": duration, "style": "dark",
        "scenes": [
            {"kind": "big", "at": 0, "text": "ONE"},
            {"kind": "big", "at": 1.5, "text": "TWO"},
        ],
        **extra,
    }


def _wav(path: Path, seconds: float = 1.0, hz: float = 440.0) -> Path:
    """A plain 48 kHz mono sine file, made with ffmpeg as the other tests do."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"sine=frequency={hz}:duration={seconds}", "-ar", "48000", str(path)],
        check=True, capture_output=True,
    )
    return path


# ------------------------------------------------------------------ recipes

@pytest.mark.parametrize("name", synth.STARTING_NAMES)
def test_every_starting_recipe_is_audible_and_within_the_peak_ceiling(name: str) -> None:
    recipe = synth.resolve_recipe({"from": name})
    samples = synth.render_recipe(recipe)
    assert samples.shape == (round(recipe["length"] * synth.SR), 2)
    measures = synth.measure(samples)
    assert measures["rms_db"] > -60, f"{name} is silent"
    assert measures["peak_db"] <= -1.0, f"{name} peaks at {measures['peak_db']} dBFS"


def test_same_recipe_and_seed_give_identical_samples_another_seed_differs() -> None:
    recipe = synth.resolve_recipe({"from": "riser"})
    a = synth.render_recipe(recipe, seed=5, jitter=1.0)
    b = synth.render_recipe(recipe, seed=5, jitter=1.0)
    c = synth.render_recipe(recipe, seed=6, jitter=1.0)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_override_replaces_length_and_sets_the_pitch_of_tonal_layers() -> None:
    recipe = synth.resolve_recipe({"from": "hit", "pitch_end": 300, "length": 0.6})
    assert recipe["length"] == 0.6
    tonal = [layer for layer in recipe["layers"] if layer["freq_start"] is not None]
    assert tonal and all(layer["freq_end"] == 300 for layer in tonal)
    noise = [layer for layer in recipe["layers"] if layer["source"] in synth.NOISE_SOURCES]
    assert noise and all(layer["freq_start"] is None for layer in noise)


def test_a_full_sound_without_length_or_layers_is_a_plan_error() -> None:
    _, errors = validate_plan({**_scene_plan(), "audio": {"sounds": {"x": {"length": 0.5}}}})
    assert any(e.startswith("audio.sounds.x:") and "length" in e and "layers" in e for e in errors), errors


def test_unknown_starting_recipe_names_the_known_ones() -> None:
    _, errors = validate_plan({**_scene_plan(), "audio": {"sounds": {"x": {"from": "nothing"}}}})
    assert any("unknown starting recipe 'nothing'" in e and "whoosh" in e for e in errors), errors


def test_a_tonal_layer_without_frequency_is_a_plan_error() -> None:
    bad = {"layers": [{"source": "sine"}], "length": 0.2}
    _, errors = validate_plan({**_scene_plan(), "audio": {"sounds": {"x": bad}}})
    assert any("freq_start" in e for e in errors), errors


# ------------------------------------------------------------------ placement

def test_cue_and_cut_references_resolve_and_unknown_ones_list_the_names() -> None:
    plan = {**_scene_plan(cues={"slam1": 2.0}), "audio": {"sfx": [
        {"at": "cut:1", "sound": "whoosh"},
        {"at": "cue:slam1", "sound": "hit"},
    ]}}
    parsed, errors = validate_plan(plan)
    assert errors == [] and parsed is not None
    bad = {**_scene_plan(cues={"slam1": 2.0}), "audio": {"sfx": [
        {"at": "cue:slam2", "sound": "whooshh"},
        {"at": "cut:9", "sound": "hit"},
    ]}}
    _, errors = validate_plan(bad)
    assert any("unknown cue 'slam2'" in e and "slam1" in e for e in errors), errors
    assert any("unknown sound 'whooshh'" in e and "whoosh" in e for e in errors), errors
    assert any("scene 9 does not exist" in e for e in errors), errors


def test_an_old_form_event_is_placed_as_before(root: Path) -> None:
    src = _wav(root / "audio" / "beep.wav")
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [{"at": 1.0, "src": "audio/beep.wav", "volume": 0.5}]}})[0]
    placed, warnings = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: root / v)
    assert warnings == []
    assert len(placed) == 1
    assert placed[0].src == src and placed[0].at == 1.0 and placed[0].volume == 0.5
    assert not (root / "cache" / "sfx").exists()  # a plain file is not rewritten


def test_align_peak_puts_the_peak_on_the_cue_within_one_frame(root: Path) -> None:
    plan = validate_plan({**_scene_plan(cues={"slam": 2.0}), "audio": {"sfx": [
        {"at": "cue:slam", "sound": "hit", "align": "peak"},
    ]}})[0]
    placed, _ = sounds.resolve_events(plan, {"slam": 2.0}, root / "cache" / "sfx", lambda v: None)
    event = placed[0]
    assert abs(event.at + event.measures["peak_at"] - 2.0) <= TOLERANCE_S


def test_align_end_puts_the_end_of_the_sound_on_the_moment(root: Path) -> None:
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [
        {"at": 2.0, "sound": "riser", "align": "end"},
    ]}})[0]
    placed, warnings = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: None)
    assert abs(placed[0].at + placed[0].measures["length"] - 2.0) <= TOLERANCE_S
    assert warnings == []


def test_a_sound_that_would_start_before_the_video_is_moved_to_zero_with_a_warning(root: Path) -> None:
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [{"at": 0.1, "sound": "riser", "align": "end"}]}})[0]
    placed, warnings = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: None)
    assert placed[0].at == 0.0
    assert any("before the video" in w for w in warnings), warnings


def test_vary_makes_repeats_differ_and_vary_zero_makes_them_equal(root: Path) -> None:
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [
        {"at": 0.2, "sound": "tick"}, {"at": 0.6, "sound": "tick"},
        {"at": 1.0, "sound": "tick", "vary": 0}, {"at": 1.4, "sound": "tick", "vary": 0},
    ]}})[0]
    placed, _ = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: None)
    varied_a, varied_b, exact_a, exact_b = placed
    assert varied_a.src != varied_b.src
    assert not np.array_equal(varied_a.mono, varied_b.mono)
    assert exact_a.src == exact_b.src
    assert np.array_equal(exact_a.mono, exact_b.mono)


def test_a_file_event_with_pitch_and_reverse_is_rendered_and_cached(root: Path) -> None:
    _wav(root / "audio" / "beep.wav")
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [
        {"at": 0.5, "src": "audio/beep.wav", "pitch": 4, "reverse": True, "fade": 0.01},
    ]}})[0]
    placed, _ = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: root / v)
    assert placed[0].src.parent == root / "cache" / "sfx"
    assert placed[0].measures["length"] < 1.0  # a higher pitch plays faster, so it is shorter


def test_a_built_in_sound_name_in_src_needs_no_project_file(root: Path) -> None:
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [{"at": 0.5, "src": "audio/whoosh.mp3"}]}})[0]
    placed, _ = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: render._resolve_file(v, [root]))
    assert placed[0].src.is_file() and placed[0].src.name == "whoosh.mp3"


def test_gain_db_becomes_the_engine_volume(root: Path) -> None:
    plan = validate_plan({**_scene_plan(), "audio": {"sfx": [{"at": 0.5, "sound": "pop", "gain_db": -6}]}})[0]
    placed, _ = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: None)
    assert placed[0].volume == pytest.approx(10 ** (-6 / 20))


# ------------------------------------------------------------------ mix checks

def _placed(index: int, at: float, amp: float, length: float = 0.2, peak_at: float = 0.0) -> sounds.Placed:
    mono = np.full(int(length * synth.SR), amp)
    return sounds.Placed(
        index=index, name=f"s{index}", src=Path("x.wav"), volume=1.0, anchor=at, at=at,
        measures={"length": length, "peak_db": 0.0, "rms_db": 0.0, "peak_at": peak_at, "attack_ms": 0.0, "centroid_hz": 1000.0},
        mono=mono,
    )


def test_checks_report_clipping_stacked_peaks_and_a_sound_past_the_end() -> None:
    mixed = np.full(synth.SR, 1.2)  # over 0 dBFS
    notes = sounds.checks(
        1.0,
        [_placed(0, 0.10, 0.5), _placed(1, 0.10, 0.5), _placed(2, 0.9, 0.1, length=0.5)],
        mixed, None, None,
    )
    assert any(n.startswith("the mix clips") for n in notes), notes
    assert any("peak within 30 ms" in n and "events 1 and 2" in n for n in notes), notes
    assert any("event 3" in n and "cut off by the video end" in n for n in notes), notes


def test_checks_report_a_sound_louder_than_the_voice_over_words() -> None:
    voice = np.full(synth.SR, 0.01)
    notes = sounds.checks(
        1.0, [_placed(0, 0.2, 0.5, length=0.3)], np.zeros(synth.SR), voice,
        [{"w": "hi", "s": 0.0, "e": 1.0}],
    )
    assert any("louder than the voice" in n for n in notes), notes


def test_a_quiet_event_with_no_words_under_it_is_not_flagged() -> None:
    notes = sounds.checks(1.0, [_placed(0, 0.2, 0.5, length=0.3)], np.zeros(synth.SR), np.full(synth.SR, 0.5), [])
    assert not any("louder" in n for n in notes), notes


# ------------------------------------------------------------------ audio render and library

def _audio_payload(root: Path, plan: dict, **extra) -> dict:
    prepared, errors = render.prepare_render(
        plan, root, mode="audio", times=None, compare=None, format=None, name="mix", **extra,
    )
    assert prepared is not None, errors
    return prepared


def _run(payload: dict) -> dict:
    return render.run_job(payload, lambda *a, **k: None)


def test_audio_mode_needs_no_engine_and_returns_the_timeline_and_checks(root: Path) -> None:
    plan = _scene_plan(
        audio={"sounds": {"hook": {"from": "whoosh", "length": 0.5}}, "sfx": [
            {"at": "cut:1", "sound": "hook", "align": "peak"},
            {"at": 2.9, "sound": "riser"},  # runs past the video end
        ]},
    )
    result = _run(_audio_payload(root, plan))
    assert result["mode"] == "audio"
    timeline = Path(result["images"][0]["path"])
    assert timeline.is_file() and PILImage.open(timeline).size[0] == render.TIMELINE_MAX_SIDE
    assert Path(result["output"]).is_file()
    assert result["events"] == 2
    assert [row["sound"] for row in result["sounds"]] == ["hook", "riser"]
    assert {"length_s", "attack_ms", "peak_dbfs", "rms_dbfs", "centroid_hz", "brightness"} <= set(result["sounds"][0])
    assert any("event 2" in w and "cut off" in w for w in result["warnings"]), result["warnings"]


def test_save_sounds_writes_a_recipe_and_the_library_lists_it(root: Path) -> None:
    plan = _scene_plan(audio={"sounds": {"hook": {"from": "whoosh", "pitch_end": 300, "length": 0.6}}, "sfx": [
        {"at": 0.5, "sound": "hook"},
    ]})
    save = [{"sound": "hook", "what": "a short airy whoosh", "fits_when": "a cut into a new idea"}]
    payload = _audio_payload(root, plan, save_sounds=save)
    result = _run(payload)
    saved = result["saved_sounds"]
    assert saved[0]["name"] == "hook"
    library = render.project_library_dir(root)
    data = json.loads((library / "sfx" / "hook.json").read_text(encoding="utf-8"))
    assert data["sound"] == {"from": "whoosh", "pitch_end": 300, "length": 0.6}
    assert data["what"] == "a short airy whoosh" and data["source"] == "sound-t"
    lines = sounds.library_lines(library)
    assert len(lines) == 1 and "hook" in lines[0] and "cut" in lines[0]


def test_save_sounds_refuses_an_existing_name_and_an_unknown_sound(root: Path) -> None:
    plan = _scene_plan(audio={"sounds": {"hook": {"from": "whoosh"}}, "sfx": [{"at": 0.5, "sound": "hook"}]})
    _run(_audio_payload(root, plan, save_sounds=[{"sound": "hook", "what": "a", "fits_when": "b"}]))
    payload, errors = render.prepare_render(
        plan, root, mode="audio", times=None, compare=None, format=None, name="mix",
        save_sounds=[{"sound": "hook", "what": "a", "fits_when": "b"}],
    )
    assert payload is None and any("already has 'hook'" in e for e in errors), errors
    payload, errors = render.prepare_render(
        plan, root, mode="audio", times=None, compare=None, format=None, name="mix",
        save_sounds=[{"sound": "ghost", "what": "a", "fits_when": "b"}],
    )
    assert payload is None and any("unknown sound 'ghost'" in e and "whoosh" in e for e in errors), errors


def test_save_sounds_only_works_in_audio_mode(root: Path) -> None:
    payload, errors = render.prepare_render(
        _scene_plan(), root, mode="stills", times=[0.5], compare=None, format=None, name="v",
        save_sounds=[{"sound": "whoosh", "what": "a", "fits_when": "b"}],
    )
    assert payload is None and any(e.startswith("save_sounds:") for e in errors), errors


def test_the_engine_gets_the_rendered_events_as_public_files(root: Path) -> None:
    plan = validate_plan({**_scene_plan(), "audio": {"sounds": {"hook": {"from": "whoosh"}}, "sfx": [
        {"at": 0.5, "sound": "hook"},
    ]}})[0]
    placed, _ = sounds.resolve_events(plan, {}, root / "cache" / "sfx", lambda v: None)
    engine = render.engine_plan_with_sounds(plan.to_dict(), placed)
    assert "sounds" not in engine["audio"]
    assert engine["audio"]["sfx"] == [{"at": round(placed[0].at, 4), "src": str(placed[0].src), "volume": 1.0}]
    public = render._PublicDir(root / ".work" / "public", [root])
    props = render._engine_props(engine, None, public, with_audio=True)
    rel = props["audio"]["sfx"][0]["src"]
    assert rel.startswith("m/") and (public.root / rel).is_file()


def test_audio_mode_mixes_the_voice_and_music_tracks(root: Path) -> None:
    _wav(root / "audio" / "voice.wav", seconds=2.0, hz=220.0)
    _wav(root / "audio" / "music.wav", seconds=3.0, hz=110.0)
    plan = _scene_plan(
        duration=3.0,
        audio={"voice": {"src": "audio/voice.wav", "volume": 1.0},
               "music": {"src": "audio/music.wav", "volume": 0.2},
               "sfx": [{"at": 1.0, "sound": "pop"}]},
    )
    payload = _audio_payload(root, plan)
    result = _run(payload)
    assert result["duration"] == 3.0 and result["events"] == 1
    assert result["mix_peak_dbfs"] > -60
    assert Path(result["output"]).is_file()
    assert Path(result["images"][0]["path"]).is_file()


def test_starting_sheet_is_one_image_with_every_recipe(tmp_path: Path) -> None:
    path = sounds.starting_sheet(tmp_path / "sheet.jpg")
    width, height = PILImage.open(path).size
    assert width == sounds.SHEET_CELL_W * 2 + sounds.SHEET_GAP
    rows = (len(synth.STARTING_NAMES) + 1) // 2
    assert height >= rows * sounds.SHEET_CELL_H


def test_studio_sfx_group_returns_the_recipe_lines_and_the_sheet() -> None:
    result = studio.kit_group_result("sfx")
    assert result["kit_group"] == "sfx"
    assert len(result["recipes"]) == len(synth.STARTING_NAMES)
    assert result["recipes"][0].startswith("- whoosh:")
    assert Path(result["strip"]["path"]).is_file()

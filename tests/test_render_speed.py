"""Render speed and checks (task 20.7a): contact sheet, one-colour and accent-word warnings,
scene labels, render timing totals, and the stills job wired to a fake node step.

None of these tests needs the engine: the node step is replaced by a fake that writes pictures.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image as PILImage

from omniframe import jobs, project
from omniframe.config import CONFIG
from omniframe.plan import validate_plan
from omniframe.tools import render


@pytest.fixture(autouse=True)
def out_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Own output dir per test: projects and jobs never leak between tests."""
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (jobs, project, render):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield


def _solid(path: Path, colour: tuple[int, int, int], size: tuple[int, int] = (90, 160)) -> Path:
    PILImage.new("RGB", size, colour).save(path, "JPEG", quality=92)
    return path


def _gradient(path: Path, size: tuple[int, int] = (90, 160)) -> Path:
    PILImage.linear_gradient("L").resize(size).convert("RGB").save(path, "JPEG", quality=92)
    return path


def _plan_dict(**extra) -> dict:
    return {"version": 2, "format": "9:16", "duration": 3, "style": "dark",
            "scenes": [{"kind": "big", "at": 0, "text": "OmniFrame"}], **extra}


# ------------------------------------------------------------------ contact sheet

@pytest.mark.parametrize("ratio", [9 / 16, 16 / 9, 1.125])
def test_sheet_grid_fits_every_cell_within_the_longest_side(ratio: float) -> None:
    for n in range(2, render.MAX_STILLS + 1):
        cols, rows, cw, ch = render.sheet_grid(n, ratio)
        assert cols * rows >= n
        assert cw > 0 and ch > 0
        assert max(cols * cw, rows * (ch + render.SHEET_LABEL_H)) <= render.SHEET_MAX_SIDE


def test_contact_sheet_is_one_image_with_each_frame_in_its_cell(tmp_path: Path) -> None:
    colours = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (220, 220, 40), (90, 90, 90)]
    cells = [
        (_solid(tmp_path / f"frame{i}.jpg", colour), f"t {i}.00 s | scenes[{i}]")
        for i, colour in enumerate(colours)
    ]
    out = render.build_contact_sheet(cells, tmp_path / "sheet.jpg")
    cols, rows, cw, ch = render.sheet_grid(len(cells), 9 / 16)
    with PILImage.open(out) as raw:
        sheet = raw.convert("RGB")
    assert sheet.size == (cols * cw, rows * (ch + render.SHEET_LABEL_H))
    for i, colour in enumerate(colours):
        x = (i % cols) * cw + cw // 2
        y = (i // cols) * (ch + render.SHEET_LABEL_H) + ch // 2
        got = sheet.getpixel((x, y))
        assert all(abs(g - c) <= 12 for g, c in zip(got, colour)), (i, got)
    # the label under the first cell is drawn (more than the background colour is present)
    label_band = sheet.crop((0, ch, cw, ch + render.SHEET_LABEL_H))
    assert len(label_band.getcolors(maxcolors=100_000)) > 5


def test_one_colour_still_is_an_empty_frame(tmp_path: Path) -> None:
    flat = _solid(tmp_path / "flat.jpg", (12, 14, 20), size=(64, 112))
    assert render.one_colour(flat) is not None
    assert render.one_colour(_gradient(tmp_path / "grad.jpg", size=(64, 112))) is None


# ------------------------------------------------------------------ warnings and labels

def test_accent_words_that_are_never_spoken_are_reported() -> None:
    plan, errors = validate_plan(_plan_dict(captions={
        "words": [{"w": "Hello,", "s": 0.0, "e": 0.5}, {"w": "prefix", "s": 0.6, "e": 1.0}],
        "accent_words": ["hello", "missing", "pre*", "*", "nope*"],
    }))
    assert plan is not None, errors
    words = [{"w": "Hello,", "s": 0.0, "e": 0.5}, {"w": "prefix", "s": 0.6, "e": 1.0}]
    notes = [n for n in render._plan_warnings(plan, words) if n.startswith("captions.accent_words")]
    assert len(notes) == 2, notes
    assert "'missing'" in notes[0] and "'nope*'" in notes[1]


def test_accent_words_are_not_checked_without_words() -> None:
    plan, errors = validate_plan(_plan_dict(captions={
        "words": [{"w": "x", "s": 0.0, "e": 0.5}], "accent_words": ["anything"],
    }))
    assert plan is not None, errors
    assert not [n for n in render._plan_warnings(plan, None) if "accent" in n]


def test_scene_label_names_the_full_scene_and_the_overlay_on_screen() -> None:
    plan, errors = validate_plan(_plan_dict(
        duration=5,
        scenes=[
            {"kind": "big", "at": 0, "text": "A"},
            {"kind": "big", "at": 2, "text": "B"},
            {"kind": "big", "at": 3, "until": 4, "overlay": True, "text": "C"},
        ],
    ))
    assert plan is not None, errors
    assert render.scene_label(plan, 1.0) == "scenes[0]"
    assert render.scene_label(plan, 2.5) == "scenes[1]"
    assert render.scene_label(plan, 3.5) == "scenes[1] + scenes[2] overlay"
    assert render.scene_label(plan, 4.5) == "scenes[1]"


def test_bundle_key_changes_only_with_the_engine_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = tmp_path / "engine"
    (engine / "src" / "custom").mkdir(parents=True)
    (engine / "src" / "index.ts").write_text("export {};", encoding="utf-8")
    (engine / "src" / "custom" / "registry.ts").write_text("export const C = {};", encoding="utf-8")
    (engine / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(render, "engine_dir", lambda: engine)
    public = tmp_path / "public"
    (public / "m").mkdir(parents=True)
    (public / "m" / "a.mp3").write_bytes(b"123")

    base = render.bundle_key(public)
    assert render.bundle_key(public) == base
    (engine / "src" / "custom" / "registry.ts").write_text("export const C = {x: 1};", encoding="utf-8")
    changed_code = render.bundle_key(public)
    assert changed_code != base
    (public / "m" / "a.mp3").write_bytes(b"12345")
    assert render.bundle_key(public) not in (base, changed_code)


def test_reused_bundle_gets_back_the_public_files_it_lost(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached bundle without `public/fonts` is repaired from the job's public dir, not served broken."""
    root = tmp_path / "proj"
    public = tmp_path / "work" / "public"
    font = public / "fonts" / "InterDisplay-Black.otf"
    font.parent.mkdir(parents=True)
    font.write_bytes(b"OTTO-font-bytes")
    (public / "m").mkdir()
    (public / "m" / "clip.mp4").write_bytes(b"clip")
    key = "ab" * 32
    calls: list[dict] = []
    notes: list[str] = []

    def fake_node(spec, work, report, lo, hi, hold):
        calls.append(dict(spec))
        if "bundleDir" in spec:  # the first job builds the bundle the way the node script does
            bundle = Path(spec["bundleDir"])
            bundle.mkdir(parents=True)
            (bundle / "index.html").write_text("<html></html>", encoding="utf-8")
            shutil.copytree(spec["publicDir"], bundle / "public")
        return {"timing": {}}

    monkeypatch.setattr(render, "_run_node", fake_node)
    report = lambda progress, note=None, *a, **k: notes.append(str(note))  # noqa: E731

    render._run_node_bundled({"publicDir": str(public)}, tmp_path, report, 0.0, 1.0, None, root, key)
    cached = root / "cache" / render.BUNDLE_DIR / key[:16]
    assert (cached / "public" / "fonts" / "InterDisplay-Black.otf").is_file()

    # the bundle loses its fonts folder, then a second render with the same key reuses it
    shutil.rmtree(cached / "public" / "fonts")
    render._run_node_bundled({"publicDir": str(public)}, tmp_path, report, 0.0, 1.0, None, root, key)

    assert "serveUrl" in calls[1] and "bundleDir" not in calls[1]  # reused, not rebuilt
    restored = cached / "public" / "fonts" / "InterDisplay-Black.otf"
    assert restored.read_bytes() == b"OTTO-font-bytes"
    assert (cached / "public" / "m" / "clip.mp4").is_file()
    assert any("restored missing public files" in n and "fonts/InterDisplay-Black.otf" in n for n in notes), notes


# ------------------------------------------------------------------ job wiring (fake node step)

def test_stills_job_flags_empty_frames_and_returns_one_sheet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project.project_dir("t")

    def fake_node(spec, work, report, lo, hi, hold, project_root, key):
        if hold is not None:
            hold.release()  # the real node step does this when the bundle is built
        for i, out in enumerate(spec["outputs"]):
            if i == 0:
                _solid(Path(out), (0, 0, 0))
            else:
                _gradient(Path(out))
        return {"timing": {"bundle_s": 0.0, "bundle_reused": True, "browser_s": 0.1, "stills_s": 0.2}}

    monkeypatch.setattr(render, "_run_node_bundled", fake_node)
    payload, errors = render.prepare_render(
        _plan_dict(), root, mode="stills", times=[0.5, 1.5], compare=None, format=None, name="video",
    )
    assert payload is not None, errors
    result = render.run_job(payload, lambda *a, **k: None)

    assert any("stills[0]" in w and "one colour" in w for w in result["warnings"]), result["warnings"]
    assert not any("stills[1]" in w for w in result["warnings"])
    assert len(result["images"]) == 1
    sheet = result["images"][0]
    assert sheet["path"].endswith("video-stills-9x16-sheet.jpg") and Path(sheet["path"]).is_file()
    assert [c["t"] for c in sheet["cells"]] == [0.5, 1.5]
    assert all(c["scene"] == "scenes[0]" for c in sheet["cells"])
    assert result["image_max_side"] == render.SHEET_MAX_SIDE
    assert result["timing"]["bundle_reused"] is True
    assert result["timing"]["total_s"] >= result["timing"]["prepare_s"] >= 0


def test_single_still_is_returned_as_one_full_size_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project.project_dir("t")

    def fake_node(spec, work, report, lo, hi, hold, project_root, key):
        if hold is not None:
            hold.release()
        _gradient(Path(spec["outputs"][0]))
        return {"timing": {}}

    monkeypatch.setattr(render, "_run_node_bundled", fake_node)
    payload, errors = render.prepare_render(
        _plan_dict(), root, mode="stills", times=[0.5], compare=None, format=None, name="video",
    )
    assert payload is not None, errors
    result = render.run_job(payload, lambda *a, **k: None)
    assert len(result["images"]) == 1
    assert result["images"][0]["path"].endswith("video-stills-9x16-01-t0.50s.jpg")
    assert "sheet" not in result["images"][0]["path"]


# ------------------------------------------------------------------ timing totals

def test_status_write_waits_out_a_short_windows_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scanner holding status.json must not turn a finished render into an error."""
    target = tmp_path / "status.json"
    target.write_text("{}", encoding="utf-8")
    real_replace = os.replace
    calls = {"n": 0}

    def locked_then_free(src, dst):
        calls["n"] += 1
        if calls["n"] <= 5:
            raise PermissionError(13, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(jobs.os, "replace", locked_then_free)
    jobs._write_json(target, {"state": "done"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "done"}
    assert calls["n"] == 6


def test_project_render_totals_sum_the_finished_renders_of_one_project(tmp_path: Path) -> None:
    root = tmp_path / "proj"

    def make(job_id: str, kind: str, project_root: Path, state: str, timing: dict) -> None:
        job_dir = jobs.jobs_root() / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "job.json").write_text(json.dumps({
            "id": job_id, "kind": kind, "payload": {"project_root": str(project_root)}, "key": None, "created": 0,
        }), encoding="utf-8")
        (job_dir / "status.json").write_text(json.dumps({"state": state, "result": {"timing": timing}}), encoding="utf-8")

    make("job1", "render", root, "done", {"prepare_s": 2.0, "total_s": 10.0, "bundle_reused": True})
    make("job2", "render", root, "done", {"prepare_s": 1.0, "total_s": 5.5})
    make("job3", "render", root, "error", {"total_s": 99.0})
    make("job4", "render", tmp_path / "other", "done", {"total_s": 99.0})
    make("job5", "export", root, "done", {"total_s": 99.0})

    assert jobs.project_render_totals(root) == {"jobs": 2, "prepare_s": 3.0, "total_s": 15.5}
    assert jobs.project_render_totals(tmp_path / "none") == {"jobs": 0}

"""Task 20.10 items 21, 23 and 24: the guide core is short and has the budget rules, every section is
reachable by number or by a word of its title, an unknown name lists the valid ones, and a project's
resume comes from `<project>/.work/state.json` in at most 5 lines.

Offline. Uses a temporary output folder.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import state  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.tools import studio  # noqa: E402

CORE_LIMIT = 4000  # characters of the guide core returned by studio_guide()


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    monkeypatch.setattr(state, "CONFIG", cfg)
    monkeypatch.setattr(studio, "CONFIG", cfg)
    studio._SENT.clear()


# ------------------------------------------------------------------ item 21: core and sections

def test_core_is_under_the_limit_and_keeps_the_rules() -> None:
    core = studio.core_text(studio.read_guide())
    assert len(core) <= CORE_LIMIT, len(core)
    assert "Do not re-read files you wrote." in core  # item 23
    assert "Never ship the engine default style." in core  # item 8 look rule, kept in the core
    assert "With \"no checks\", go straight to the preview." in core


def test_core_holds_the_reuse_rule_and_the_kit_line() -> None:  # task 20.11
    core = studio.core_text(studio.read_guide())
    assert (
        "If the library has an element that fits, import it and change only props, text and timing. "
        "Write a new one only when the user asks for something different, the reference shows a different look, "
        "or no entry fits."
    ) in core
    assert "Transitions, bursts, shake, flashes and HUD: set them by kit name in the plan instead of writing your own code." in core


def test_core_lists_every_other_section() -> None:
    text = studio.read_guide()
    core = studio.core_text(text)
    for num in studio.guide_sections(text):
        if num != "0":
            assert f'studio_guide(section="{num}")' in core


def test_every_section_is_reachable_by_number_and_by_title() -> None:
    sections = studio.guide_sections(studio.read_guide())
    assert "10" in sections and "5" in sections
    for num, (title, body) in sections.items():
        by_number = studio.section_for_model(num)
        assert "error" not in by_number, num
        assert by_number["text"] == body
        assert studio.find_section(sections, title.split()[0].lower()) is not None


def test_unknown_section_lists_the_valid_names() -> None:
    answer = studio.section_for_model("nope")
    assert answer["error"].startswith("unknown section")
    assert any(name.startswith("5 ") for name in answer["sections"])
    assert any(name.startswith("10 ") for name in answer["sections"])


def test_repeated_section_read_is_one_line_until_full() -> None:
    first = studio.section_for_model("5")
    again = studio.section_for_model("5")
    assert "text" in first
    assert again.get("unchanged") is True
    assert studio.section_for_model("5", full=True).get("text") == first["text"]


def test_studio_guide_returns_the_core_not_the_whole_guide() -> None:
    out = studio.studio_guide([], config=CONFIG)
    assert len(out["guide"]) <= CORE_LIMIT
    assert "## 5. Look and motion" not in out["guide"]


# ------------------------------------------------------------------ item 24: resume

def test_resume_comes_from_the_state_file_in_at_most_five_lines() -> None:
    state.record("Demo Video", plan="/p/plan.json", last_render={"mode": "final", "job_id": "render-1", "summary": "done"},
                 voice="/p/audio/voice.mp3", last_export="/p/final")
    lines = state.resume_lines("Demo Video")
    assert 1 <= len(lines) <= state.MAX_RESUME_LINES
    assert lines[0] == "plan: /p/plan.json"
    assert any("render-1" in line for line in lines)


def test_studio_guide_adds_resume_only_when_a_project_is_given() -> None:
    state.record("demo", plan="/p/plan.json")
    assert "resume" not in studio.studio_guide([], config=CONFIG)
    out = studio.studio_guide([], config=CONFIG, project="demo")
    assert out["resume"] == ["plan: /p/plan.json"]


def test_state_is_merged_and_a_broken_file_is_ignored() -> None:
    state.record("demo", plan="a.json")
    state.record("demo", voice="v.mp3")
    assert state.load("demo") == {"plan": "a.json", "voice": "v.mp3"}
    state.state_path("demo").write_text("{ not json", encoding="utf-8")
    assert state.load("demo") == {}
    assert state.resume_lines("demo") == []

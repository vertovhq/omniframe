"""Starter recipes (task 20.16): twelve Markdown guides, and the `recipes` list and `recipe` argument of studio_guide."""

from __future__ import annotations

import dataclasses
import inspect
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import server  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.tools import recipes, studio  # noqa: E402

RECIPE_DIR = Path(__file__).resolve().parents[1] / "src" / "omniframe" / "recipes"
SLUGS = sorted([
    "numbered-tips-kinetic", "presenter-floating-cards", "talking-head-lesson", "tool-demo-callouts",
    "spoken-list-screenshots", "founder-diary-broll", "product-proof-pip", "product-launch-reveal",
    "explainer-from-scratch", "data-story-charts", "series-next-episode", "beat-synced-visuals",
])
SECTIONS = [
    "What it is", "Fits when", "Hook, first 3 s", "Shot order", "Captions and type",
    "Motion and transitions", "Sound and music", "Material needed", "Common mistakes",
    "OmniFrame tools to use",
]
MAX_LINES = 60
TOOL_NAME = re.compile(r"`([a-z_]+)[`(]")  # a backticked tool name, alone or called with arguments
CYRILLIC = re.compile(r"[\u0400-\u04FF]")


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """studio_guide reads the knowledge base and the library folder: point both into tmp_path.

    The repeat-read cache is cleared, so every call returns the full result.
    """
    cfg = dataclasses.replace(CONFIG, knowledge_base=tmp_path / "KNOWLEDGE_BASE.md", output_dir=tmp_path / "out")
    monkeypatch.setattr(studio, "CONFIG", cfg)
    monkeypatch.setattr(studio, "_SENT", {})


def _text(slug: str) -> str:
    return (RECIPE_DIR / f"{slug}.md").read_text(encoding="utf-8")


def _sections(text: str) -> dict[str, list[str]]:
    """`{heading: lines}` for the `## ` sections, in file order."""
    out: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def _registered_tools() -> set[str]:
    return {tool.name for tool in server.mcp._tool_manager.list_tools()}


def test_twelve_recipe_files_exist_with_the_agreed_slugs() -> None:
    assert len(SLUGS) == 12
    assert recipes.slugs() == SLUGS
    for slug in SLUGS:
        assert (RECIPE_DIR / f"{slug}.md").is_file()


@pytest.mark.parametrize("slug", SLUGS)
def test_each_recipe_has_every_section_in_order(slug: str) -> None:
    text = _text(slug)
    assert text.startswith("# ")
    assert list(_sections(text)) == SECTIONS


@pytest.mark.parametrize("slug", SLUGS)
def test_each_recipe_is_at_most_60_lines(slug: str) -> None:
    assert len(_text(slug).splitlines()) <= MAX_LINES


@pytest.mark.parametrize("slug", SLUGS)
def test_what_it_is_and_fits_when_are_one_line_each(slug: str) -> None:
    sections = _sections(_text(slug))
    for name in ("What it is", "Fits when"):
        assert len([line for line in sections[name] if line.strip()]) == 1, name


@pytest.mark.parametrize("slug", SLUGS)
def test_recipes_are_english_and_have_no_percentage_thresholds(slug: str) -> None:
    text = _text(slug)
    assert not CYRILLIC.search(text)
    assert "%" not in text  # product steering: no percentage thresholds on creative content


@pytest.mark.parametrize("slug", SLUGS)
def test_tools_section_names_only_registered_tools(slug: str) -> None:
    body = "\n".join(_sections(_text(slug))["OmniFrame tools to use"])
    names = TOOL_NAME.findall(body)
    assert names, "the section names no tool"
    assert set(names) <= _registered_tools(), set(names) - _registered_tools()


@pytest.mark.usefixtures("isolated")
def test_studio_guide_lists_every_recipe_with_its_what_line() -> None:
    listed = server.studio_guide()["recipes"]

    assert [entry["slug"] for entry in listed] == SLUGS
    for entry in listed:
        expected = _sections(_text(entry["slug"]))["What it is"][0].strip()
        assert entry["what"] == expected and entry["what"]


@pytest.mark.usefixtures("isolated")
def test_studio_guide_takes_a_recipe_argument_with_no_default() -> None:
    parameter = inspect.signature(server.studio_guide).parameters["recipe"]
    assert parameter.default is None


@pytest.mark.usefixtures("isolated")
@pytest.mark.parametrize("slug", SLUGS)
def test_recipe_argument_returns_the_full_text_every_time(slug: str) -> None:
    first = server.studio_guide(recipe=slug)
    second = server.studio_guide(recipe=slug)  # a repeat is not shortened to a hash line

    assert first["recipe"] == slug and first["text"] == _text(slug)
    assert second["text"] == _text(slug)


@pytest.mark.usefixtures("isolated")
def test_recipe_slug_ignores_case_and_surrounding_spaces() -> None:
    assert server.studio_guide(recipe="  Talking-Head-Lesson ")["recipe"] == "talking-head-lesson"


@pytest.mark.usefixtures("isolated")
def test_unknown_recipe_returns_an_error_with_the_valid_slugs() -> None:
    result = server.studio_guide(recipe="vlog-daily")

    assert "text" not in result
    assert "vlog-daily" in result["error"]
    assert result["recipes"] == SLUGS

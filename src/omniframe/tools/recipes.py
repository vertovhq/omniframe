"""Starter recipes: Markdown guides for popular short-video formats (task 20.16).

A recipe is text the model reads. Nothing here scores or picks one: `index()` lists the
files, `recipe_for_model()` returns the text of the slug the model asked for, and the
model decides which format fits. The files ship in the package under `omniframe/recipes/`.
"""

from __future__ import annotations

from importlib import resources

from .. import __version__

WHAT_IT_IS = "What it is"


def _folder():
    return resources.files("omniframe").joinpath("recipes")


def slugs() -> list[str]:
    """Every recipe slug in sorted order: the file names without `.md`."""
    return sorted(item.name[:-3] for item in _folder().iterdir() if item.name.endswith(".md"))


def read(slug: str) -> str:
    """The Markdown text of one recipe. `slug` must come from `slugs()`."""
    return _folder().joinpath(f"{slug}.md").read_text(encoding="utf-8")


def what_it_is(text: str) -> str:
    """The first non-empty line under `## What it is`, or "" when the section is missing."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"## {WHAT_IT_IS}":
            for following in lines[i + 1:]:
                if following.strip():
                    return following.strip()
            return ""
    return ""


def index() -> list[dict]:
    """`[{"slug", "what"}]` for every recipe: the `recipes` list of `studio_guide`."""
    return [{"slug": slug, "what": what_it_is(read(slug))} for slug in slugs()]


def recipe_for_model(slug: str) -> dict:
    """`studio_guide(recipe=...)`: the full text of one recipe, read again on every call.

    The slug is matched without regard to case and surrounding spaces. An unknown slug
    returns an error with the valid slugs.
    """
    head = {"engine": f"OmniFrame {__version__}"}
    key = slug.strip().lower()
    names = slugs()
    if key not in names:
        return {**head, "error": f"unknown recipe {slug!r}", "recipes": names}
    return {**head, "recipe": key, "text": read(key)}

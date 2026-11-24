import re
from dataclasses import replace

import pytest

from omniframe import project
from omniframe.config import CONFIG
from omniframe.project import PROJECT_FOLDERS, project_dir, slugify

SLUG_PATTERN = re.compile(r"[a-z0-9-]{1,48}")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Hello, World!", "hello-world"),
        ("  a  --  b__c ", "a-b-c"),
        ("Кот в ботинках", "kot-v-botinkah"),
        ("Щётка Ёжика", "shchyotka-yozhika"),
        ("Clip #3 (final)", "clip-3-final"),
    ],
)
def test_slugify_rules(name, expected):
    assert slugify(name) == expected


def test_slugify_truncates_to_48_without_trailing_hyphen():
    slug = slugify("a" * 47 + " b")
    assert slug == "a" * 47
    assert len(slugify("x" * 200)) == 48


def test_slugify_rejects_names_without_letters_or_digits():
    with pytest.raises(ValueError):
        slugify("!!! ???")


@pytest.mark.parametrize("name", ["Hello", "Кот в ботинках", "x" * 200, "  ЁЖ-ёж  "])
def test_slug_matches_design_pattern(name):
    assert SLUG_PATTERN.fullmatch(slugify(name))


@pytest.fixture
def isolated_output(tmp_path, monkeypatch):
    monkeypatch.setattr(project, "CONFIG", replace(CONFIG, output_dir=tmp_path / "out"))
    return tmp_path / "out"


def test_project_dir_creates_design_folders(isolated_output):
    root = project_dir("Morning Routine")

    assert root == isolated_output / "projects" / "morning-routine"
    for folder in PROJECT_FOLDERS:
        assert (root / folder).is_dir(), folder


def test_project_dir_is_idempotent_and_keeps_files(isolated_output):
    root = project_dir("demo")
    marker = root / "audio" / "voice.mp3"
    marker.write_bytes(b"x")

    assert project_dir("demo") == root
    assert marker.read_bytes() == b"x"

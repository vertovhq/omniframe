"""The old ARGUS names still work after the rename to OmniFrame."""

import os
from pathlib import Path

from omniframe import _compat


def test_old_env_name_is_copied_when_new_name_is_missing(monkeypatch):
    monkeypatch.delenv("OMNIFRAME_LEGACY_TEST_VALUE", raising=False)  # registers the restore
    monkeypatch.setenv("ARGUS_LEGACY_TEST_VALUE", "from-old-name")

    _compat.mirror_legacy_env()

    assert os.environ["OMNIFRAME_LEGACY_TEST_VALUE"] == "from-old-name"


def test_new_env_name_wins_over_old_one(monkeypatch):
    monkeypatch.setenv("OMNIFRAME_LEGACY_TEST_VALUE", "new")
    monkeypatch.setenv("ARGUS_LEGACY_TEST_VALUE", "old")

    _compat.mirror_legacy_env()

    assert os.environ["OMNIFRAME_LEGACY_TEST_VALUE"] == "new"


def test_home_folder_is_argus_only_when_it_is_the_only_one(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert _compat.omniframe_home() == tmp_path / ".omniframe"  # neither exists

    (tmp_path / ".argus").mkdir()
    assert _compat.omniframe_home() == tmp_path / ".argus"  # only the old one

    (tmp_path / ".omniframe").mkdir()
    assert _compat.omniframe_home() == tmp_path / ".omniframe"  # new one exists: it wins

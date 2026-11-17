"""Freesound SFX tool tests: parsing, license filters, ID validation - no network."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.tools import sfx  # noqa: E402

# Minimal synthetic Freesound search-result block (same shape the parser reads).
HTML_ROW = """
<div class="bw-search__result">
  <div data-sound-id="12345" data-title="Paper Slide" data-username="foleypro"
       data-duration="0.7" data-mp3="https://cdn.freesound.org/previews/12/12345_999-lq.mp3"
       data-num-downloads="4200"></div>
  <a href="/people/foleypro/sounds/12345/">Paper Slide</a>
  <a href="https://creativecommons.org/publicdomain/zero/1.0/" title="License: Creative Commons 0"></a>
  <div class="max-h-60px" title="A dry single paper slide on wood.">A dry single paper slide on wood.</div>
  <div class="bw-rating__count">(97 ratings)</div>
  <div aria-label="Average rating of 4.4">4.4</div>
</div>
"""


def test_parse_search_extracts_metadata() -> None:
    doc = sfx.Document(HTML_ROW)
    rows = sfx.parse_search(doc)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "fs:12345"
    assert row["title"] == "Paper Slide"
    assert row["author"] == "foleypro"
    assert row["duration_seconds"] == pytest.approx(0.7)
    assert row["license_label"] == "Creative Commons 0"
    assert row["page_url"].endswith("/sounds/12345/")
    assert row["rating"] == pytest.approx(4.4)
    assert row["rating_count"] == 97
    assert "paper slide" in row["description"].lower()
    assert "-hq.mp3" in row["preview_url"]


def test_license_code_mapping() -> None:
    assert sfx.license_code("https://creativecommons.org/publicdomain/zero/1.0/") == "CC0-1.0"
    assert sfx.license_code("https://creativecommons.org/licenses/by/4.0") == "CC-BY-4.0"
    assert sfx.license_code("https://example.com/other") is None


def test_check_license_policy() -> None:
    sfx.check_license("CC0-1.0", "cc0")
    sfx.check_license("CC0-1.0", "by")
    sfx.check_license("CC-BY-4.0", "by")
    with pytest.raises(ValueError, match="CC BY"):
        sfx.check_license("CC-BY-4.0", "cc0")
    with pytest.raises(ValueError):
        sfx.check_license(None, "cc0")


def test_sound_id_validation() -> None:
    assert sfx.sound_id("fs:12345") == "12345"
    assert sfx.sound_id("12345") == "12345"
    with pytest.raises(ValueError, match="Invalid Freesound ID"):
        sfx.sound_id("fs:abc")
    with pytest.raises(ValueError):
        sfx.sound_id("fs:0")


def test_search_adapter_validates_args() -> None:
    with pytest.raises(ValueError, match="limit"):
        sfx.search_freesound("click", limit=100)
    with pytest.raises(ValueError, match="max_duration"):
        sfx.search_freesound("click", min_duration=2.0, max_duration=1.0)

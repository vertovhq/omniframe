"""Style library (task 20.3): save through `export_package`, list through `studio_guide`, import from a component.

Videos are synthetic (lavfi, same masters as `test_export`); nothing needs the network. The render
test that imports an entry lives in `test_components.py`, next to the other engine tests.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_export import _master  # noqa: E402  (synthetic final that passes QA)

from omniframe import jobs, project, server  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.media_out import Image  # noqa: E402
from omniframe.tools import components, export, library, memory, qa, studio  # noqa: E402

TEXTS = {"tiktok": {"caption": "Yacht day", "hashtags": ["yacht"]}}
ART = "import {useStyle} from '../style';\nimport Dot from './Dot';\nexport default function Art() { useStyle(); return <Dot />; }\n"
DOT = "export default function Dot() { return <i />; }\n"
SPEC = {
    "name": "Yacht scenes",
    "components": ["Art"],
    "what": "Night harbour with a yacht, a captain and a HUD plate.",
    "fits_when": "Money or luxury stories in dark neon.",
    "props": "accent, label",
}


@pytest.fixture(scope="module")
def master(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _master(tmp_path_factory.mktemp("lib") / "vertical.mp4", "1080x1920")


@pytest.fixture
def out_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output = tmp_path / "out"
    for module in (project, jobs, qa):
        monkeypatch.setattr(module, "CONFIG", dataclasses.replace(module.CONFIG, output_dir=output))
    cfg = dataclasses.replace(CONFIG, knowledge_base=tmp_path / "KB.md", output_dir=output)
    for module in (studio, memory):
        monkeypatch.setattr(module, "CONFIG", cfg)
    return output


@pytest.fixture
def root(out_dir: Path) -> Path:
    base = project.project_dir("Yacht Rework")
    (base / "components" / "Art.tsx").write_text(ART, encoding="utf-8")
    (base / "components" / "Dot.tsx").write_text(DOT, encoding="utf-8")
    return base


def _final(root: Path, master: Path) -> dict[str, str]:
    target = root / "renders" / "project-1-final-9x16.mp4"
    target.write_bytes(master.read_bytes())
    return {"9:16": str(target)}


def _entry(lib: Path, name: str, what: str, *, age: int = 0, poster: bool = True) -> None:
    """An entry written the way `save_entry` writes it, without a video (for listing tests)."""
    folder = lib / name
    folder.mkdir(parents=True)
    (folder / "Scene.tsx").write_text("export default () => null;\n", encoding="utf-8")
    (folder / library.CARD).write_text(
        library.card_text(name, {"what": what, "fits_when": f"when {name} fits", "props": "", "source": "p",
                                 "files": ["Scene.tsx"], "saved": "2026-11-19"}),
        encoding="utf-8",
    )
    if poster:
        PILImage.new("RGB", (288, 512), (10 * age % 255, 40, 90)).save(folder / library.POSTER)
    # `studio_guide` orders posters by the poster's mtime (the save time), so the age goes on both files
    stamp = 1_700_000_000 + age
    for path in (folder / library.CARD, folder / library.POSTER):
        if path.is_file():
            os.utime(path, (stamp, stamp))


# ------------------------------------------------------------------ saving

def test_saving_writes_the_entry_the_poster_and_the_index(out_dir: Path, root: Path, master: Path) -> None:
    result = export.export_package(
        "Yacht Rework", _final(root, master), TEXTS, save_to_library={**SPEC, "poster_time": 1.0}, wait_s=300
    )
    assert isinstance(result, list), result
    data = json.loads(result[0])
    assert data["exported"] is True
    saved = data["library"]
    assert saved["saved"] is True and len(saved["entries"]) == 1
    assert saved["entries"][0]["entry"] == "yacht-scenes" and saved["entries"][0]["poster_t"] == 1.0

    lib = out_dir / "library"
    entry = lib / "yacht-scenes"
    assert sorted(p.name for p in entry.iterdir()) == ["Art.tsx", "Dot.tsx", "card.md", "poster.jpg"]  # Dot comes with Art
    assert (entry / "Art.tsx").read_text(encoding="utf-8") == ART
    with PILImage.open(entry / "poster.jpg") as poster:
        assert poster.format == "JPEG" and max(poster.size) == library.POSTER_SIDE and poster.size == (288, 512)

    card = (entry / "card.md").read_text(encoding="utf-8")
    for expected in ("**What:** Night harbour", "**Fits when:** Money or luxury", "**Props:** accent, label",
                     "**Source project:** yacht-rework", "**Files:** Art.tsx, Dot.tsx", "./library/yacht-scenes/Art",
                     "**Version:** 1", "**Times used:** 0", "- v1 (", "first save"):
        assert expected in card
    index = (lib / "index.md").read_text(encoding="utf-8")
    lines = [line for line in index.splitlines() if line.startswith("- ")]
    assert len(lines) == 1
    assert lines[0].startswith(
        "- **yacht-scenes** (v1, used 0 times): Night harbour with a yacht, a captain and a HUD plate. "
        "Fits when: Money or luxury stories in dark neon."
    )
    assert "Files: Art, Dot" in lines[0]
    assert not [p for p in lib.iterdir() if p.name.startswith(".")]  # no staging folder is left

    # the cover (1) and the library poster (2) come back as pictures; the poster copy is outside the entry
    assert len(result) == 3 and all(isinstance(item, Image) for item in result[1:])
    assert not list(entry.glob("*.view.jpg"))
    assert (root / "final" / "yacht-rework_9x16.mp4").is_file()


def test_a_list_saves_every_element_in_one_export(out_dir: Path, root: Path, master: Path) -> None:
    videos = _final(root, master)
    plain = {**SPEC, "name": "Plain dot", "components": ["Dot"], "what": "A dot.", "fits_when": "Never."}
    result = export.export_package("Yacht Rework", videos, TEXTS, wait_s=300, save_to_library=[SPEC, plain])
    data = json.loads(result[0])["library"]
    assert data["saved"] is True and [e["entry"] for e in data["entries"]] == ["yacht-scenes", "plain-dot"]

    lib = out_dir / "library"
    index = (lib / "index.md").read_text(encoding="utf-8")
    assert [ln.split("**")[1] for ln in index.splitlines() if ln.startswith("- ")] == ["plain-dot", "yacht-scenes"]

    (lib / "plain-dot" / "card.md").unlink()  # a folder without a card is no entry
    assert [c["name"] for c in library.read_cards(lib)] == ["yacht-scenes"]
    assert "plain-dot" not in library.build_index(lib)


def test_a_second_save_of_a_name_is_the_next_version_and_keeps_the_old_files(
    out_dir: Path, root: Path, master: Path
) -> None:
    videos = _final(root, master)
    export.export_package("Yacht Rework", videos, TEXTS, save_to_library=SPEC, wait_s=300)

    again = export.export_package("Yacht Rework", videos, TEXTS, save_to_library=SPEC, wait_s=300)
    assert isinstance(again, dict) and again["valid"] is False
    assert "changed" in again["errors"][0] and "'yacht-scenes'" in again["errors"][0]

    second = export.export_package(
        "Yacht Rework", videos, TEXTS, wait_s=300,
        save_to_library={**SPEC, "what": "New text.", "changed": "Bigger HUD plate."},
    )
    entry = json.loads(second[0])["library"]["entries"][0]
    assert entry["saved"] is True and entry["version"] == 2

    lib = out_dir / "library" / "yacht-scenes"
    assert (lib / "Art.tsx").read_text(encoding="utf-8") == ART  # the newest files at the top
    old = lib / "versions" / "v1"
    assert (old / "Art.tsx").read_text(encoding="utf-8") == ART and (old / "card.md").is_file()
    assert (old / "poster.jpg").is_file()
    card = (lib / "card.md").read_text(encoding="utf-8")
    assert "**Version:** 2" in card and "- v1 (" in card and "- v2 (" in card
    assert "first save" in card and "Bigger HUD plate." in card
    index = (out_dir / "library" / "index.md").read_text(encoding="utf-8")
    assert "- **yacht-scenes** (v2, used 0 times): New text." in index

    clash = export.export_package(
        "Yacht Rework", videos, TEXTS, wait_s=300,
        save_to_library=[SPEC, {**SPEC, "changed": "Again."}],
    )
    assert clash["valid"] is False and any("appears twice" in e for e in clash["errors"])


def test_times_used_counts_each_render_that_imports_the_entry(out_dir: Path) -> None:
    lib = out_dir / "library"
    _entry(lib, "demo", "Demo.")
    _entry(lib, "other", "Other.")
    library.count_use(lib, ["demo"])
    library.count_use(lib, ["demo", "missing"])  # a name with no card is skipped
    cards = {c["name"]: c for c in library.read_cards(lib)}
    assert cards["demo"]["times_used"] == 2 and cards["other"]["times_used"] == 0
    assert "- **demo** (v1, used 2 times): Demo." in (lib / "index.md").read_text(encoding="utf-8")
    assert "**Times used:** 2" in (lib / "demo" / "card.md").read_text(encoding="utf-8")


def test_validating_a_save_request_writes_nothing(out_dir: Path, root: Path, master: Path) -> None:
    payload, errors = export.prepare_export(root, _final(root, master), TEXTS, save_to_library=SPEC)
    assert errors == [] and payload is not None and payload["library"][0]["entry"] == "yacht-scenes"
    assert not (out_dir / "library").exists()  # validation writes nothing


@pytest.mark.parametrize("change, message", [
    ({"nope": 1}, "save_to_library.nope: unknown field"),
    ({"what": ""}, "save_to_library.what: required"),
    ({"fits_when": "x" * 251}, "at most 250"),
    ({"what": "x" * 201}, "at most 200"),
    ({"name": "Kit"}, "'kit' is reserved"),
    ({"name": "!!!"}, "save_to_library.name"),
    ({"components": []}, "save_to_library.components"),
    ({"components": ["Missing"]}, "file not found: components/Missing.tsx"),
    ({"components": ["bad name"]}, "is not a component name"),
    ({"replace": True}, "save_to_library.replace: unknown field"),
    ({"changed": "x" * 201}, "at most 200"),
    ({"props": 3}, "save_to_library.props: must be a string"),
    ({"poster_time": -1}, "outside the video"),
    ({"poster_time": 99}, "outside the video"),
    ({"poster_time": "soon"}, "not a number"),
])
def test_bad_save_requests_are_listed_and_nothing_starts(
    out_dir: Path, root: Path, change: dict, message: str
) -> None:
    errors_text = "\n".join(library.validate_save({**SPEC, **change}, root, out_dir / "library", 4.0)[1])
    assert message in errors_text


def test_saving_refuses_components_that_break_the_contract(out_dir: Path, root: Path) -> None:
    (root / "components" / "Net.tsx").write_text("import x from 'left-pad';\nexport default () => null;\n", encoding="utf-8")
    lib = out_dir / "library"
    _, errors = library.validate_save({**SPEC, "components": ["Net"]}, root, lib)
    assert any("left-pad" in e for e in errors)
    clean, errors = library.validate_save(SPEC, root, lib)
    assert errors == [] and clean[0]["files"] == ["Art.tsx", "Dot.tsx"] and clean[0]["source"] == "yacht-rework"
    assert clean[0]["uses"] == []


# ------------------------------------------------------------------ composed entries (Uses)

BG_V1 = "export default function Bg() { return <i />; }\n"
BG_V2 = "export default function Bg() { return <b />; }\n"
WRAP = "import Bg from './library/neon-bg/Bg';\nexport default function Wrap() { return <Bg />; }\n"


def _save(project_root: Path, lib: Path, master: Path, spec: dict) -> dict:
    """Save through the same two steps the export job uses: validate, then write the entry."""
    clean, errors = library.validate_save(spec, project_root, lib, 4.0)
    assert errors == [] and clean, errors
    return library.save_entry(clean[0], project_root, lib, master, 1.0)


@pytest.fixture
def bg_source(out_dir: Path) -> Path:
    base = project.project_dir("Neon Source")
    (base / "components" / "Bg.tsx").write_text(BG_V1, encoding="utf-8")
    return base


def test_a_component_that_imports_entries_is_saved_with_uses_and_no_copies(
    out_dir: Path, root: Path, bg_source: Path, master: Path
) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    (root / "components" / "Wrap.tsx").write_text(WRAP, encoding="utf-8")

    clean, errors = library.validate_save({"name": "wrapper", "components": ["Wrap"], "what": "W.", "fits_when": "W."},
                                          root, lib)
    assert errors == [] and clean[0]["files"] == ["Wrap.tsx"]
    assert clean[0]["uses"] == [{"entry": "neon-bg", "version": 1}]

    library.save_entry(clean[0], root, lib, master, 1.0)
    entry = lib / "wrapper"
    assert sorted(p.name for p in entry.iterdir()) == ["Wrap.tsx", "card.md", "poster.jpg"]  # Bg stays in neon-bg
    assert "import Bg from '../neon-bg/Bg';" in (entry / "Wrap.tsx").read_text(encoding="utf-8")
    card = (entry / "card.md").read_text(encoding="utf-8")
    assert "**Uses:** neon-bg v1" in card and "import Wrap from './library/wrapper/Wrap';" in card


def test_importing_a_composed_entry_copies_its_dependencies_at_the_pinned_version(
    out_dir: Path, root: Path, bg_source: Path, master: Path
) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    (root / "components" / "Wrap.tsx").write_text(WRAP, encoding="utf-8")
    _save(root, lib, master, {"name": "wrapper", "components": ["Wrap"], "what": "W.", "fits_when": "W."})

    # a newer neon-bg is saved afterwards; the wrapper still pins v1
    (bg_source / "components" / "Bg.tsx").write_text(BG_V2, encoding="utf-8")
    second = _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.",
                                            "fits_when": "Dark.", "changed": "Bigger HUD."})
    assert second["version"] == 2
    assert (lib / "neon-bg" / "versions" / "v1" / "Bg.tsx").read_text(encoding="utf-8") == BG_V1

    (root / "components" / "Uses.tsx").write_text(
        "import W from './library/wrapper/Wrap';\nexport default W;\n", encoding="utf-8")
    files, errors, _ = components.collect_files(root, ["Uses"], lib)
    assert errors == []
    by_rel = {f.rel: f.path for f in files}
    assert sorted(by_rel) == ["Uses.tsx", "library/neon-bg/Bg.tsx", "library/wrapper/Wrap.tsx"]
    assert by_rel["library/neon-bg/Bg.tsx"].read_text(encoding="utf-8") == BG_V1  # the pinned v1, not the newest
    assert by_rel["library/neon-bg/Bg.tsx"].parent == lib / "neon-bg" / "versions" / "v1"


def test_a_render_that_needs_two_versions_of_one_entry_is_refused(
    out_dir: Path, root: Path, bg_source: Path, master: Path
) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    (root / "components" / "Wrap.tsx").write_text(WRAP, encoding="utf-8")
    _save(root, lib, master, {"name": "wrapper", "components": ["Wrap"], "what": "W.", "fits_when": "W."})
    (bg_source / "components" / "Bg.tsx").write_text(BG_V2, encoding="utf-8")
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.",
                                   "fits_when": "Dark.", "changed": "Bigger HUD."})

    (root / "components" / "Both.tsx").write_text(
        "import W from './library/wrapper/Wrap';\nimport B from './library/neon-bg/Bg';\nexport default W;\n",
        encoding="utf-8")
    _, errors, _ = components.collect_files(root, ["Both"], lib)
    assert any("needed in two versions" in e and "library/neon-bg/Bg.tsx" in e for e in errors)


def test_chains_are_one_level_deep(out_dir: Path, root: Path, bg_source: Path, master: Path) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    (root / "components" / "Wrap.tsx").write_text(WRAP, encoding="utf-8")
    _save(root, lib, master, {"name": "wrapper", "components": ["Wrap"], "what": "W.", "fits_when": "W."})

    # an entry that uses `wrapper`, which already uses `neon-bg`: two levels
    outer = lib / "outer"
    outer.mkdir(parents=True)
    (outer / "Outer.tsx").write_text("import W from '../wrapper/Wrap';\nexport default W;\n", encoding="utf-8")
    (outer / library.CARD).write_text(library.card_text("outer", {
        "what": "O.", "fits_when": "O.", "source": "p", "files": ["Outer.tsx"], "saved": "2026-11-23",
        "uses": [{"entry": "wrapper", "version": 1}],
    }), encoding="utf-8")
    (root / "components" / "Deep.tsx").write_text(
        "import O from './library/outer/Outer';\nexport default O;\n", encoding="utf-8")
    _, errors, _ = components.collect_files(root, ["Deep"], lib)
    assert any("uses other entries itself" in e for e in errors)

    # and a saved component cannot import `wrapper`, which uses an entry itself
    (root / "components" / "Deep2.tsx").write_text(
        "import W from './library/wrapper/Wrap';\nexport default W;\n", encoding="utf-8")
    clean, errors = library.validate_save({"name": "deeper", "components": ["Deep2"], "what": "D.", "fits_when": "D."},
                                          root, lib)
    assert clean is None and any("chains are one level deep" in e for e in errors)


def test_an_entry_import_must_be_listed_under_uses(out_dir: Path, root: Path, bg_source: Path, master: Path) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    _entry(lib, "plain", "Plain.")
    (lib / "plain" / "Scene.tsx").write_text("import B from '../neon-bg/Bg';\nexport default B;\n", encoding="utf-8")
    (root / "components" / "Uses.tsx").write_text(
        "import S from './library/plain/Scene';\nexport default S;\n", encoding="utf-8")
    _, errors, _ = components.collect_files(root, ["Uses"], lib)
    assert any("needs 'neon-bg' under Uses in card.md" in e for e in errors)


def test_a_pinned_version_that_is_not_kept_is_reported(out_dir: Path, root: Path, bg_source: Path, master: Path) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    outer = lib / "gone"
    outer.mkdir(parents=True)
    (outer / "Gone.tsx").write_text("import B from '../neon-bg/Bg';\nexport default B;\n", encoding="utf-8")
    (outer / library.CARD).write_text(library.card_text("gone", {
        "what": "G.", "fits_when": "G.", "source": "p", "files": ["Gone.tsx"], "saved": "2026-11-23",
        "uses": [{"entry": "neon-bg", "version": 7}],
    }), encoding="utf-8")
    (root / "components" / "Uses.tsx").write_text(
        "import G from './library/gone/Gone';\nexport default G;\n", encoding="utf-8")
    _, errors, _ = components.collect_files(root, ["Uses"], lib)
    assert any("neon-bg v7 has no file Bg" in e for e in errors)


def test_uses_survive_a_render_that_counts_the_use(out_dir: Path, root: Path, bg_source: Path, master: Path) -> None:
    lib = out_dir / "library"
    _save(bg_source, lib, master, {"name": "neon-bg", "components": ["Bg"], "what": "BG.", "fits_when": "Dark."})
    (root / "components" / "Wrap.tsx").write_text(WRAP, encoding="utf-8")
    _save(root, lib, master, {"name": "wrapper", "components": ["Wrap"], "what": "W.", "fits_when": "W."})
    library.count_use(lib, ["wrapper"])
    card = library.read_card(lib / "wrapper")
    assert card["uses"] == [{"entry": "neon-bg", "version": 1}] and card["times_used"] == 1
    assert "**Uses:** neon-bg v1" in (lib / "wrapper" / "card.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ reading

def test_studio_guide_without_entries_stays_a_dict(out_dir: Path) -> None:
    result = server.studio_guide()
    assert isinstance(result, dict) and result["library"] == {"dir": str(out_dir / "library"), "entries": 0}


def test_studio_guide_lists_entries_and_returns_their_posters_as_images(out_dir: Path) -> None:
    lib = out_dir / "library"
    _entry(lib, "yacht-scenes", "Night harbour.", age=1)
    _entry(lib, "plain-card", "A card.", age=2)
    _entry(lib, "no-poster", "Has no poster.", age=3, poster=False)

    result = server.studio_guide()
    assert isinstance(result, list)
    data = json.loads(result[0])
    assert data["library"]["entries"] == 3
    index = data["library"]["index"]
    assert len([ln for ln in index.splitlines() if ln.startswith("- ")]) == 3
    assert "- **yacht-scenes** (v1, used 0 times): Night harbour. Fits when: when yacht-scenes fits." in index
    posters = data["library"]["posters"]
    assert [p["entry"] for p in posters] == ["plain-card", "yacht-scenes"]  # newest first, entries without a poster skipped
    images = result[1:]
    assert len(images) == 2 and all(isinstance(item, Image) for item in images)
    assert data["guide"].startswith("# OmniFrame Studio Guide") and "preferences" in data
    assert not list(lib.glob("*/*.view.jpg"))
    with PILImage.open(posters[0]["path"]) as picture:
        assert max(picture.size) <= library.POSTER_SIDE


def test_studio_guide_returns_at_most_eight_posters(out_dir: Path) -> None:
    lib = out_dir / "library"
    for i in range(11):
        _entry(lib, f"entry-{i:02d}", f"Entry {i}.", age=i)

    result = server.studio_guide()
    data = json.loads(result[0])
    assert data["library"]["entries"] == 11
    assert len([ln for ln in data["library"]["index"].splitlines() if ln.startswith("- ")]) == 11  # every entry is listed
    assert len(result) == 1 + library.MAX_POSTERS == 9
    assert [p["entry"] for p in data["library"]["posters"]][:2] == ["entry-10", "entry-09"]


# ------------------------------------------------------------------ importing (source checks; stills are in test_components)

def _scan(root: Path, library_root: Path, name: str = "Uses") -> list[str]:
    plan = {"version": 2, "format": "9:16", "duration": 3, "style": "dark",
            "scenes": [{"kind": "custom", "at": 0, "until": 3, "component": name}]}
    from omniframe.plan import validate_plan

    parsed, errors = validate_plan(plan)
    assert parsed is not None, errors
    found, warnings = components.check_components(parsed, root, library_root)
    return found + warnings


def test_a_component_can_import_an_entry_file_and_what_that_file_imports(out_dir: Path, root: Path) -> None:
    lib = out_dir / "library"
    _entry(lib, "demo", "Demo.")
    (lib / "demo" / "Scene.tsx").write_text(
        "import {useStyle} from '../style';\nimport Part from './Part';\nexport default () => <Part />;\n", encoding="utf-8")
    (lib / "demo" / "Part.tsx").write_text("export default () => <b />;\n", encoding="utf-8")
    (root / "components" / "Uses.tsx").write_text(
        "import Scene from './library/demo/Scene';\nexport default () => <Scene />;\n", encoding="utf-8")

    assert _scan(root, lib) == []
    files, errors, _ = components.collect_files(root, ["Uses"], lib)
    assert errors == []
    assert [f.rel for f in files] == ["Uses.tsx", "library/demo/Scene.tsx", "library/demo/Part.tsx"]


@pytest.mark.parametrize("source, message", [
    ("import S from './library/demo/Nope';\nexport default S;\n", "has no file in the style library (the entry has: Scene)"),
    ("import S from './library/ghost/Scene';\nexport default S;\n", "(there is no such entry)"),
    ("import S from './library/Demo/Scene';\nexport default S;\n", "is not allowed"),
    ("import S from '../library/demo/Scene';\nexport default S;\n", "is not allowed"),
])
def test_library_imports_that_do_not_resolve_are_reported(out_dir: Path, root: Path, source: str, message: str) -> None:
    lib = out_dir / "library"
    _entry(lib, "demo", "Demo.")
    (root / "components" / "Uses.tsx").write_text(source, encoding="utf-8")
    assert any(message in e for e in _scan(root, lib))


def test_entry_files_follow_the_contract_and_may_not_import_other_entries(out_dir: Path, root: Path) -> None:
    lib = out_dir / "library"
    _entry(lib, "demo", "Demo.")
    _entry(lib, "other", "Other.")
    (lib / "demo" / "Scene.tsx").write_text(
        "import O from './library/other/Scene';\nimport axios from 'axios';\nexport default () => <O />;\n", encoding="utf-8")
    (root / "components" / "Uses.tsx").write_text(
        "import S from './library/demo/Scene';\nexport default S;\n", encoding="utf-8")

    errors = "\n".join(_scan(root, lib))
    assert "library/demo/Scene.tsx:1:" in errors and "not allowed in a library entry" in errors
    assert "import 'axios' is not allowed" in errors


def test_library_imports_without_a_library_do_not_resolve(root: Path) -> None:
    (root / "components" / "Uses.tsx").write_text("import S from './library/demo/Scene';\nexport default S;\n", encoding="utf-8")
    assert any("no file in the style library" in e for e in _scan(root, None))

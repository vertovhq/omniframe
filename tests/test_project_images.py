"""Task 20.10 item 26: a custom component names a project image as `mediaUrl("media/x.png")`; ARGUS
links the file into the job's public dir, and the engine helper maps the name to the same path.

Offline: the picture is a generated PNG, nothing renders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.tools import render  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "proj"
    (project / "media").mkdir(parents=True)
    PILImage.new("RGB", (8, 8), (255, 0, 0)).save(project / "media" / "octo.png")
    components = project / "components"
    components.mkdir()
    return project, components


def test_component_image_is_linked_and_named_under_m(tmp_path: Path) -> None:
    project, components = _project(tmp_path)
    (components / "Octo.tsx").write_text(
        "import {mediaUrl} from '../kit';\nexport const src = mediaUrl(\"media/octo.png\");\n",
        encoding="utf-8",
    )
    public = render._PublicDir(tmp_path / "public", [project])

    linked = render.link_project_images(public, components, [project])

    assert linked == {"media/octo.png": "m/media_octo.png"}
    assert (public.root / "m" / "media_octo.png").is_file()


def test_unresolved_names_and_non_media_strings_are_skipped(tmp_path: Path) -> None:
    project, components = _project(tmp_path)
    (components / "Ghost.tsx").write_text(
        "const a = mediaUrl('media/missing.png');\nconst b = 'fonts/Inter.otf';\n", encoding="utf-8",
    )
    public = render._PublicDir(tmp_path / "public", [project])

    assert render.link_project_images(public, components, [project]) == {}


def test_key_rule_matches_the_engine_helper() -> None:
    ts = (ROOT / "engine" / "src" / "kit" / "media.ts").read_text(encoding="utf-8")
    match = re.search(r"name\.replace\(/(\[[^/]+\])/g, '_'\)", ts)
    assert match, "mediaKey regex not found in engine/src/kit/media.ts"
    assert match.group(1) == "[^A-Za-z0-9._-]"
    assert render._media_key("media/my file (1).png") == "media_my_file__1_.png"


def test_kit_index_exports_the_helper() -> None:
    index = (ROOT / "engine" / "src" / "kit" / "index.ts").read_text(encoding="utf-8")
    assert "export * from './media';" in index

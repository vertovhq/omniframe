"""Custom scene components (task 16, requirement 11).

The source checks and the lock run offline. The tests marked `needs_engine` use the real
Remotion engine (typecheck with tsc, stills) and are skipped without `engine/node_modules`.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus import jobs, project  # noqa: E402
from argus.config import CONFIG  # noqa: E402
from argus.plan import validate_plan  # noqa: E402
from argus.tools import components, render  # noqa: E402

ENGINE = Path(__file__).resolve().parents[1] / "engine"
REGISTRY = ENGINE / "src" / "custom" / "registry.ts"
needs_engine = pytest.mark.skipif(
    not (ENGINE / "node_modules").is_dir(), reason="engine/node_modules is missing (run npm install in engine/)"
)
WAIT = 300

SAMPLE = """\
import {interpolate, useCurrentFrame} from 'remotion';
import {fontFor, useLayout, useStyle} from '../style';

export default function ScoreBoard({label = 'SCORE', value = 42}: {label?: string; value?: number}) {
  const frame = useCurrentFrame();
  const style = useStyle();
  const {fs, u} = useLayout();
  const shown = Math.round(interpolate(frame, [0, 10], [0, value], {extrapolateRight: 'clamp'}));
  return (
    <div style={{textAlign: 'center', color: style.colors.text, fontFamily: fontFor(style, 'display').css}}>
      <div style={{fontSize: fs(60), color: style.colors.muted}}>{label}</div>
      <div style={{fontSize: fs(300), fontWeight: 900, color: style.colors.accent, marginTop: u(12)}}>{shown}</div>
    </div>
  );
}
"""

BROKEN = """\
import {useCurrentFrame} from 'remotion';

export default function Broken() {
  const frame: string = useCurrentFrame();
  return <div>{frame}{missingName}</div>;
}
"""


@pytest.fixture(autouse=True)
def render_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (jobs, project, render):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield
    for proc in list(jobs._PROCS.values()):
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    jobs._PROCS.clear()


@pytest.fixture
def root() -> Path:
    return project.project_dir("t")


def _plan(*names: str, **extra) -> dict:
    scenes = [{"kind": "custom", "at": i * 1.5, "until": (i + 1) * 1.5, "component": n,
               "props": {"label": "POINTS", "value": 87}} for i, n in enumerate(names)]
    return {"version": 2, "format": "9:16", "duration": 3, "style": "dark", "scenes": scenes, **extra}


def _write(root: Path, name: str, source: str) -> Path:
    path = root / "components" / f"{name}.tsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _check(plan: dict, root: Path) -> tuple[list[str], list[str]]:
    parsed, errors = validate_plan(plan)
    assert parsed is not None, errors
    return components.check_components(parsed, root)


# ------------------------------------------------------------------ committed engine

def test_committed_registry_is_an_empty_map() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    assert "= {};" in text and "import C" not in text and "./job/" not in text
    assert text.replace("\r\n", "\n") == components.EMPTY_REGISTRY
    assert not (ENGINE / "src" / "custom" / "job").exists()
    assert (ENGINE / "src" / "custom" / "README.md").is_file()


# ------------------------------------------------------------------ source checks (offline)

def test_a_valid_component_has_no_findings(root: Path) -> None:
    _write(root, "ScoreBoard", SAMPLE)
    assert _check(_plan("ScoreBoard"), root) == ([], [])


def test_missing_component_file_is_reported_with_the_scene(root: Path) -> None:
    errors, _ = _check(_plan("Nope"), root)
    assert len(errors) == 1 and errors[0].startswith("scenes[0].component:") and "components/Nope.tsx" in errors[0]


def test_imports_outside_the_contract_and_network_calls_are_errors(root: Path) -> None:
    _write(root, "Bad", """\
import React from 'react';
import axios from 'axios';
import {Gif} from '@remotion/gif';
import {useStyle} from '../style';
// import evil from 'commented-out';
export default function Bad() {
  fetch('/x');
  const ws = new WebSocket('ws://x');
  const m = import('./lazy');
  return <img src="https://example.com/a.png" xmlns="http://www.w3.org/2000/svg" />;
}
""")
    errors, _ = _check(_plan("Bad"), root)
    text = "\n".join(errors)
    assert "import 'axios' is not allowed" in text and "import '@remotion/gif' is not allowed" in text
    assert "commented-out" not in text and "import 'react'" not in text and "import '../style'" not in text
    assert "network access" in text and "dynamic import()" in text
    assert text.count("web URL") == 1  # the w3.org namespace is not a network call
    assert all(e.startswith("components/Bad.tsx:") for e in errors)
    assert "components/Bad.tsx:2:" in text  # line numbers point at the offending line


def test_local_imports_follow_other_components_and_non_deterministic_calls_warn(root: Path) -> None:
    _write(root, "Outer", "import Inner from './Inner';\nexport default function Outer() { return <Inner />; }\n")
    _write(root, "Inner", "export default function Inner() { return <b>{Math.random()}</b>; }\n")
    errors, warnings = _check(_plan("Outer"), root)
    assert errors == []
    assert len(warnings) == 1 and warnings[0].startswith("components/Inner.tsx:1:") and "Math.random" in warnings[0]
    _write(root, "Lost", "import X from './Missing';\nexport default function Lost() { return null; }\n")
    errors, _ = _check(_plan("Lost"), root)
    assert errors and "'./Missing' has no file" in errors[0]


def test_render_video_returns_source_errors_and_starts_no_job(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a, **k):
        raise AssertionError("an invalid component must not start a job")

    monkeypatch.setattr(jobs, "run_or_detach", boom)
    _write(root, "Bad", "import x from 'left-pad';\nexport default () => null;\n")
    out = render.render_video(_plan("Bad"), "t")
    assert out["valid"] is False and any("left-pad" in e for e in out["errors"])


# ------------------------------------------------------------------ the engine lock (offline)

def test_lock_is_exclusive_and_a_dead_owners_lock_is_taken_over(tmp_path: Path) -> None:
    components._take_lock(tmp_path, 1)
    with pytest.raises(components.ComponentError, match="another render"):
        components._take_lock(tmp_path, 0.5)
    (tmp_path / components.LOCK_NAME).write_text(json.dumps({"pid": 2**22 + 12345, "time": time.time()}), encoding="utf-8")
    components._take_lock(tmp_path, 1)  # the pid is not running: stale, taken over
    assert json.loads((tmp_path / components.LOCK_NAME).read_text())["pid"] == os.getpid()


def test_release_is_idempotent_and_frees_the_lock(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    (engine / "src" / "custom").mkdir(parents=True)
    (engine / "src" / "custom" / "registry.ts").write_bytes(b"committed\r\n")
    hold = components.EngineHold(engine, tmp_path, [], tmp_path / "work")
    assert hold.acquire() == []
    assert (engine / components.LOCK_NAME).exists()
    hold.release()
    hold.release()
    assert not (engine / components.LOCK_NAME).exists()
    assert hold.registry.read_bytes() == b"committed\r\n"


def test_a_registry_left_by_a_crashed_render_is_repaired(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    (engine / "src" / "custom" / "job").mkdir(parents=True)
    (engine / "src" / "custom" / "job" / "Old.tsx").write_text("x", encoding="utf-8")
    (engine / "src" / "custom" / "registry.ts").write_text("import C0 from './job/Old';\n", encoding="utf-8")
    hold = components.EngineHold(engine, tmp_path, [], tmp_path / "work")
    assert hold.acquire() == []
    hold.release()
    assert hold.registry.read_text(encoding="utf-8") == components.EMPTY_REGISTRY
    assert not hold.job_dir.exists()


# ------------------------------------------------------------------ with the engine

def _engine_untouched() -> None:
    assert REGISTRY.read_text(encoding="utf-8").replace("\r\n", "\n") == components.EMPTY_REGISTRY
    assert not (ENGINE / "src" / "custom" / "job").exists()
    assert not (ENGINE / components.LOCK_NAME).exists()


@needs_engine
def test_broken_component_returns_compiler_errors_and_leaves_the_engine_alone(root: Path) -> None:
    before = REGISTRY.read_bytes()
    _write(root, "Broken", BROKEN)
    out = render.render_video(_plan("Broken"), "t", mode="stills", times=[0.5], wait_s=WAIT)
    assert isinstance(out, dict) and out.get("valid") is False, out
    text = "\n".join(out["errors"])
    assert "components/Broken.tsx(4," in text and "TS2322" in text  # string = number
    assert "missingName" in text
    assert "images" not in out and not list((project.project_dir("t") / "renders").glob("*"))
    assert REGISTRY.read_bytes() == before
    _engine_untouched()
    assert not list((project.project_dir("t") / ".work").glob("render-*"))


@needs_engine
def test_default_export_that_is_not_a_component_is_reported(root: Path) -> None:
    _write(root, "Number", "export default 5;\n")
    out = render.render_video(_plan("Number"), "t", mode="stills", times=[0.5], wait_s=WAIT)
    assert out.get("valid") is False, out
    assert any(e.startswith("components/Number.tsx:") for e in out["errors"]), out["errors"]
    _engine_untouched()


@needs_engine
def test_valid_component_renders_in_stills(root: Path) -> None:
    _write(root, "ScoreBoard", SAMPLE)
    out = render.render_video(_plan("ScoreBoard"), "t", mode="stills", times=[1.0], wait_s=WAIT)
    assert isinstance(out, list), out
    summary = json.loads(out[0])
    assert "valid" not in summary and len(summary["stills"]) == 1, summary
    with PILImage.open(summary["stills"][0]) as img:
        assert img.size == (1080, 1920)
        # the dark background is ~#0A0A12; the number and label add many bright pixels
        pixels = np.asarray(img.convert("RGB").resize((108, 192)))
    bright = int((pixels.max(axis=2) > 150).sum())
    assert bright > 100, f"the component drew almost nothing ({bright} bright pixels)"
    _engine_untouched()
    assert not list((project.project_dir("t") / ".work").glob("render-*"))

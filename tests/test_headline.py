"""Headline caption motion (task 20.10 item 12): a word slams into its own slot and never grows over its neighbours.

The engine's pure module `engine/src/headline.ts` is bundled with esbuild (already in engine/node_modules) and
run in node; no browser. Skips when the engine dependencies are not installed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "engine"

needs_engine = pytest.mark.skipif(
    not (ENGINE / "node_modules" / "esbuild").is_dir(),
    reason="engine/node_modules is missing (run npm install in engine/)",
)

RUNNER = """
const esbuild = require(require.resolve('esbuild', {paths: [process.argv[2]]}));
const built = esbuild.buildSync({entryPoints: [process.argv[3]], bundle: true, format: 'cjs', write: false, platform: 'node'});
const bundle = {exports: {}};
new Function('module', 'exports', 'require', built.outputFiles[0].text)(bundle, bundle.exports, require);
const samples = [-0.5, 0, 0.1, 0.25, 0.5, 0.75, 0.9, 1, 1.5];
console.log(JSON.stringify(samples.map((p) => ({p, ...bundle.exports.headlineMotion(p)}))));
"""


@needs_engine
def test_headline_word_drops_into_its_slot_and_never_grows(tmp_path: Path) -> None:
    runner = tmp_path / "run.cjs"  # .cjs: node reads it as CommonJS whatever the parent package says
    runner.write_text(RUNNER, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(runner), str(ENGINE), str(ENGINE / "src" / "headline.ts")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    rows = json.loads(proc.stdout)
    by_p = {row["p"]: row for row in rows}

    # before the word is spoken it is hidden and sits above its slot
    assert by_p[-0.5]["opacity"] == 0
    assert by_p[0]["translateEm"] == pytest.approx(-0.5)
    # once it has landed it is in its slot, upright and fully visible
    assert by_p[1]["translateEm"] == pytest.approx(0, abs=1e-9)
    assert by_p[1]["rotateDeg"] == pytest.approx(0, abs=1e-9)
    assert by_p[1]["opacity"] == 1
    assert by_p[1.5]["translateEm"] == pytest.approx(0, abs=1e-9)  # clamped after the slam

    for row in rows:
        # no scale field at all: the word keeps its own slot, so it cannot cover a neighbour
        assert set(row) == {"p", "opacity", "translateEm", "rotateDeg"}
        # the drop starts 0.5 em above the slot; the overshoot ends below it by at most 0.1 em
        assert -0.5 - 1e-6 <= row["translateEm"] <= 0.1
        assert abs(row["rotateDeg"]) <= 5.0
        assert 0 <= row["opacity"] <= 1

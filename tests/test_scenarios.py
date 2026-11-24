"""Scenario end-to-end tests (design §17, requirement 17.1): the flows the author runs in Kiro.

Two of the three scenarios, on synthetic media and the real engine and job workers:

1. reference: watch a reference, preview a plan with style tokens next to it, render the
   final video, check it with QA and export it for TikTok.
3. idea: the graphics-only sample plan with a voice made the way edge-tts makes one (word
   boundaries from a stand-in for the edge_tts client), render the final video and export it.

2. footage: a synthetic talking clip with fixture words (a stand-in for Whisper): the words
   `watch_video` returns, the cut list of `examples/plans/footage_16x9.json`, the captions moved
   onto the kept clips, the final video and QA. The video is as long as the kept ranges.

Nothing here uses the network. The tests are skipped when `engine/node_modules` is missing.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs, project  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.media_out import Image  # noqa: E402
from omniframe.tools import export, qa, render, voiceover, watch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "examples" / "plans"
needs_engine = pytest.mark.skipif(
    not (ROOT / "engine" / "node_modules").is_dir(),
    reason="engine/node_modules is missing (run npm install in engine/)",
)
WAIT = 300  # a job worker is a fresh Python process, and it bundles the engine

# scenario 1: a synthetic reference of five solid colours, 1.2 s each, a beep at every cut
REFERENCE_COLOURS = ("red", "cyan", "blue", "yellow", "black")
SEGMENT_S = 1.2
REFERENCE_NARRATION = "the hook lands in one second no warm up part two tomorrow"

# scenario 3: the edge-tts stand-in. Word k starts at FIRST + k * STEP and lasts LENGTH seconds.
EDGE_FIRST_WORD_S = 0.2
EDGE_WORD_STEP_S = 0.45
EDGE_WORD_LENGTH_S = 0.4
EDGE_TICKS = 10_000_000  # WordBoundary offset and duration are in 100 ns units
NARRATION = "one json plan is all it takes describe the video and omniframe makes it follow for more"

# scenario 2: a 20 s recording. The sample plan keeps 1.2-7.8 s and 10.4-16.0 s of it. The words
# are in seconds of the recording: fillers before the first range, a stumble between the two
# ranges (8.0-10.1 s) and a goodbye after the second.
TALK_S = 20.0
KEPT_RANGES = ((1.2, 7.8), (10.4, 16.0))
KEPT_S = sum(end - start for start, end in KEPT_RANGES)  # 12.2 s
TALK_WORDS = [
    ("um", 0.20, 0.50), ("so", 0.60, 0.90),
    ("my", 1.40, 1.70), ("heart", 1.80, 2.20), ("rate", 2.30, 2.70), ("is", 2.80, 3.00),
    ("the", 3.10, 3.30), ("first", 3.40, 3.80), ("thing", 3.90, 4.30), ("i", 4.60, 4.80),
    ("check", 4.90, 5.30), ("every", 5.40, 5.80), ("morning", 5.90, 6.50), ("okay", 6.60, 7.20),
    ("so", 8.00, 8.30), ("so", 8.40, 8.70), ("um", 9.00, 9.40), ("uh", 9.80, 10.10),
    ("tip", 10.60, 10.90), ("two", 11.00, 11.40), ("is", 11.50, 11.70), ("sleep", 11.80, 12.30),
    ("your", 12.60, 12.90), ("heart", 13.00, 13.40), ("needs", 13.50, 13.90), ("it", 14.00, 14.20),
    ("more", 14.30, 14.80), ("than", 14.90, 15.20), ("coffee", 15.30, 15.90),
    ("thanks", 16.50, 16.90), ("for", 17.00, 17.20), ("watching", 17.30, 18.00),
]


# ------------------------------------------------------------------ fixtures and helpers

@pytest.fixture(autouse=True)
def scenario_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Own output dir per test. Job workers read it from OMNIFRAME_OUTPUT_DIR, set by `jobs`."""
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out")
    for module in (jobs, project, render, watch, qa, voiceover):
        monkeypatch.setattr(module, "CONFIG", cfg)
    yield
    for proc in list(jobs._PROCS.values()):
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    jobs._PROCS.clear()


def _quiet(*args: object, **kwargs: object) -> None:
    """Progress callback for calls that do not show progress."""


def _ffmpeg(*args: str) -> None:
    subprocess.run([CONFIG.ffmpeg, "-hide_banner", "-y", "-v", "error", *args], check=True, capture_output=True)


def _tone(path: Path, hz: int, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}", "-ar", "48000", str(path))
    return path


def _reference(path: Path) -> Path:
    """A 6 s vertical clip: the colours of REFERENCE_COLOURS, and a 880 Hz beep at the start of each."""
    n = len(REFERENCE_COLOURS)
    args: list[str] = []
    for colour in REFERENCE_COLOURS:
        args += ["-f", "lavfi", "-i", f"color=c={colour}:s=180x320:r=30:d={SEGMENT_S}"]
    beep = f"if(lt(mod(t\\,{SEGMENT_S})\\,0.15)\\,0.8*sin(2*PI*880*t)\\,0)"
    args += ["-f", "lavfi", "-i", f"aevalsrc={beep}:d={SEGMENT_S * n}:s=44100"]
    graph = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]"
    _ffmpeg(
        *args, "-filter_complex", graph, "-map", "[v]", "-map", f"{n}:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path),
    )
    return path


def _schedule(text: str) -> list[tuple[str, float, float]]:
    """(word, start, end) in seconds for each word of `text`, one word every EDGE_WORD_STEP_S."""
    rows = []
    for k, word in enumerate(text.split()):
        start = EDGE_FIRST_WORD_S + k * EDGE_WORD_STEP_S
        rows.append((word, round(start, 3), round(start + EDGE_WORD_LENGTH_S, 3)))
    return rows


def _edge_module(voice_wav: bytes) -> types.ModuleType:
    """Stands in for `edge_tts`: `Communicate(text, voice, boundary=...)` streams the audio, then WordBoundary events."""

    class Communicate:
        def __init__(self, text: str, voice: str = "", **options) -> None:
            self.text = text

        async def stream(self):
            yield {"type": "audio", "data": voice_wav}
            for word, start, end in _schedule(self.text):
                yield {
                    "type": "WordBoundary",
                    "offset": round(start * EDGE_TICKS),
                    "duration": round((end - start) * EDGE_TICKS),
                    "text": word,
                }

    module = types.ModuleType("edge_tts")
    module.Communicate = Communicate
    return module


def _talking_clip(path: Path) -> Path:
    """A 16:9 recording of TALK_S seconds: a moving test picture and a steady tone for the voice."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={TALK_S}",
        "-f", "lavfi", "-i", f"sine=frequency=180:duration={TALK_S}", "-ar", "48000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    )
    return path


class _FakeWhisper:
    """Stands in for faster-whisper: says TALK_WORDS (with the fillers kept) as one segment."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def detect_language(self, audio, **kw):
        return "en", 0.99, {}

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        words = [SimpleNamespace(word=f" {w}", start=s, end=e) for w, s, e in TALK_WORDS]
        text = " " + " ".join(w for w, _s, _e in TALK_WORDS)
        seg = SimpleNamespace(start=TALK_WORDS[0][1], end=TALK_WORDS[-1][2], text=text, words=words)
        return iter([seg]), SimpleNamespace(language=kw.get("language") or "en")


def _summary_and_images(out) -> tuple[dict, list[Image]]:
    """A tool result `[summary_json, Image, ...]` as (summary, images). Anything else fails the test."""
    assert isinstance(out, list) and isinstance(out[0], str), out
    return json.loads(out[0]), [item for item in out[1:] if isinstance(item, Image)]


def _tiktok_plan() -> dict:
    """A 9:16 plan styled with tokens: colours, a bundled font, safe area, gradient, grain."""
    return {
        "version": 2,
        "format": "9:16",
        "fps": 30,
        "style": {
            "colors": {"bg": "#14110F", "text": "#FFF4E0", "muted": "#A89B88", "accent": "#FF8A1F"},
            "fonts": {
                "display": {"family": "Inter Display", "src": "fonts/InterDisplay-Black.otf"},
                "body": {"family": "Inter", "weight": 600},
            },
            "text_scale": 1.1,
            "safe_area": {"top": 0.1, "bottom": 0.22, "left": 0.07, "right": 0.14},
            "background": {"type": "gradient", "stops": ["#14110F", "#2A1608"], "angle": 160},
            "grain": 0.04,
        },
        "scenes": [
            {"kind": "words", "at": 0.0, "text": "the hook lands in one second"},
            {"kind": "big", "at": 2.0, "text": "NO WARM-UP"},
            {
                "kind": "chip", "at": 3.6,
                "items": [{"text": "Retention", "value": "92%"}, {"text": "Watch time", "value": "18s"}],
            },
            {"kind": "cta", "at": 4.8, "text": "part two tomorrow", "handle": "@omniframe.studio"},
        ],
        "captions": {
            "words": [{"w": w, "s": s, "e": e} for w, s, e in _schedule(REFERENCE_NARRATION)],
            "accent_words": ["hook"],
        },
        "audio": {
            "voice": {"src": "audio/voice.wav"},
            "music": {"src": "audio/music.wav", "volume": 0.12, "duck": 0.35, "fade_out": 1.0},
        },
    }


def _assert_tiktok_folder(root: Path, name: str, caption: str) -> None:
    """After export: the video, one cover and post.md in final/, and no work folder left behind."""
    final_dir = root / "final"
    assert sorted(p.name for p in final_dir.iterdir()) == sorted(
        [f"{name}_9x16.mp4", f"{name}_cover_9x16.jpg", "post.md"]
    )
    post = (final_dir / "post.md").read_text(encoding="utf-8")
    assert "## TikTok" in post and caption in post
    assert not (root / ".work").exists()


# ------------------------------------------------------------------ scenario 1: reference

@needs_engine
def test_reference_to_tiktok(tmp_path: Path) -> None:
    """Watch the reference, compare stills with it, render the final, pass QA, export for TikTok."""
    ref = _reference(tmp_path / "reference.mp4")
    name = "reference-tiktok"
    root = project.project_dir("tiktok-ref")

    # watch: the cuts and the beeps of the reference, and its contact sheets as images
    summary, sheets = _summary_and_images(
        watch.watch_video(str(ref), "tiktok-ref", transcript=False, wait_s=WAIT)
    )
    assert summary["has_audio"] is True
    shots = summary["shots"]
    assert len(shots) == len(REFERENCE_COLOURS), shots
    for k, (start, _end) in enumerate(shots):
        assert abs(start - k * SEGMENT_S) <= 1 / 30 + 1e-6, shots  # within one frame
    beeps = [event["t"] for event in summary["sound_events"]]
    assert len(beeps) == len(REFERENCE_COLOURS), beeps
    assert all(abs(t - k * SEGMENT_S) <= 0.05 for k, t in enumerate(beeps)), beeps  # within 50 ms
    assert sheets and all(isinstance(sheet, Image) for sheet in sheets)

    # the plan, next to the reference, at three moments
    _tone(root / "audio" / "voice.wav", 330, 6.0)
    _tone(root / "audio" / "music.wav", 220, 8.0)
    plan = _tiktok_plan()
    times = [0.5, 2.0, 4.0]
    stills, pairs = _summary_and_images(render.render_video(
        plan, "tiktok-ref", mode="stills", times=times,
        compare={"video": str(ref), "times": times}, wait_s=WAIT,
    ))
    cells = stills["images"][0]["cells"]  # one contact sheet, one cell per time
    assert [c["t"] for c in cells] == times
    assert [c["reference_t"] for c in cells] == times
    assert len(pairs) == 1
    for cell in cells:
        with PILImage.open(cell["path"]) as picture:  # reference and render side by side, not stacked
            assert picture.format == "JPEG" and picture.width > picture.height * 0.9

    # the final video: 1080x1920, loudness normalised, and it passes QA
    final = render.render_video(plan, "tiktok-ref", mode="final", name=name, wait_s=WAIT)
    assert isinstance(final, dict) and "output" in final, final
    video = Path(final["output"])
    assert video == root / "renders" / f"{name}-final-9x16.mp4"
    assert (final["output_width"], final["output_height"]) == (1080, 1920)
    assert final["has_audio"] is True
    assert abs(final["output_duration"] - final["duration"]) < 0.2
    assert not final.get("warnings"), final.get("warnings")
    report = qa.verify_video(video, format="9:16", target="tiktok")
    assert report["passed"], report["hard_failures"]

    # export: the video, a cover at 2 s, and the TikTok text
    caption = "A hook in one second, no warm-up"
    texts = {"tiktok": {"caption": caption, "hashtags": ["omniframe", "#shorts"]}}
    exported, covers = _summary_and_images(export.export_package(
        "tiktok-ref", {"9:16": str(video)}, texts, cover_times={"9:16": 2.0}, name=name, wait_s=WAIT,
    ))
    assert exported["exported"] is True and exported["removed_work"] is True
    assert len(covers) == 1
    _assert_tiktok_folder(root, name, caption)
    assert "#omniframe #shorts" in (root / "final" / "post.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ scenario 2: footage

@needs_engine
def test_footage_edit_with_remapped_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Watch the recording, cut it with the sample plan, caption the kept words, render, pass QA."""
    root = project.project_dir("footage-talk")
    # the sample plan names these files by relative path; they are looked up in the project folder
    talk = _talking_clip(root / "examples" / "media" / "talk_sample.mp4")
    _tone(root / "audio" / "music.mp3", 196, 16.0)

    # watch: the recording's words come back verbatim, fillers and repeats included
    fake = _FakeWhisper()
    monkeypatch.setattr(watch, "whisper_available", lambda: True)
    monkeypatch.setattr(watch, "_whisper_model", lambda name: fake)
    seen = watch.run_job({"path": str(talk), "project": "footage-talk", "transcript": True}, _quiet)
    assert seen["duration"] == pytest.approx(TALK_S, abs=0.1) and seen["has_audio"] is True
    assert seen["language"] == "en" and fake.calls[0]["initial_prompt"] == watch.ENGLISH_VERBATIM_PROMPT
    assert seen["word_count"] == len(TALK_WORDS)  # all 32, nothing tidied away; the list is in words_path
    words_file = Path(seen["words_path"])
    assert [(w["w"], w["s"], w["e"]) for w in json.loads(words_file.read_text(encoding="utf-8"))] == TALK_WORDS
    # the plan names the transcript as examples/media/talk_sample.words.json: the same words
    sample_words = root / "examples" / "media" / "talk_sample.words.json"
    sample_words.write_text(words_file.read_text(encoding="utf-8"), encoding="utf-8")

    # the plan: the sample, unchanged. Its cut list is the clips; its length is the kept ranges
    plan = json.loads((SAMPLES / "footage_16x9.json").read_text(encoding="utf-8"))
    assert [(c["in"], c["out"]) for c in plan["clips"]] == list(KEPT_RANGES)
    assert plan["clips"][1]["at"] == pytest.approx(plan["clips"][0]["at"] + KEPT_RANGES[0][1] - KEPT_RANGES[0][0])
    assert plan["duration"] == pytest.approx(KEPT_S)

    # captions: only the words inside the kept ranges, on the new timeline
    payload, errors = render.prepare_render(
        plan, root, mode="final", times=None, compare=None, format=None, name="footage",
    )
    assert errors == [] and payload is not None
    assert payload["plan"]["duration"] == pytest.approx(KEPT_S)
    spoken = payload["caption_words"]
    kept = [w for w, s, e in TALK_WORDS if any(a <= (s + e) / 2 <= b for a, b in KEPT_RANGES)]
    assert [w["w"] for w in spoken] == kept
    assert "um" not in kept and "uh" not in kept and "thanks" not in kept  # fillers and the goodbye are cut
    first_in_second = next(w for w in spoken if w["w"] == "tip")
    assert (first_in_second["s"], first_in_second["e"]) == pytest.approx((6.8, 7.1), abs=0.02)  # 10.6 - 10.4 + 6.6
    assert spoken[0]["s"] == pytest.approx(0.2, abs=0.02)  # "my" at 1.4 s, the first range starts at 1.2 s
    assert all(0 <= w["s"] < w["e"] <= KEPT_S + 0.05 for w in spoken)

    # stills just before and after the cut, and at the zoom
    times = [0.5, 6.5, 6.8, 9.0]
    stills, shown = _summary_and_images(render.render_video(
        plan, "footage-talk", mode="stills", times=times, wait_s=WAIT,
    ))
    assert [c["t"] for c in stills["images"][0]["cells"]] == times and len(shown) == 1  # one contact sheet

    # the final video: 1920x1080, as long as the kept ranges (+-1 frame), with sound, and it passes QA
    final = render.render_video(plan, "footage-talk", mode="final", name="footage", wait_s=WAIT)
    assert isinstance(final, dict) and "output" in final, final
    video = Path(final["output"])
    assert video == root / "renders" / "footage-final-16x9.mp4"
    assert (final["output_width"], final["output_height"]) == (1920, 1080)
    assert final["has_audio"] is True
    assert final["output_duration"] == pytest.approx(KEPT_S, abs=1 / 30 + 0.01)
    assert not final.get("warnings"), final.get("warnings")
    report = qa.verify_video(video, format="16:9", target="youtube")
    assert report["passed"], report["hard_failures"]


# ------------------------------------------------------------------ scenario 3: idea

@needs_engine
def test_idea_with_graphics_and_an_edge_voice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The sample graphics plan with an edge-style voice: voice -> final -> export."""
    name = "idea"
    root = project.project_dir("idea-graphics")

    # voice: the real edge voiceover job, with edge_tts replaced by the stand-in
    words_spoken = NARRATION.split()
    voice_wav = _tone(tmp_path / "edge-stand-in.wav", 220, 8.2).read_bytes()
    monkeypatch.setitem(sys.modules, "edge_tts", _edge_module(voice_wav))
    voice = voiceover.run_job({
        "text": NARRATION, "project": "idea-graphics", "provider": "edge",
        "voice": "en-US-GuyNeural", "name": "voice", "settings": {},
    }, _quiet)
    assert voice["provider"] == "edge" and voice["words_source"] == "provider"
    assert voice["words"] == len(words_spoken)
    words = json.loads(Path(voice["words_path"]).read_text(encoding="utf-8"))
    assert [w["w"] for w in words] == words_spoken
    assert words[-1]["e"] <= voice["duration"]

    # the sample plan, unchanged; its music bed is a stand-in tone
    _tone(root / "audio" / "music.mp3", 196, 12.0)
    plan = json.loads((SAMPLES / "graphics_9x16.json").read_text(encoding="utf-8"))
    final = render.render_video(plan, "idea-graphics", mode="final", name=name, wait_s=WAIT)
    assert isinstance(final, dict) and "output" in final, final
    video = Path(final["output"])
    assert video == root / "renders" / f"{name}-final-9x16.mp4"
    assert (final["output_width"], final["output_height"]) == (1080, 1920)
    assert final["has_audio"] is True
    assert final["output_duration"] >= voice["duration"] - 0.1  # the whole narration is in the video
    assert not final.get("warnings"), final.get("warnings")

    # export: QA runs again inside the export and refuses on a hard failure
    caption = "One JSON plan is all it takes"
    texts = {"tiktok": {"caption": caption, "hashtags": ["omniframe"]}}
    exported, covers = _summary_and_images(export.export_package(
        "idea-graphics", {"9:16": str(video)}, texts, cover_times={"9:16": 1.0}, name=name, wait_s=WAIT,
    ))
    assert exported["exported"] is True and exported["removed_work"] is True
    assert len(covers) == 1
    _assert_tiktok_folder(root, name, caption)

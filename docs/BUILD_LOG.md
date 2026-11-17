# ARGUS v2 — build log (Kiroween 2026)

A factual record of how ARGUS v2 was built in Kiro. It is the source for the Medium
article and for the submission's "how Kiro was used" answer. Facts only, no marketing.

## How the work is split

- **Planning:** Claude Opus 5.5 in Kiro wrote the spec (`.kiro/specs/argus-v2`:
  requirements, design, tasks), steering (`.kiro/steering`: product, tech, engine), the
  studio guide for the model, and two hooks (pytest after every spec task, engine
  typecheck on save) in one planning session.
- **Why v2:** v1 grew feature by feature into creative "gates" (30% story-overlap and
  30% digit-density rules, slop-word lists, a 150-line rule book), a renderer limited to
  dark/light vertical frames, and tools that returned file paths the model could not see.
  Output was generic "neuroslop". v2 makes the model the director and ARGUS its eyes,
  ears and hands.
- **Coding:** Claude Sonnet 5.5 (high effort) for core tasks; Claude Haiku 5.5 (max
  effort) planned for well-specified, test-covered tasks (QA, export, scripts, CI, docs
  drafts). Opus only plans and audits from diffs and reports, to save credits.

## Credits

| Date | Tasks | Model / effort | Credits used / total |
|---|---|---|---|
| (author fills) | 1–8, 9 started | Sonnet 5.5 high | 330 / 4000 |

## Entry template

```
## Task N — <title> (<date>, <model> <effort>)
- Built: <what changed, 1–2 lines>
- Bugs & fixes: <symptom> → <cause> → <fix>   (or "none")
- Kiro: <which Kiro feature helped, concretely: spec task/steering rule/hook caught X/MCP/autopilot>   (or "none")
- Verified: <command or manual check> → <result>
- Credits: <author fills>
```

## Entries

## Task 1 — Setup

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 2 — Remove creative gates

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 3 — Studio guide and preferences

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 4 — Images to the model + jobs

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 5 — watch_video and get_frames (2026-11-16, Sonnet 5.5)
- Built: `tools/watch.py` (content-hash cache by stage, shot detection, frame budget, 6-tile contact sheets, onset sound events, faster-whisper transcript when installed, 2 sheets per page) run as a `watch` job; `get_frames` with `crop` and an 8-time cap; both registered in `server.py`; `analyze_reference` and `tools/reference.py` removed. Small changes elsewhere: `ffmpeg.decode_audio` and `run_ffmpeg_stderr`, `beats._onset_envelope` on a running sum, `image_max_side` in `jobs`.
- Bugs & fixes: pagination test found 13 shots instead of 14 → a magenta→red cut scores below the 0.30 `scene` threshold → test video uses neighbours far apart in luma. On the real 7:30 animation the detector found only 3 shots → soft transitions stay under 0.30 → not fixed, listed in `task5.md`. Terminal output came back empty or garbled → read the output from log files. I skipped this log entry when the task was done → found it when asked about tasks 11 and 12.
- Kiro: spec task text and design §6 gave the pipeline; steering `tech.md` (tool shape, `run_or_detach`, offline tests); the MCP reload let me call both tools from Kiro chat and check that the model sees the images; no hook result noted.
- Verified: pytest `tests/test_watch.py` 24 passed, 1 skipped (real faster-whisper run); full suite then 120 passed, 1 skipped; real MCP stdio session returns `image/jpeg` content; from Kiro, `watch_video` on a 7:30 vertical file and `get_frames` at 5 times returned images the model read. Not verified: transcription on real faster-whisper (not installed), `detect_language` call against its docs.
- Credits: <author fills>
- Details: `.kiro/specs/argus-v2/task5.md`

## Task 6 — Voice v2

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 7 — Plan model v2

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 8 — Engine: formats and style tokens

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 9 — Engine: captions and audio (2026-11-16, Sonnet 5.5)
- Built: `captions.tsx` (word and phrase modes, accent words, upper/center/lower inside the safe area, plate), `audio.tsx` (voice, music with ducking and 0.25 s ramps, fades, `audio.sfx`); `sfx.ts` no longer adds automatic effects.
- Bugs & fixes: none in the engine. Two of my own check assertions were wrong (float equality on a ramp value; a phrase-length case that fits the character budget), and a light-theme still had a scene under the caption → fixed the checks and the test plan.
- Kiro: steering `engine.md` (layer order, "no automatic sound effects", no hardcoded sizes) set the design of the two components; `get_diagnostics` gave quick type errors while editing.
- Verified: `tsc --noEmit` exit 0; `node test-baseline/check_audio_captions.mjs` (ducking, fades, phrase grouping, accent matching, SFX list) passed; 34 stills rendered (both modes, 9:16 and 16:9, upper/center/lower, plate, light theme), 10 of them looked at by eye (the rest are unchecked); pytest 189 passed, 1 skipped.
- Credits: <author fills>

## Task 10 — render_video: stills, preview, final (2026-11-17, Sonnet 5.5)
- Built: `engine/scripts/render.mjs` (bundle once, stills or one video, progress as protocol lines), `tools/render.py` (validation with `path: message` errors, caption words load/remap, per-job public dir with hardlinks, `render` job, side-by-side stills, two-pass loudnorm + faststart + tag for final, `plan.json`, cleanup), `render_video` in `server.py`; `_find_browser` and the SFX synthesis moved from `kinetic.py`.
- Bugs & fixes: node failed with `Unexpected token` on a hand-written spec → PowerShell `Set-Content -Encoding utf8` adds a BOM → `render.mjs` strips a BOM before `JSON.parse`. Background test runs from the Kiro shell looked dead (empty output file, process "exited") → the output only reached the file when pytest finished → ran them detached and polled the file.
- Kiro: spec task text and design §9 gave the exact contract (modes, outputs, post-processing); steering `tech.md` rules (tools return `engine` + `tool_result` images, long work through `run_or_detach`) fixed the shape of the tool; none beyond that.
- Verified: pytest `tests/test_render.py` 22 passed (17 offline, 5 engine e2e: stills 9:16 and 16:9, stills with compare, 3-second final through `qa_verify_video`, half-size preview); `render_video` on `examples/plans/reference_style_9x16.json` with `compare` against a generated mp4: 5 side-by-side images, 2 viewed by eye.
- Credits: 62.41 (61.58 for the task, 0.83 for the follow-up message with the Russian summary; per the author)

## Task 11 — Technical QA v2 (2026-11-17, Haiku 5.5)
- Built: `tools/qa.py` to design §11. Hard: resolution for the format, fps, scan, audio present, loudness -14 ±1.5 LU, true peak ≤ -1 dBTP, video/audio length, black ≥ 1.0 s mid-video. Warnings: shorter black, black at the edges, frozen picture, mid-video silence, platform duration. Images: evenly spread frames plus black and freeze frames (cap 8). Runs as a `qa` job; `qa_verify_video(video_path, format, frames, target)` in `server.py`.
- Bugs & fixes: a clip with a 3 s silence measured -11.2 LUFS after one-pass `loudnorm` → that filter does not reach the target on such a clip → test clips go through `finalize_video`, the two-pass step final renders use.
- Kiro: none beyond steering `tech.md` (long work through `run_or_detach`, images through `tool_result`).
- Verified: pytest 220 passed, 1 skipped (QA section: 11 tests, incl. 1.5 s black hard, 0.7 s black warning, 3 s silence warning, hot peak hard, valid master passes); 90 s 1080×1920 clip checked in 13 s.
- Credits: <author fills>

## Task 12 — export_package (2026-11-17, Haiku 5.5)
- Built: `tools/export.py` to design §12: QA on each video (a hard failure refuses the export), stream copy with faststart into `final/`, covers 1080x1920 and 1280x720 (JPEG under 2 MB), `post.md` with each platform's texts, length limits reported per field, `.work/` removed. Job kind `export`; `export_package` in `server.py`.
- Bugs & fixes: none in the code. Design conflict: `prepare_image` writes its `.view.jpg` copy next to the source, so covers in `final/` would leave view files there → the model's views go to `cache/export/`.
- Kiro: spec task text and design §12 gave the contract; steering `tech.md` (long work through `run_or_detach`, pictures through `tool_result`) fixed the shape.
- Verified: pytest 231 passed, 1 skipped (new `tests/test_export.py`, 11 tests); real export of two synthetic 6 s clips: `final/` holds 2 mp4, 2 covers and `post.md`, `.work/` removed, the 9:16 cover is a non-black frame.
- Credits: 19± (per the author)


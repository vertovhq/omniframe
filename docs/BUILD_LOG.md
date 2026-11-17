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

## Task 13 (addition) — voice_options: compact answer (2026-11-17, Sonnet 5.5)
- Built: `voice_options` in `tools/voiceover.py` and its wrapper in `server.py`. `query` is split into words (max 4); a voice matches when any word occurs, in any case, in its name, description, accent, age, gender, use case or language. Each voice is `{id, name, gender, age, accent, language, description}`, empty fields left out, description cut at 80 characters. Library voices with `free_users_allowed=false` go to `library_voices_paid_plan_only` with a note. The whole answer is held to 6000 characters (JSON, indent 2): the longest lists lose their last voices and `notes` says so. New `details=False`: `elevenlabs_models` and `delivery` come only with `details=True`, and `/v1/models` is not even requested without it.
- Bugs & fixes: my first version lifted the size cap when `details=True`; measured 35 842 characters for 150 voices → the cap now holds for every answer, and `details` takes its ~1400 characters out of the voice lists. The Voice Library search takes one text, so with several words it runs once per word and merges the answers (the voices matching most words first). A query word is matched as part of a word, so a short word such as "at" also hits "Vindemiatrix".
- Kiro: none beyond steering `tech.md` (tests offline, mocked HTTP); the field `free_users_allowed` comes from the ElevenLabs API reference (URL in `voiceover.py`).
- Verified: `tests/test_voice_options.py` and `tests/test_voiceover.py` 51 passed (voice_options: 26 tests, was 15); size checks on 100 own and 50 library voices: 5 890 characters without `details`, ≤ 6 000 with it; full suite 247 passed, 0 skipped (the run before: 234 passed, 1 skipped; 11 of the 12 new tests are in `test_voice_options.py`, I did not trace the twelfth). Not verified: a real ElevenLabs call, so the answer shape of `/v1/shared-voices` and the effect of the per-word search are known from the API reference and mocks only. The skip of the earlier runs is gone because faster-whisper is now installed in `.venv`, so `test_real_transcript_runs_when_faster_whisper_is_installed` ran for the first time and passed.
- Fixed (13.1, frames cache): `frames.<N>.json` from the old `select_frames` returned 3 frames for a 24-frame request, because those files had no version → `FRAMES_VERSION = 2` is checked on read (absent or older → rebuilt); shot and transcript caches unchanged. `tests/test_watch.py` 27 passed; the full-suite summary was not seen in this session.
- Credits: <author fills>


## Task 16 — Custom components (2026-11-17, Sonnet 5.5)
- Built: `engine/src/custom/registry.ts` (committed empty map), `custom/style.ts` (re-export so `../style` works from `custom/job/`), `custom/README.md` (contract), `kind: 'custom'` in `Main.tsx` (throws when the name is not in the registry). `tools/components.py`: source check of `<project>/components/*.tsx` (allowed imports, no network, warnings for `Math.random`/`Date.now`), `EngineHold` (lock `engine/.render.lock`, copy to `custom/job/`, generated registry, `tsc` with a temp tsconfig, restore in `release`). `render.mjs` emits `bundled`; the hold is released then, so the lock lasts only while bundling. Compile errors return as `{"valid": false, "errors": ["components/X.tsx(4,9): error TS...", ...]}`.
- Bugs & fixes: none in the engine or Python code. One of my own test assertions was wrong (it expected `'../style'` to be absent from the error text, but the message lists it as an allowed import) → the assertion now checks `import '../style'`. A Pillow `getdata` deprecation warning in the stills test → replaced with numpy. Terminal commands in the Kiro shell returned empty output and the full-suite run took 6 min → wrote output to files and polled them. Design decision: all renders take the lock while bundling, not only those with components, because a plain render bundling during another render's install would pick up that render's components. A registry left by a killed render is repaired from the lock's stale-owner check and the `./job/` marker.
- Kiro: steering `engine.md` (committed registry stays an empty map, the tsc command) set the restore rule; the task's Tests line gave the two test cases.
- Verified: `tsc --noEmit -p engine` exit 0; `tests/test_components.py` 12 passed (valid sample renders in stills, broken one returns TS2322 and TS2304 errors, registry bytes unchanged, no `custom/job/`, no lock afterwards); I looked at the sample still (label and accent number centered in the safe area); full suite 260 passed. Old test `test_warnings_for_custom_scenes_and_unducked_music` became `test_warning_for_unducked_music`, since custom scenes are now drawn.
- Credits: <author fills>

## Task 17 — User scripts (2026-11-17, Haiku 5.5)
- Built: `tools/scripts_runner.py` (listing reads docstrings with `ast`; a run goes through the `scripts_runner` job as `python -P <script> <args.json>`, parses the last stdout line as JSON, returns listed `images` as pictures), `scripts/frame_stats.py`, `scripts/README.md`, `run_script` in `server.py`. `-P` is not in design §13: without it a user `json.py` shadows the standard library.
- Bugs & fixes: during the 5-minute full-suite run, Kiro shell commands returned empty output and their effects appeared only later → cause not established → wrote results to files in `%TEMP%` and polled them. Removing two scratch folders in `%TEMP%` from the same shell did not take effect → left in place, outside the repo.
- Kiro: steering `tech.md` ("anything over ~20 s goes through `run_or_detach`") decided the job wrapper; the task text and design §13 gave the file names, the contract and the test list.
- Verified: `pytest tests/test_scripts_runner.py` → 13 passed; full `pytest` → 273 passed (was 260); real config (repo `scripts/`, `OMNIFRAME_OUTPUT_DIR` in a temp folder) → listing shows both scripts with summary and args, `frame_stats` on a white image → brightness 1.0, user `json.py` still imports the standard library, bad name / unknown name / `timeout_s=5000` refused. Not verified: `run_script` from Kiro chat (needs the `argus` server reloaded).
- Credits: <author fills>

## Task 14 — Clips track and media prep (2026-11-17, Sonnet 5.5)

- Built: `engine/src/clips.tsx` (video/image track: `Sequence` from `at`, `trimBefore` from `in`, `fit`, volume/muted, zoom keyframes around a focus point), drawn in `Main.tsx` above the background and below the scenes; `tools/media_prep.py` (proxy in `<project>/cache/proxies/` for VFR, non-H.264 or `clean_audio`, reused by a hash of path, size, mtime, fps); `render.py` uses the proxies, checks clip ranges against the file and no longer warns that clips are not drawn.
- Bugs & fixes: zoom test measured 204 px instead of 384 → `images[].path` is the downscaled `.view.jpg`, the full-size stills are in `stills` → tests read `stills`. One suite failure came from my own edit of a test after pytest had collected it → reran that file.
- Kiro: the sub-agent `spec-task-execution` was not registered ("not found in registry"), so the orchestrator could not dispatch the task and I did it directly after the author said so; steering `engine.md` (layer order, no hardcoded sizes) fixed where clips go.
- Verified: engine `tsc --noEmit` exit 0; `tests/test_clips.py` 16 passed (12 offline, 4 engine: in/out part and duration, open-ended clip, zoom at 3 times, focus point); zoom math checked in node; full suite 288 passed + 1 fixed test. Not verified: a real phone VFR file, long files, audio mix of clip + voice + music.
- Credits: <author fills>
- Details: `.kiro/specs/argus-v2/task14.md` (section 8: 15 questions for the auditor)

## Task 15 — Footage editing scenario (2026-11-17, Sonnet 5.5)

- Built: `watch_video` now returns `words` (`[word, start, end]`, up to 1200 words, else `words_note` + `words_path`) and `word_count`; English gets a verbatim prompt like Russian (other languages none). Guide section 7 rewritten to the real behaviour (cut list from words, `clips` back to back, `captions.words` with `remap: "clips"`, `duration`, zoom, `clean_audio`, muted b-roll clip, `duck`). `examples/plans/footage_16x9.json` got `duration: 12.2`. Scenario test (2) in `tests/test_scenarios.py`: 20 s synthetic recording, fake Whisper with fixture words, the sample plan unchanged, remapped caption words, stills, final, QA.
- Bugs & fixes: design says the video equals the kept ranges ±1 frame, but a plan without `duration` gets a 0.6 s hold after the last clip (12.8 s, not 12.2 s) → sample plan and guide set `duration` to the sum of the kept ranges.
- Kiro: none. The Kiro shell returned empty output again and commands ran minutes late → read results from files and from a sub-agent's run (cause not established).
- Verified: new scenario test passed alone (193 s); `test_watch`, `test_plan`, `test_studio_guide`, `test_offline_tools`, `test_scenarios` together: 89 passed in 577 s. Not verified: the real Whisper on English speech with the new prompt, and the manual edit of `examples/media/talk_sample.mp4` (the file does not exist yet).
- Audit status:
  - [x] Verify step 1: scenario test (2) green (193 s alone; 89 passed with the related test files).
  - [ ] Verify step 2: manual edit of `examples/media/talk_sample.mp4` from Kiro. Not done, the file does not exist yet.
  - Overall: **not fully OK** until the manual step is done and question 1 is answered.
- Questions for the audit:
  1. Real Whisper (`small`, int8) on English speech with `ENGLISH_VERBATIM_PROMPT`: does it keep "um/uh" and repeats? Only a fake Whisper was tested. If not, drop the prompt or change its text.
  2. The plan must set `duration`, otherwise a 0.6 s hold is added after the last clip. Keep this as a guide rule, or make `derive_duration` skip the tail when the last item is a clip?
  3. `watch.transcribe` also aligns voices from providers without timings (`voiceover._align_with_whisper`). English now gets the filler prompt there too. Can it add false "um" words to the captions of a clean voice? Not tested.
  4. Inline `words` are `[word, start, end]` triples (limit 1200 words), while `words.json` uses `{w, s, e}`. Is one format better for the model?
  5. Transcripts cached before this change (English, no prompt) stay in the cache: `CACHE_VERSION` was not bumped, to avoid re-running shot detection on long files. Acceptable?
  6. Guide §7 says a muted clip placed inside a talking clip works as b-roll (later clips are drawn above, the speaker's sound continues). This comes from reading `clips.tsx`; no test renders it.
  7. Cut boundaries were never judged by eye: the test video is synthetic (`testsrc2`), so "cut not mid-gesture" is untested.
  8. The scenario test takes about 3 min (engine bundle, 4 stills, a 12 s final in 1080p). The three scenarios together took part of the 577 s run; check the total against the CI limit of ~10 min (task 19).
- Errors during the work: none in the code. Environment: the Kiro shell returned empty output and ran commands minutes late. Scratch files `.chk10_task15.txt` / `.chk11_task15.txt` may appear in the repo root and can be deleted.
- Credits: <author fills>

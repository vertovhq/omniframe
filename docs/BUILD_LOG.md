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
| 2026-11-18 | 20 (video 1: retiming, sound, preview, final, QA, export) | Sonnet 5.5 | 91 credits, 1 h 20 min (per the author) |

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

## Task 1 — Setup (date and model not recorded; commit 0f3129f)
- Built: `src/argus/project.py` (`slugify`, `project_dir` with the folder layout), config fields `whisper_model`, `eleven_model`, `render_concurrency`, `scripts_dir` and the `.env` lookup order, `numpy` and `Pillow` dependencies with the `asr` extra, version `3.0.0.dev0`, `.kiro/settings/mcp.json`.
- Bugs & fixes: none recorded.
- Kiro: none recorded beyond the spec task list and steering `tech.md` that set the layout.
- Verified: no result recorded in `tasks.md` or this log. Tests in git: `tests/test_project.py`.
- Credits: <author fills>

## Task 2 — Remove creative gates (date and model not recorded; commit 0f3129f)
- Built: removed the `validate_beats` and `story_guide` tools, `detect_genre`, the slop-word list, the overlap helpers, `src/argus/STORY_GUIDE.md` and `tests/test_reference.py`; removed the borrowing-limit section from `STARTER.md` and the two montazh `SKILL.md` files; server instructions replaced with the text from design §2.
- Bugs & fixes: none recorded.
- Kiro: none recorded.
- Verified: no result recorded in `tasks.md` or this log.
- Credits: <author fills>

## Task 3 — Studio guide and preferences (date and model not recorded; commit 0f3129f)
- Built: `studio_guide()` returning the guide, capabilities (tools, providers from config and import checks) and the last 4,000 characters of the preferences file; `learn_and_record_memory` writing `# ARGUS — user preferences`; `src/argus/STUDIO_GUIDE.md`, copied from the spec and later edited by tasks 20.5b, 20.6 and 20.7a.
- Bugs & fixes: none recorded.
- Kiro: none recorded.
- Verified: `tests/test_studio_guide.py` exists in git; no run result recorded in `tasks.md` or this log.
- Credits: <author fills>

## Task 4 — Images to the model + jobs (date and model not recorded; commit 0f3129f)
- Built: `src/argus/media_out.py` (`prepare_image`, `tool_result` returning a summary plus image content), `src/argus/jobs.py` (`run_or_detach`, the worker `python -m argus.jobs <job_dir>`, status, cleanup of jobs older than 7 days), the `job_status` tool; tests `tests/test_jobs.py` and `tests/test_media_out.py`.
- Bugs & fixes: none recorded.
- Kiro: none recorded.
- Verified: no run result recorded in `tasks.md` or this log.
- Credits: <author fills>

## Task 5 — watch_video and get_frames (2026-11-16, Sonnet 5.5)
- Built: `tools/watch.py` (content-hash cache by stage, shot detection, frame budget, 6-tile contact sheets, onset sound events, faster-whisper transcript when installed, 2 sheets per page) run as a `watch` job; `get_frames` with `crop` and an 8-time cap; both registered in `server.py`; `analyze_reference` and `tools/reference.py` removed. Small changes elsewhere: `ffmpeg.decode_audio` and `run_ffmpeg_stderr`, `beats._onset_envelope` on a running sum, `image_max_side` in `jobs`.
- Bugs & fixes: pagination test found 13 shots instead of 14 → a magenta→red cut scores below the 0.30 `scene` threshold → test video uses neighbours far apart in luma. On the real 7:30 animation the detector found only 3 shots → soft transitions stay under 0.30 → not fixed, listed in `task5.md`. Terminal output came back empty or garbled → read the output from log files. I skipped this log entry when the task was done → found it when asked about tasks 11 and 12.
- Kiro: spec task text and design §6 gave the pipeline; steering `tech.md` (tool shape, `run_or_detach`, offline tests); the MCP reload let me call both tools from Kiro chat and check that the model sees the images; no hook result noted.
- Verified: pytest `tests/test_watch.py` 24 passed, 1 skipped (real faster-whisper run); full suite then 120 passed, 1 skipped; real MCP stdio session returns `image/jpeg` content; from Kiro, `watch_video` on a 7:30 vertical file and `get_frames` at 5 times returned images the model read. Not verified: transcription on real faster-whisper (not installed), `detect_language` call against its docs.
- Credits: <author fills>
- Details: `.kiro/specs/argus-v2/task5.md`

## Task 6 — Voice v2 (2026-11-16, model not recorded)
- Built: `tools/voiceover.py` with providers `elevenlabs`, `edge` and `gemini` behind a `VoiceProvider` protocol, `split_text` for long text, `words_from_alignment`, job kind `voiceover`; `voice_options` returning `provider_choice` and, with a key, the `delivery` vocabulary. Provider doc URLs are in code comments. Tests `tests/test_voiceover.py` (25) and `tests/test_voice_options.py` (15).
- Bugs & fixes: none recorded. The task was marked `[x]` by the owner before its live ElevenLabs check ran, so that check is still open in `tasks.md`.
- Kiro: none recorded.
- Verified: offline tests; full suite 158 passed, 1 skipped (task notes). Real ElevenLabs and edge-tts calls: not run.
- Credits: <author fills>

## Task 7 — Plan model v2 (2026-11-16, model not recorded)
- Built: `src/argus/plan.py` (pydantic models, `dark` and `light` presets, format sizes, safe areas, `validate_plan` returning every error as `path: message`, `derive_duration`); `src/argus/captions.py` (word helpers moved from `tools/subtitles.py`, `remap_words_to_clips`); `engine/src/types.ts` (plan types); four sample plans in `examples/plans/`. Tests `tests/test_plan.py` and `tests/test_captions.py`.
- Bugs & fixes: none recorded.
- Kiro: none recorded.
- Verified: full suite 189 passed, 1 skipped; engine `tsc --noEmit` exit 0 (task notes).
- Credits: <author fills>

## Task 8 — Engine: formats and style tokens (2026-11-16, model not recorded)
- Built: `engine/src/style.ts` replacing `theme.ts` (`resolveStyle`, `StyleContext` and `useStyle()`, `useLayout()`, `fontFor`, font loading); `Root.tsx` takes width and height from the format; text sizes relative to the short side; scenes with `until` and `overlay`.
- Bugs & fixes: none recorded. The 9:16 output differs from v1 by centring in the safe area (card about 60 px higher, HUD plate about 16 px higher); listed in the task notes.
- Kiro: none recorded.
- Verified: `tsc --noEmit` exit 0; pytest 189 passed, 1 skipped; 9:16 dark stills compared side by side with the v1 baseline (`engine/test-baseline/`, git-ignored); 16:9 and stress plans checked by eye for the safe area.
- Credits: <author fills>

## Task 9 — Engine: captions and audio (2026-11-16, Sonnet 5.5)
- Built: `captions.tsx` (word and phrase modes, accent words, upper/center/lower inside the safe area, plate), `audio.tsx` (voice, music with ducking and 0.25 s ramps, fades, `audio.sfx`); `sfx.ts` no longer adds automatic effects.
- Bugs & fixes: none in the engine. Two of my own check assertions were wrong (float equality on a ramp value; a phrase-length case that fits the character budget), and a light-theme still had a scene under the caption → fixed the checks and the test plan.
- Kiro: steering `engine.md` (layer order, "no automatic sound effects", no hardcoded sizes) set the design of the two components; `get_diagnostics` gave quick type errors while editing.
- Verified: `tsc --noEmit` exit 0; `node test-baseline/check_audio_captions.mjs` (ducking, fades, phrase grouping, accent matching, SFX list) passed; 34 stills rendered (both modes, 9:16 and 16:9, upper/center/lower, plate, light theme), 10 of them looked at by eye (the rest are unchecked); pytest 189 passed, 1 skipped.
- Credits: <author fills>

## Task 10 — render_video: stills, preview, final (2026-11-17, Sonnet 5.5)
- Built: `engine/scripts/render.mjs` (bundle once, stills or one video, progress as protocol lines), `tools/render.py` (validation with `path: message` errors, caption words load/remap, per-job public dir with hardlinks, `render` job, side-by-side stills, two-pass loudnorm + faststart + tag for final, `plan.json`, cleanup), `render_video` in `server.py`; `_find_browser` and the SFX synthesis moved from the v1 kinetic module (removed in task 18).
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

## Task 18 — Remove superseded v1 tools (2026-11-17, Sonnet 5.5)
- Built: deleted the four v1 tool modules (kinetic, assemble, subtitles, timeline), the bundled ASS font folder and the four MCP wrappers; the helpers they shared were already in `render.py` and `captions.py`, so nothing was moved. `doctor.py`: the ASS-subtitle probe removed; numpy, Pillow and the engine packages (`remotion`, `@remotion/renderer`, `@remotion/bundler`) are critical; faster-whisper and edge-tts are warnings only. `server.startup_banner()` counts the registered tools. README, README.ru, STARTER, TUTORIAL and `pyproject.toml` no longer name the removed tools.
- Bugs & fixes: one full-suite run failed `test_clip_without_out_plays_to_the_end_of_the_file` (render job state `error`) → I had two pytest runs going at once on the same engine folder; the test passed alone and in the next full run → no code change. Kiro shell returned only echoed input and ran commands minutes late again → started pytest and tsc with `Start-Process` into files and polled them.
- Kiro: the user's instruction to commit before deleting (checkpoint commit `aada601`, so the removal can be rolled back); none otherwise.
- Verified: engine `tsc --noEmit` exit 0; full `pytest` 290 passed, exit 0 (419 s); `grep` for the four removed tool names, their module paths, the ASS probe and the fonts path over `src`, `tests`, `docs`, `README*.md`, `STARTER.md`, `INSTALL.md` finds nothing (run before this entry was written; the entry itself avoids those strings). Not verified: `argus-doctor` on this machine (only mocked probes); the server in Kiro needs a reload to drop the old tools.
- Credits: <author fills>
- Audit status (task 18):
  - [x] Verify: full pytest 290 passed; engine `tsc --noEmit` exit 0; grep over `src`, `tests`, `docs`, `README*.md`, `STARTER.md`, `INSTALL.md` clean.
  - [ ] Not checked: `argus-doctor` run for real on this machine; the server reloaded in Kiro; the README plan example run through `validate_plan`.
  - Overall: code and tests OK; the questions below need an answer from the author or auditor.
- Questions for the audit (task 18):
  1. edge-tts went from critical to a warning in `doctor.py`. Design §15 lists it as optional, but the task text did not ask for it. Consequence: `doctor` reports `ok` on a machine with no voice provider at all. Keep?
  2. The engine check only tests that three folders exist in `engine/node_modules`. It does not compare versions with the 4.0.540 pin and does not look for a browser (`_find_browser`, Remotion's own download). A machine with `node_modules` but no Chrome/Edge passes the doctor and fails at the first render. Add a browser check?
  3. Doctor texts are still in Russian, while `product.md` says tool messages are in English. This was already so before the task and I left it. I wrote the new checks in Russian to keep one report in one language. Translate all of them?
  4. The server banner now says "ACTIVE | N tools | fps | output", in English, without the frame size. `ArgusConfig.width/height` still exist; design §15 says tools should stop using them. I did not search for the remaining uses.
  5. The engine still reads the v1 props (`theme`, `accent`, `voice`, `music`, `sfx_list`, the `sfx` flag) in `Main.tsx` / `types.ts` / `sfx.ts`, and `engine/sample-props.json` still uses `theme`. No tool sends them now. Remove them (and the Studio sample) in a later task, or keep for the Studio?
  6. `render.py` still synthesizes `whoosh.mp3`, `pop.mp3`, `hit.wav` into `engine/public/sfx` when a plan names them. I kept it because the sample plans name them. Is a built-in sound set wanted at all, given "no automatic sound effects"?
  7. The bundled Montserrat ExtraBold font was deleted with the bundled ASS font folder. It was the font of the old `phrase` subtitle look (the reference series). The engine has only Inter Display. Does `examples/plans/reference_style_9x16.json` or a future reference-style video need Montserrat in `engine/public/fonts`?
  8. `examples/timestamps.example.json` was the input example of the removed subtitles tool. Nothing refers to it now. Delete it or keep it as a `words.json` example?
  9. `skills/` was not searched or edited (steering: not unless the task says so). The skills and `tts.py` may still name the removed tools. Search them before task 22.
  10. I reworded one line in the task 10 entry of this log (it named the deleted kinetic module). Acceptable to touch a log entry for this, or should old entries stay verbatim and be excluded from the grep?
  11. `test_server_registers_exactly_the_v2_tools` fails whenever a tool is added or removed, on purpose. Design §2 is titled "17 tools" and the test lists 17; the design table does not list `run_script` and `doctor` as rows the same way. Confirm that 17 is the intended set.
  12. The one failed test (`test_clip_without_out_plays_to_the_end_of_the_file`, render job state `error`) was blamed on two pytest runs sharing the engine folder. I did not read the job's error text before it was cleaned up, so the cause is not proven. If two `render_video` calls on one machine can end in `error` instead of waiting for `engine/.render.lock`, that is a product bug. Test it with two parallel renders.
- Advice for the author (task 18):
  - Before task 21, regenerate the tool tables in README / README.ru from `studio_guide` capabilities, so they cannot drift again (this task fixed the count by hand in the docs and by code in the banner only).
  - The doctor could print the exact Remotion browser path or say "will download on first render"; today a missing browser shows up only as a failed render.
  - The checkpoint commit `aada601` holds tasks 14–17 together; they were not reviewed commit by commit. The removal itself is uncommitted for review. Git printed LF → CRLF warnings for most files; consider `.gitattributes` with `* text=auto`.
  - Scratch files in the repo root (`.chk*`, `.poll.txt`, `.proc14.txt`, `.pt14sub.txt`, `.pytest_task8.txt`, `check_task4.txt`, `import_out.txt`, `engine/.pytest_out.txt`) are not committed and can be deleted.
  - Running two pytest sessions on the same machine at once is unsafe for the engine tests; run the full suite one at a time.
  - The Kiro shell returned only echoed input and ran commands minutes late in this task as well (see tasks 10, 15, 16, 17). Cause not established. The reliable way here was `Start-Process` with redirected output files, polled with `read_file`.

## Task 19 — End-to-end suite and CI (2026-11-17, Haiku 5.5)
- Built: `.github/workflows/ci.yml` job `e2e` (ubuntu-latest, timeout 15 min): Python 3.14, ffmpeg, Node 20, `npm ci` in `engine/`, `pytest tests/test_scenarios.py`. The Python matrix and the `engine` typecheck job are unchanged. Task 19 is ticked in `tasks.md`.
- Bugs & fixes: `control_pwsh_process` did not start the test command (the background list stayed empty) → cause not established → the run went through `execute_pwsh` with `run_in_background`, output to a file. The Kiro shell returned empty output for several calls → the log was read with `read_file`.
- Kiro: spec task 19 and the tech steering (test command; a task is ticked only after its Verify steps).
- Verified: local `pytest tests/test_scenarios.py -v --durations=0` → 3 passed in 181.48 s (footage 86.6 s, reference 47.6 s, idea 45.8 s). Not verified: a GitHub Actions run of the `e2e` job (duration and result unknown), and the Linux render path.
- Credits: <author fills>

## Task 20 — Dogfood video 1, «Яхта за рубль» (2026-11-18, Sonnet 5.5)
- Built: retimed the nine drawn scenes to the real George voice (`Film.tsx` cues, local times in `Scenes1/2.tsx` with the voice words in comments), real captions from `voice.words.json`, CC0 music and 9 sound effects from Freesound, then stills (4 rounds), preview, final, QA and `export_package` → `final/yacht_9x16.mp4` (86.1 s), cover, `post.md`. The video and its components live outside the repo; the repo got the notes (`task20.md`) and Known issues 23–26.
- Bugs & fixes: compile error `TS2304 eIn` in `Scenes2.tsx` → an earlier edit of scene 8 used `eIn` without importing it → `render_video` typechecked the component and refused to render → added the import. Final QA hard failure, true peak -0.28 dBTP at -14.1 LUFS → `finalize_video` has no limiter before the AAC encode → re-encoded the audio of the finished file with `alimiter=limit=0.708` → -1.16 dBTP; the render pipeline itself is not fixed (Known issue 24). `alimiter=limit=-2dB` gave only -0.50 dBTP.
- Defects seen and left: long words in phrase captions lose the gap to the next word (Known issue 25, cause not confirmed). Known issue 21 (safe area) did not reproduce with the default safe area (issue 23). The Kiro shell again returned no output for waits, so I followed the renders with `job_status`.
- Kiro: the `argus` MCP tools did the work: `render_video` stills showed the model the frames and its component typecheck caught the missing import before a render; `qa_verify_video` caught the peak that the loudness figure alone hid; `studio_guide` gave the working order (stills, preview, final, QA, export). Steering `product.md` / `tech.md` set the order and the build log; no hook result noted.
- Verified: stills at about 30 times over four rounds, 8 preview frames, QA of the final after the limiter: 1080x1920, 30 fps, -14.1 LUFS, -1.16 dBTP, no black, freeze or silence → passed; `export_package` → 1 mp4, cover, `post.md`, no violations. Reviewed by the author, who listened to the voice and watched the final and accepted it (per the author); I did not hear the voice or the mix myself. No 16:9 version. Task 20 stays `[ ]` in `tasks.md` because it asks for three videos; this is video 1.
- Credits: 91 credits and 1 h 20 min for this part (per the author)
- Details: `.kiro/specs/argus-v2/task20.md`

## Task 20.1 — Fixes from video 1 (2026-11-18, Haiku 5.5)
- Built: `LIMITER_FILTER` (`alimiter`, -2 dBFS, `level=disabled`, `latency=true`) after `loudnorm` in `finalize_video`; word-gap margins for the active word in phrase captions (`engine/src/captions.tsx`); `captions.style.case` (`upper`/`as_is`) in plan, types and engine; `job_status(wait_s)`, capped at 20 s, with `eta_s`; compact `watch_video` result (`words_path`, `segments_path`, `transcript_head`, no inline words); `voice_options` reads the plan (`GET /v1/user/subscription`) and on the free tier moves non-premade own voices and all Voice Library voices to the paid-plan list.
- Bugs & fixes: no synthetic mix reproduced the true-peak failure without the limiter (13 signals, -1.1 to -1.5 dBTP without it), so the test checks the filter itself (a 0.99 burst must come out at or below 0.8 linear). The active word's 1.08 scale covered the gap to the next word, so each word now reserves half its growth as side margin. `test_scenarios` read inline words, so it reads `words_path` now. The running `argus` server predates the `case` field (`unknown field 'case'`), so it needs a reload.
- Real file: `project-1/renders/yacht-final-9x16.mp4` before `finalize_video` -0.28 dBTP at -14.06 LUFS, after it -1.82 dBTP at -14.06 LUFS (measured with `measure_loudness`, the function QA uses). The temporary `.tp-check.mp4` was deleted.
- Kiro: `argus` MCP `render_video` stills for the gap check. The Kiro shell stopped returning output during long test runs, so runs wrote to files that were read back.
- Verified: test_plan + test_captions 31 passed; test_jobs 18 passed; test_watch + test_studio_guide 42 passed; test_voice_options 29 passed; full `pytest tests` 298 passed and 1 failed (`test_footage_edit_with_remapped_captions`, fixed, rerun 1 passed); engine `tsc --noEmit` exit 0; caption stills show the gap in four frames.
- Not verified: a final of an `examples/plans` sample passing QA with no manual limiter (not run); `case` in a still (server predates it); a live ElevenLabs call on the free tier (none made); caption gap in pixels (not measured).
- Author direction: ElevenLabs is the priority voice provider; edge-tts is a fallback, not the default for finals. Verify items and the checkbox for 20.1 are left to the author. Credits: 40


## Task 20.2 — Motion kit: universal blocks for custom scenes (2026-11-18, Sonnet 5.5)
- Built: `engine/src/kit/` (motion, timing, wrappers, text, effects, info, `KIT.md` of 3,458 characters) and `custom/kit.ts` so a component imports `../kit`; `components.py` allows that import. `plan.cues` (seconds, or `{word, nth, offset}` found in `captions.words`) is resolved to seconds by `resolve_cues` (`captions.py`, checked in `prepare_render`) and reaches the engine through `timing.ts` (`PlanTimingContext`, `ClockContext`, set in `Main.tsx`); `useCue`, `useCues`, `useWords`, `useT`, `useDuration` return seconds on the scene's own clock. `studio_guide(custom_scenes=true)` adds `motion_kit`. STUDIO_GUIDE has the five text rules; `render_video` docstring and `custom/README.md` describe `../kit` and `cues`.
- Bugs & fixes: the first write of `kit/timing.tsx` was cut off by a tool error and the file was not created → rewrote it. `Set-Content -Encoding UTF8` put a BOM into `types.ts` → removed the three bytes, diff back to 7 lines. The Kiro shell returned only echoed input, then ran nothing; the author cancelled the session. Later calls worked, and the stills rendered earlier were still on disk.
- Kiro: spec task 20.2 gave the block list; the engine steering rule on determinism is why `Particles` use `random(seed)`; `render_video` stills with its component typecheck are the test of the kit. No hook result noted.
- Verified: engine `tsc --noEmit` exit 0; `test_captions` + `test_plan` + `test_studio_guide` 48 passed; `test_components` offline subset 25 passed; three new engine tests passed in 24.41 s (`SceneTrack` switching on a word cue from a words file in a scene that starts at 1 s; the `KIT.md` example in 9:16 and in 16:9). Looked at four of the eight stills of the example (9:16 and 16:9 at 1.5 s and 3.6 s): text, plate and pop-up are centred and not clipped in both formats.
- Not verified: full `pytest -q` after the change (started once at the end, output still empty after about 16 minutes, so no result; `Plan.to_dict()` now always has `cues: {}`, so a test that compares a whole plan dict could fail); no still or test for `LightCone`, dust `Particles`, `PollCard`, `Checklist`, `ProgressBar`, `Bubble`, `Label`, `Slide`, `Pop`; an unknown cue name in `useCue` (should stop the render with a message) was not tried; the running `argus` server must be reloaded; the target (under 20 minutes and 20 credits on the Kiroween video) is not measured and belongs after 20.3.
- Later run: full `pytest -q` → 340 passed (exit 0) at the start of 20.6, recorded in the Task 20.5 entry. The run above has no result.
- Credits: <author fills>
- Questions for the auditor:
  1. Word cues need `captions.words`, so a video with a voice and no captions cannot use them. Should the voice's own words file count, or is requiring `captions` right?
  2. The kit is HTML/CSS in design px. The yacht code was SVG in a fixed 1080x1920 viewBox, and story drawings (characters, boats) still have to be SVG. Does the kit need a small SVG frame helper that scales a drawing to both formats, or should drawings stay outside it?
  3. Kit hooks return seconds on the scene's own clock (video time minus the scene start), while plan times are video time. Is that the right default?
  4. `SceneTrack` stacks scenes: the new one fades in over the old one, and the old one is removed when the new one is fully visible. A scene with transparent areas would pop at that moment. Is a dissolve mode needed, or is "each scene paints its own `Stage`" enough?
  5. `Delta` falls back to `#FF4D5E` and `LightCone` to `#FFE9A8` when the style or props give no colour. Does that break "the kit has no look of its own"?
  6. `studio_guide` returns the catalogue only with `custom_scenes=true`, to keep the default answer short. Should it always be included?
  7. Nine blocks have no render test. Is typecheck plus the example scene enough for a P0 task, or should each block get a still?

## Task 20.3 — Style library (2026-11-19, Sonnet 5.5)

- Built: `tools/library.py`; `export_package(save_to_library=...)` writes `<output>/library/<entry>/` (component files, `card.md`, `poster.jpg` 512 px from the final) and rebuilds `index.md`; `studio_guide` returns `library` (index, up to 8 posters as images); a component imports `./library/<entry>/<File>`, `components.py` copies the used files into `custom/job/library/<entry>/` with `style.ts`/`kit.ts` re-exports. Guide text, `custom/README.md` and docstrings updated.
- Bugs & fixes: two pytest runs at once → the shared `engine/src/custom/registry.ts` was left generated and `_engine_untouched` failed → one run at a time, no code change. A chained PowerShell `.Replace` edit overwrote an import line in `render.py` → restored with a direct edit. Kiro shell commands ran late and in one shared queue → results read from output files.
- Kiro: none beyond the spec task text and steering rules.
- Verified: `pytest -q` → 338 passed (8 min 6 s); new `tests/test_library.py` plus two engine tests in `test_components.py` (render with an imported entry; compile error names the entry). The author's Verify (yacht entry, two references) is not run yet; the `argus` MCP server must be reloaded.
- Credits: <author fills>

## Task 20.5 — Kit backgrounds, transitions, energy kit: visual part only (2026-11-20, Sonnet 5.5)

- Built: in `engine/src/kit/`: `fx.tsx` (`MotionBlur`, `RgbSplit`, `shakeOffset`); `transitions.tsx` (`Transition`, `transitionDur`; fade, whip, zoom, wipe, slice, split, flash, glitch, shake, ramp); `energy.tsx` (`Shake`, `Stepped`, `Boil`, `Snap`, `Burst`, `Flash`, `Aberration`, `FilmBurn`, `LensFlare`, `Vhs`, `FreezeStamp`); nine backgrounds added to `backgrounds.tsx` (`AnimatedGradient`, `Mesh`, `Stripes`, `Vignette`, `LightLeaks`, `Scanlines`, `Starfield`, `Bokeh`, `Paper`). `SceneTrack` takes `enter` (on the track or per scene; default stays a cross-fade). `KIT.md` rewritten to 4,983 characters (prop lists of older blocks shortened to fit).
- Bugs & fixes: the Kiro shell returned only echoed input for most calls; results were read from a temp file and from `get_diagnostics`. A PowerShell command that cut `timing.tsx` at a marker was blocked by Kiro and not run; the edit was redone with `str_replace`. A stray `timing.head.tmp` was created and deleted.
- Kiro: the engine steering rule on determinism (no `Math.random`, use `random(seed)`) shaped every random pattern; `get_diagnostics` showed no type errors in the five changed files when the shell gave nothing back.
- Verified: `get_diagnostics` on `fx.tsx`, `transitions.tsx`, `timing.tsx`, `energy.tsx`, `backgrounds.tsx` → no problems. Search of `engine/src` for `Math.random(` and `Date.now(` → none (`Particles` already used `random(seed)`). `KIT.md` length 4,983 (< 5,000).
- Status: `[x]` (Verify stills open, SFX → 20.5b). Closed at the start of 20.6 (2026-11-20): full `pytest -q` → 340 passed in 514.50 s (exit 0); engine `tsc --noEmit -p engine` → exit 0. `KIT.md` got two lines (scenes with video render slower; `Starfield` flies out of a point, `Particles` stars twinkle in place) and a shorter example, still under 5,000 characters (16 catalogue and guide tests passed).
- Still open: no stills of any background, transition or energy block (they come with the 20.6 contact strips); no two-look stills; STUDIO_GUIDE §5 rule on choosing a transition per cut is in 20.6; SFX kit → 20.5b; optional Remotion skills not tried.
- Auditor answers (2026-11-20): 20.5 visual `[x]`, SFX split into 20.5b; `Freeze` on the scene clock is wanted, check it on the test video; check the edge fade of the blur filters with one still on the test video, and if the edges pale, enlarge the layer by 2–3 % under the filter; keep `glitch`, `slice`, `split` as they are; `split` with the old scene on top is low risk (the new scene shows through transparent areas, as doors need); a speed ramp as a transition is enough for now, a real video time remap comes after the contest; warm default colours of `LightLeaks`, `FilmBurn`, `LensFlare` do not break the rule (colour stays a prop); keep both `Starfield` and `Particles`; the `KIT.md` limit stays at 5,000 (20.6 turns it into an index); cue names in the energy blocks come in 20.6.
- Credits: <author fills>
- Questions for the auditor:
  1. The Verify steps (pytest, one still per background in 9:16, two-look stills, transition stills) were not run, so the box stays open. Is it right to leave it open when the visual half is written, or should the task be split into 20.5a (visual) and 20.5b (SFX)?
  2. `Stepped` and `FreezeStamp` use Remotion's `<Freeze>`. From the 4.0.540 source, `frame` is read on the clock of the enclosing sequence, and nested sequences inside restart at 0. Not tried in a render. Is that the behaviour we want inside a `SceneTrack` scene?
  3. `MotionBlur`, `RgbSplit` and `Boil` are inline SVG filters (`feGaussianBlur`, `feColorMatrix`, `feDisplacementMap`), ids from `useId`. `edgeMode="duplicate"` may be ignored by the render browser, which would fade the picture edges. Needs a still to confirm.
  4. `glitch`, `slice` and `split` draw the scene's children several times (5, up to 8, 2). A scene with a video would decode it several times for the length of the transition. Acceptable, or limit these kinds to scenes without video?
  5. `split` puts the old scene on top of the new one (`zIndex: 2`) so it can open like doors. Other kinds keep the new scene on top. Any risk for scenes with transparent areas?
  6. "Speed ramp" is built as a scale-and-blur ramp between two scenes. A real time remap of a video (changing `playbackRate` over time) is not in the kit. Is the transition enough for the task text?
  7. `LightLeaks`, `FilmBurn` and `LensFlare` have warm default colours (a leak or a burn is warm by nature). Does that break "no default look tied to a past video", as the same question did for `Delta` and `LightCone` in 20.2?
  8. `Starfield` (flying out of a point) and `Particles kind='stars'` (twinkling) overlap in purpose. Keep both, or fold the twinkle into `Starfield`?
  9. To fit `KIT.md` under 5,000 characters I shortened the prop lists of `wrappers`, `text`, `effects`, `info` and the example (one text line removed). Is a catalogue of names plus main props enough, or should the limit move to about 6,000?
  10. `at` is a plain number or a list of seconds (usually `useCue('hit')`). Should the energy blocks also accept a cue name directly, so the model does not write `useCue` by hand?

## Task 20.6 — Rich motion: HUD, kinetic type, bursts, depth, camera, catalogue with previews (2026-11-20, Sonnet 5.5)
- Built: kit groups `hud.tsx`, `type.tsx`, `bursts.tsx`, `depth.tsx`, `camera.tsx`; `at.ts` (`at` takes a cue name or a list of names and numbers); `captions.mode: "headline"` (`captions.tsx`, `types.ts`, `plan.py`); `KIT.md` is now an index (3,525 characters) with ten group files in `engine/src/kit/groups/`; `tools/kit_preview.py` and `engine/src/custom/previews/*.tsx` render one frame per block into a cached contact strip; `studio_guide(kit_group=...)` returns a group's text and its strip (a detached `kit_preview` job when not cached); `STUDIO_GUIDE.md` edited.
- Bugs & fixes: in the first 9:16 stills of the sample scene the `WordSlam` text sat at the top edge and over the HUD timecode and pills → `WordSlam` is in normal flow and the sample had no centring wrapper → wrapped it in a full-frame flex `div` in the `SHOWCASE` test scene and added one line to `groups/type.md`. The Kiro shell hung → long commands ran as background processes and wrote to files.
- Kiro: none beyond the spec task text and the steering rules (engine determinism, tech Verify).
- Verified: `tsc --noEmit -p engine` → exit 0; quick tests → 55 passed, 18 deselected in 10.6 s; full `pytest -q` → 354 passed in 606 s (exit 0); contact strips built for all ten groups (8–17 s each), `energy`, `transitions` and `hud` strips viewed; neon look of the sample scene in 9:16, five stills viewed (HUD layer, headline caption, speed lines and glow burst on the cue, whip and glitch transitions).
- Not done: the second look and the 16:9 stills were not viewed (the test suite renders both and checks size and brightness only); the other seven strips were not viewed; in the sample the slam text and the headline caption share the middle of the frame and overlap; `Aberration` and `glitch` show a coloured band at the left edge in stills, not judged; STUDIO_GUIDE text (§5, §6) not re-read in this pass.
- Credits: <author fills>
## Task 20.7a — Cheaper and faster videos (2026-11-21, Haiku 5.5)
- Baseline before any speed change (10 s slice of `argus-trailer-en`, copied to project `argus-timing-slice` with `duration` 10, final 9:16, `ARGUS_RENDER_CONCURRENCY` unset = 2 workers, wall 113.0 s, job 109.3 s): prepare 5.7 s, bundle 15.7 s, browser 1.2 s, frames + encode 79.1 s (300 frames), mux 0.1 s, loudness 3.4 s.
- Measured with a timing field added to render results (node side: bundle, browser, frames + encode, mux; Python side: prepare, finalize, total). No behaviour change in this step.
- Built: `timing` in every render result. Bundle reuse from `<project>/cache/bundle/<key>` (key = engine/src, package.json, the job's public files). A stills round of 2+ frames returns one contact sheet (up to 12 cells, each labelled with time and `scenes[i]`), full frames stay listed. Warnings for one-colour frames and accent words never spoken. `export_package` adds `render_timing`. Guide §5 and §8 and the `render_video` docstring updated.
- Measured, 10 s slice, final 9:16: baseline 109.3 s total (bundle 15.7 s). After, bundle reused: 48.1 s (bundle 0 s). Second stills call: bundle 3.2 s to 0 s. Frames + encode with identical settings ranged 41 to 74 s (2 workers: 51, 41, 74; 3: 48, 55; 4: 50). The frame stage is not shown to be faster. Preset: `fast` 45.3 s and 10.2 MB against `medium` 41.0 s and 9.5 MB; `veryfast` 41.4 s. Default stays `medium`, 2 workers.
- Bugs: Windows refused `status.json` replace while a reader or scanner held it, so a finished render was marked error (retry window 1.3 s, now about 18 s). Test fake node left the engine lock, so the next test waited 300 s (fake now releases it). Lock leaked if the bundle key failed (now released).
- Not done: stills scene subset (a still draws only the scenes on its frame; the bundle was the cost). Guide edited in `src/argus/STUDIO_GUIDE.md` only.
- Kiro: `control_pwsh_process` for the long runs; multi-step chains often ended early, so single commands were used.
- Verified: full `pytest` 368 passed (first full run 362 passed, 6 failed on the old per-frame shape and one run killed by me; all fixed and rerun 6 passed); `tsc --noEmit -p engine` exit 0; trailer stills sheet of 6 cells viewed, labels and frames legible.
- Left behind: `argus-trailer-en/renders/sheet-check-*` and a 38 MB `cache/bundle`; scratch project `argus-timing-slice` and timing files in `OMNIFRAME_OUTPUT/timing/`.
- Credits: <author fills>

## Task 22 — Pre-existing work and skills/ (2026-11-21, Haiku 5.5)
- Built: `skills/` (72 tracked files) copied to `../argus-skills` and removed from this repo in `540ba82`; its lines removed from `.gitignore`; README.md, README.ru.md and STARTER.md no longer name the skills folder (per the commit message).
- Bugs & fixes: none.
- Kiro: none.
- Verified: `git ls-files skills` → 0 files; `Test-Path ..\argus-skills` → True; full `pytest` → 368 passed in 685.77 s, exit 0.
- Left for the author: `launch_argus_mcp.bat` kept (INSTALL.md lines 89 and 96 use it); README.md line 11 still names `~/.zcode/skills`; the disclosure text is in task 21.
- Credits: <author fills>

## Task 20.5b - Sound design: synthesized sounds, variations, SFX library (2026-11-21, Haiku 5.5)
- Built: sound events placed on the timeline (`src/argus/tools/sounds.py`), synthesized sounds (`src/argus/tools/synth.py`), tests (`tests/test_sounds.py`); plan, server, studio and `STUDIO_GUIDE.md` updated to match.
- Bugs & fixes: (1) built-in sounds were not found in `run_job` and `_run_audio` -> both now resolve files through `render._resolve_file`. (2) 404 on `InterDisplay-Black.otf` in a full run, not reproduced on a rerun -> cause: the cached bundle `<project>/cache/bundle/<key>/public/` had no `fonts/` folder while `m/` had its files, and the source of the loss is not known -> before a cached bundle is served, `render._restore_public` links back every file of the job public dir that the bundle lacks and reports the list. Test: `test_reused_bundle_gets_back_the_public_files_it_lost`.
- Kiro: none.
- Verified: `test_render_speed.py`, `test_scenarios.py`, `test_render.py` -> 42 passed in 240.04 s, exit 0; full `pytest -q` -> 414 passed in 750.28 s, exit 0.
- Not done: Freesound sounds in the library and ducking in audio mode (after the contest); listening and re-voicing (at the demo).
- Credits: <author fills>

## Task 20.8 — Current models and all voices (2026-11-21, Haiku 5.5)
- Built: `tools/model_catalog.py` (Gemini TTS and Veo from google-genai `models.list`, newest by the version number in the id); ElevenLabs TTS models from `GET /v1/models` in `voiceover.py`, default is the newest one (now `eleven_v4`), `ARGUS_ELEVEN_MODEL` pins one; `voice_options` returns `models` with `default`; voices from all pages of `GET /v2/voices`; `generate_veo_clip` route `api` refused with the 2026-10-22 shutdown message (Flow route unchanged); `.env.example` model ids empty; `chatSessionId` removed from `tasks.meta.json`.
- Bugs & fixes: the first full run failed `test_veo_provider_validation` (ImportError) because `veo.py` and `model_catalog.py` were edited while that run was still collecting tests → rerun on the final code, no code change. `test_studio_guide` expected `veo_api` available with a key → test now expects the shutdown note. `test_config` read a pinned `ARGUS_TTS_MODEL` from the user's `.env` → the test clears the model variables first.
- Kiro: none beyond the spec task text and the steering rules. The shell returned echoed input, so runs wrote to files that were read back.
- Verified: full `pytest -q` 441 passed, exit 0 (10 min 31 s, on the final code). Live, read-only, with the author's key: `/v2/voices` returns 24 voices over all pages (21 premade, 3 Voice Library copies, 0 personal); models as listed above. Not verified: the count in the author's ElevenLabs app; no real Veo call (the route is refused by design).
- Credits: <author fills>

## Task 20.9 — Leftovers before the freeze (2026-11-21, Haiku 5.5)
- Built: `argus-doctor` in English, with a render-browser line (Chrome or Edge path, or "Remotion downloads its own"); one `NO_WINDOW` flag for every subprocess call in `src/argus`; `style_note` on stills and preview answers for the `dark` and `light` presets; `qa_verify_video` reports size, loudness and true peak of a `-preview-` file as warnings; `calculate_beat_grid` replies with 12 beats and `beats_path` (full list in JSON, `project` optional); STUDIO_GUIDE §5 on the look and on low beat confidence; the spec copy of the guide is a pointer; 20.4 set to dropped; gaps in this log filled.
- Bugs & fixes: `test_beats` read `beats` after the reply stopped carrying it → KeyError in 3 tests → the test reads `beats_path`, and the tests write to a temp output folder. Beat times came back as `np.float64` → cast to float. `style_note` covered `dark` only → added `light` with its own line and tests for both. A pytest run started on a stale test file → stopped and restarted. Commit `4473b5d` had a BOM in its message → amended without BOM.
- Kiro: none beyond the 20.9 checks in `tasks.md` and the steering rule for detached runs (output to files, then read back).
- Verified: full `pytest -q` 465 passed, exit 0 (607 s); targeted run of items 1–6 and 8: 63 passed; engine `tsc --noEmit` exit 0. Direct runs: `argus-doctor` exit 0; QA on a generated 540x960 preview → passed, warnings `resolution` and `loudness`; beat grid on a 120 s click track at 170 BPM → reply 556 characters, 342 beats in the file.
- Credits: <author fills>

## Task 20.10 — Credit economy and demo-run bugs (date not recorded, Haiku 5.5 high)
- Built: items 19–24 and 26 and the task's Decisions in commit `8837a86` (25 files): reply-size log `economy.jsonl`, shorter tool surface, guide core with sections, `then: ["qa", "export"]` chain, resume file `state.json`, `mediaUrl` for project images in custom scenes, missing-media check in the stills job; mock-up kit blocks and their preview `engine/src/custom/previews/mockups.tsx`.
- Bugs & fixes: `test_components` raised FileNotFoundError because the preview of group `mockups` was never written → wrote it from the kit blocks. `mediaKey` was exported from `media.ts`, so the kit test wanted it in a group file → made it private and documented `mediaUrl` in `groups/core.md`. Tool surface was 9,011 characters against a 9,000 limit → shortened the `calculate_beat_grid` description.
- Kiro: steering `tech.md` (long runs detached, output to files, read back with `read_file`); no hook or MCP result.
- Verified: `tests/test_components.py` 31 passed; full `pytest -q -rf` 523 passed, exit 0 (13 min 41 s); engine `tsc --noEmit -p engine` exit 0. Not verified: the octopus run (Verify step 2: credits and minutes before and after, `economy` totals from `export_package`).
- Octopus run 2026-11-23 on Haiku: ~4 min, <1 credit (author's counter), ElevenLabs George v4, QA passed, render_timing total 73 s; economy lost to the export bug, fixed.
- Credits: <author fills>

## Task 20.7b — Scene language `layers` (dropped, code on branch `layers-wip`)
- Built: scene kind `layers` (`plan.py`, `layers.py`, `engine/src/layers.tsx`), guide section 11 (2,979 characters), commit `7f45153` on `layers-wip`; main branch has none of it. Dropped by the author on 2026-11-22: stills looked crude and the plan was longer than TSX.
- Measured on `octopus-layers` (Swim + Blood): plan 11,256 characters against 7,829 in `Swim.tsx` + `Blood.tsx`; the 6 stills were rendered next to the old video and in a second look.
- Verified: `test_layers`, guide and tool-surface tests 50 passed; engine `tsc --noEmit` exit 0. Not verified: the full `pytest` run (its result was never read).

## Voice overwrite guard (date not recorded, Haiku 5.5)
- Built: `synthesize_voiceover` leaves `<project>/audio/<name>.mp3` alone when it holds other text. `<name>.text.sha256` records each voice's text; the same text is a repeat, and `overwrite=true` replaces the file. Guide core line: check `studio_guide(project=...)` and the style library before a new video.
- Bugs & fixes: the new `overwrite` flag raised the tool surface from about 8,996 to 9,103 characters against the 9,000 limit → the author set `SURFACE_LIMIT` to 9,200 in `tests/test_tool_surface.py`.
- Kiro: none.
- Verified: `test_voiceover.py`, `test_voice_project.py`, `test_voice_options.py`, `test_guide_sections.py`, `test_tool_surface.py`: 92 passed, and the surface test failed until the limit change. After it, `test_tool_surface.py`: 4 passed. Full pytest not run.
- Not verified: a voice file made before this change has no text record, so a repeat of its text is refused until one `overwrite=true` call. Not run against octopus-hearts.
- Credits: <author fills>

## Task 20.11 — Library grows from every final (2026-11-23, Haiku 5.5 high)
- Built: `export_package(save_to_library=[...])` saves up to 12 elements after QA passes; a name that exists makes the next version (`<entry>/versions/v<n>/` keeps the old files, `card.md` lists the versions); `times used` counts renders that import an entry; the `studio_guide` index shows version and times used; the reuse rule is in the guide core.
- Bugs & fixes: (1) a list with the same name twice, where the other item lacked `changed`, did not say "appears twice" → the duplicate check ran only on items that passed the other checks → every item's name is checked first. (2) `studio_guide` poster order differed from the test → the code orders by poster mtime, the test aged only `card.md` → the test ages the poster as well. (3) an index line test expected a shortened `what` → test updated.
- Kiro: none beyond the steering rule for detached runs (output to files, read back).
- Verified: `test_library.py` 31 passed; `test_library`, `test_guide_sections`, `test_tool_surface`, `test_export`, `test_components`, `test_studio_guide` 104 passed, exit 0 (217 s). Seeded `OMNIFRAME_OUTPUT/library` with `neon-octopus` (Octopus.tsx) and `neon-bg` (Bg.tsx) from octopus-neon, posters from the final at 1.9 s. The author's Verify is not run; the task stays `[ ]`.
- Credits: <author fills>

## Task 20.11 follow-ups — library entries that use other entries, shorter tail, neon-bg v2 (2026-11-24, Haiku 5.5 high; commit by Opus)
- Built: a component that imports library entries can be saved; its card lists `Uses:` with pinned versions, and the dependency files are copied with it (one level deep only). `TAIL_S` 0.6 → 0.3 s for a computed duration; an explicit `duration` is kept as asked. `neon-bg` v2 in the user library takes a `clock` prop for a whole-video HUD timer (v1 kept).
- Bugs & fixes: two tests still expected the old 0.6 s tail (`test_clips.py`, `test_render.py` line 191) → updated to 2.3 s; a `git commit -F -` without input hung the shell → committed with `-m`.
- Kiro: none.
- Verified: `test_library.py` + `test_tail.py` 40 passed; `test_clips.py` + `test_render.py` 42 passed, exit 0 (128 s); engine `tsc --noEmit` exit 0. Full pytest not run. `octopus-color` not re-rendered with `clock`.
- Credits: <author fills>
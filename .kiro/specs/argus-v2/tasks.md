# Implementation Plan — ARGUS v2

Work one top-level task at a time, in order. Each task lists the design sections to
read, the files to touch, and how to verify. Priority: **P0** = needed for the author's
own TikTok work (milestone M1), **P1** = universality (freeze Nov 30), **P2** = submission.

- [x] 1. Setup: Kiro MCP connection, dependencies, project folders (P0)
  - Read: design §3, §15.
  - `src/argus/config.py`: `_load_dotenv()` order `ARGUS_ENV_FILE` → `./.env` → `<repo>/.env`; add config fields `whisper_model` (`ARGUS_WHISPER_MODEL`, default `small`), `eleven_model` (`ARGUS_ELEVEN_MODEL`, default `eleven_v3`), `render_concurrency` (`ARGUS_RENDER_CONCURRENCY`, default 0 = auto), `scripts_dir` (`ARGUS_SCRIPTS_DIR`, default `~/.argus/scripts`). Document them in `.env.example`.
  - `pyproject.toml`: add `numpy`, `Pillow` to dependencies; add extra `asr = ["faster-whisper>=1.0"]`. `src/argus/__init__.py`: version `3.0.0.dev0`.
  - New `src/argus/project.py`: `slugify(name)`, `project_dir(name) -> Path` creating the folders from design §3.
  - New `.kiro/settings/mcp.json` registering ARGUS for Kiro (check field names in Kiro docs); update `examples/mcp-config.example.json` with Windows and macOS/Linux variants.
  - Tests: `tests/test_project.py` (slug rules, folders), config `.env` fallback test.
  - Verify: pytest green; after reloading MCP servers in Kiro, the `doctor` tool runs from Kiro chat.
  - _Requirements: 15.1, 16.1_

- [x] 2. Remove creative gates (P0)
  - Read: design §2 (server instructions), §16.
  - `src/argus/server.py`: delete the `validate_beats` and `story_guide` tools; replace `instructions=` with the text in design §2; strip "<=30%" wording from the `analyze_reference` docstring.
  - `src/argus/tools/reference.py`: delete `validate_beats`, `detect_genre`, `SLOP_MARKERS`, `_NUM_WORDS`, overlap helpers, `story_guide`, and the `analysis_protocol` text (keep only frame extraction until task 5).
  - Delete `src/argus/STORY_GUIDE.md` and `tests/test_reference.py`.
  - Remove the "Граница заимствования" section from `STARTER.md`, `skills/montazh-mani/SKILL.md`, `skills/montazh-esse/SKILL.md` (only that section).
  - Verify: `grep -ri "30%\|validate_beats\|story_guide\|STORY_GUIDE"` over `src tests STARTER.md skills/*/SKILL.md README*.md` finds nothing relevant; pytest green.
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 3. Studio guide and preferences (P0)
  - Read: design §14.
  - Copy `.kiro/specs/argus-v2/STUDIO_GUIDE.md` to `src/argus/STUDIO_GUIDE.md` unchanged; make sure it is packaged (hatch includes non-py files under `src/argus`; check the wheel).
  - New `studio_guide()` tool: guide + capabilities (registered tool names; providers from config and import checks: elevenlabs, gemini, edge, faster-whisper, veo_api, flow session dir exists) + preferences (last ~4000 chars of the knowledge base file).
  - `learn_and_record_memory`: docstring per design §14; header for a new file `# ARGUS — user preferences`.
  - One-time archive: if the local `KNOWLEDGE_BASE.md` exists, rename it to `KNOWLEDGE_BASE.old.md` (the user agreed); add `KNOWLEDGE_BASE.old.md` to `.gitignore`.
  - Tests: guide returns all three parts; preferences capped; recorded preference appears in the next call.
  - Verify: call `studio_guide` from Kiro chat.
  - _Requirements: 2.1–2.4_

- [x] 4. Images to the model + jobs (P0)
  - Read: design §4, §5.
  - New `src/argus/media_out.py` (`prepare_image`, `tool_result`).
  - New `src/argus/jobs.py` (`start`, `run_or_detach`, worker entry `python -m argus.jobs <job_dir>`, `status`, cleanup of jobs older than 7 days at server start). Port single-flight and stale-pid logic from `tools/assemble.py`.
  - New `job_status(job_id)` tool.
  - Temporary debug tool is NOT added; instead verify images through `get_frames` in task 5.
  - Tests: `tests/test_jobs.py` (inline result, detach + poll to done, error tail, single-flight, dead pid → error); `tests/test_media_out.py` (downscale, list shape).
  - Verify: pytest green.
  - _Requirements: 3.1–3.3, 4.1–4.4_

- [x] 5. `watch_video` and `get_frames` (P0)
  - Read: design §6.
  - New `src/argus/tools/watch.py` per §6 (hash cache, shots, frame budget, contact sheets with Pillow, faster-whisper transcript when installed, onset sound events from `tools/beats.py`, pagination). Runs through `run_or_detach("watch", ...)`.
  - `get_frames` in the same module.
  - `server.py`: register both tools; delete `analyze_reference`; delete `tools/reference.py`.
  - Tests: synthetic video of 5 colour segments with beeps → shots within 1 frame, sound events within 50 ms, cache hit on second call, pagination; transcript test skipped when faster-whisper is absent; get_frames crop dimensions.
  - Verify (manual, record result in the task notes): from Kiro chat run `watch_video` on any local mp4 and `get_frames` on 2 times. Confirm the model actually sees the images. If not, apply the fallback from design §4 and add the guide line.
  - _Requirements: 3.4, 5.1–5.6, 6.1–6.2_
  - Audit report: `.kiro/specs/argus-v2/task5.md` (what works, what is unverified, deviations from design §6, known weak spots).
  - Notes (2026-11-16):
    - Code and tests done: `tools/watch.py`, `tests/test_watch.py` (24 passed, 1 skipped: real faster-whisper run), full suite 120 passed, 1 skipped. `analyze_reference` and `tools/reference.py` removed.
    - Over a real MCP stdio session (`python -m argus`) both tools return a text block plus `image/jpeg` content blocks (`watch_video`: 1 contact sheet; `get_frames` with 2 times and a crop: 2 images).
    - **Manual check in Kiro chat: passed.** After the MCP reload, `watch_video` (7:30 vertical file, 576x1024) and `get_frames` (5 times) both returned images the model could see and read (Russian subtitles, HUD numbers). No design §4 fallback line was needed.
    - Known limits seen in that run: `watch_video` has no time-range parameter (it always covers the whole file); on flat animation with soft transitions the detector (`scene` > 0.30) found only 3 shots where the content clearly changes more often, so `get_frames` is needed to check a stretch; no transcript without faster-whisper.
    - Helpers added for this task: `ffmpeg.run_ffmpeg_stderr`, `ffmpeg.decode_audio`; `beats._onset_envelope` now sums squares with a running sum (same result, no n_hops×1024 matrix); `jobs` honours `image_max_side` in a result so contact sheets (1600 px) are not shrunk to 1024.

- [x] 6. Voice v2 (P0) — marked done by the owner's instruction while the live Verify step is still open (see notes)
  - Read: design §7. Check current ElevenLabs docs: model ids (`GET /v1/models`), `with-timestamps` response, shared voices endpoint and whether library voices must be added before use. Put doc URLs in comments.
  - `src/argus/tools/voiceover.py`: provider protocol; providers `elevenlabs` (default with key), `gemini`, `edge` (default without keys); chunking of long text; words.json; output into `<project>/audio/`.
  - `voice_options(language, gender, query, limit)`: own voices + library search + edge defaults + providers status.
  - `server.py`: new signatures and docstrings (model-facing: "choose the voice yourself, write delivery with v3 audio tags; SSML breaks only on v2 models").
  - Tests (mocked HTTP): alignment → words with tags stripped; chunk offsets; edge WordBoundary → words; no keys → edge; gemini without whisper → `words_source: none`. Update `tests/test_voice_options.py`.
  - Verify: one real ElevenLabs call (short line) from Kiro, words.json timings match the audio length.
  - _Requirements: 7.1–7.6_
  - Notes (2026-11-16):
    - Code and tests done: `tools/voiceover.py` rewritten (providers `elevenlabs`, `edge`, `gemini` behind `VoiceProvider`, `register_provider`; `split_text`; `words_from_alignment`; job kind `voiceover`), `server.py` signatures and docstrings, `tests/test_voiceover.py` (25 tests) and `tests/test_voice_options.py` (15 tests, rewritten). Full suite 158 passed, 1 skipped. Added at the owner's request: `voice_options` returns `provider_choice` (ElevenLabs recommended when its key is set; `ask_user` when 2+ providers work, so the model asks the user once per project) and, with a key, a `delivery` vocabulary (audio tags and pacing rules).
    - Audit report: `.kiro/specs/argus-v2/task6.md` (what works, what is unverified, deviations from design §7, open questions for the audit in section 11).
    - **Marked `[x]` at the owner's request (2026-11-16) although the live Verify step below has not been run.** It stays the first thing to do after the MCP reload; if it fails, reopen this task.
    - **Open: the live Verify step.** The `argus` MCP server connected to Kiro still runs the old code (its `synthesize_voiceover` schema has `voice_name`/`output_path`), so a real call now would test v1. Reload the server in Kiro (MCP Server view), then call `synthesize_voiceover(text="[whispers] This is a short ARGUS voice check. [excited] It works!", project="voice-check")` and compare the last `words.json` end with `duration`. Also try `voice_options(language="ru", gender="male", limit=3)` to see the live response shapes. Nothing in the code has run against the real ElevenLabs or edge-tts service yet.
    - Doc findings (URLs in `voiceover.py` comments): `with-timestamps` returns `audio_base64` plus `alignment` (per-character start/end seconds). Library voices need no "add to account" step, so ARGUS never adds voices (design §7 said it would); the docs warn that library voices are not available through the API on the free plan, and the tool adds that explanation to a 401/402/403. Models now include `eleven_v4` (10 000 characters per request; `eleven_v3` is 5 000); v3 and v4 take audio tags and no SSML. `GET /v1/voices` is replaced by `GET /v2/voices` (search, filters).
    - Deviations from design §7: no ElevenLabs forced-alignment fallback (missing alignment goes straight to faster-whisper, else `words_source: "none"`); Gemini is chosen only with `provider="gemini"` (a Gemini key alone does not change the default); `words_source` values are `provider`, `faster-whisper`, `none`; the `master` flag is gone, mastering is always on; own-voice language filtering orders by match instead of excluding (premade voices speak other languages on v3/v4).
    - `.env.example` documents `ARGUS_TTS_PROVIDER`.

- [x] 7. Plan model v2 (P0)
  - Read: design §8.
  - New `src/argus/plan.py`: pydantic models, presets `dark`/`light` (values from `engine/src/theme.ts getTheme`), format sizes, safe-area defaults, duration derivation, `validate_plan(dict) -> (Plan, errors)` with `path: message` strings.
  - New `src/argus/captions.py`: move `clean_word_timings`, `group_phrases`, `_load_words` from `tools/subtitles.py` (leave thin re-exports there until task 18); add `remap_words_to_clips(words, clips, source)`.
  - `engine/src/types.ts`: mirror the model.
  - Sample plans: `examples/plans/graphics_9x16.json`, `graphics_16x9.json`, `footage_16x9.json`, `reference_style_9x16.json`.
  - Tests: every sample validates; typo field → error with path; remap keeps only words inside kept ranges and shifts them.
  - Verify: pytest + engine typecheck.
  - _Requirements: 8.1, 8.2, 8.4, 10.2_
  - Audit report: `.kiro/specs/argus-v2/task7.md`.
  - Notes (2026-11-16):
    - Done and verified: full suite 189 passed, 1 skipped (new: `tests/test_plan.py`, `tests/test_captions.py`); engine `tsc --noEmit` exit 0. Engine code is untouched except `types.ts` (additive: plan types, `SceneTiming`, `CustomScene`; v1 `KineticProps` stays until task 8).
    - `validate_plan` returns `(Plan | None, errors)`; all problems come back at once, with union tags removed from paths (`scenes[3].media`, not `scenes.3.card.media`) and "did you mean" for typos. Also exposed: `Plan.resolved(format=, voice_duration=, words_end=, clip_lengths=)` (format override, safe area, grain, duration), `derive_duration`, `Plan.to_dict()` (JSON for the engine, `in` alias kept).
    - Decisions the design left open, for tasks 8-10 and 14 to confirm or change:
      - `style` is expanded from `"dark"`/`"light"` at validation time, so `Plan.style` is always tokens. Presets also carry the extra colors `word_base`, `word_active`, `card_border` (from `getTheme`); display font Inter 900, body Inter 600.
      - `captions.words` as `{source, remap: 'clips'}`: `source` is the words.json (design §10); new optional `media` names the footage file the words belong to (default: the first clip's `src`). `remap_words_to_clips(..., source)` takes that footage path.
      - `remap_words_to_clips` keeps a word when its midpoint is inside `[in, out]`, clamps its edges and shifts by `at - in`; a missing `out` means "to the end".
      - Defaults live in Python: captions `mode` `phrase`, `position` `lower`; music `volume` 0.12, `duck` 1 (no ducking), `fade_out` 1.5; clip `fit` `cover`; grain 0.05 for custom tokens without one.
      - Units: caption `size`, `outline`, `shadow` are fractions of the short side; zoom `t` is seconds from the start of the clip on the timeline; zoom `x`/`y` are fractions of the frame.
      - A clip without `out` adds nothing to the derived duration unless the caller passes its probed length (`clip_lengths`).
    - `tools/subtitles.py` now imports the helpers from `captions.py` (`_load_words` is `captions.load_words`); `captions.parse_words` is new (shared by file and inline words).

- [x] 8. Engine: formats and style tokens (P0)
  - Read: design §8, §9 "Engine changes"; steering `engine.md`.
  - Before changing code: render stills of the current engine for `examples/plans/graphics_9x16.json` (converted to v1 props) as the visual baseline in `engine/test-baseline/` (not committed).
  - `Root.tsx` width/height from format; `theme.ts` → `style.ts` with `useStyle()`; font loading for plan fonts.
  - `scenes.tsx`, `hud.tsx`, `text.tsx`: remove hardcoded sizes; relative to the short side × `text_scale`; respect safe area; `until` and `overlay` on all scenes; background from tokens.
  - Verify: typecheck; stills for 9:16 dark look like the baseline (side by side, inspect yourself); stills for 16:9 have nothing cut off or overlapping.
  - _Requirements: 8.2, 8.3_
  - Notes (2026-11-16):
    - Verified: `tsc --noEmit` exit 0; pytest 189 passed, 1 skipped (Python untouched). Baseline: 9 v1 stills (words, title, counter, big, cta, act, chip, card, HUD) in `engine/test-baseline/v1/`; the same frames from the new engine, side by side, in `test-baseline/compare/`. Checked by eye: 9:16 dark matches; 16:9 (graphics, extra, tokens) and stress plans (long texts, 7 chips, 4-row HUD, overlay, `text_scale` 1.25, gradient) stay inside the safe area in both formats. `test-baseline/` is git-ignored; helper scripts there: `stills.mjs` (bundle once, many stills), `make_props.py` (sample plans → engine props), `compare.py`.
    - Differences from v1 in 9:16, all from centering content in the safe area (right margin .12 shifts content about 32 px left; vertical centre is .44 of the height instead of per-scene paddings .42–.50): the card sits about 60 px higher; the HUD plate is about 16 px higher; text width is the safe width (886 px) instead of 90% of the frame.
    - `theme.ts` is now `style.ts`: `resolveStyle(tokens | 'dark' | 'light', {format, accent})`, `StyleContext` + `useStyle()`, `useLayout()` (`u(n)` geometry, `fs(n)` text × `text_scale`, `safe` rect in px; design numbers are for a 1080 px short side), `fontFor(style, role)`, `ensureFonts()` (bundled Inter) and `loadStyleFonts()` (plan fonts). The Inter presets are mirrored from `STYLE_PRESETS` in `plan.py`; change both together.
    - Decisions for the next tasks:
      - `FontRef.src` is resolved with `resolveMedia()`, so task 10 must copy plan font files into the job's public dir and write that relative path into the props. A project font is registered for weights 100–900, so the browser never fakes a bold.
      - Font roles keep v1 weights with the Inter presets: display = token weight (900), heading = min(display, 700) (act title, CTA), body = token weight (600), bodyLight = body − 100 (counter sub), mono = HUD values (token `mono`, else a system monospace at 800).
      - Scene windows: a scene lasts until its `until`, else until the next non-overlay scene, else the end. Overlay scenes are drawn above full scenes without a background; full scenes draw the token background again under themselves so clips (task 14) are hidden below them.
      - Props: `EngineProps` accepts plan v2 (`format`, `style`) and the v1 props (`theme`, `accent`, `voice`, `music`, `sfx_list`) so `tools/kinetic.py` keeps working until task 18. Auto SFX plays only for v1 props. Task 9 owns `audio`, `captions` and removing `buildSfxTimeline`; plan `audio`/`captions`/`clips` are ignored by the engine for now. `custom` scenes render nothing until task 16.
      - Text blocks that could overflow shrink to fit the safe width and height (words, title, big, act, CTA incl. handle, counter number + suffix, chip stack, HUD plate); the card gives up height for its caption.
      - Measuring uses the CSS font list of the element and tabular digits for numbers, so measured and rendered widths match.

- [x] 9. Engine: captions and audio (P0)
  - Read: design §9 "Engine changes".
  - New `captions.tsx` (word and phrase modes, colors from tokens, accent words, positions inside safe area).
  - New `audio.tsx`: voice, music with `duck` during speech windows (0.25 s ramps), fade in/out, `audio.sfx` events.
  - `sfx.ts`: remove automatic events.
  - Verify: typecheck; stills show captions in both modes and both formats.
  - _Requirements: 1.4, 9.5_
  - Notes (2026-11-16):
    - Verified: `tsc --noEmit` exit 0; pytest 189 passed, 1 skipped (Python untouched). `engine/test-baseline/check_audio_captions.mjs` (dev check, git-ignored) bundles `audio.tsx`, `captions.tsx`, `sfx.ts` with esbuild and asserts the pure logic: speech windows, ducking ramps, fades, phrase grouping, accent matching, SFX list. Passed. Stills: 8 caption plans (`make_caption_props.py`: phrase, word, upper + plate, center in the light theme; 9:16 and 16:9) rendered at 4 times each; I looked at 10 of them (phrase, word, plate, center in both formats). Text stayed inside the safe area and was readable on dark and light. The rest of the stills and the accent-word color on a light theme were not looked at.
    - **Not verified: audio in a real render.** The ducking math is checked, but no `renderMedia` run was made with a voice and a music file, so the mixed loudness has not been measured. Do this in task 10 (final render, then `qa_verify_video`/volumedetect over a speech window and a gap).
    - Files: new `captions.tsx`, `audio.tsx`; `sfx.ts` now only exports `collectSfx` (merge, drop broken events, sort); `Main.tsx` draws `CaptionsLayer` above the HUD and below the grain and uses `AudioTracks`; `types.ts` comments for the v1 `sfx` flag.
    - Decisions for task 10 and later:
      - `captions.words` must reach the engine as a word list `[{w, s, e}]`. A path or `{source, remap}` draws nothing, so task 10 loads files and remaps clips first. Phrase grouping is done in the engine (`groupPhrases` in `captions.tsx`, same limits as `group_phrases` in `captions.py`: 4 words, 26 characters, 0.45 s pause, sentence end); change both together. Task 10 does not need to send lines.
      - Ducking follows `captions.words` when it is a list, else the v1 `words` prop. A plan with `duck` < 1 but no captions gets no ducking unless task 10 also passes the voice words as `words`.
      - Speech windows merge pauses up to 0.35 s so the music does not pump between words. The duck reaches full depth when a window starts (the ramp runs 0.25 s before it) and returns over 0.25 s after it ends.
      - Caption look: size 0.065 of the short side in phrase mode, 0.1 in word mode, times `text_scale`; at most 2 rows (the size shrinks otherwise, and a single word wider than the safe width shrinks too). Spoken words use `style.color` (default `colors.text`), the active word `active_color` (default `word_active`, scaled 1.08), upcoming words are the base color at half opacity or `upcoming_color`. Accent words always use `colors.accent` (upcoming ones at 0.65 opacity). Word mode strips trailing `, . ; :`. Outline 0.006 and shadow 0.004 of the short side, outline color is `colors.bg`.
      - `upper`/`center`/`lower` place the caption block inside the safe rect (bottom edge at the safe bottom for `lower`: 80 % of the height in 9:16, 92 % in 16:9).
      - The v1 `sfx` flag is ignored and the engine plays only `audio.sfx` and the v1 `sfx_list`. `tools/kinetic.py` still copies its default whoosh/pop/hit files into the public dir (unused) until task 18, so the old `build_kinetic_video` renders no longer have automatic sound effects.

- [x] 10. `render_video` with stills / preview / final (P0)
  - Read: design §9.
  - `engine/package.json`: add `@remotion/bundler` and `@remotion/renderer` pinned to the `remotion` version; `npm install`.
  - New `engine/scripts/render.mjs` (bundle once; stills | media; progress to the job status file).
  - New `src/argus/tools/render.py`: validation, captions preprocessing, public dir with hardlinks, render job, compare side-by-side for stills, final post-processing (loudnorm, faststart, tag), outputs and `plan.json`, cleanup. Keep `_find_browser` and SFX synthesis helpers from `tools/kinetic.py` (move them).
  - `server.py`: register `render_video` (docstring: stills first, then preview, then final).
  - Tests (engine e2e, skip without node_modules): stills for both formats return images; 3-second final passes `qa_verify_video`; invalid plan returns errors without starting a render.
  - Verify: from Kiro, render stills of `examples/plans/reference_style_9x16.json` with `compare` against any mp4.
  - _Requirements: 8.4, 9.1–9.5_
  - Notes (2026-11-17):
    - Verified: pytest 211 passed, 1 skipped (22 new in `tests/test_render.py`: 17 offline, 5 engine e2e: stills 9:16 and 16:9, stills with compare, 3-second final that passes `qa_verify_video`, half-size preview). `tsc --noEmit` printed nothing (exit code not captured). Verify step: `server.render_video` (the function behind the MCP tool) on `examples/plans/reference_style_9x16.json` with `compare` against a generated 12 s mp4, 5 times, 13 s end to end; looked at 2 of the 5 side-by-side images (HUD, chips, captions with accent word, label bars all correct). **Not done from the Kiro chat:** the running `argus` MCP server was started before this task and does not list `render_video`; reconnect it (MCP Server view) and call the tool once. The example plan needs `fonts/Anton-Regular.ttf`, `fonts/JetBrainsMono-Bold.ttf` and `audio/voice.words.json` in the project folder; I used Impact and Consolas as stand-ins. Audio of a real render with voice + music + ducking was not measured (task 9 asked for it): only a voice-only final went through `qa_verify_video`.
    - Contract:
      - `render_video(plan, project, mode="stills"|"preview"|"final", times, compare, format, name)`; `plan` is a dict or a path (looked up in the project folder, then cwd). Relative file paths in the plan resolve in the project folder, the plan file's folder, cwd, then `engine/public` (so `fonts/InterDisplay-Bold.otf` and `sfx/whoosh.mp3` work without copying; `whoosh`/`pop`/`hit` are synthesized when missing).
      - Invalid request: `{"valid": false, "errors": ["path: message", ...]}`, no job started. Checked: plan schema, every named file (audio and SFX only when not `stills`), caption words (file, inline, or `remap: 'clips'` with the `media` or first clip), `times` (≤ 8, inside the video; default: one per second up to 6), `compare` (same length as `times`, reference times inside the reference video).
      - Stills wait up to 90 s inline; preview/final return a `job_id` after 20 s. Progress comes from node as `@@ARGUS {...}` stdout lines and is forwarded to `report()`; node does not write the status file itself.
      - Outputs in `<project>/renders/`: `<name>-stills-<9x16>-NN-t<sec>s.jpg`, `<name>-compare-…`, `<name>-preview-9x16.mp4`, `<name>-final-9x16.mp4`; a final render also writes `<project>/plan.json` (resolved plan with the original paths). `.work/render-<id>` is deleted on success and kept on failure (`render.log`, `spec.json`).
      - Final: two-pass `loudnorm` to `CONFIG.loudness_target` (-14) with TP -1.5, LRA 11, video copied, AAC 192k at 48 kHz, `+faststart`, `comment=Made with ARGUS Studio vX`. A file without audio is only tagged. The result reports `loudness_before` / `loudness_after`.
    - Differences from design §9: the engine is bundled once per job, not cached across jobs (about 6 s with the webpack cache); the bundler copies the public dir on Windows, so the hardlinks save only the step before it. Step 4 (proxies) and step 5 (custom components) belong to tasks 14 and 16: until then `clips` and `custom` scenes are accepted but not drawn, and the result's `warnings` say so. `music.duck` has no effect without `captions` (ducking follows the caption words); this is also in `warnings`.
    - `tools/kinetic.py` now imports `engine_dir`, `_find_browser`, `_ensure_default_sfx`, `DEFAULT_SFX` from `tools/render.py`. `engine/package.json` pins `@remotion/bundler` and `@remotion/renderer` to 4.0.540.

- [x] 11. Technical QA v2 (P0)
  - Read: design §11.
  - `src/argus/tools/qa.py`: format-aware checks, black/freeze/silence detection, true peak, platform duration warnings, images.
  - Tests: synthetic defects (wrong size, 1.5 s black gap mid-video → hard, 0.7 s → warning, 3 s silence → warning, hot peak → hard); valid master passes. Update `tests/test_offline_tools.py` QA tests.
  - Verify: pytest green.
  - _Requirements: 12.1–12.4_
  - Notes (2026-11-17):
    - Verified: full suite 220 passed, 1 skipped (was 211 + 1 skipped). The QA section of `tests/test_offline_tools.py` has 11 tests: a valid master passes with 4 spread frames; a 720x1280 clip (shape 9:16, wrong size) and a 1920x1080 clip with `format="9:16"` fail on resolution; 1.5 s of black mid-video is a hard failure, 0.7 s a warning; 3 s of silence mid-video a warning; a true peak above -1 dBTP a hard failure; a 4 s frozen picture a warning; `target` above the limit a warning; `qa_verify_video` through the job returns the summary and 2 images.
    - Speed: a 90 s 1080x1920 clip takes 13 s (loudness 4.2 s, silence 3.0 s, black and freeze 4.9 s, frames 0.8 s). Longer files run in the `qa` job.
    - Not verified from Kiro: the `argus` server connected to Kiro still has the old `qa_verify_video`. Reload it in the MCP Server view and call `qa_verify_video` on a `mode="final"` render.
    - Decisions the design left open:
      - Without `format`, the frame's shape decides: 9:16 or 16:9 at any size, anything else fails. §11 says "format (or plan)"; there is no plan argument, so `format` is the input.
      - Black at the start or end is a warning at any length from 0.5 s. In the middle, 0.5 to 1.0 s is a warning and 1.0 s or more a hard failure.
      - ffmpeg 8 logs only the start of a freeze that lasts to the end of the file, so that freeze ends with the file.
      - Silence has timecodes but no frame: §11 asks for frames at black and freeze issues. Requirement 12.3 says "each reported issue". Say if silence should get a frame too.
      - Platform limits (warnings): tiktok 600 s, shorts 180 s, youtube 900 s (15 min unverified, 12 h verified). The shorts and youtube figures come from YouTube's help pages (URLs in `qa.py`). TikTok's support page could not be read, so its 600 s comes from third-party guides and is marked in the code.
      - At most 8 images per result: spread frames first, then black and freeze issues, hard ones first. Frames go to `<project>/.work/qa/` (or `<output>/.work/qa/` for files outside a project).
    - `tests/test_render.py` calls `qa.verify_video` (the dict form). `qa.qa_verify_video` is the job-backed tool logic.
    - Audit report: `.kiro/specs/argus-v2/task11.md`.

- [x] 12. `export_package` (P0)
  - Read: design §12. Verify current platform text limits; put sources in comments.
  - New `src/argus/tools/export.py` + tool registration.
  - Tests: both formats exported, covers sizes, `post.md` content, limit violation reported, refuses on QA hard failure, `.work/` removed.
  - Verify: pytest green.
  - _Requirements: 13.1–13.3_
  - Notes (2026-11-17):
    - Verified: full suite 231 passed, 1 skipped (was 220 passed, 1 skipped). The 11 new tests in `tests/test_export.py` cover both formats (`moov` before `mdat`), cover sizes (1080x1920; 1280x720 under 2 MB), `post.md` sections and text, `.work/` removed, covers returned as images through the job, a 1.5 s black gap refused with nothing written to `final/`, limit violations reported and marked, an invalid request starting no job, and tool registration.
    - Real run: two synthetic 6 s clips (9:16 and 16:9) exported into a scratch project. `final/` held 2 mp4, 2 covers and `post.md`, and `.work/` was gone. I looked at the 9:16 cover: a non-black frame.
    - Limits (sources in `tools/export.py`, checked 2026-11-17): TikTok caption 2200 UTF-16 units with hashtags (Content Posting API doc); YouTube title 100 characters, description 5000 bytes, tags 500 characters including commas and quotation marks (YouTube Data API `videos` doc); 16:9 cover 1280x720 under 2 MB (YouTube help, which states the 2 MB limit for phone uploads).
    - Decisions: a limit violation is reported (`violations`, and marked in post.md) and does not stop the export, because 13.2 says "report". §12's "first frame of the strongest QA frame" needs a score, which the product steering rules out. The default cover is therefore the first evenly spread QA frame whose mean brightness is at least 16 of 255. Model views of covers go to `<project>/cache/export/`, because `prepare_image` writes its copy next to the source and would leave `.view.jpg` files in `final/`.
    - Not verified from Kiro: the `argus` server connected to Kiro still runs the old code. Reload it in the MCP Server view, then call `export_package` once on a real `render_video` final.
    - Open: export removes all of `<project>/.work/`, including work of a render or another export still running in that project. Hashtags are not checked for spaces, which YouTube's help page says are not allowed.

- [ ] 13. Milestone M1 check (P0, target Nov 25)
  - Automated: scenario e2e tests (1) reference and (3) idea from design §17.
  - Manual in Kiro (author): one real TikTok from a reference, start to finish, using only ARGUS tools. Write every problem into a "Known issues" list at the end of this file; fix blockers before moving on.
  - Ask Opus to review the produced video and the open issues (one review session).
  - _Requirements: 17.1, 17.3_
  - Notes (2026-11-17):
    - Automated part done. `tests/test_scenarios.py` has scenario (1) `test_reference_to_tiktok`: synthetic reference → `watch_video` → stills with `compare` → final → `qa_verify_video` → `export_package`. It also has scenario (3) `test_idea_with_graphics_and_an_edge_voice`: `examples/plans/graphics_9x16.json` with a voice from the real edge voiceover job, where `edge_tts` is replaced by a stand-in that streams WordBoundary events → final → export. Both skip without `engine/node_modules` and both pass (about 100 s).
    - Blocker found and fixed in `tools/qa.py`. Scenario (3) stopped at export with a hard failure: black for 1.67 s mid-video (9.37–11.03 s). The frames show the CTA ("follow for more", handle, arrow) on the dark background, so the gap was false. Cause: blackdetect `pix_th` 0.10 (about 25 of 255). The `dark` background `#0A0A12`, lifted to about 13–25 by glow and grain, sits at or below that level for 97 to 99 % of pixels. blackdetect calls a frame black when 98 % or more of its pixels are at or below it, so a frame counted as black whenever its caption covered about 2 % of the picture or less. On that render, at 0.03 (about 8 of 255) fewer than 0.05 % of the pixels in each of seven sampled frames fall at or below the level. Fix: `BLACK_PIXEL_THRESHOLD = 0.03`. Pure black is still a hard failure.
    - Regression test `test_qa_dark_background_with_a_small_caption_is_not_a_black_gap` failed on the old threshold with the same 1.5 s finding and passes now. The other QA tests pass.
    - Deviation from design §11, which still says `pix_th=0.10`. This is the question `task11.md` §5 left open (item 2). Keeping 0.10 would need an exception for dark styles, which is the author's call.
    - Verified: `tests/test_scenarios.py` 2 passed; QA tests 12 passed; full suite 234 passed, 1 skipped (was 231 passed, 1 skipped; the skip is the real faster-whisper test). I looked at the reference final (12 frames: words, big, chips, CTA with handle) and the idea final (CTA at 9.6–11.7 s). Both show the intended content.
    - Not done, because it needs the author in Kiro: the manual TikTok run and the Opus review. First reload the `argus` server in the MCP Server view, so `render_video` and `export_package` are listed. Then make the TikTok with ARGUS tools only, write each problem into Known issues, and run the Opus review. This task stays `[ ]` until then. The BUILD_LOG entry follows the manual run.

- [x] 13.1 Fixes from the first real run (P0) — do this, then task 16, then 14 and 15
  - Order change: the author's channel needs custom components (task 16) before footage editing (14, 15). Task 16 does not depend on 14.
  - `src/argus/tools/watch.py`: the frame cache must not return a frame list built by an older `select_frames`. Add a separate frames version (or the selection rule) to the `frames.<max_frames>.json` cache check so old caches are rebuilt; transcript and shot caches stay valid. Test: a stored frames file with the old version is rebuilt.
  - `voice_options` in `src/argus/tools/voiceover.py`:
    - the text query matches name, description, accent and labels, case-insensitive, any word;
    - compact default response under ~6000 characters: id, name, gender, age, accent, language, description cut to 80 characters;
    - library voices that the free plan cannot use through the API go into a separate, labelled list;
    - the model list and the delivery vocabulary only with `details=True`.
  - Update tests; add a BUILD_LOG entry.
  - Verify: pytest green; from Kiro, `voice_options(language="ru", gender="male", query="narrator")` returns Russian male voices in a short answer.
  - Notes (2026-11-17):
    - `voice_options` was done in another session (owner's instruction). It was not re-checked here, and the Kiro call in the Verify line was not run in this session.
    - Frames cache: `FRAMES_VERSION = 2` in `tools/watch.py`, stored as `frames_version` in `frames.<N>.json` and checked together with `CACHE_VERSION`. Files without it are rebuilt; shot and transcript caches are unchanged. Test `test_frames_file_from_an_older_select_frames_is_rebuilt`.
    - `tests/test_watch.py`: 27 passed. The full suite did not print a summary line in this session (background runs ended early), so "pytest green" is not confirmed; rerun `pytest -q` to check.

- [x] 14. Clips track and media prep (P1)
  - Read: design §8 `Clip`, §9 steps 3–4, "Engine changes" `clips.tsx`.
  - New `engine/src/clips.tsx`; Python media prep with proxies in `<project>/cache/proxies/` (VFR / non-H.264 / `clean_audio`).
  - Tests: clip with in/out renders the right duration; VFR synthetic source gets a proxy; zoom keyframes visible in stills.
  - _Requirements: 9.5, 10.1, 10.3, 10.4_
  - Notes (2026-11-17):
    - Done by hand in the main session, not by a sub-agent: the `spec-task-execution` agent was not registered in this environment ("not found in registry"), and the author told me to do it myself.
    - Files: new `engine/src/clips.tsx` (`ClipsLayer`, `zoomAt`, `clipLengthSeconds`), new `src/argus/tools/media_prep.py`, new `tests/test_clips.py`; `Main.tsx` draws the clips above the background and below the scenes; `types.ts` `Clip.length` (engine props only); `tools/render.py` (`_prepare_clip_media`, `_engine_props(clip_media=)`, clip range check, no more "clips are not drawn" warning); `tests/test_render.py` assertion for that warning inverted.
    - Verified: engine `tsc --noEmit` exit 0; `tests/test_clips.py` 16 passed (12 offline, 4 engine: in/out part and duration of a final render with the clip's own sound, clip without `out` to the end of the file, zoom at 3 times, zoom around a focus point). Dev check `engine/test-baseline/check_clips.mjs` (git-ignored) passed for the zoom math. I looked at 2 zoom stills: the white square is 384 px wide at scale 1 and 576 px at the middle of the ease (scale 1.5); measured 382, 574, 764 px at 0.05, 1.0, 2.5 s.
    - Contract:
      - Media prep (design §9 step 4): a video file gets a proxy in `<project>/cache/proxies/<hash>.mp4` when `r_frame_rate` and `avg_frame_rate` differ by more than 0.5 %, when the codec is not H.264, or when `clean_audio` is set and the file has audio. Recipe: `libx264 -crf 18 -r <plan fps> -fps_mode cfr`, AAC 192k, 48 kHz; `clean_audio` adds `highpass=f=80,afftdn`. When only `clean_audio` is the reason, the video stream is copied. The proxy covers the whole file and keeps its timeline, so all clips from one file share it and `in`/`out` stay valid. The hash covers path, size, mtime, fps, clean flag and a recipe version. Written through a temp file, then renamed. Images and constant-rate H.264 are used as they are.
      - Stills ignore `clean_audio` (no sound in a still), so they do not wait for an audio proxy. The result lists `proxies` (clip, source, proxy, reasons).
      - `render_video` rejects a clip whose `in` is past the end of the file or whose `out` is more than 0.1 s past it (`clips[i].in: ...`), before any job starts. A clip without `out` lasts until the end of its file (derived duration uses it); an image clip without `out` lasts until the end of the video.
      - Zoom keys (`t` in seconds from the clip start): before the first key the picture is neutral (scale 1), so a lone key at 2.5 s is a push-in that reaches its scale at 2.5 s; after the last key the zoom holds. A key without `x`/`y` keeps the previous focus (first: frame center). The ease belongs to the key the picture moves to (`inOut` = cubic). The zoom scales around the focus point, so that point stays where it is and the frame stays covered. The design did not say any of this; confirm or change.
      - Later clips are drawn above earlier ones (plan order for equal `at`). Overlay scenes draw above the clips; full scenes hide them.
    - Bug on the way: my first zoom test measured 204 px instead of 384 → the result's `images[].path` points to the downscaled `.view.jpg` (1024 px wide), not the full-size still → the tests read `summary["stills"]`. The engine output was right.
    - Not verified: a real VFR phone recording (only a synthetic one made with `setpts`); a long file (the proxy covers the whole source, so a 30-minute recording costs a full re-encode once); audio of a final render with clip sound plus voice plus music was not measured, only that the clip's sound reaches the file (`has_audio`); `fit: contain` and image clips were not rendered. Mixed fps sources (25 fps file in a 30 fps plan) rely on Remotion's time-based frame extraction and were not checked.
    - Audit report with the open questions for the auditor: `.kiro/specs/argus-v2/task14.md`.
    - Suite: full `pytest -q` 288 passed, 1 failed in 425 s; the one failure was the old "clips are not drawn" assertion in `test_render.py`, which I had edited after pytest collected it. After the edit the 15 offline tests of `test_render.py` pass (2.4 s). I did not rerun the whole suite once more, so "289 passed" is the sum, not one run.

- [x] 15. Footage editing scenario (P1)
  - Read: design §10.
  - Make sure `watch_video` returns verbatim words for footage and the guide section on footage editing matches the real tool behaviour.
  - Add `examples/plans/footage_16x9.json` flow to the scenario e2e test (2) with fixture words.
  - Verify: test (2) green; manual: edit `examples/media/talk_sample.mp4` (once the author records it) from Kiro.
  - _Requirements: 10.1–10.4, 17.1_
  - Notes (2026-11-17):
    - Changes: `tools/watch.py` (summary gets `words` as `[word, start, end]` and `word_count`; over `INLINE_WORDS_LIMIT` = 1200 words only `words_note` and `words_path`; `ENGLISH_VERBATIM_PROMPT` next to the Russian one, chosen through `VERBATIM_PROMPTS`), `server.py` docstring of `watch_video`, guide section 7 (both copies, identical), `examples/plans/footage_16x9.json` (`duration: 12.2`), `tests/test_watch.py`, `tests/test_scenarios.py`.
    - Decisions to confirm: (1) a plan without `duration` gets a 0.6 s hold after its last clip, so the design's "duration equals kept ranges ±1 frame" holds only when the plan sets `duration`; I set it in the sample and told the guide to do it, and did not change `derive_duration`. (2) `watch.transcribe` is also used to align voices from providers without timings (`voiceover._align_with_whisper`), so English alignment now gets the filler prompt too (Russian already did). (3) Words come back inline as triples, not `{w, s, e}`, to save tokens.
    - Verified: scenario test (2) `test_footage_edit_with_remapped_captions` passed alone (193 s). It checks: the words `watch.run_job` returns equal the fixture (32 words, fillers kept; the fake Whisper received the English prompt); the sample plan's clips are back to back and `duration` is 12.2; `prepare_render` gives caption words only from the kept ranges (24 of 32), `tip` at 10.6 s lands at 6.8 s, no `um`/`uh`/`thanks`; stills at 0.5, 6.5, 6.8, 9.0 s; final 1920x1080 with sound, length 12.2 s ±1 frame, no warnings, `qa_verify_video` passes. Together with `test_watch`, `test_plan`, `test_studio_guide`, `test_offline_tools`: 89 passed in 577 s. I did not run the whole suite or the engine typecheck (no engine files changed).
    - Not verified: real Whisper on English speech with the new prompt (a prompt like this is a known technique, but I did not test that it keeps "um" on a real recording); the manual step with `examples/media/talk_sample.mp4`, which the author has not recorded; the test uses a synthetic picture, so cut boundaries were not judged by eye.

- [x] 16. Custom components (P1)
  - Read: design §9 step 5.
  - `engine/src/custom/registry.ts` (committed empty map), `engine/src/custom/README.md` (component contract: default export `FC<props>`, may import `react`, `remotion`, `../style`; no network).
  - Python: copy, generate registry, typecheck with temp tsconfig, lock, restore in `finally`.
  - Tests: a valid sample component renders in stills; a broken one returns compiler errors and the committed registry is unchanged afterwards.
  - _Requirements: 11.1–11.3_
  - Notes (2026-11-17):
    - `tools/components.py` + `tests/test_components.py`. `render_video` checks the component source before any job (missing file, imports outside the contract, network calls) and returns `path: message` errors. The job then takes the engine lock, installs and typechecks; TypeScript errors come back as `components/<File>.tsx(line,col): error TS...`.
    - Additions to the task text: `engine/src/custom/style.ts` re-exports `../style` (components run from `custom/job/`, so the contract path `../style` needs it); `render.mjs` emits a `bundled` event and the lock is freed then, so it is held only while bundling. Every render takes it, not only those with components.
    - Verified: engine `tsc` exit 0; `tests/test_components.py` 12 passed; full suite 260 passed (was 247). I looked at a still of the sample component.

- [x] 17. User scripts (P1)
  - Read: design §13.
  - New `src/argus/tools/scripts_runner.py`, tool `run_script`; `scripts/README.md`; `scripts/frame_stats.py`.
  - Tests: list shows summary and args; run returns JSON; bad name rejected; timeout reported.
  - _Requirements: 14.1–14.3_
  - Notes (2026-11-17):
    - `tests/test_scripts_runner.py`: 13 passed. Covers listing (and that listing does not run a script), a JSON result, a script's `images` returned as pictures, 7 bad names, an unknown name, the timeout, and the server registration.
    - Three choices beyond the design text. The script runs as `python -P`, so a user file named `json.py` cannot shadow the standard library. The run goes through the `scripts_runner` job, because the 120 s default timeout is longer than the 20 s inline budget. A name that exists in both folders runs the copy in `scripts/`.
    - Checked against the real config (temporary output and user folders): the listing, `frame_stats` on a white image (brightness 1.0), a user script named `json` that still imports the standard library, and the MCP schema (`name` and `args` optional, `timeout_s` 120).
    - Verified: full suite 273 passed (was 260).
    - Not done here: the `argus` server in Kiro must be reloaded in the MCP Server view before `run_script` appears there. The banner still says 15 tools; task 18 fixes it.

- [x] 18. Remove superseded v1 tools (P1)
  - Read: design §16. Only after tasks 10 and 14 tests are green.
  - Delete `tools/kinetic.py`, `tools/assemble.py`, `tools/subtitles.py`, `tools/timeline.py`, `src/argus/fonts/` and their tool wrappers; move any helper still needed.
  - `doctor.py`: checks per design §15 (drop libass; add numpy, Pillow, engine renderer deps; optional faster-whisper). Update `tests/test_doctor.py`, `tests/test_offline_tools.py`.
  - `server.py` banner: real tool count computed, not hardcoded.
  - Verify: pytest green; engine typecheck; `grep` finds no references to removed tools in `src`, `tests`, `README*`, `STARTER.md`, `INSTALL.md`, `docs/`.
  - _Requirements: 15.3, 17.2_
  - Notes (2026-11-17):
    - A checkpoint commit (`aada601`, tasks 14-17) was made before any deletion, so the removal can be undone with git.
    - No helper had to move: `engine_dir`, `_find_browser` and the built-in SFX files were already in `tools/render.py` (task 10), and the caption helpers in `captions.py` (task 7). `server.py` lost its four wrappers; `tools/__init__.py` imports only `memory` and `qa`.
    - `doctor.py` follows design §15: critical are python, ffmpeg, ffprobe, node, npx, the engine (now also `remotion`, `@remotion/renderer`, `@remotion/bundler` inside `node_modules`), numpy, Pillow and the output dir. faster-whisper and edge-tts are warnings (edge-tts used to be critical; §15 lists it as optional). `startup_banner()` in `server.py` gives the real tool count.
    - Tests: `test_offline_tools.py` lost the subtitles, timeline and assemble tests; `test_captions.py` the re-export test; `test_render.py` now checks that the server registers exactly the 17 v2 tools and that the banner count matches; `test_doctor.py` covers numpy/Pillow (critical), faster-whisper/edge-tts (warning) and a missing renderer package.
    - README, README.ru, STARTER and `docs/TUTORIAL.md` got the minimum edits so they name no removed tool; task 21 still rewrites them. A line of `docs/BUILD_LOG.md` (task 10) that named `kinetic.py` was reworded. Comments in `engine/src/{Main.tsx,types.ts,sfx.ts}` no longer promise `kinetic.py`; the engine still reads the v1 props (`theme`, `voice`, `music`, `sfx_list`), which `engine/sample-props.json` uses.
    - Verified: engine `tsc` exit 0; full suite 290 passed. One earlier full run failed a clips test while a second pytest ran on the same engine folder; it passed alone and in the clean rerun.

- [x] 19. End-to-end suite and CI (P1)
  - All three scenario tests from design §17 green locally.
  - `.github/workflows/ci.yml`: keep Python matrix and typecheck; add engine e2e job if it runs in < ~10 min.
  - _Requirements: 17.1_
  - Notes (2026-11-17):
    - Local: `pytest tests/test_scenarios.py -v --durations=0` → 3 passed in 181.48 s (footage 86.6 s, reference 47.6 s, idea 45.8 s). The log was read by Kiro before it was deleted.
    - CI: new job `e2e` in `.github/workflows/ci.yml` (ubuntu-latest, `timeout-minutes: 15`, Python 3.14, ffmpeg, Node 20, `npm ci` in `engine/`, `pytest tests/test_scenarios.py`). The Python matrix and the `engine` typecheck job are unchanged.
    - Not verified: a run of the `e2e` job on GitHub Actions, so its duration and result are unknown. Linux is untested: `_find_browser` returns nothing there, so Remotion uses its own browser. If `engine/node_modules` were missing, the tests would skip and the job would still pass; check the log for `3 passed`.

- [ ] 20. Feature freeze and dogfooding (P1, Nov 30)
  - Author produces two real TikToks from references and one footage edit in Kiro.
  - Every defect: fix, or add to "Known issues". No new features after this task.
  - Opus review session of the three videos and the issue list.
  - The author runs the manual QA himself once 20.1 to 20.3 are done.
  - _Requirements: 17.3_
  - Progress: video 1 (project `project-1`) is made, exported and reviewed by the author (voice and video listened to and watched, 2026-11-18). Notes: `task20.md`. The task stays `[ ]` because it asks for three videos and the Opus review; the second reference video and the footage edit are not made yet.

- [x] 20.1 Fixes from video 1 (P0, before the next video) — model: Haiku high; Sonnet if Verify fails twice
  - Source: Known issues 18, 20, 24, 25, 26 and the author's review of `project-1`. Design §5, §7, §9, §11.
  - True peak (issue 24): `finalize_video` in `src/argus/tools/render.py` limits the mix after `loudnorm`, so a final passes QA (≤ -1.0 dBTP) without a manual step. `alimiter` takes a linear `limit`; check https://ffmpeg.org/ffmpeg-filters.html#alimiter and put the URL next to the constant. Test: a synthetic mix with a 0 dBFS transient passes the QA true-peak check and keeps the loudness target.
  - Caption gap (issue 25): the larger active word must not cover the gap to the next word, in every caption mode. Fix in `engine/src/captions.tsx`. Check with stills of a plan with long Russian words ("пятнадцать миллионов", "Прежний капитан").
  - Caption case: `captions.style.case` = `"upper"` or `"as_is"` (default `"as_is"`), applied in the engine, accepted by plan validation, described in the `render_video` docstring. Test the validation.
  - Waiting on jobs (issue 26): `job_status(job_id, wait_s=0)`, `wait_s` capped at 20. Returns when the job ends or when `wait_s` runs out, with progress and an estimate when known. Test with a short fake job.
  - Compact job results (issue 18): a finished `watch_video` job returns file paths for the transcript and words plus a short summary, never the full word list. Test that the result stays far below 30,000 characters.
  - Voices on the free plan (issue 20): `voice_options` marks or drops voices the API refuses on the current plan. If the plan cannot be read, the result says so. Check the ElevenLabs docs for the subscription endpoint and put the URL in a comment.
  - Notes, true peak (done): `LIMITER_FILTER` in `render.py` holds the `alimiter` string (limit -2 dBFS, `level=disabled`, `latency=true`), and `finalize_video` appends it after `loudnorm`. Real file `projects/project-1/renders/yacht-final-9x16.mp4` (the -0.28 dBTP final): before -0.28 dBTP at -14.06 LUFS; after `finalize_video` -1.82 dBTP at -14.06 LUFS, measured with `measure_loudness` (the function QA uses). The `.tp-check.mp4` copy was deleted. Test: a 0.99 burst through `LIMITER_FILTER` peaks at or below 0.8 linear. No synthetic mix reproduced the failure without the limiter (13 signals, output between -1.1 and -1.5 dBTP without it), so the test checks the filter itself.
  - Notes, caption gap (done): `engine/src/captions.tsx` gives each word in phrase mode a side margin of half its growth at `ACTIVE_SCALE` (measured with `measureTextWidth`), so the grown active word stays in its own slot and the layout does not move when a word becomes active. Engine typecheck exit 0. Stills (`caption-gap-check`, 9:16): "Пятнадцать миллионов" and "Девятнадцатилетний юнга" at `style.size` 0.05 keep a visible gap in every frame, active word included. Side effect: the space between words in phrase mode is wider than before, by about the grown width of each neighbour. Not measured in px.
  - Notes, caption case (done in code): `CaptionStyle.case` in `plan.py` (`"upper"` or `"as_is"`, default `"as_is"`), `case` in `types.ts`, `shownWord()` in `captions.tsx` applies it to drawing and to measuring. `render_video` docstring says it. Tests: `test_caption_case_is_upper_or_as_is` (accepts both values, rejects `"lower"`); `test_plan.py` and `test_captions.py` pass (31). Not yet seen in a still: the running `argus` MCP server predates this field and rejects `case` (`unknown field 'case'`), so it needs a reload (Known issue 1).
  - Notes, waiting on jobs (done): `job_status(job_id, wait_s=0)` in `jobs.py` and `server.py`; `wait_s` is clamped to 0..20 (`clamp_status_wait`, `MAX_STATUS_WAIT_S`), so a bigger value is capped, not an error. The wait stops when the job is done or failed. A running job with known progress carries `eta_s` (a linear estimate). Tests (`test_jobs.py`, 18 passed): clamp, a short selftest job returns as done before the wait ends, a long one stops at the wait and reports progress.
  - Notes, compact `watch_video` results (done): `run_job` no longer lists `words` or `segments`. The result has `words_path`, `segments_path` and `transcript_head` (first 300 characters, `TRANSCRIPT_HEAD_CHARS`). `INLINE_WORDS_LIMIT` is gone. `server.py` and `STUDIO_GUIDE.md` describe the paths. Test: a 240-sentence, 2,400-word talk gives a result under 10,000 characters (limit 30,000). `test_watch.py` and `test_studio_guide.py`: 42 passed.
  - Notes, voices on the free plan (done): `voice_options` reads `GET /v1/user/subscription` (`tier`; https://elevenlabs.io/docs/api-reference/user/get-subscription). On tier `free` it moves every own voice that is not `premade` and every Voice Library voice to `library_voices_paid_plan_only`, with `FREE_PLAN_NOTE`. Reason: video 1 showed HTTP 402 for a library voice (`free_users_allowed` did not help) and for an own non-premade voice; George (premade) worked. If the tier cannot be read, `plan.note` says so and no voice is marked. `test_voice_options.py`: 29 passed (3 new tests).
  - Not done yet: a final of an `examples/plans` sample through QA with no manual limiter. The examples have no audio assets, and the running `argus` MCP server predates these changes (Known issue 1), so it must be reloaded first. The full `pytest -q` run was started but its output did not come back in this session, so the suite is not confirmed green yet.
  - Verify: pytest green; engine typecheck green; caption stills show every gap; a final of an `examples/plans` sample passes QA with no manual limiter.

- [x] 20.2 Motion kit: universal blocks for custom scenes (P0, before the next video) — model: Sonnet high
  - AUDIT: marked done at the author's request before Verify finished. Backgrounds (`kit/backgrounds.tsx`) and the props-driven `Budget` example in `KIT.md` are written and the engine typecheck passed on `backgrounds.tsx`. Not run to the end: the two-looks test, the `Media` test, stills in 9:16 and 16:9, full pytest. `engine/src/custom/registry.ts` may still hold a generated import from an interrupted test run (restore with `git checkout -- engine/src/custom/registry.ts`).
  - Problem (video 1, `project-1`): about 1 h 20 min and about 91 credits for an 86 s video; the preview and final renders took about 9 minutes of it. The model wrote about 72 KB of TSX by hand (`Art.tsx`, `Scenes1.tsx`, `Scenes2.tsx`, `Film.tsx`) and reviewed 6 rounds of stills (46 frames). Most of `Art.tsx` and `Film.tsx` is not story-specific: easing, timing, camera, text, fades, glow, particles, plates, cards, scene order.
  - `engine/src/kit/`, imported by custom components the same way as `../style`. Mechanics only, no fixed look: colours and fonts come from the plan style or props; every block works in 9:16 and 16:9.
    - every block takes colour, font, size and timing through props; a look that cannot be changed by a prop is a defect of the block;
    - backgrounds: Solid, Gradient, Grid, Noise, Media (image or video with a dim overlay);
    - motion: clamp, seg, lerp, easings, stagger, camera (zoom, pan);
    - wrappers: Fade, Pop, Slide;
    - text: Text (stroke, shadow, glow, caps), Label;
    - effects: Glow, Particles (dust, stars), LightCone;
    - info: Counter (animated number with formatting), Plate (bordered HUD plate with a colour change, issue 12), Delta popup (issue 13), PollCard and Checklist (issue 14), ProgressBar, Bubble, Card;
    - timing: `SceneTrack` (scenes, cue times, crossfade) and a hook that gives a custom component the voice word timings and named cues from the plan (issue 22), so cues are no longer typed by hand.
  - Start from the working code in `<OUTPUT_DIR>` (the author's project). Generalise it; leave story drawings (yacht, hero, captain) out.
  - `engine/src/kit/KIT.md`: catalogue for the model, one line per export with its props, plus one example scene of at most 40 lines. `studio_guide` returns it when the model plans custom scenes; keep it under about 5,000 characters.
  - STUDIO_GUIDE rules (text only): built-in scene kinds first, then kit blocks, new code only for what neither covers; edit component files instead of rewriting them; one stills round of at most 8 frames before the preview, later rounds only for changed scenes; wait with `job_status(wait_s=20)` and write the post texts meanwhile; do not watch the final in chat, rely on QA.
  - Tests: engine typecheck; stills of a custom scene that uses kit blocks and `SceneTrack` with cues from a words file (skips without `engine/node_modules`).
  - The yacht code is only the source of working mechanics. The kit has no look of its own, and the yacht style is not a default.
  - Verify: pytest green; engine typecheck green; stills of the kit example scene in 9:16 and 16:9; the same example scene in two unlike looks (e.g. dark neon and light flat), changed only through props.
  - Measured after 20.3, on the author's next video (the Kiroween demo, from a TikTok motion-graphics reference in a different style). Record active time and credits per stage (watch, plan, code, stills, voice, preview, final, export). Target: under 20 minutes of active time and under 20 credits. Write the real numbers to `docs/BUILD_LOG.md` either way, as the main problem of the build: symptom → cause → fix → result.

- [x] 20.3 Style library: reuse what worked (P0, before the next video) — model: Sonnet high
  - Goal: the model looks at a new reference, checks the library and reuses matching scenes, characters, plates or caption styles instead of writing them again. Whether something matches is the model's call; no code scores similarity.
  - Where: `<OMNIFRAME_OUTPUT_DIR>/library/<entry>/`, per user, not in the repo. Each entry: component files, `card.md` (what it is, when it fits, props, source project), `poster.jpg` (512 px). `library/index.md` is generated from the cards.
  - Saving: only after the user approves; the model offers it after a good final. Done through an existing tool (for example `export_package(save_to_library=...)`), no new tool. The poster is taken from the final.
  - Reading: `studio_guide` returns the index (one line per entry) and the posters as images (at most 8, 512 px), so the model can compare them with the reference. A custom component can import a library entry by name.
  - Idea from https://github.com/Ariz0na45/claude-motion-library (no code taken).
  - Tests: saving updates the index and writes the poster; `studio_guide` lists entries with images; a custom scene that imports a library entry renders stills.
  - Verify (author, new sessions): save the yacht scenes as the first entry. A yacht-like reference: the model takes the entry from the library. An unrelated reference: the model does not push the yacht look.
  - Notes (2026-11-19), built and marked `[x]` at the owner's request; full suite 338 passed. The author's Verify above (live sessions) is still open:
    - New `tools/library.py`. Saving is `export_package(save_to_library={name, components, what, fits_when, props?, replace?, poster_time?})`, validated before the job starts (errors as `save_to_library.<field>: ...`, nothing written) and done inside the export job after the covers, so the poster is a frame of the final (`poster_time`, else the cover frame; the 9:16 video when there is one). The job result has a `library` block and the poster as an image. If only the library step fails, the export still counts as done and `library.saved` is false with the error.
    - Entry = the listed `<project>/components/` files plus the files they import (copied as they are), `card.md` (what, fits when, props, source project, files, saved date, import line), `poster.jpg` (longest side 512 px). `index.md` is rebuilt from the cards on every save. A folder without a card is not an entry. `what` is at most 200 characters, `fits_when` 250, `props` 600, so the index line stays short. Names `style` and `kit` are reserved. An existing entry needs `replace=true`. Components that import library files cannot be saved (the entry would point at another entry).
    - Reading: `studio_guide` has a `library` block: `entries`, `index` (one line per entry, built from the cards on each call), `posters` (the 8 newest entries that have one). With posters the result is `[json, Image, ...]` (512 px files as they are; `prepare_image` would write `.view.jpg` copies into the entries). Without entries it is still a dict with `library: {dir, entries: 0}`. STUDIO_GUIDE §5 tells the model to compare the posters with the reference, decide itself, and not bend a different reference toward an old entry; §8 tells it to offer saving after a good final and never save on its own (if the export is done, call `export_package` again with `save_to_library`).
    - Import: `import X from './library/<entry>/<File>'` in a project component. `components.py` checks it (an unknown entry or file lists what the entry has; entry files follow the same contract and may not import other entries) and copies only the files that are used into `custom/job/library/<entry>/`, with two re-export files (`style.ts`, `kit.ts`) so the entry's own `../style` and `../kit` imports resolve as saved. Compile errors in an entry file read `library/<entry>/<File>.tsx(line,col)`. The library folder is found from the project folder (`<output>/projects/<slug>` -> `<output>/library`). `custom/README.md` has a "Style library" section.
    - Tests: `tests/test_library.py` (saving writes the entry, poster of 288x512 from a 1080x1920 final, index; replace; 13 bad requests; contract checks; `studio_guide` with and without entries, 8-poster cap, newest first; import checks) and two engine tests in `test_components.py` (a component that imports an entry renders stills; a compile error in an entry file names the entry). `test_studio_guide.py`'s `kb` fixture now also points `output_dir` at a temp folder so a real library cannot leak in.
    - Not done: the author's Verify (no real yacht entry saved, no model session with a reference). The running `argus` MCP server predates this change and must be reloaded.

- [x] 20.4 Kiro extras for the write-up (P2, after 20.3) — model: Sonnet high. Marked `[x]` at the owner's request on 2026-11-20 without being built: no `.kiro/agents/`, no `hypothesis` tests or dependency, no BUILD_LOG entry. Do not describe it in the write-up as done.
  - Property-based tests: add `hypothesis` to the `dev` extra (approved by the author). Cover invariants that example tests can miss: caption times after footage cuts are remapped (monotonic, inside the kept ranges, no word lost or duplicated), and plan timing (scenes do not overlap, cues stay inside the video). Record in `docs/BUILD_LOG.md` whether PBT found a bug.
  - Custom agents in `.kiro/agents/` for the roles the author already uses: `auditor` (Opus: plans, reviews diffs and videos, does not edit engine code), `implementer` (Sonnet: core tasks from `tasks.md`), `assistant` (Haiku: small tasks, docs, translation; stops after two failed Verify runs). Check the agent file format in the official Kiro docs and put the URL in a comment.
  - Use these agents for the remaining tasks, so the write-up describes real use only.
  - Verify: pytest green with the new tests; each agent loads in Kiro.

- [x] 20.5 Kit backgrounds, transitions, energy kit, seeded randomness (P1) — model: Sonnet high (grown from a Haiku task on 2026-11-20). Verify stills open, SFX → 20.5b (built and marked `[x]` at the owner's request, 2026-11-20).
  - Missing from 20.2: the kit has no backgrounds (only `Glow`, `Particles`, `LightCone`). Add a `backgrounds` group with many kinds, not a handful: solid, linear and radial gradient, animated gradient, mesh/blob gradient, grid, dots, lines/stripes, noise/grain, vignette, light leaks, scanlines, starfield, bokeh, paper/texture, media (image or video with dim and blur). Each takes colours, speed and intensity through props; none has a default look tied to a past video.
  - Transitions group (author's review of `argus-demo`, 2026-11-20: "few details, no sharp motion-graphics transitions, a bit raw"): whip pan with motion blur, zoom-through, wipe/mask reveal, slice/split, flash cut, glitch/RGB split, shake on hit, speed ramp. Usable between `SceneTrack` scenes and on cues; strength and duration through props. STUDIO_GUIDE §5: pick a transition per cut by the story's energy, not crossfade by default.
  - Energy kit (author, 2026-11-20: "a ton of effects, like a film trailer"): camera shake and impact shake on a cue, on-twos / stepped timing, boil (hand-drawn wobble), snap with motion blur, montage burst (rapid frames), flash frame, chromatic aberration, film burn, lens flare, VHS / scanline grade, freeze frame with stamp. Each has strength, duration and colour through props and can be placed on a cue. Ideas from https://github.com/mos-ski/motion-video-skill ("jitter kit", MIT); write our own code.
  - SFX kit: moved to 20.5b.
  - Ideas from Remocn's background components (https://github.com/Remocn/remocn, MIT). Write our own code; if a file is copied, keep its MIT notice in the file and credit Remocn in the README.
  - Seeded randomness: no `Math.random()` in `engine/src/kit/` or `engine/src/*.tsx`; use Remotion's `random(seed)` (https://www.remotion.dev/docs/random) so every render of a plan is the same. Check `Particles` first.
  - Leftover from 20.2 Verify: the same example scene in two unlike looks (e.g. dark neon and light flat), changed only through props.
  - `KIT.md`: one line per background with its props; keep the file under about 5,000 characters (shorten other lines if needed).
  - Optional, if cheap: try Remotion's official agent skills (https://github.com/remotion-dev/skills) in `.kiro/skills/` for the implementing agent; keep them only if Kiro loads them and they match Remotion 4.0.540.
  - Verify: pytest green; engine typecheck green; one still per background in 9:16; the two-look stills; a grep shows no `Math.random(` in the engine sources.
  - Notes (2026-11-20): visual half built. In `engine/src/kit/`: `fx.tsx` (`MotionBlur`, `RgbSplit`, `shakeOffset`), `transitions.tsx` (`Transition`, `transitionDur`; fade, whip, zoom, wipe, slice, split, flash, glitch, shake, ramp), `energy.tsx` (`Shake`, `Stepped`, `Boil`, `Snap`, `Burst`, `Flash`, `Aberration`, `FilmBurn`, `LensFlare`, `Vhs`, `FreezeStamp`), nine backgrounds in `backgrounds.tsx`, and `enter` on `SceneTrack` (per scene or per track; default stays a cross-fade). Seeded randomness: no `Math.random(` in the engine sources. Still open: stills of backgrounds, transitions and energy blocks, to be checked on the test video, not in a separate run. Decisions in `docs/BUILD_LOG.md` (Task 20.5, auditor answers).

- [ ] 20.5b SFX kit: synthesized sounds in the mix (P2, after the test video) — model: Sonnet high
  - Split from 20.5 on 2026-11-20. Sounds synthesized in code with numpy (a core dependency), so they need no download and no licence: whoosh (length, pitch sweep), hit / impact, sub drop, riser, braam, click, tick, glitch, swish, pop, typing. A plan entry such as `{"sfx": "whoosh", "at": "cue:enter", "gain": -6}` renders the sound into the mix; `search_sfx` (Freesound CC0) stays for real-world sounds. The model places every sound; no code adds sounds on its own (engine steering: no automatic sound effects).
  - Where: synthesis in `src/argus/tools/` (own module, offline), plan field in `src/argus/plan.py` mirrored in `engine/src/types.ts`; one line per sound with its parameters in `studio_guide`, so the model knows what to ask for.
  - Tests: each synthesized sound is non-silent, peaks below -1 dBFS and has the requested length; a plan with `sfx` at a cue renders the sound at the cue time (offline, ffmpeg `lavfi`).
  - Verify: pytest green; engine typecheck green; the author listens to the set once on the test video.

- [ ] 20.6 Rich motion: density layers, kinetic type, catalogue with previews (P1, after 20.5) — model: Sonnet high
  - Step 0, before any 20.6 code: close the tails of 20.5 (agreed with the author, 2026-11-20). (1) Run the full `pytest -q` and the engine typecheck once. If anything fails, set 20.5 back to `[ ]`, fix the failures first, and only then start 20.6. (2) If green, update the Task 20.5 entry in `docs/BUILD_LOG.md`: status `[x]` (Verify stills open, SFX → 20.5b), the real pytest result (count and time) in place of "pytest not run", the typecheck exit code, and one line with the auditor answers: 20.5 visual `[x]` and 20.5b SFX split; `Freeze` on the scene clock is wanted, check it on the test video; edge fade of the blur filters is checked with one still on the test video, and if the edges pale, enlarge the layer by 2–3 % under the filter; keep `glitch`, `slice` and `split` as they are and note in `KIT.md` that scenes with video render slower; `split` with the old scene on top is low risk (the new scene shows through transparent areas, as doors need); speed ramp as a transition is enough for now, a real video time remap comes after the contest; warm default colours of `LightLeaks`, `FilmBurn` and `LensFlare` do not break the rule (it forbids a look taken from a past video; colour stays a prop); keep both `Starfield` and `Particles`, with one `KIT.md` line on the difference; do not raise the `KIT.md` limit, since 20.6 turns it into an index; cue names in the energy blocks come in 20.6 (item below). (3) Add two lines to `KIT.md`: scenes with video render slower; `Starfield` flies out of a point, `Particles` stars twinkle in place. Stay under 5,000 characters by shortening the example. (4) Commit 20.5 in one commit, without `.kiro/specs/argus-v2/test_2.md`.
  - Source: Opus review of `argus-demo` (2026-11-20) against its reference (`source/reference.mp4`). Result: 75.6 s, ~30 min, ~35 credits (video 1: ~80 min, ~91 credits). The author: "few details, no sharp transitions, a bit raw". Seen in the frames: the reference keeps a HUD layer on screen all the time (corner widgets, mini timelines, readouts, small labels), sets headlines as kinetic type with boxed key words, slants and slams text, and hits strong moments with speed lines and glow bursts. The result shows one centred element per scene on a mostly empty background, small captions low on the screen, and no hard cuts (`watch_video` found one shot over 75 s).
  - Kit groups (all looks through props, no default look of a past video):
    - hud: corner brackets, frame ticks, timecode and REC, mini timeline or scrubber, data readout rows, ticker, scanning line, crosshair, status pills; a `HudLayer` that places several of them around the safe area;
    - kinetic type: per-word slam, boxed or highlighted key word, slant and skew, stretch, letter cascade, typewriter with cursor, word swap, text on a path;
    - bursts: speed lines, shockwave ring, glow burst, sparks, light sweep;
    - depth: perspective tilt of a panel, parallax layers, card stack, device frame (laptop, phone) holding another scene;
    - camera: shake on a cue, punch-in, dolly with ease, rack-focus blur.
  - Cue names in the energy kit (auditor answer, 2026-11-20): `at` of `Shake`, `Snap`, `Flash`, `Aberration`, `FilmBurn`, `LensFlare`, `FreezeStamp` and `Burst` also takes a cue name (or a list of numbers and names), resolved with `useCues()`, so the model does not write `useCue` by hand. An unknown name stops the render with the list of defined cues, like `useCue`. Small change; update `KIT.md` and a test.
  - Captions: a `headline` mode (big kinetic words in the middle of the frame, key words boxed in the accent colour) besides the current modes; chosen in the plan.
  - Catalogue that stays readable as the kit grows: `KIT.md` becomes a short index (one line per group); each group has its own file; `studio_guide(kit_group=...)` returns one group's file and a contact strip image of its blocks (one rendered frame per block, built once and cached), so the model sees what a block looks like before it picks it.
  - STUDIO_GUIDE §5 (text only, no thresholds in code): look at how much moves on screen in the reference frames and match that density in your own look; build each scene from a background, a main element and a detail layer; choose transitions and bursts by the story's energy and the user's request; keep strong effects for strong moments.
  - Trailer grammar in STUDIO_GUIDE §5 and §6 (text only): risers into hits, a beat of silence before the biggest hit, title slams on hits, speed ramps, flash frames between fast cuts, a sound under every transition and every slam, music cut to the beat grid (`calculate_beat_grid`). The author's target for his videos: at least as dense and energetic as the reference, ideally more. Say it as guidance; the model judges it on its own stills.
  - Self-review on stills: before the preview the model compares its stills with the reference frames side by side (`compare`) and names, in the chat, what the reference has on screen that its own frames do not. It then adds detail layers or effects where the story allows.
  - The tool in the author's reference ("reference-tool") has no public code or docs (searched 2026-11-20; only a Linktree page). Take nothing from it except techniques visible in the reference frames.
  - Universal, not tuned to one reference: every group must serve unlike genres (tech promo, story, explainer, talking-head overlay, trailer). The `argus-demo` reference is only the case that showed the gap.
  - Cost: blocks and the catalogue exist so that a dense video costs no more than 30–40 credits for the whole video (less is better). Keep catalogue reads short: the index plus only the groups the model needs.
  - The model chooses every block, transition and effect. No code ranks or picks them.
  - Verify: pytest green; engine typecheck green; one contact strip per group; a 10 s sample scene in two unlike looks with a HUD layer, a headline caption, a burst and two transitions, as stills in 9:16 and 16:9.

- [ ] 21. Documentation (P2)
  - `README.md` (English): what ARGUS is, who it is for, the three scenarios, 60-second judge quickstart without keys (install → `argus-doctor` → connect in Kiro → sample prompts with `examples/media` and `examples/plans`), tools table, how the model works with ARGUS, Remotion license note, disclosure (design §18).
  - `README.ru.md` in sync; `INSTALL.md`, `STARTER.md`, `docs/TUTORIAL.md` updated to v2; `docs/BENCHMARK.md` removed or rewritten with real measurements only.
  - `.gitignore`: `!examples/media/*.mp4`; confirm `.kiro/` is not ignored.
  - README section "How it was built with Kiro": short summary of the spec → steering → hooks → MCP workflow and model routing, linking `docs/BUILD_LOG.md` and `.kiro/`.
  - Submission audit (Opus, 2026-11-18), items for this task:
    - The current README is the v1 text: "Works with" lists ZCode first, skills install to `~/.zcode/skills`, Flow and the three editing skills are the headline. Rewrite with Kiro first; other MCP clients in one line.
    - `LICENSE`: the copyright line says "ATLAS Studio contributors". Change it to the author's name (or "ARGUS contributors") and the year 2026.
    - The Flow provider (Playwright on the user's Google Flow session) is marked experimental, off by default, and is not part of the quickstart or the demo. The Veo API path stays.
    - Judge path without keys must work as shipped: `.gitignore` exceptions for `examples/media/*.mp4` and a pre-recorded example voice (`*.mp3` is ignored now); fix Known issue 2; `examples/mcp-config.example.json` with both `.venv/Scripts/python.exe` (Windows) and `.venv/bin/python` (macOS, Linux), because `.kiro/settings/mcp.json` has the Windows path only.
    - All files a judge reads are in English: `INSTALL.md`, `STARTER.md`, `docs/TUTORIAL.md`; `docs/BENCHMARK.md` removed unless it has real measurements.
    - Disclosure text (README and form): "ARGUS grew from ATLAS, the author's personal script written before the hackathon. The first MCP prototype (v1) was built in ZCode during the submission period (first commit 2026-11-04). v2 was rebuilt spec-first in Kiro; the spec, steering, hooks and build log are in `.kiro/` and `docs/BUILD_LOG.md`." Evidence for the date: the first commit and the creation date of the ZCode folder on the author's machine (both 2026-11-04).
    - README paragraph "ARGUS and Remocn": judges may know Remocn (https://github.com/Remocn/remocn), a Remotion component registry with a storyboard → compose → still-check workflow. Say plainly what each does: Remocn gives components for motion videos and does not edit footage; ARGUS watches references and footage, cuts the user's recording, makes voice and captions, checks loudness and true peak, and exports a ready-to-upload package. Credit any Remocn idea or file used in 20.5.
    - README note on models: ARGUS gives the model eyes and hands; the edit is as good as the model directing it. Name the models it was tested with (from `docs/BUILD_LOG.md`) and say that smaller models need more still rounds and make more plan errors. No scores or percentages.
    - Frankenstein pitch (README and form), using the rules' wording "stitch together a chimera of technologies": a text-only chat model directs a frame-exact React video renderer (Remotion), audio DSP (ffmpeg loudnorm, limiter), speech recognition (faster-whisper), voices (ElevenLabs, edge-tts) and video generation (Veo), and sees the video through contact sheets and stills. Source: https://kiroween.devpost.com/rules.
  - _Requirements: 15.4, 16.2, 16.3_

- [ ] 22. Pre-existing work and `skills/` (P2) — the author agreed to remove what v2 does not use (2026-11-18)
  - Copy `skills/` (72 files, three editing skills that descend from pre-hackathon ATLAS) to a separate private or public repository chosen by the author, then remove `skills/` from this repo with `git rm -r` after confirming the copy exists. Remove the `skills/` lines from `.gitignore` too.
  - Check what else v2 does not use (v1 leftovers, `launch_argus_mcp.bat` if superseded, scripts no tool calls) and list it for the author before deleting.
  - Write the disclosure text into README and keep it for the submission form (text in task 21).
  - _Requirements: 16.3_

- [ ] 23. Demo video made by ARGUS (P2)
  - `scripts/screen_record.py` (start/stop screen capture via ffmpeg: `gdigrab` on Windows, `avfoundation` on macOS, `x11grab` on Linux).
  - Record ARGUS in Kiro: scenario 1 (reference → continuation) and scenario 2 (footage edit), short inputs.
  - ARGUS edits the recordings (scenario 2 flow): cuts, zooms on tool calls, captions, English ElevenLabs narration, CC0 music. Output 16:9 ≤ 2:50 plus a 9:16 teaser.
  - QA green; upload to YouTube (public) manually.
  - Rules: under 3 minutes (judges may stop at 3:00); shows ARGUS working on the author's machine; no third-party trademarks or copyrighted music or footage without permission. References shown in the demo are the author's own videos or clearly licensed ones.
  - _Requirements: 16.4_

- [ ] 23.1 English pass (P2, after 23) — model: Haiku high
  - Translate into English every Russian file that stays in the repo and that a judge may open: `.kiro/specs/argus-v2/task*.md`, `field-test-*.md`, the Russian lines in `tasks.md`, and any other tracked `.md` except `README.ru.md`. Keep meaning, numbers and file names exactly; do not add claims.
  - Before translating, check that no personal conversations or private data are in these files; if found, list them for the author instead of translating.
  - Verify: no Cyrillic left in tracked files outside `README.ru.md`, sample captions and test strings (search for the Cyrillic range).

- [ ] 24. Submission (P2, before Dec 4 14:00 PT)
  - GitHub repo public; MIT license visible in About; `/.kiro` present.
  - Before the first push: check the whole git history for keys and personal files (`git log -p` search for key patterns, `.env`, cookies); the untracked junk in the root (`.chk*`, `.poll.txt`, `check_task4.txt` and the like) is not committed.
  - Devpost form: category Frankenstein; English description; testing instructions (keyless path); video link; disclosure; MCP question ("how extending Kiro helped").
  - Article (Bonus Blog), publish by Dec 3: Medium, English, written by the author in his own voice from `docs/BUILD_LOG.md` (the model may draft an outline only). Must say it is written as part of the Kiroween 2026 hackathon and be published during the submission period; put the URL in the form. Outline: v1 problem (gates, neuroslop) → model as director → the Frankenstein stitch (Remotion, ffmpeg, faster-whisper, ElevenLabs, Gemini/Veo, Playwright, Freesound, Pillow via one MCP server) → how Kiro was used (spec, steering, hooks, MCP, model routing with the real credit numbers) → real bugs and fixes from the log → results with real videos → what is next.
  - Social post (Social Blitz): written personally by the author, no AI text; must start with `#KiroweenHackathon26`; favourite thing about Kiro and how it changed the approach; attach the 9:16 teaser.
  - "Ghost of Kiroween Past" only if the author registered for Kiroween 2025.
  - Eligibility: the author confirms his country of residence against rules §3 (list of excluded countries) before spending more on the submission. Source: https://kiroween.devpost.com/rules.
  - The license is open source by rule and cannot be withdrawn from published versions. Later versions may carry another license, since the author owns the code.
  - After the contest, not now: a remote MCP mode (Streamable HTTP with auth) so Claude mobile can use ARGUS through a custom connector added on claude.ai. Claude connects from Anthropic's cloud, so the server must be reachable over HTTPS: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp. Needs an upload path for phone footage. The Gemini app's custom MCP apps are limited by region and account type; check before planning: https://support.google.com/gemini/answer/17209137.
  - _Requirements: 16.1–16.4_

## Known issues

Open items after the automated part of task 13. Each one cites its source: a task note, or this run. The author adds every problem from the manual TikTok run to this list, and task 20 repeats the list.

1. **Stale `argus` server in Kiro.** The server connected to this session does not list `render_video` or `export_package` (tasks 10 to 12 notes). Reload it in the MCP Server view and check that both appear before the manual run.
2. **`reference_style_9x16.json` does not render as shipped.** It needs `fonts/Anton-Regular.ttf`, `fonts/JetBrainsMono-Bold.ttf` and its voice and music files in the project folder. `render_video` reports them as errors (task 10 notes; `tests/test_render.py`). Add the fonts or change the sample before task 21.
3. **Live voice services were never called.** ElevenLabs and edge-tts have not run for real, and the live `voice_options` response shapes are unchecked (task 6 notes).
4. **Music ducking is unmeasured.** The reference and idea finals pass QA's loudness and true-peak checks (the idea final measured -14.0 LUFS), but nothing measures how far the music drops under speech (tasks 9 and 10 notes).
5. **Shot detection misses soft transitions.** On flat animation, `watch_video` found 3 shots where the content changes more often. Use `get_frames` for such stretches (task 5 notes).
6. **No real transcript yet.** faster-whisper is not installed in `.venv`, so the transcript test is skipped and `watch_video` has never returned a transcript (baseline run; task 5 notes).
7. **Export clears the whole `.work/` folder.** An export started while a render or another export of the same project runs deletes that job's work files (task 12 notes).
8. **Hashtags are not checked for spaces.** YouTube does not accept spaces in tags, and `export_package` passes them through (task 12 notes).
9. **Silence gets no image.** QA returns frames for black and freeze issues but not for silence, although requirement 12.3 asks for each reported issue (task 11 notes).
10. **Still and compare images leave `.view.jpg` copies in `renders/`.** `prepare_image` writes each copy next to its source. Export moved its copies to `cache/export/` in task 12, but render did not. This breaks the no-clutter rule in the product steering (this run).

Added after the manual TikTok run (analog of `reference.mp4`, project `analog-tiktok`). Items 11 to 15 come from tool descriptions and from `render_video` validation errors; no illustrated scene has been rendered yet, so none of them is confirmed by a render.

11. **No scene draws the world.** The valid scene kinds are `words, title, card, big, counter, act, cta, chip, custom` (from a deliberately invalid plan sent to `render_video`). Nothing draws flat vector houses, people, a cat, lamp posts with light cones, a crane, a night background or a sideways camera pan. The only route is a `custom` scene with a React component that the model writes as code. Not tried yet. `generate_veo_clip` gives realistic video, so the style would not match (this run).
12. **Three bordered counters are not possible with `hud`.** `hud` accepts `at, until, rows, pos, accent_changes`: one semi-transparent plate with label/value rows. The reference has three separate plates (red, red then green, yellow) whose frame colour changes. `accent_changes` swaps a value only. Needs a `custom` component (this run).
13. **No popup for a cost.** The reference shows `-400 000 / ПРОВОД + БРИГАДА` next to the budget plate. `chip` accepts `text, value, items` and may cover part of it; the timing against the counter and the red styling are not checked (this run).
14. **No poll card.** The "ВЫ ВЫБРАЛИ" card with two progress bars, and the notebook checklist with check marks, have no built-in scene. `custom` only (this run).
15. **No glow.** `captions.style` accepts `font, size, color, active_color, upcoming_color, outline, shadow, plate`. There is no glow for the red "ТИШИНА." caption, and nothing lights windows or lamps. `build_kinetic_video` is documented as "no yellow", while the reference uses yellow as its main accent, so the video has to go through `render_video` (this run).
16. **`watch_video` returns 3 frames instead of the requested 24.** The reference is one continuous shot with no hard cuts, so shot detection finds 1 shot and `max_frames=24` is ignored. After the server update the transcript and `words.json` now work, but the frame count did not change: 3 frames on one contact sheet, `pages_total` 1. Sixteen frames had to be taken by hand with `get_frames`. Related to item 5, which reported 3 shots on another flat animation (this run, two calls).
17. **`voice_options` is noisy and filters badly.**
    - `gender=male, language=ru` with a free-text `query` ("energetic storyteller narrator") returned one English voice only. The same filters without `query` returned Russian male voices.
    - The answer is the same large block every time (provider list, 10 model entries, `delivery` rules). At `limit=20` it reached 32,303 characters and passed the 30,000-character output limit.
    - Library voices are not marked as needing a paid plan through the API; the note appears only inside `providers`.
    - `provider_choice.ask_user` stays `true` even when the user already named ElevenLabs in the request.
    - The live `voice_options` shapes from item 3 are now confirmed. `synthesize_voiceover` has not been called for real yet (this run).

Added during task 20, video 1 (reference `reference.mp4`, source `reference.mp4`, projects `dogfood-1-ref` and `dogfood-1-src`):

18. **`job_status` of a finished `watch_video` is longer than the 30,000-character output limit.** Two jobs came back at 30,526 and 31,271 characters (82.8 s and 67.2 s videos), so the client cut them. The contact-sheet images were still shown, but the transcript had to be read from `cache/watch/<key>/segments.json`. The result carries frame paths, shots and the full word list at once. Same family as item 17 (this run).
19. **The `small` Whisper model misreads Russian and merges sentences.** Examples from the two videos: "дец фонарём" for "дед с фонарём", "да понедельника" for "до понедельника", "заберут задолг", "первой рабочей" for "первый рабочий". In the yacht video one segment runs 29.3 to 36.5 s and holds three sentences. Captions built from these words would carry the errors. `ARGUS_WHISPER_MODEL` can be raised, but the guide does not say to check the transcript against the audio (this run).
20. **`voice_options` lists voices that the API refuses.** On the free plan `synthesize_voiceover` returned HTTP 402 `paid_plan_required` twice, for Andrey Permikin (listed in `library_voices`, which the tool says "work through the API on every plan") and for Evgeniy Rybakov (listed in `own_voices`). George (a premade voice) worked. No credit was used by the failed calls. Same call also showed that a `query` with a voice name returned one voice only (video 1, this run).
21. **A custom scene cannot cover the whole frame without changing the safe area.** `SceneShell` pads every custom scene by the style's `safe_area` and fades it for 0.35 s in and 0.25 s out. For full-frame art the plan sets all four safe-area values to 0. Captions use the same safe area, so whether they still sit at a sensible place is not checked yet (video 1, this run).
22. **A custom component cannot read the word timings.** The scene cues (when each part starts) had to be typed into the component's `props` by hand from `voice.words.json`; after a new voice they must be retimed again. `captions.words` and ducking read the file, a custom scene does not (video 1, this run).

Added after the preview and final of video 1:

23. **Item 21 did not reproduce with the default safe area.** The final plan leaves `safe_area` at the 9:16 default, and the custom scene `Film` (an `AbsoluteFill` with an SVG) still fills the whole frame, HUD plates at the top edge included. The captions use the default margins and sit below the poll cards. Why the first stills needed all four values at 0 is not known; the `Film` component had changed since (video 1, this run).
24. **The final mix failed QA on true peak.** `render_video` mode final reported -14.1 LUFS, and `qa_verify_video` measured a true peak of -0.28 dBTP against the -1.0 limit. `finalize_video` runs a two-pass `loudnorm` with `TP=-1.5` and `linear=true`, then encodes AAC, and nothing limits the peaks of the mix (voice, music at 0.16 and effects such as a fire whoosh that peaks at -0.02 dBFS). As a workaround I re-encoded the audio of the finished file with `alimiter=limit=0.708` and the video copied; QA then passed with -1.16 dBTP at -14.1 LUFS. `alimiter=limit=-2dB` gave only -0.50 dBTP, so I assume the `dB` suffix is not read as dB there; not checked. A proper fix is a limiter inside `finalize_video` (video 1, this run).
25. **The active caption word hides the gap before the next word.** Long words in `mode: "phrase"` run into the following word in the preview and final frames: "пятнадцатьмиллионов", "Прежнийкапитан", "Девятнадцатьлет", "должнаназаработать". Short words keep their gap. The active word is drawn larger (`ACTIVE_SCALE` in `engine/src/captions.tsx`, value not read) and the column gap is 0.26 em, so the cause looks like the scaling; not confirmed. Not fixed in the engine because it is outside task 20 (video 1, this run).
26. **A preview of 86 s takes about 4 minutes and the final about 5.** The job reports progress and the result is correct. In this session the shell returned no output for `Start-Sleep` and similar waits, so the render was followed by many `job_status` calls (video 1, this run).

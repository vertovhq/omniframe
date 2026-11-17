# Requirements — ARGUS v2

## Introduction

ARGUS v1 grew feature by feature and ended up with creative "gates" (30% story
overlap, 30% digit density, slop-word lists), a 150-line rule book for the model,
a renderer that only knows `dark`/`light` themes and vertical frames, and tools
that hand the model file paths it cannot see. The output was generic.

ARGUS v2 makes the model the director and ARGUS its hands. The model watches
references and footage as real images with timecodes and transcripts, writes the
story and the voice performance, expresses the look as style tokens and custom
components, checks its own stills against the reference, and delivers a
ready-to-upload package. Scripts do mechanics and technical QA only.

Hard deadline: Kiroween 2026 submission, December 4, 2026, 14:00 PT. Feature
freeze: November 30. Milestone M1 (author can produce his TikTok videos from a
reference): November 25.

Terms: **project** — a folder `OMNIFRAME_OUTPUT_DIR/projects/<name>/` holding all
inputs and outputs of one video. **plan** — the JSON timeline the model writes and
the engine renders. **job** — a detached long-running operation with a status file.

## Requirements

### Requirement 1 — Creative decisions belong to the model

**User Story:** As a creator, I want the model to judge story and style itself, so
that rigid formulas stop pushing every video toward the same template.

#### Acceptance Criteria

1. THE server SHALL NOT expose `validate_beats`, `story_guide` or any tool that
   scores or gates stories, styles or originality.
2. THE repository SHALL NOT contain percentage rules for creative content (story
   overlap, digit density) in code, tool docstrings, server instructions,
   `STARTER.md` or skill documents.
3. THE server instructions SHALL describe tools as capabilities and point the model
   to `studio_guide`, without mandatory engine-selection rules.
4. THE engine SHALL NOT add sound effects automatically; only SFX listed in the plan play.

### Requirement 2 — Studio guide and user preferences

**User Story:** As a model working in ARGUS, I want one short guide with the working
method, the available capabilities and the user's saved preferences, so that I can
start without reading a rule book.

#### Acceptance Criteria

1. WHEN `studio_guide` is called THEN THE server SHALL return the guide text, the
   list of available tools and configured providers (ElevenLabs, Gemini, edge-tts,
   faster-whisper, Veo API, Flow session), and the user's saved preferences.
2. THE guide SHALL state principles in plain language and SHALL NOT contain numeric
   thresholds for creative content.
3. WHEN `learn_and_record_memory` is called THEN THE server SHALL append the
   preference to the knowledge base file, and the next `studio_guide` call SHALL
   include it.
4. THE preferences returned by `studio_guide` SHALL be capped in size so that a long
   file cannot flood the model context.

### Requirement 3 — The model sees pictures

**User Story:** As a model, I want frames returned as images, so that I can see the
reference, the footage and my own renders.

#### Acceptance Criteria

1. WHEN a tool produces frames for the model (watch, frames, stills, QA, export cover)
   THEN THE tool SHALL return them as MCP image content together with a JSON summary.
2. THE images SHALL be downscaled (longest side ≤ 1024 px by default, JPEG) to keep
   token cost bounded, and the summary SHALL list each image's timecode and file path.
3. THE number of images per call SHALL be bounded by a parameter with a safe default.
4. IF the client does not display image content THEN the file paths in the summary
   SHALL still let the model open the images with its own file tools.

### Requirement 4 — Long operations do not block

**User Story:** As a user on a weak laptop, I want long operations to keep running
even when the MCP client times out a call, so that renders and transcripts never die halfway.

#### Acceptance Criteria

1. WHEN an operation may exceed ~20 seconds (render preview/final, transcription,
   watching a long video) THEN THE tool SHALL either finish within the wait budget
   and return the result, or return a `job_id` while the work continues in a detached process.
2. WHEN `job_status(job_id)` is called THEN THE server SHALL return state
   (`queued|running|done|error`), progress when known, the result when done, and the
   error tail when failed.
3. WHEN the same operation with the same key is already running THEN THE server
   SHALL return the existing job instead of starting a second one.
4. IF a job's process died THEN `job_status` SHALL report `error` instead of `running` forever.

### Requirement 5 — Watching a video of any length

**User Story:** As a model, I want to watch any reference or footage, short or long,
so that I understand its shots, text, pacing, speech and sound.

#### Acceptance Criteria

1. WHEN `watch_video` is called on a local video THEN THE tool SHALL detect every
   shot change over the whole file at full frame rate and return all shot boundaries.
2. THE tool SHALL select representative frames within a frame budget (shot starts
   first; long shots get an extra frame; evenly spread when shots exceed the budget)
   and return them as labelled contact sheets (timecode on every tile).
3. WHERE faster-whisper is installed THE tool SHALL return a word-level transcript
   with timestamps, keeping stumbles and repeats (verbatim mode), language auto-detected
   unless given.
4. THE tool SHALL return sound events (times of sharp onsets with strength) and speech
   segments, so the model can relate sounds to frames.
5. WHEN the same file (same content hash) is watched again THEN THE tool SHALL reuse
   the cached result.
6. WHEN the result has more contact sheets than one call should carry THEN THE tool
   SHALL paginate (`page` parameter) instead of dropping frames.

### Requirement 6 — Inspecting exact frames

**User Story:** As a model, I want any frame at any time, full resolution or cropped,
so that I can read fonts, HUD values, colors and the exact look around a cut.

#### Acceptance Criteria

1. WHEN `get_frames(path, times, crop?)` is called THEN THE tool SHALL return one image
   per requested time, cropped to the given region (fractions of the frame) when provided.
2. THE tool SHALL cap the number of times per call and report the cap when exceeded.

### Requirement 7 — Voice directed by the model

**User Story:** As a creator, I want the model to choose the voice, emotions and pauses
itself, so that voiceovers sound performed, not read.

#### Acceptance Criteria

1. WHERE an ElevenLabs key is configured THE default voice provider SHALL be ElevenLabs.
2. WHEN `voice_options` is called with filters (language, gender, query) THEN THE tool
   SHALL return the user's own voices and matching Voice Library voices with ids,
   names and labels.
3. WHEN `synthesize_voiceover` is called THEN THE tool SHALL pass the model's text with
   its delivery markup (ElevenLabs v3 audio tags, punctuation) unchanged, use the voice
   and model the model chose, and save audio plus a `words.json` with word timings.
4. THE word timings SHALL come from the provider when available (ElevenLabs timestamps,
   edge-tts word boundaries); otherwise from faster-whisper alignment when installed;
   otherwise the tool SHALL say captions are unavailable.
5. WHERE no paid key is configured THE tool SHALL work with edge-tts.
6. THE provider layer SHALL allow adding a local provider (Voice Studio) later without
   changing tool signatures.

### Requirement 8 — Plan with free style and both formats

**User Story:** As a model, I want to express any visual style and both 9:16 and 16:9
in the plan, so that I can match any reference without new code.

#### Acceptance Criteria

1. THE plan SHALL declare `format` (`9:16` → 1080×1920, `16:9` → 1920×1080) and `fps`.
2. THE plan SHALL carry style tokens: named colors, fonts (bundled family or a font file
   from the project), text scale, safe area, background, grain; `dark` and `light`
   SHALL remain as presets.
3. THE engine SHALL lay out every scene from the frame size and style tokens; no
   hardcoded 1080/1920 values.
4. WHEN a plan is invalid THEN THE render tool SHALL return every problem as
   `path: message` before starting any render.

### Requirement 9 — Rendering with a cheap review loop

**User Story:** As a model, I want stills and low-res previews before the final render,
so that I can fix the look without spending a full render each time.

#### Acceptance Criteria

1. WHEN `render_video` is called with `mode="stills"` and times THEN THE tool SHALL
   render those frames only and return them as images.
2. WHEN stills are requested with a comparison video and times THEN THE tool SHALL
   return side-by-side images (reference | render) with labels.
3. WHEN `mode="preview"` THEN THE tool SHALL render at half resolution; WHEN
   `mode="final"` THEN at full resolution, followed by loudness normalisation to the
   target and a metadata tag.
4. THE engine SHALL be bundled once per render job and report progress to the job status.
5. THE render SHALL place clips (video and images), scenes, overlays, HUD, captions,
   voice, music (ducked under speech) and listed SFX on one timeline.

### Requirement 10 — Editing the user's footage

**User Story:** As a doctor with a talking-head recording, I want ARGUS to cut and
decorate my video, so that I get a watchable result without editing skills.

#### Acceptance Criteria

1. THE plan SHALL support clips with source in/out points, placement time, fit,
   volume, and zoom/pan keyframes.
2. WHEN captions are set to follow the clips THEN THE render SHALL remap the footage
   transcript from source time to output time for the kept ranges.
3. WHEN source footage is variable-frame-rate or not H.264 THEN THE render SHALL use a
   cached constant-frame-rate H.264 proxy so audio and video stay in sync.
4. WHERE a clip requests audio cleanup THE proxy SHALL apply a fixed denoise/high-pass chain.

### Requirement 11 — Custom visuals written by the model

**User Story:** As a model, I want to write my own React component when no built-in
scene fits the reference, so that any style is reachable without changing ARGUS.

#### Acceptance Criteria

1. WHEN a plan references a custom component THEN THE render SHALL load it from the
   project's `components/` folder.
2. WHEN a custom component fails to typecheck THEN THE render SHALL return the compiler
   errors to the model and not start the render.
3. THE committed engine SHALL stay buildable with no custom components present.

### Requirement 12 — Technical QA

**User Story:** As a creator, I want every final video checked for technical defects,
so that nothing broken reaches my channel.

#### Acceptance Criteria

1. WHEN `qa_verify_video` runs THEN THE tool SHALL check resolution against the format,
   fps, progressive scan, audio presence, integrated loudness against the target,
   true peak, and audio/video length difference; failures SHALL be hard failures.
2. THE tool SHALL detect black gaps, frozen video and long silences and report them
   with timecodes; long black gaps mid-video SHALL be hard failures, the rest warnings.
3. THE tool SHALL return frames as images: evenly spread plus frames at each reported issue.
4. THE tool SHALL NOT judge creative quality.

### Requirement 13 — Ready-to-upload package

**User Story:** As a creator, I want a finished folder per video, so that publishing
takes a minute.

#### Acceptance Criteria

1. WHEN `export_package` is called THEN THE tool SHALL write to `<project>/final/`: the
   video per format, a cover image per format, and `post.md` with the texts per platform.
2. THE tool SHALL validate texts against platform length limits and report violations.
3. WHEN export succeeds THEN THE tool SHALL remove `<project>/.work/`.

### Requirement 14 — The user's own scripts

**User Story:** As the author, I want to drop my own Python script into a folder and
have the model use it, so that I can extend ARGUS without editing the server.

#### Acceptance Criteria

1. WHEN `run_script()` is called without a name THEN THE tool SHALL list scripts from
   `scripts/` in the repo and from `ARGUS_SCRIPTS_DIR`, with each script's summary and
   argument example from its docstring.
2. WHEN `run_script(name, args)` is called THEN THE tool SHALL run the script in a
   subprocess with a timeout and return its JSON result (and images it lists).
3. THE tool SHALL only run scripts from those folders, by validated name.

### Requirement 15 — Install, keyless path, doctor

**User Story:** As a judge or a new user, I want ARGUS to install and work without paid
keys, so that I can try it immediately.

#### Acceptance Criteria

1. THE server SHALL load `.env` from the repository root even when started from another
   working directory.
2. WITHOUT any API key THE user SHALL be able to: watch videos, edit own footage,
   build graphics videos with edge-tts voice, run QA and export.
3. `doctor` SHALL check exactly what v2 needs (python, ffmpeg/ffprobe, node/npx, engine
   deps, numpy/Pillow; optional: faster-whisper, edge-tts, playwright, keys) and print an
   install command under every failure.
4. THE repository SHALL ship short sample media for trying scenarios 2 and 3.

### Requirement 16 — Kiro integration and Kiroween submission

**User Story:** As the author, I want the repo and the demo to meet every Kiroween rule
and show deep Kiro use, so that the project can win the Frankenstein category.

#### Acceptance Criteria

1. THE repository SHALL contain `/.kiro` (specs, steering, hooks, MCP settings) and
   SHALL NOT ignore it in `.gitignore`.
2. THE repository SHALL be public on GitHub with an open-source license detected in
   the About section, and an English README with install and testing instructions.
3. THE README SHALL disclose pre-existing work and third-party code used.
4. THE demo video SHALL be under 3 minutes, in English, on YouTube, without copyrighted
   music, and SHALL be edited by ARGUS itself from screen recordings of ARGUS working in Kiro.

### Requirement 17 — Reliability and cleanup

**User Story:** As the author, I want ARGUS to work every time at the deadline, so that
judges and viewers never see errors or slop caused by the tooling.

#### Acceptance Criteria

1. THE test suite SHALL include end-to-end tests for all three scenarios on synthetic
   media, skipping only when the engine is not installed.
2. THE server SHALL NOT keep tools superseded by v2 (`analyze_reference`,
   `build_kinetic_video`, `assemble_master_video`, `build_pop_subtitles`,
   `calculate_acoustic_timeline`) once their replacements pass the end-to-end tests.
3. BEFORE feature freeze THE author SHALL produce at least two real TikTok videos from
   references and one footage edit with ARGUS in Kiro, and every defect found SHALL be
   fixed or listed as known.

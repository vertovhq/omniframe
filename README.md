# OmniFrame

An MCP video studio for vertical video (TikTok, YouTube Shorts, YouTube). The AI model in your
client directs the edit. OmniFrame gives it eyes, ears and hands: it watches and listens to footage,
makes voiceovers, renders, checks the technical quality and packages the upload.

Made by VertovHQ. Built with Kiro for Kiroween 2026. Repository: https://github.com/vertovhq/omniframe

Русская версия: [README.ru.md](README.ru.md).

## What OmniFrame does

The model makes every creative decision. OmniFrame never scores or grades a story, a style or
originality. It returns material the model can perceive (pictures, timecodes, transcripts, sound
events) and runs deterministic checks for technical faults only: size, frame rate, loudness,
peaks, black gaps and audio length.

OmniFrame covers three scenarios:

1. **Reference to new video.** Give it a reference clip. The model watches it and makes a
   continuation, an analog, or your own idea in the same style.
2. **Your footage to edited video.** Cut stumbles, repeats and long pauses from your recording.
   Add captions, zooms, graphics, sound effects and music.
3. **Idea to video from scratch.** Kinetic graphics from a JSON plan.

Every scenario ends with the same output: a 9:16 and/or 16:9 file ready to upload, a cover image,
and a `post.md` with title, description and hashtags. Publishing stays manual. OmniFrame calls no
platform APIs.

## How OmniFrame differs from video-shotcraft and OpenFilm

[video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) (Apache 2.0) is an agent skill
for Claude Code and Codex. It turns a product's screenshots and copy into a promo, drawn with
Remotion. [OpenFilm](https://github.com/openfilm/openfilm) turns a coding agent into a film maker:
a film is a folder of HTML pages, and it has its own desktop editor. OmniFrame is an MCP server, so any
MCP client can drive it, Kiro included. It starts from a reference video and makes a continuation
of it. It also edits your own recording, then checks the result (frame size, loudness, true peak,
black gaps, audio length) and exports the upload package. Its sound effects are synthesized in code
(whoosh, pop, hit) and can be mixed with CC0 sounds from Freesound. One finished 9:16 video costs
N credits and takes M min. These numbers will be filled in after the demo.

## Quickstart without keys

Without any API key you get kinetic graphics, the free edge-tts voices, video watching and framing,
QA and export.

1. Install (see [Install](#install)).
2. Run `omniframe-doctor`. It prints a table: ✓ ready, ✗ missing with the install command, ⚠ optional.
3. Connect your MCP client (see [Connect your client](#connect-your-client)) and reload its MCP servers.
4. Ask in the chat, in this order (files are in [`examples/media/`](examples/media/README.md)):
   - `Call studio_guide and follow its working order.`
   - `Watch examples/media/moving-shapes-8s.mp4 with watch_video, then get_frames at 2 and 6 seconds. Describe what you see.`
   - `Read examples/media/sample-voiceover.txt and voice it with synthesize_voiceover, project demo.`
   - `Render stills of examples/plans/graphics_9x16.json in project demo at 1, 4 and 8 seconds. Show me the frames.`

   Then ask for the preview, the final render, `qa_verify_video` and `export_package`. The plan
   reads `audio/voice.words.json` from the project folder, so the voice step must use the same project
   name as the render.

   For production-quality voice, add your ElevenLabs API key to .env (ELEVENLABS_API_KEY). Without a key OmniFrame falls back to a free voice so the example still runs.

## Install

Requirements: Python 3.11+, ffmpeg on PATH, Node.js 18+ (for the Remotion engine). Windows, macOS
and Linux.

```bash
git clone https://github.com/vertovhq/omniframe.git
cd omniframe
bash install.sh     # Windows: powershell -ExecutionPolicy Bypass -File install.ps1
```

The install script creates `.venv`, installs the Python package, the edge-tts voice, the Node packages
of the engine and a `.env` copy of `.env.example`. At the end it runs `omniframe-install`, which adds OmniFrame
to every AI IDE it finds: Kiro, Cursor, Claude Code, VS Code (Copilot) and Antigravity. No JSON by hand.
It changes only the `omniframe` entry, keeps an existing one (`--update` replaces it) and writes
`<file>.omniframe-backup` before the first change. See first: `omniframe-install --dry-run`. One IDE only:
`omniframe-install --client cursor`. Step by step and other MCP clients: [INSTALL.md](INSTALL.md).

### Without cloning: uvx or Kiro Power

With [uv](https://docs.astral.sh/uv/) installed, the server runs straight from GitHub. Use this as the
MCP command:

```bash
uvx --from git+https://github.com/vertovhq/omniframe omniframe
```

On the first start the server installs the graphics engine into `~/.omniframe/engine` in the background. It
needs Node.js 18 or newer and ffmpeg on PATH. Check progress with the `doctor` tool, or with
`uvx --from git+https://github.com/vertovhq/omniframe omniframe-doctor`. Keys go in `~/.omniframe/.env`.

The [`kiro-power/`](kiro-power/README.md) folder is a Kiro power. It bundles the same server and the
working guide in one install.

## Connect your client

Kiro reads `.kiro/settings/mcp.json` in the workspace, or `~/.kiro/settings/mcp.json` for every
workspace:

```json
{
  "mcpServers": {
    "omniframe": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "omniframe"],
      "env": { "OMNIFRAME_OUTPUT_DIR": "./output" }
    }
  }
}
```

On macOS and Linux, use `.venv/bin/python`. In the user-level file, use the absolute path to the
venv's Python. Keep API keys in `.env`, not in this file. More variants:
[`examples/mcp-config.example.json`](examples/mcp-config.example.json).

Any other MCP client works the same way: start `python -m omniframe` from the venv, or the
`omniframe` command after install.

## Tools

| Tool | What it does | Keys |
|---|---|---|
| `studio_guide` | Working order, available tools and providers, and the user's saved preferences. Call it first in each session | none |
| `watch_video` | Shots, contact sheets, transcript words (faster-whisper, optional) and sound events of a video, as pictures and timecodes | none |
| `get_frames` | Exact frames of a video as pictures, optionally cropped | none |
| `voice_options` | Voices, models and providers available now | optional |
| `synthesize_voiceover` | Voice audio and word timings (`{w, s, e}`), mastered to -14 LUFS. Providers: edge (free), ElevenLabs, Gemini | none (edge); keys improve quality |
| `render_video` | Plan to stills, preview or final in 9:16 or 16:9: graphics, footage clips, captions, music, sound effects | none |
| `job_status` | State and result of a long job that returned a `job_id` | none |
| `qa_verify_video` | Technical checks (size, fps, loudness, true peak, black gaps, audio length) and frames to look at | none |
| `export_package` | Final folder with the videos, covers and `post.md`. Refuses when QA has a hard failure | none |
| `calculate_beat_grid` | Tempo and beat grid of a music track | none |
| `search_sfx` (with `download=[ids]`, `out_dir`) | Freesound sound effects (CC0 by default). They read public Freesound pages | none |
| `run_script` | Runs your own Python scripts from the scripts folder | none |
| `learn_and_record_memory` | Saves a lasting user preference; `studio_guide` returns it in later sessions | none |
| `doctor` | Environment check: Python, ffmpeg, Node, engine, numpy, Pillow, optional extras, keys, output folder | none |

## Plan example

A plan is a JSON description of the scenes. This one is checked by the plan model in `src/omniframe/plan.py`:

```json
{
  "version": 2,
  "format": "9:16",
  "style": "dark",
  "hud": {
    "at": 0.5, "until": 5.5,
    "rows": [
      {"label": "DUE IN", "value": "365 DAYS"},
      {"label": "WORKERS", "value": "0/100"}
    ],
    "pos": "top",
    "accent_changes": [{"at": 3.0, "row": 1, "value": "20/100"}]
  },
  "scenes": [
    {"at": 0.0, "kind": "words", "text": "stop scrolling this right now"},
    {"at": 2.5, "kind": "title", "kicker": "chapter 1", "text": "what is going on here"},
    {"at": 5.0, "kind": "counter", "value": 87, "suffix": "%", "sub": "never finish the video"},
    {"at": 6.5, "kind": "cta", "text": "grab it free", "handle": "@you"}
  ],
  "audio": {"voice": {"src": "audio/voice.mp3"}}
}
```

`hud` is a plan-level overlay, not a scene: a dark plate with monospace values that stays over all
scenes during its interval. `accent_changes` swaps a row's value and highlights it. More plans are in
[`examples/plans/`](examples/plans).

The working order for every plan: `synthesize_voiceover` when the video has a voiceover, then
`render_video` in `stills` mode (the model looks at each frame), then `preview`, then `final`, then
`qa_verify_video`, then `export_package`.

## Coming soon

AI video clips through Google Flow (Veo) are coming in the next update. The current code is on branch `veo-wip`.

## Honest notes

- **Captions come from the plan.** The engine draws them from the plan's `captions` block. OmniFrame
  writes no `.ass` files.
- **Free ElevenLabs plans** may not reach library voices through the API. `voice_options` says so
  when that happens.

## How the model works with OmniFrame

- The model calls `studio_guide` first. It returns the working order, the tools and providers
  available, and the user's saved preferences.
- Long work (renders, QA of long files) returns a `job_id`. The model polls `job_status`.
- The build used Claude Opus 5.5 for planning and audits, Claude Sonnet 5.5 for the core tasks, and
  Claude Haiku 5.5 for smaller tasks, all inside Kiro. The edit is only as good as the direction the
  model gives OmniFrame, so each step ends with pictures the user can check.

## How it was built with Kiro

- **Spec.** `.kiro/specs/argus-v2/` holds the requirements, the design and the task list. Each task
  names the design sections to read, the files to touch and its verify steps.
- **Steering.** `.kiro/steering/product.md`, `tech.md` and `engine.md` set the product rules (no
  creative gates), the code conventions (tools return pictures through `tool_result`, long work runs
  as jobs) and the engine rules.
- **Hooks.** `.kiro/hooks/` runs the engine typecheck on every save of an engine source file. It also
  runs the test suite when a spec task is marked done.
- **MCP.** `.kiro/settings/mcp.json` registers OmniFrame in Kiro. After a reload, the chat calls its tools.
- **Build log.** [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) has an entry per task: the model used, what
  was built, the bugs and their fixes, and what was verified.

## Disclosure

OmniFrame grew from ATLAS, the author's personal script written before the hackathon. The first MCP
prototype (v1) was built in ZCode during the submission period (first commit 2026-11-04). v2 was
rebuilt spec-first in Kiro; the spec, steering, hooks and build log are in `.kiro/` and
`docs/BUILD_LOG.md`.

## Category: Frankenstein

The Kiroween rules ask for a project that will "stitch together a chimera of technologies into one
app" (https://kiroween.devpost.com/rules). OmniFrame does that. A chat model directs a frame-exact React
renderer (Remotion), ffmpeg audio and video processing, speech recognition (faster-whisper), voices
(edge-tts, ElevenLabs, Gemini) and Freesound sounds. The model
sees the video through contact sheets and stills.

## Third-party code and assets

Code, fonts and media from other projects, with their licenses, are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The main ones are video-shotcraft (Apache 2.0) and
Remotion (its own license).

## License

Copyright (C) 2026 vertovhq

OmniFrame is free and open source under the [AGPL-3.0-or-later](LICENSE). Made by VertovHQ.
Commercial licensing: contact VertovHQ.

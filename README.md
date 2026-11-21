# ARGUS

**An MCP studio for vertical video: two content paths — AI generation and pure graphics.**

> ⚠️ Install only from the official repository. The Flow provider uses **your own single
> Google account session** — it never shares cookies and never farms accounts; multi-account
> credit farming gets accounts banned.

| Works with |
|---|
| Any MCP client: **ZCode**, Claude Desktop / Claude Code, Cursor, Codex, OpenCode, Gemini CLI — skills install to `~/.zcode/skills/` or `~/.claude/skills/` |

ARGUS assembles 1080×1920 clips from anything: Veo 3.1 clips via the official Gemini API
or via your own Google Flow browser session (free monthly credits, no manual cookies),
or with no AI at all — vertical kinetic typography rendered locally by the bundled
Remotion engine from a JSON plan. Plus voiceover with word timings, captions drawn from
those timings, rendering, QA and export — all as MCP tools your AI assistant can drive.

```
                    ┌─▶ generate_veo_clip (api | flow) ──┐
prompts ────────┤                                        ├──▶ render_video ──▶ QA ──▶ export_package
script ─────────┴─▶ graphics scenes in the plan ─────────┘      ▲   (9:16 / 16:9, −14 LUFS)
voice ──▶ synthesize_voiceover (audio + word timings) ──────────┘
```

## Tools

| Tool | What it does | Offline |
|---|---|---|
| `studio_guide` | Working method, available tools and providers, and the user's saved preferences. Called first in every session | ✅ |
| `watch_video` | Shots, contact sheets, transcript words and sound events of a video, as images and timecodes | ✅ |
| `get_frames` | Exact frames of a video as images (optionally cropped) | ✅ |
| `voice_options` | Voices and providers available now | ✅ |
| `synthesize_voiceover` | Voice audio plus word timings (edge-tts, Gemini, ElevenLabs), mastered to −14 LUFS | edge-tts needs network |
| `generate_veo_clip` | Veo 3.1 clip. `provider="api"` — official API (paid; Veo has no free API tier); `provider="flow"` — your flow.google session (free credits, one-time `flow_login`) | — |
| `flow_login` | One-time Flow login wizard: opens a window, you log in, the session profile is saved. No cookie files. One own account — credit farming gets accounts banned | — |
| `render_video` | Plan → stills, preview or final in 9:16 / 16:9: graphics scenes, footage clips, captions, music and sound effects from the plan | ✅ |
| `job_status` | State and result of a long operation that returned a `job_id` | ✅ |
| `qa_verify_video` | Technical checks (size, fps, loudness, peaks, black gaps, A/V length) plus frames to look at | ✅ |
| `export_package` | Final folder: videos, covers, `post.md` | ✅ |
| `calculate_beat_grid` | Tempo and beat grid of a music track | ✅ |
| `search_sfx`, `download_sfx` | Freesound CC0 sound effects | — |
| `run_script` | Runs your own Python scripts from `scripts/` | ✅ |
| `learn_and_record_memory` | Saves a lasting user preference; `studio_guide` returns it in later sessions | ✅ |
| `doctor` | One-command environment self-check (`argus-doctor` CLI or MCP): python / ffmpeg / Node / engine / numpy / Pillow / optional faster-whisper, edge-tts, playwright, keys / output dir — ✓/✗/⚠ table with an exact install command under every ✗ | ✅ |

## Install

Requirements: Python 3.11+, ffmpeg on PATH. Node.js 18+ for the kinetic engine.

```bash
git clone <your argus-studio repo url>     # or download and unpack an archive
cd argus-studio
bash install.sh          # or: powershell -ExecutionPolicy Bypass -File install.ps1
```

Manual path:

```bash
pip install -e ".[dev,pretty,voice]"  # voice = edge-tts (free TTS); add flow → pip install -e ".[flow,pretty]"
playwright install chromium           # only for provider="flow"
cd engine && npm install --no-audit --no-fund && cd ..   # only for kinetic
cp .env.example .env                  # Gemini key for api mode / TTS
```

Benchmark vs the biggest agent-harness repos and the roadmap: [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Connect your assistant

```json
{
  "mcpServers": {
    "argus": {
      "command": "argus-studio",
      "env": { "ARGUS_GEMINI_API_KEY": "your-key", "ARGUS_VEO_PROVIDER": "api" }
    }
  }
}
```

More variants in [`examples/mcp-config.example.json`](examples/mcp-config.example.json).
Full docs in Russian: [README.ru.md](README.ru.md).

## Both content paths

**Through Veo** — cinematic generated footage:

```text
generate_veo_clip(prompt="night city, neon, rain", output_path="out/c1.mp4")
generate_veo_clip(prompt="...", output_path="out/c2.mp4", provider="flow")  # free Flow credits
```

**Through graphics** (no AI, local, free):

```text
render_video(project="demo", mode="stills", times=[1, 4, 8], plan={
  "version": 2,
  "format": "9:16",
  "style": "dark",
  "hud": {                                   # overlay drawn over all scenes
    "at": 0.5, "until": 5.5,                 # plate lifetime, seconds
    "rows": [
      {"label": "DUE IN", "value": "365 DAYS"},
      {"label": "WORKERS", "value": "0/100"}
    ],
    "pos": "top",                            # top | bottom
    "accent_changes": [                      # value swap + accent highlight
      {"at": 3.0, "row": 1, "value": "20/100"}
    ]
  },
  "scenes": [
    {"at": 0.0, "kind": "words", "text": "stop scrolling this right now"},
    {"at": 2.5, "kind": "title", "kicker": "chapter 1", "text": "what is going on here"},
    {"at": 5.0, "kind": "counter", "value": 87, "suffix": "%", "sub": "never finish the video"},
    {"at": 6.5, "kind": "cta", "text": "grab it free", "handle": "@you"}
  ],
  "audio": {"voice": {"src": "audio/voice.mp3"}}
})
```

Look at the stills, then render `mode="preview"` and `mode="final"`. More plans are in
[`examples/plans/`](examples/plans).

`hud` is a plan-level game-UI overlay (not a scene): a semi-transparent dark plate
with monospace values that lives over all scenes inside its interval without
touching them. On `accent_changes` the row's value swaps and gets the accent
highlight (progress "0/100" → "20/100").

Then the same either way: `synthesize_voiceover` → `render_video` (stills, preview, final;
captions come from the plan's `captions` block) → `qa_verify_video` → `export_package`.

## Honest notes

- Veo via API is paid (~$0.40/s quality, ~$0.10–0.12/s Fast); there is no free API tier.
  The free path is `provider="flow"` with your own flow.google credits; it depends on their
  UI — selectors live in one place in `src/argus/tools/flow_browser.py`.
- Captions are drawn by the engine from the plan's `captions` block; there are no `.ass` files.
- Prompts go to Veo exactly as written — no content-policy workarounds.

## License

[MIT](LICENSE)

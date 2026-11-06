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
Remotion engine from a JSON plan. Plus voiceover with voice cloning, frame-accurate
subtitles, pause-snapped scene cutting, master assembly and QA — all as MCP tools your
AI assistant can drive.

The monorepo also ships three editing skills («Эпизод», «Мани», «Эссе») that replicate
personal editing styles from a plan.json — see [`skills/`](skills/README.md) (docs in Russian).

```
                    ┌─▶ generate_veo_clip (api | flow) ──┐
prompts ────────┤                                        ├──▶ assemble ──▶ QA ──▶ master
script ─────────┴─▶ build_kinetic_video (graphics) ─────┘      ▲        (1080×1920, −14 LUFS)
voice ──▶ TTS / voice clone ──▶ timeline ──▶ subtitles ────────┘
```

## Tools (10)

| Tool | What it does | Offline |
|---|---|---|
| `generate_veo_clip` | Veo 3.1 clip. `provider="api"` — official API (paid; Veo has no free API tier); `provider="flow"` — your flow.google session (free credits, one-time `flow_login`) | — |
| `flow_login` | One-time Flow login wizard: opens a window, you log in, the session profile is saved. No cookie files. One own account — credit farming gets accounts banned | — |
| `build_kinetic_video` | **Vertical video from pure graphics**: word-by-word typography, cards, counters, chapters, chip badges, CTA. Auto sound design (whoosh on cuts, pops/hits), music bed. Dark/light themes | ✅ |
| `synthesize_voiceover` | Gemini TTS + radio mastering (−14 LUFS). Voice cloning via `tts.py` in skills | — |
| `build_pop_subtitles` | Karaoke .ass subtitles. Styles: `clean` (white, default), `outline`, `pop` (legacy yellow) | ✅ |
| `calculate_acoustic_timeline` | Cut points snapped to real speech pauses | ✅ |
| `assemble_master_video` | Concat clips + voice/music mix + subtitle burn-in | ✅ |
| `qa_verify_video` | Strict checks: 1080×1920, fps, scan, LUFS ±2 | ✅ |
| `learn_and_record_memory` | Production lessons into KNOWLEDGE_BASE.md | ✅ |
| `doctor` | One-command environment self-check (`argus-doctor` CLI or MCP): python / ffmpeg+libass / Node / engine / edge-tts / playwright / Gemini key / output dir — ✓/✗/⚠ table with an exact install command under every ✗ | ✅ |

## Install

Requirements: Python 3.11+, ffmpeg on PATH. Node.js 18+ for the kinetic engine.

```bash
git clone <your argus-studio repo url>     # or download and unpack an archive
cd argus-studio
bash install.sh          # or: powershell -ExecutionPolicy Bypass -File install.ps1
```

Manual path:

```bash
pip install -e ".[dev,pretty,voice]"  # voice = edge-tts (free skills TTS); add flow → pip install -e ".[flow,pretty]"
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
build_kinetic_video(plan={
  "theme": "dark",
  "voice": "out/voiceover.mp3",
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
  ]
}, output_path="out/kinetic.mp4")
```

`hud` is a plan-level game-UI overlay (not a scene): a semi-transparent dark plate
with monospace values that lives over all scenes inside its interval without
touching them. On `accent_changes` the row's value swaps and gets the accent
highlight (progress "0/100" → "20/100").

Then the same either way: `synthesize_voiceover` → `calculate_acoustic_timeline` →
`build_pop_subtitles(style="clean")` → `assemble_master_video` → `qa_verify_video`.

## Honest notes

- Veo via API is paid (~$0.40/s quality, ~$0.10–0.12/s Fast); there is no free API tier.
  The free path is `provider="flow"` with your own flow.google credits; it depends on their
  UI — selectors live in one place in `src/argus/tools/flow_browser.py`.
- Subtitles default to the `clean` white style; the yellow `pop` style is legacy opt-in.
- Prompts go to Veo exactly as written — no content-policy workarounds.
- `skills/` ships without paid-subscription sounds or personal media — add your own.

## License

[MIT](LICENSE)

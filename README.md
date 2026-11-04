# ARGUS

**An MCP studio for vertical video: two content paths — AI generation and pure graphics.**

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

## Tools (9)

| Tool | What it does | Offline |
|---|---|---|
| `generate_veo_clip` | Veo 3.1 clip. `provider="api"` — official API (paid; Veo has no free API tier); `provider="flow"` — your flow.google session (free credits, one-time `flow_login`) | — |
| `flow_login` | One-time Flow login wizard: opens a window, you log in, the session profile is saved. No cookie files. One own account — credit farming gets accounts banned | — |
| `build_kinetic_video` | **Vertical video from pure graphics**: word-by-word typography, cards, counters, chapters, CTA. Dark/light themes, modern look, no yellow | ✅ |
| `synthesize_voiceover` | Gemini TTS + radio mastering (−14 LUFS). Voice cloning via `tts.py` in skills | — |
| `build_pop_subtitles` | Karaoke .ass subtitles. Styles: `clean` (white, default), `outline`, `pop` (legacy yellow) | ✅ |
| `calculate_acoustic_timeline` | Cut points snapped to real speech pauses | ✅ |
| `assemble_master_video` | Concat clips + voice/music mix + subtitle burn-in | ✅ |
| `qa_verify_video` | Strict checks: 1080×1920, fps, scan, LUFS ±2 | ✅ |
| `learn_and_record_memory` | Production lessons into KNOWLEDGE_BASE.md | ✅ |

## Install

Requirements: Python 3.11+, ffmpeg on PATH. Node.js 18+ for the kinetic engine.

```bash
git clone https://github.com/your-name/argus-studio
cd argus-studio
pip install -e ".[dev,pretty]"       # add flow → pip install -e ".[flow,pretty]"
playwright install chromium           # only for provider="flow"
cd engine && npm install --no-audit --no-fund && cd ..   # only for kinetic
cp .env.example .env                  # Gemini key for api mode / TTS
```

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
  "scenes": [
    {"at": 0.0, "kind": "words", "text": "stop scrolling this right now"},
    {"at": 2.5, "kind": "title", "kicker": "chapter 1", "text": "what is going on here"},
    {"at": 5.0, "kind": "counter", "value": 87, "suffix": "%", "sub": "never finish the video"},
    {"at": 6.5, "kind": "cta", "text": "grab it free", "handle": "@you"}
  ]
}, output_path="out/kinetic.mp4")
```

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

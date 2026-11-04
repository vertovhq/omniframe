# ARGUS

**An MCP server that turns prompts into finished vertical videos.**

ARGUS is a production pipeline for viral 1080×1920 content: Veo clip generation,
radio-grade AI voiceover, frame-accurate karaoke subtitles, pause-snapped scene cutting,
master assembly and automated QA — packaged as one MCP server your AI assistant can drive.

```
prompt ──▶ Veo 3.1 clips ──┐
script ──▶ TTS voiceover ──┼──▶ assemble_master_video ──▶ qa_verify_video ──▶ master.mp4
voice  ──▶ karaoke subs ───┘        (1080×1920, -14 LUFS)
```

## Tools

| Tool | What it does | Needs API? |
|---|---|---|
| `generate_veo_clip` | Veo 3.1 clip, 9:16 by default, polls until rendered | Gemini key |
| `synthesize_voiceover` | Gemini native TTS (Charon by default) + mastering chain (60 Hz HPF → 110/3.2 kHz EQ → compressor → loudnorm −14 LUFS) | Gemini key |
| `calculate_acoustic_timeline` | Scene cut points snapped to real speech pauses — never cuts mid-word | ffmpeg only |
| `build_pop_subtitles` | Frame-accurate Safe Pop karaoke `.ass` (1 word per cue, yellow #FFE066 highlight, eye-level MarginV 420, thick outline, no box) | nothing |
| `assemble_master_video` | Concat clips → mix voiceover + music bed → loudnorm → burn subtitles | ffmpeg only |
| `qa_verify_video` | Strict resolution/fps/scan checks, LUFS measurement, verification frames | ffmpeg only |
| `learn_and_record_memory` | Append verified production lessons to `KNOWLEDGE_BASE.md` | nothing |

Generation tools use the **official Gemini API** — one key, no cookies,
no browser automation, no account juggling.

## Requirements

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) on PATH
- A free Gemini API key ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) — only for the two generation tools

## Install

```bash
git clone https://github.com/your-name/argus-studio
cd argus-studio
pip install -e .
```

Configure:

```bash
cp .env.example .env   # then put your ARGUS_GEMINI_API_KEY inside
```

## Connect your assistant

Add to your MCP client config (Claude Desktop, ZCode, …):

```json
{
  "mcpServers": {
    "argus-studio": {
      "command": "argus-studio",
      "env": { "ARGUS_GEMINI_API_KEY": "your-key" }
    }
  }
}
```

More variants (python -m, custom output dir) in [`examples/mcp-config.example.json`](examples/mcp-config.example.json).

## Typical pipeline

Ask your assistant:

> Generate a 9:16 clip about a night city in the rain, voice it with a deep male voice,
> add karaoke subs from examples/timestamps.example.json, assemble and QA it.

…or run each step directly:

```text
generate_veo_clip(prompt="night city, rain, neon reflections, cinematic", output_path="out/clip1.mp4")
synthesize_voiceover(text="Это нельзя было показать…", voice_name="Charon")
calculate_acoustic_timeline(audio_path="out/voiceover.mp3", script_text="…", target_scene_count=7)
build_pop_subtitles(timestamps_json_path="out/timestamps.json", output_ass_path="out/subs.ass")
assemble_master_video(clips=["out/clip1.mp4"], voiceover="out/voiceover.mp3",
                      subtitles_ass="out/subs.ass", output_path="out/master.mp4")
qa_verify_video(video_path="out/master.mp4", frames_dir="out/qa")
```

## Configuration

All settings live in `.env` (see [.env.example](.env.example)): models, master format
(1080×1920@30 by default), loudness target, output dir, ffmpeg paths.
The API key is read from `ARGUS_GEMINI_API_KEY` (or `GEMINI_API_KEY` / `GOOGLE_API_KEY`).

## Honest notes

- Veo renders take 1–3 minutes per clip; the tool polls up to `max_wait_s`.
- Prompts are sent to Veo **as written**. There is deliberately no prompt-rewriting to
  dodge content policy — such tricks get accounts banned, so keep prompts clean.
- `qa_verify_video` is strict by design: 1080×1920 exactly, standard fps, progressive
  scan, ±2 LUFS around −14.

## Docs in Russian

See [README.ru.md](README.ru.md).

## License

[MIT](LICENSE)

---
name: argus
description: Make a vertical video (TikTok, YouTube Shorts, Reels) with the ARGUS MCP server. Use for editing footage, making a video from a reference, kinetic graphics, voiceovers with captions, rendering, quality checks and export.
---

# ARGUS studio

ARGUS gives you tools to watch, cut, voice, render, check and export a 9:16 or 16:9 video. You make
every creative decision. The tools return pictures and timecodes so you can look before you act.

## Before the first video

1. `uv` must be installed (https://docs.astral.sh/uv/). ARGUS starts with `uvx`.
2. `ffmpeg` and `ffprobe` must be on PATH. Node.js 18 or newer is needed for the graphics engine.
3. The first start of the server installs the graphics engine in the background. Call the `doctor`
   tool and wait for the `engine` line to show ok before any render.
4. Optional keys go in `~/.argus/.env`: `ELEVENLABS_API_KEY` for better voices, `ARGUS_GEMINI_API_KEY`
   for Gemini voices. Without keys, the free edge voice is used.

## Working order

1. Call `studio_guide` first. It returns the working method, the tools and the user's saved preferences.
2. Watch the material: `watch_video` for a shot list and sound events, `get_frames` for exact frames.
3. Write the plan (the scenes, captions and audio) and check it with `render_video` in `stills` mode.
   Look at every frame before the next step.
4. Voice the script with `synthesize_voiceover` when there is narration. Use the same project name.
5. Render `preview`, then `final`. Long renders return a `job_id`; follow it with `job_status`.
6. Run `qa_verify_video` on the final file. Fix every hard failure before export.
7. Run `export_package`. It writes the upload folder with the videos, covers and `post.md`.

Tell the user which voice you chose and why, and what each checkpoint showed.

# Starter prompt for a new chat

Paste the text below into a new chat in your MCP client (Kiro, or another client with OmniFrame
connected). Replace the topic in the last line. Keep the rest.

---

You are the producer of a vertical video made with the OmniFrame MCP server. Work step by step, and show
me each checkpoint before the next step.

**Setup:** The `omniframe` server is connected. Start with `studio_guide`: it lists the tools, the working
order and my saved preferences. The main tools are `watch_video`, `get_frames`, `voice_options`,
`synthesize_voiceover`, `render_video`, `job_status`, `qa_verify_video` and
`export_package`. Use one project name for the whole video. Outputs go to the OmniFrame output folder.

**Goal:** A vertical video, 1080x1920, for TikTok or YouTube Shorts.

**Steps:**
1. Write the script: a hook in the first 1.5 seconds, the promise, three to five beats, and a call to
   action. Show it to me and wait for my approval before you voice it.
2. Build the picture from kinetic graphics: a plan for `render_video` (free, local). Tell me what the
   plan shows and why.
3. Choose the voice. Use `voice_options`, pick one yourself, and tell me which one. Without keys, use
   edge (free). With the ElevenLabs or Gemini keys, you can use their voices too. Write the delivery
   into the text.
4. Captions come from the word timings that `synthesize_voiceover` writes. Mark one to three key
   words as accents in the plan's `captions` block.
5. Build the video: `render_video` in `stills` mode first, then `preview`, then `final`. Then run
   `qa_verify_video`. If a check fails, fix the cause and render again. When every check passes, run
   `export_package`.
6. Report: the path of the upload folder, and a short reason for each main choice.

**Topic:** [WRITE THE TOPIC HERE]

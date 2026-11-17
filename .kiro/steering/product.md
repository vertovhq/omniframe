# ARGUS — product steering

ARGUS is an MCP server that turns the AI model inside Kiro (or any MCP client)
into a video editor and producer. The model is the director. ARGUS tools are its
eyes, ears and hands: they watch, listen, render, check and package. They never
make creative decisions.

## Who uses it

- Solo creators making TikTok / YouTube Shorts / YouTube videos. The author runs
  his own TikTok channel with ARGUS: "here is a reference, make a continuation /
  an analog / my idea in this style".
- Experts with no editing skills, e.g. a doctor with a talking-head recording:
  "here is my video, edit it with effects".

## Scenarios ARGUS must handle

1. **Reference → new video**: analog, continuation, or the user's own idea in the
   reference's style.
2. **User footage → edited video**: cuts (stumbles, repeats, long pauses),
   captions, zooms, b-roll/graphics, sound effects, music.
3. **Idea → video from scratch**: graphics (kinetic engine), AI clips (Veo), or both.

Output of every scenario: a 9:16 and/or 16:9 file ready to upload, a cover image,
and title / description / hashtags. Publishing stays manual (no platform APIs).

## Principles (apply to every change)

- Creative judgement belongs to the model. Do not add code that scores, grades or
  gates stories, styles or "originality". No percentage thresholds on creative content.
- Tools hand the model material it can actually perceive: images (MCP image
  content), timecodes, transcripts, sound events. File paths alone are not enough.
- Deterministic checks are allowed only for technical defects: resolution, fps,
  loudness, peaks, black gaps, A/V length, broken files.
- Fewer, clearer tools beat many overlapping ones. One renderer: the Remotion engine.
- Works without paid keys (edge-tts voice, graphics, user footage). Paid services
  (ElevenLabs, Gemini/Veo) add quality, never gate basic use.
- Long jobs never block an MCP call: they run detached and report via `job_status`.
- No clutter: work files live in `<project>/.work/` and are removed after export.
- Tool messages are in English; the model talks to the user in the user's language.

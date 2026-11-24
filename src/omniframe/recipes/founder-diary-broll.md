# Founder diary with b-roll

## What it is
A first-person diary of a day or a project: the user's voice over their own footage, with short b-roll cuts and dated text notes.

## Fits when
A person shares progress on a project or a working day, with real footage and their own voice.

## Hook, first 3 s
Open on the most striking b-roll shot, with the first line spoken over it. The date card appears at 0 to 1 s.

## Shot order
**15 s**
- 0-3 s: hook shot and line.
- 3-10 s: two b-roll shots under the voice.
- 10-14 s: result shot.
- 14-15 s: end card.

**30 s**
- 0-3 s: hook.
- 3-12 s: morning shots.
- 12-21 s: the work.
- 21-27 s: a setback shot.
- 27-30 s: end card.

**60 s**
- 0-4 s: hook.
- 4-16 s: start of the day.
- 16-30 s: work block.
- 30-42 s: a problem.
- 42-53 s: the fix.
- 53-57 s: end of the day.
- 57-60 s: end card.

## Captions and type
Phrase captions at the lower position. Dates are title scenes: the kicker holds the date or the day count. Move captions to the upper position when a face sits low in the frame.

## Motion and transitions
Cut at phrase ends and on picture changes; use a hard cut inside a moment. A short dissolve only across a time jump. Keep the handheld feel of the footage and do not add shake.

## Sound and music
The clip's own sound at low level under the voice. A quiet music bed. One soft sound on each date card.

## Material needed
Own footage (a phone is enough; keep the same frame rate across clips), the user's voice or a synthesized one, and a list of dates.

## Common mistakes
- Clip sound louder than the voice.
- Clips from several phones with mixed frame rates, which makes the render slower.
- Captions that cover faces in the footage.

## OmniFrame tools to use
- `watch_video`: shots, sound events and words of each clip.
- `get_frames`: check a frame at each cut.
- `calculate_beat_grid`: beats for the music bed, if it has a clear pulse.
- `render_video(mode="preview")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`.

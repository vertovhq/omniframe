# Product launch reveal

## What it is
A teaser that builds a question, a hard reveal of the product, three benefits, and the name with a call to action.

## Fits when
A new product, app or update is announced, and it has a strong visual (render, packaging or screen) or a clear name.

## Hook, first 3 s
Open on a dark or blank frame with a riser and the question in one spoken line. The reveal lands at 2 to 4 s.

## Shot order
**15 s**
- 0-3 s: teaser, blank frame, riser.
- 3-5 s: reveal, flash cut, hit.
- 5-11 s: three benefits, about 2 s each.
- 11-15 s: name and call to action.

**30 s**
- 0-4 s: teaser.
- 4-6 s: reveal.
- 6-18 s: three benefits, about 4 s each.
- 18-24 s: the product in motion.
- 24-30 s: name and call to action.

**60 s**
- 0-8 s: teaser.
- 8-11 s: reveal.
- 11-30 s: three benefits, about 6 s each.
- 30-45 s: product demo.
- 45-55 s: proof with a counter.
- 55-60 s: name and call to action.

## Captions and type
The product name is a big title scene. Voice in phrase captions at the lower position. Benefits are chip scenes, one line each.

## Motion and transitions
Build with a zoom or a speed ramp, reveal with a flash cut on the hit, and bring in the benefits with a pop or a slide. Keep the strongest effect for the reveal; the rest stays plain.

## Sound and music
A riser under the teaser. A hit on the reveal, with its peak placed on the cut (`audio.sfx` with the peak aligned to the cut). A short silence before the hit. Music cut to the beat grid.

## Material needed
A product render, packaging or screen recording, plus the name and one line per benefit. Graphics or own footage both work.

## Common mistakes
- Revealing the product before the teaser has set a question.
- Three benefits that say the same thing.
- A riser that stops before the hit.

## OmniFrame tools to use
- `search_sfx`: riser and hit sounds with their licence lines.
- `calculate_beat_grid`: beats for the cuts.
- `render_video(mode="audio")`: the sound timeline, before the preview.
- `render_video(mode="final")`, then `qa_verify_video` and `export_package`.

# Beat-synced visuals

## What it is
A short video where every cut, title and effect lands on the beat of one music track.

## Fits when
The user has a music track and wants a rhythm-led video: a montage, a product in motion, or a trailer-style cut.

## Hook, first 3 s
Start on the first strong beat with the strongest visual. The title lands on the first downbeat.

## Shot order
**15 s**
- 0-2 s: hook on the first beat.
- 2-7 s: four cuts, every second beat.
- 7-13 s: faster cuts, every beat.
- 13-15 s: last hit and end card.

**30 s**
- 0-3 s: hook.
- 3-12 s: cuts every two bars.
- 12-22 s: cuts every bar, one effect.
- 22-28 s: peak, with a burst and a flash.
- 28-30 s: end card.

**60 s**
- 0-4 s: hook.
- 4-18 s: slow build.
- 18-34 s: cuts every bar.
- 34-44 s: breakdown, quiet, one shot.
- 44-56 s: final build with faster cuts.
- 56-60 s: hit and end card.

## Captions and type
Titles and single words only, landing on the beat. No phrase captions unless there is speech. Keep the type heavy and large.

## Motion and transitions
Snap every cut to the beat grid from `calculate_beat_grid`. Use flash, whip or slice transitions on the strong beats only, and plain cuts for the rest. A shot with text holds long enough to read.

## Sound and music
The track is the sound: full level in the loud parts, a beat of silence before the biggest hit, and an impact on the drop, with its peak on the cut. Whooshes only on the strong beats.

## Material needed
A music track with clear rights (licensed or the user's own), and footage or graphics for each cut. Both work.

## Common mistakes
- Every cut on a beat, so no shot holds long enough to see.
- Trusting a low-confidence reading from `calculate_beat_grid`. Check a few cuts by ear in the audio render first.
- An effect on every beat, so the strong beats lose their meaning.

## OmniFrame tools to use
- `calculate_beat_grid`: tempo, beats and snapped cut times.
- `search_sfx`: impacts and whooshes with their licence lines.
- `render_video(mode="audio")`: the sound timeline, before the preview.
- `render_video(mode="final")`, then `qa_verify_video` and `export_package`.

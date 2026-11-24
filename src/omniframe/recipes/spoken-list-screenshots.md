# Spoken list with screenshots

## What it is
A narrated list where each item gets its own image, and its name is on screen while the voice reads it.

## Fits when
The video names several things (apps, books, places, products), and each one has an image the user can show.

## Hook, first 3 s
Open on the strongest item's image, with the list promise spoken in the first second, for example "five apps worth installing".

## Shot order
**15 s**
- 0-2 s: hook.
- 2-6 s: item 1.
- 6-10 s: item 2.
- 10-14 s: item 3.
- 14-15 s: end card.

**30 s**
- 0-3 s: hook.
- 3-23 s: items 1 to 4, about 5 s each.
- 23-27 s: item 5.
- 27-30 s: end card.

**60 s**
- 0-4 s: hook.
- 4-53 s: items 1 to 7, about 7 s each.
- 53-57 s: the best item again.
- 57-60 s: end card.

## Captions and type
Item names as title scenes: the kicker holds the count ("2 of 5") and the text holds the name. Voice in phrase captions at the lower position.

## Motion and transitions
Each image enters with a slow push-in and leaves on a hard cut. No spins or flashy transitions. Set `fit` to contain on an image card when cropping would hide the part that matters.

## Sound and music
Voice first. One soft tick when each item title appears. Music low, and ducked under speech when the plan has captions.

## Material needed
Screenshots or images at 1080 px or more on the long side, which the user has the right to show.

## Common mistakes
- Screenshots too small or blurry at phone size.
- Items read in a different order from the titles.
- More than seven items in 60 s. Each item needs time to be read.

## OmniFrame tools to use
- `voice_options`, then `synthesize_voiceover`: narration with word timings for captions.
- `render_video(mode="stills")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`.

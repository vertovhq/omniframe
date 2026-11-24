# Numbered tips, kinetic type

## What it is
A list of numbered tips. Each tip is a big kinetic title on screen with one short spoken explanation.

## Fits when
The topic is one clear subject and the content is five or more short, separate tips.

## Hook, first 3 s
Open on the strongest tip as a bold claim, spoken in the first second. Show the count ("3 tips") at once so the viewer knows the promise.

## Shot order
**15 s**
- 0-3 s: hook line and the count, in big type.
- 3-10 s: tips 1 and 2, one big title and one spoken line each.
- 10-14 s: tip 3, the same layout, the last word stressed.
- 14-15 s: end card with a save prompt.

**30 s**
- 0-3 s: hook.
- 3-9 s: tip 1.
- 9-15 s: tip 2.
- 15-21 s: tip 3.
- 21-26 s: tip 4.
- 26-30 s: end card.

**60 s**
- 0-4 s: hook.
- 4-49 s: five tips, about 9 s each.
- 49-55 s: recap, all five titles stacked as a list.
- 55-60 s: end card with a save prompt.

## Captions and type
Voice in phrase captions at the lower position. Tip titles are big scenes, not captions. Use a heavy display font, and one accent colour for the number.

## Motion and transitions
Each title slams in when its word is spoken (a cue in the plan), holds for 1.5 to 2 s, then cuts. Use a whip transition between tips, not a slow fade.

## Sound and music
A short tick on each number and a whoosh on each whip. Music under the voice at low volume. Music ducks under speech only when the plan has captions. Land the last tip on a music hit.

## Material needed
Graphics only: titles, numbers and the voiceover. Add one own-footage shot per tip if you have one.

## Common mistakes
- A tip that needs more than eight seconds. Split it or shorten it.
- A count on screen that does not match the number of tips.
- Captions that cover the tip title.

## OmniFrame tools to use
- `voice_options`, then `synthesize_voiceover`: the narration and its word timings.
- `calculate_beat_grid`: beats for the title hits.
- `render_video(mode="stills")`, then `render_video(mode="preview")` and `render_video(mode="final")`.
- `qa_verify_video` before `export_package`.

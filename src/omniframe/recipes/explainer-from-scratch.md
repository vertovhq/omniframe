# Explainer from scratch

## What it is
A narrated explainer made only from graphics: one idea per scene, with a diagram or big text for each step.

## Fits when
The user has an idea or a concept and no footage, and the video explains how something works.

## Hook, first 3 s
State the question in one spoken line over the first diagram. Show the first element of the answer at once.

## Shot order
**15 s**
- 0-3 s: question.
- 3-9 s: step 1 diagram.
- 9-14 s: step 2 and the result.
- 14-15 s: end card.

**30 s**
- 0-3 s: question.
- 3-11 s: step 1.
- 11-20 s: step 2.
- 20-26 s: step 3.
- 26-30 s: end card.

**60 s**
- 0-5 s: question.
- 5-17 s: step 1.
- 17-30 s: step 2.
- 30-42 s: step 3.
- 42-53 s: a worked example.
- 53-57 s: recap.
- 57-60 s: end card.

## Captions and type
Phrase captions at the lower position for the voice. The key term of each step is a big title scene, with a kicker that holds the step number.

## Motion and transitions
Build each diagram in stages, with one cue per element, so the picture moves with the words. Fade or whip between steps. No burst effects.

## Sound and music
Voice clear and centred. A soft tick when each element appears, on its cue. Music very low, or none.

## Material needed
Graphics only: text, shapes and diagrams drawn in custom scenes (the kit `info` and `depth` groups, or plain React or SVG for a diagram), and a voiceover.

## Common mistakes
- More than three elements visible in one scene.
- A diagram element that appears before the voice names it.
- A custom component that tries to load a file or an address from the web. Components have no network access.

## OmniFrame tools to use
- `voice_options`, then `synthesize_voiceover`: narration and word timings.
- `render_video(mode="stills")`: check each diagram.
- `render_video(mode="final")`, then `qa_verify_video` and `export_package`.

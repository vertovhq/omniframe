# Product proof with a speaker in the corner

## What it is
The product or a claim is shown on a real screen or a demo, and the speaker sits in a small box in the corner.

## Fits when
A product, app or service must show that a claim is true: a feature working, a number, or a before and after.

## Hook, first 3 s
Start on the proof itself, with the claim spoken over it in the first second. The speaker box appears at about 2 s.

## Shot order
**15 s**
- 0-3 s: proof and claim.
- 3-10 s: the proof in steps, zoomed to the number.
- 10-14 s: the number as a counter.
- 14-15 s: end card.

**30 s**
- 0-3 s: claim.
- 3-12 s: proof 1.
- 12-21 s: proof 2, with a counter.
- 21-27 s: the speaker explains, box large.
- 27-30 s: end card.

**60 s**
- 0-4 s: claim.
- 4-16 s: proof 1.
- 16-28 s: proof 2.
- 28-40 s: proof 3, with a counter.
- 40-50 s: the speaker explains, box large.
- 50-56 s: before and after.
- 56-60 s: end card.

## Captions and type
Phrase captions at the lower position. On full-screen proof shots, move them to the upper position so they do not cover the number.

## Motion and transitions
Zoom into the number that matters, with a focus point, then cut. The speaker box is an overlay, so the proof stays visible under it. Keep one counter per proof.

## Sound and music
Speech on top. Keep the product's own sound low, or replace it with one click per proof. Music quiet and ducked under speech.

## Material needed
A screen recording of the product, speaker footage for the box (optional), and the source of every number, kept for the description.

## Common mistakes
- A claim the proof does not show on screen.
- A speaker box that covers the number.
- A number in the post text with no source.

## OmniFrame tools to use
- `watch_video`: cut points and sound events of the recording.
- `get_frames`: check that the number is readable.
- `render_video(mode="stills")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`, with the sources in the post texts.

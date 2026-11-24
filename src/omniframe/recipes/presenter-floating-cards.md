# Presenter with floating cards

## What it is
A talking head with each key fact shown as a card that floats in beside the speaker when it is said.

## Fits when
A person talks to camera and the points are facts, numbers or named items the viewer should remember.

## Hook, first 3 s
Start tight on the face, with the first claim spoken in the first second. A card with the claim's number appears at about 2 s.

## Shot order
**15 s**
- 0-3 s: face, claim, first card.
- 3-10 s: face with one card per point, two points.
- 10-14 s: face and the last point's card.
- 14-15 s: end card with the one-line takeaway.

**30 s**
- 0-3 s: hook.
- 3-12 s: point 1 with its card.
- 12-21 s: point 2 with its card.
- 21-27 s: point 3 with its card.
- 27-30 s: end card.

**60 s**
- 0-4 s: hook.
- 4-14 s: point 1.
- 14-26 s: point 2.
- 26-38 s: point 3.
- 38-50 s: point 4.
- 50-55 s: all points as a stacked recap of cards.
- 55-60 s: end card.

## Captions and type
Phrase captions at the lower position. Each card holds at most six words in a heavy display font, one card per fact.

## Motion and transitions
Cards slide in from the side in 0.3 s and leave before the next point. Cards are overlay scenes, so the footage shows under them. Keep the footage still: a slow push-in at most, on the key sentence only.

## Sound and music
A soft tick when a card lands. Voice on top. Music quiet and ducked under speech, which needs captions in the plan.

## Material needed
Own talking-head footage: one take in good light. Graphics for the cards only.

## Common mistakes
- A card that covers the speaker's face.
- A card with more words than the viewer can read in its time.
- A card that appears after the speaker has moved on to the next point.

## OmniFrame tools to use
- `watch_video`: cut points and word timings of the take.
- `get_frames`: check each cut and each card position.
- `render_video(mode="preview")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`.

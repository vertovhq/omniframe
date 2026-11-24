# Tool demo with callouts

## What it is
A screen recording of a tool, step by step, where each step gets a zoom to the action, a callout box and one spoken line.

## Fits when
The video shows how to do a task in an app, a website or a program, in a fixed order.

## Hook, first 3 s
Show the finished result for 3 seconds, with the promise in one line spoken over it. Then start step 1.

## Shot order
**15 s**
- 0-3 s: result and promise.
- 3-10 s: two steps, each with a zoom and a callout.
- 10-14 s: last step.
- 14-15 s: end card.

**30 s**
- 0-3 s: result.
- 3-9 s: step 1.
- 9-16 s: step 2.
- 16-23 s: step 3.
- 23-27 s: step 4.
- 27-30 s: end card.

**60 s**
- 0-5 s: result.
- 5-16 s: step 1.
- 16-27 s: step 2.
- 27-38 s: step 3.
- 38-48 s: step 4.
- 48-54 s: a shortcut tip.
- 54-60 s: end card.

## Captions and type
Phrase captions. When a callout sits low on the screen, move the captions to the upper position. Callout text is short: the name of the button or the field.

## Motion and transitions
Zoom to the element the callout names, ease in over 0.4 s, hold 1 to 2 s, then zoom out before the next step. Time each callout to the spoken word that names it, using a cue in the plan.

## Sound and music
A light click on each callout. Voice on top. Music optional and low.

## Material needed
Own screen recording at 1080 px or more, with notifications hidden and personal data removed. Graphics for the callout boxes.

## Common mistakes
- Text too small to read at phone size, even after the zoom.
- A callout box that covers the button it names.
- Account names, email addresses or keys visible in the recording.

## OmniFrame tools to use
- `watch_video`: cut points and sound events of the recording.
- `get_frames`: check that small text can be read at each zoom.
- `render_video(mode="stills")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`.

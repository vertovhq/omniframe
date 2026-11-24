# Talking-head lesson

## What it is
One expert explains one method, fact or rule to camera, cut tight, with a title and one visual per point.

## Fits when
A person who knows the subject teaches one idea in one take, and no set or location is needed.

## Hook, first 3 s
Start on the problem as a question the viewer already has, spoken in the first second. No greeting. The title with the topic appears at 0 to 2 s.

## Shot order
**15 s**
- 0-2 s: title with the question.
- 2-9 s: the explanation with one visual.
- 9-14 s: the result, in one line.
- 14-15 s: end card.

**30 s**
- 0-3 s: hook and title.
- 3-12 s: step 1.
- 12-22 s: step 2 with its visual.
- 22-27 s: the mistake to avoid.
- 27-30 s: end card.

**60 s**
- 0-4 s: hook and title.
- 4-17 s: step 1.
- 17-30 s: step 2 with its visual.
- 30-42 s: step 3.
- 42-52 s: the common mistake.
- 52-57 s: recap.
- 57-60 s: end card.

## Captions and type
Phrase captions at the lower position. Name the key term in a title card. Do not put the speaker's name on screen unless the user asks for it.

## Motion and transitions
Cut only at stumbles and long pauses, on word boundaries. Hold on the speaker between cuts. One small push-in on the key sentence at most.

## Sound and music
Speech stays clear and centred. Music is off or very low, and ducks under speech when the plan has captions. One soft sound on each title.

## Material needed
Own talk-to-camera footage, and one visual per point: a screenshot, a chart or a drawn diagram.

## Common mistakes
- A jump cut that splits a word.
- A visual that stays on screen while the speaker talks about something else.
- A long intro before the first point.

## OmniFrame tools to use
- `watch_video`: cut and word timings of the take.
- `get_frames`: check the frame at each cut.
- `render_video(mode="stills")`, `render_video(mode="preview")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`.

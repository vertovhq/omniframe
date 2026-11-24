# Data story with charts

## What it is
A story told in numbers: each scene shows one number or one chart that changes, and the voice gives the meaning.

## Fits when
The user has numbers, a trend or a before and after, and the point is the change.

## Hook, first 3 s
The biggest number on screen in the first second, with the change named in the voice.

## Shot order
**15 s**
- 0-3 s: big number.
- 3-9 s: chart changes.
- 9-13 s: the reason, in one line.
- 13-15 s: end card.

**30 s**
- 0-3 s: number.
- 3-12 s: chart 1.
- 12-20 s: chart 2 with the turning point.
- 20-26 s: comparison.
- 26-30 s: end card.

**60 s**
- 0-5 s: number.
- 5-17 s: chart 1.
- 17-30 s: chart 2.
- 30-42 s: the turning point.
- 42-52 s: comparison.
- 52-57 s: what it means.
- 57-60 s: end card.

## Captions and type
Phrase captions at the lower position. Numbers are counter scenes, with a suffix and a one-line sub label. Round numbers to what the viewer needs.

## Motion and transitions
Counters count up and land on the spoken number (a cue on the word). Charts draw from left to right over about 1 s. Hard cut to each new chart. Hold each chart at least 2.5 s so it can be read.

## Sound and music
A soft tick on each counter step, a hit on the turning point, and music quiet under speech.

## Material needed
The numbers with their source (the source goes in the description), chart data passed as props to a custom scene, and a voiceover.

## Common mistakes
- Unlabelled axes, or a chart with no unit.
- A counter that ends on a different number from the one spoken.
- A number with no source in the post text.

## OmniFrame tools to use
- `voice_options`, then `synthesize_voiceover`.
- `render_video(mode="stills")`, then `render_video(mode="final")`.
- `qa_verify_video`, then `export_package`.

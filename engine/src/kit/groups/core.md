# core: timing, wrappers, text

`import {...} from '../kit'`. Sizes are design px (1080 short side). Times are seconds on the scene's clock (0 = scene start).

**motion** `clamp seg(t,a,b) lerp remap` · `eOut eIn eInOut eBack eElastic eLinear` · `stagger(i,step,start)` · `pulse(t,hz)` · `formatNumber(n,dec,sep)`
**timing** `useT() useDuration() useCue(name,fallback?) useCues() useWords()` · `<SceneTrack scenes={[{at: 0|'cue', enter?, render: ({t,d,i}) => node}]} enter fade/>` (each scene paints its own `Stage`; `enter` kinds are in the `transitions` group)
**at** `useAt(at)` turns a time, a cue name or a list of both into seconds; `ageOf(t, times)` is the seconds since the latest of them (null before the first). Blocks that take `at` call them for you.
**wrappers** `<Fade from to inDur outDur/>` `<Pop from to dur fromScale/>` `<Slide from to side dist/>` (all: `keepSpace`) · `<Stage bg/>` full-frame layer, first thing a scene draws · `<Camera zoom pan from to origin/>` slow push (more camera moves in the `camera` group)
**text** `<Text size color font weight stroke strokeColor shadow glow glowColor caps align spacing lineHeight maxWidth/>` · `<Label size fill color border rotate caps/>` plate with text · `readableOn(bg)` black or white for a hex colour. Kinetic type is in the `type` group.
**media** `mediaUrl(name)` URL of a project file a component names, e.g. `<img src={mediaUrl('media/octo.png')} />`; ARGUS links the file into the render.

Cues: `"cues": {"burn": {"word": "сгорает"}, "end": 41.2}` in the plan; a word cue is where it is spoken (`nth`, `offset`; needs `captions.words`). Read one with `useCue('burn')`, or hand its name to any block that takes `at`.
Scenes that hold a video (`Media` with a video file) render slower than pure graphics: use them where the story needs them.

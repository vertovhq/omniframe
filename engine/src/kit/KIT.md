# Motion kit (`import {...} from '../kit'`)

No look of its own: colours and fonts come from the plan style or props (any CSS colour). Sizes are design px (1080 short side), so blocks work in 9:16 and 16:9. Times are seconds on the scene's clock (0 = scene start). `at` = a time, usually `useCue('hit')`.

**motion** `clamp seg(t,a,b) lerp remap` · `eOut eIn eInOut eBack eElastic eLinear` · `stagger(i,step,start)` · `pulse(t,hz)` · `formatNumber(n,dec,sep)`
**timing** `useT() useDuration() useCue(name,fallback?) useCues() useWords()` · `<SceneTrack scenes={[{at: 0|'cue', enter?, render: ({t,d,i}) => node}]} enter fade/>` (each scene paints its own `Stage`)
**transitions** (`enter` of a scene or track: a kind or `{kind,dur,strength,dir,color,count,shape,soft,seed}`; kinds `fade whip zoom wipe slice split flash glitch shake ramp`; pick per cut by the story's energy, not fade by default) · `<Transition spec role='in'|'out' t/>` · `transitionDur(spec)`
**wrappers** `<Fade from to/>` `<Pop from to fromScale/>` `<Slide from to side dist/>` (`keepSpace`) · `<Stage bg/>` · `<Camera zoom pan from to/>`
**backgrounds** (fill the parent, first in a `Stage`) `<Solid color/>` `<Gradient stops angle kind='linear'|'radial' at spin/>` `<AnimatedGradient stops angle speed period/>` `<Mesh colors base count size speed seed/>` `<Grid kind='lines'|'dots' color step line drift/>` `<Stripes color angle width gap drift/>` `<Noise opacity size rate seed blend/>` `<Paper color grain shade ruling='none'|'lines'|'squares'/>` `<Starfield count speed streak centre seed/>` `<Bokeh colors count size speed seed/>` `<LightLeaks colors intensity speed seed/>` `<Vignette color strength size/>` `<Scanlines color gap thickness roll/>` `<Media src fit dim dimColor blur start rate/>` (all: `opacity`)
**text** `<Text size color font weight stroke shadow glow caps align spacing maxWidth/>` · `<Label size fill color border rotate caps/>` · `readableOn(bg)`
**effects** (percent of the parent) `<Glow x y size color opacity hz/>` · `<Particles kind='dust'|'stars' count seed color area/>` · `<LightCone x y width height angle color/>`
**energy** (`at` may be a list; `strength` 1 = normal, `dur` rings out) wrap the picture: `<Shake at dur kind='impact'|'camera' every/>` `<Stepped fps/>` (on twos) `<Boil strength fps frames/>` `<Snap at dir dist zoom appear/>` `<Aberration at dur angle/>` `<Vhs strength roll/>` `<FreezeStamp at until label color/>` · overlay: `<Flash at hold color invert/>` `<FilmBurn at colors side/>` `<LensFlare x y to at color size ghosts/>` `<Burst items at dur rate loop/>` · parts: `<MotionBlur x y/>` `<RgbSplit amount angle/>` `shakeOffset(frame,seed,amp)`
**info** `<Counter to from start dur decimals prefix suffix size color/>` · `<Plate label value color changes alert/>` · `<Delta value label at hold/>` · `<PollCard title options at pick/>` · `<Checklist items at step/>` · `<ProgressBar value at dur label/>` · `<Bubble tail size fill color>` · `<Card width padding fill border>`

Cues: `"cues": {"burn": {"word": "сгорает"}, "end": 41.2}`; a word cue is where it is spoken (`nth`, `offset`; needs `captions.words`).
Scenes with video (`Media`) render slower than graphics only. `Starfield` flies out of a point; `Particles kind='stars'` twinkle in place.

```tsx
import {Camera, Counter, Fade, Glow, Gradient, Grid, Pop, SceneTrack, Stage, Text} from '../kit';
import {useStyle} from '../style';

type Look = {bg?: string[]; ink?: string; accent?: string; loss?: string; grid?: boolean; glow?: number; font?: 'display' | 'body' | 'mono'};
const col = {position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40} as const;

// Any look through props: {"component": "Budget", "props": {...}}
export default function Budget({bg, ink, accent, loss = '#FF4D5E', grid = true, glow = 0.4, font = 'display'}: Look) {
  const {colors} = useStyle();
  const [fg, hi] = [ink ?? colors.text, accent ?? colors.accent];
  return (
    <SceneTrack enter={{kind: 'whip', dir: 'bottom'}} scenes={[
      {at: 0, render: () => (
        <Stage>
          <Gradient stops={bg} kind="radial" at={[50, 40]} />
          {grid && <Grid color={hi} opacity={0.3} drift={[0, 30]} />}
          <Glow y={30} color={hi} hz={0.4} opacity={glow} />
          <Camera zoom={0.05}>
            <div style={col}>
              <Fade from={0.2}><Text size={56} color={fg} font={font} caps>Budget</Text></Fade>
              <Counter to={250000} dur={1.4} size={150} color={hi} font={font} />
            </div>
          </Camera>
        </Stage>
      )},
      {at: 'burn', enter: 'flash', render: () => (
        <Stage>
          <Gradient stops={bg} angle={160} />
          <div style={col}>
            <Pop from={0.2}><Counter from={250000} to={-150000} start={0.6} dur={1} size={150} color={loss} font={font} /></Pop>
          </div>
        </Stage>
      )},
    ]} />
  );
}
```

# Motion kit (`import {...} from '../kit'`)

Mechanics only, no look: colours and fonts come from the plan style or from props. Sizes are design px (1080 short side), so every block works in 9:16 and 16:9. Times are seconds on the scene's clock (0 = scene start; inside a `SceneTrack` scene, that scene's start).

**motion** `clamp(v,lo,hi)` `seg(t,a,b)` progress 0..1 · `lerp(a,b,p)` `remap(v,inA,inB,outA,outB)` · `eOut eIn eInOut eBack eElastic eLinear` · `stagger(i,step,start)` · `pulse(t,hz)` · `formatNumber(n,decimals,sep)`
**timing** `useT()` · `useDuration()` · `useCue(name,fallback?)` · `useCues()` · `useWords()` ({w,s,e}) · `<SceneTrack scenes={[{at: 0 | 'cueName', render: ({t,d,i}) => node}]} fade={0.5}/>` (cross-fade, each scene paints its own `Stage`)
**wrappers** `<Fade from to inDur outDur/>` `<Pop from to dur fromScale/>` `<Slide from to side dist dur/>` (all: `keepSpace`, `style`) · `<Stage bg/>` full-frame layer · `<Camera zoom pan={[x,y]} from to origin/>`
**backgrounds** (fill the parent, put first in a `Stage`) `<Solid color opacity/>` `<Gradient stops angle kind='linear'|'radial' at spin/>` `<Grid kind='lines'|'dots' color opacity step line drift fadeEdges/>` `<Noise opacity size rate seed blend/>` `<Media src fit dim dimColor blur start rate/>` (image or video + dim overlay)
**text** `<Text size color font weight stroke strokeColor shadow glow glowColor caps align spacing maxWidth/>` · `<Label size fill color border rotate caps/>` · `readableOn(bg)`
**effects** (percent of the parent, put in a `Stage`) `<Glow x y size color opacity hz/>` · `<Particles kind='dust'|'stars' count seed color area size speed/>` · `<LightCone x y topWidth width height angle color opacity/>`
**info** `<Counter to from start dur decimals prefix suffix format size color font/>` · `<Plate label value color changes={[{at,color?,value?}]} alert={{from,to,color,hz}}/>` · `<Delta value label at hold positive negative/>` · `<PollCard title options={[{label,share,color?}]} at pick/>` · `<Checklist items={[text | {text,at}]} at step/>` · `<ProgressBar value at dur label showValue/>` · `<Bubble tail tailAt size fill color>` · `<Card width padding fill border>`

Cues: put `"cues": {"burn": {"word": "сгорает"}, "end": 41.2}` in the plan. A word cue is where that word is spoken (`nth`, `offset`, `миллион*` prefix); it needs `captions.words` and follows a new voice by itself. Read it with `useCue('burn')`.

```tsx
import {Camera, Counter, Fade, Glow, Gradient, Grid, Noise, Particles, Pop, SceneTrack, Stage, Text} from '../kit';
import {useStyle} from '../style';

type Look = {bg?: string[]; ink?: string; accent?: string; loss?: string; grid?: boolean; stars?: boolean; glow?: number; font?: 'display' | 'body' | 'mono'};
const col = {position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40} as const;

// One scene, any look: everything below comes from props (plan: {"component": "Budget", "props": {...}}).
export default function Budget({bg, ink, accent, loss = '#FF4D5E', grid = true, stars = true, glow = 0.4, font = 'display'}: Look) {
  const {colors} = useStyle();
  const [fg, hi] = [ink ?? colors.text, accent ?? colors.accent];
  return (
    <SceneTrack scenes={[
      {at: 0, render: () => (
        <Stage>
          <Gradient stops={bg} kind="radial" at={[50, 40]} />
          {grid && <Grid color={hi} opacity={0.3} drift={[0, 30]} />}
          {stars && <Particles kind="stars" count={50} color={fg} />}
          <Glow y={30} color={hi} hz={0.4} opacity={glow} />
          <Camera zoom={0.05}>
            <div style={col}>
              <Fade from={0.2}><Text size={56} color={fg} font={font} caps>Budget</Text></Fade>
              <Counter to={250000} dur={1.4} size={150} color={hi} font={font} />
            </div>
          </Camera>
        </Stage>
      )},
      {at: 'burn', render: () => (
        <Stage>
          <Gradient stops={bg} angle={160} />
          <Noise opacity={0.12} rate={8} />
          <div style={col}>
            <Pop from={0.2}><Counter from={250000} to={-150000} start={0.6} dur={1} size={150} color={loss} font={font} /></Pop>
            <Fade from={1}><Text size={44} color={fg} font={font} caps>after wiring + crew</Text></Fade>
          </div>
        </Stage>
      )},
    ]} />
  );
}
```

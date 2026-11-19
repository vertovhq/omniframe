# Motion kit (`import {...} from '../kit'`)

Mechanics only, no look: colours and fonts come from the plan style or from props. Sizes are design px (1080 short side), so every block works in 9:16 and 16:9. Times are seconds on the scene's clock (0 = scene start; inside a `SceneTrack` scene, that scene's start).

**motion** `clamp(v,lo,hi)` `seg(t,a,b)` progress 0..1 · `lerp(a,b,p)` `remap(v,inA,inB,outA,outB)` · `eOut eIn eInOut eBack eElastic eLinear` · `stagger(i,step,start)` · `pulse(t,hz)` · `formatNumber(n,decimals,sep)`
**timing** `useT()` · `useDuration()` · `useCue(name,fallback?)` · `useCues()` · `useWords()` ({w,s,e}) · `<SceneTrack scenes={[{at: 0 | 'cueName', render: ({t,d,i}) => node}]} fade={0.5}/>` (cross-fade, each scene paints its own `Stage`)
**wrappers** `<Fade from to inDur outDur/>` `<Pop from to dur fromScale/>` `<Slide from to side dist dur/>` (all: `keepSpace`, `style`) · `<Stage bg/>` full-frame layer · `<Camera zoom pan={[x,y]} from to origin/>`
**text** `<Text size color font weight stroke strokeColor shadow glow glowColor caps align spacing maxWidth/>` · `<Label size fill color border rotate caps/>` · `readableOn(bg)`
**effects** (percent of the parent, put in a `Stage`) `<Glow x y size color opacity hz/>` · `<Particles kind='dust'|'stars' count seed color area size speed/>` · `<LightCone x y topWidth width height angle color opacity/>`
**info** `<Counter to from start dur decimals prefix suffix format size color/>` · `<Plate label value color changes={[{at,color?,value?}]} alert={{from,to,color,hz}}/>` · `<Delta value label at hold positive negative/>` · `<PollCard title options={[{label,share,color?}]} at pick/>` · `<Checklist items={[text | {text,at}]} at step/>` · `<ProgressBar value at dur label showValue/>` · `<Bubble tail tailAt size fill color>` · `<Card width padding fill border>`

Cues: put `"cues": {"burn": {"word": "сгорает"}, "end": 41.2}` in the plan. A word cue is where that word is spoken (`nth`, `offset`, `миллион*` prefix); it needs `captions.words` and follows a new voice by itself. Read it with `useCue('burn')`.

```tsx
import {Camera, Counter, Delta, Fade, Glow, Particles, Plate, SceneTrack, Stage, Text} from '../kit';
import {useStyle} from '../style';

export default function Budget() {
  const {colors} = useStyle();
  return (
    <SceneTrack scenes={[
      {at: 0, render: () => (
        <Stage bg={colors.bg}>
          <Camera zoom={0.05}>
            <Glow y={30} color={colors.accent} hz={0.4} />
            <Particles kind="stars" count={50} />
            <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40}}>
              <Fade from={0.2}><Text size={56} color={colors.muted} caps>Budget</Text></Fade>
              <Counter to={250000} dur={1.4} size={150} color={colors.accent} />
            </div>
          </Camera>
        </Stage>
      )},
      {at: 'burn', render: () => (
        <Stage bg={colors.bg}>
          <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 36}}>
            <Plate label="Budget" value="250 000" changes={[{at: 0.6, value: '−400 000', color: '#FF4D5E'}]} alert={{from: 0.6, to: 3, color: '#FF4D5E'}} />
            <Delta value={-400000} label="wiring + crew" at={0.6} />
          </div>
        </Stage>
      )},
    ]} />
  );
}
```

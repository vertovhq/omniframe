# Motion kit (`import {...} from '../kit'`)

Blocks for custom scenes. No look of its own: colours and fonts come from the plan style or props (any CSS colour). Sizes are design px (1080 short side), so blocks work in 9:16 and 16:9. Times are seconds on the scene's clock (0 = scene start); `at` takes seconds, a cue name from `plan.cues`, or a list of both.

Build each scene from three layers: a background, a main element, a detail layer. Open only the groups you need: `studio_guide(kit_group='hud')` returns that group's text and a contact strip with one frame per block (built once; the first call may hand you a job to poll).

**core** timing and cues (`SceneTrack useCue useAt`), wrappers (`Fade Pop Slide Stage`), text (`Text Label`), motion maths
**backgrounds** fills and ambient layers: gradients, mesh, grid, stripes, grain, paper, starfield, bokeh, light leaks, vignette, scanlines, media, glow, particles
**transitions** cuts with motion between `SceneTrack` scenes: fade, whip, zoom, wipe, slice, split, flash, glitch, shake, ramp
**energy** trailer hits and grades on a cue: shake, snap, aberration, flash, film burn, lens flare, freeze stamp, VHS, boil, montage burst
**hud** instrument-panel details: corner brackets, ruler ticks, timecode, scrubber, readouts, ticker, scan line, crosshair, pills, and `HudLayer` that places several
**type** kinetic text: word slam with boxed key words, slant, stretch, letter cascade, typewriter, word swap, text on a path
**bursts** bright accents for a hit: speed lines, shockwave, glow burst, sparks, light sweep
**depth** panel tilt, parallax layers, card stack, phone and laptop frames that hold another scene
**camera** dolly, punch-in, rack focus (shake and snap are in energy)
**info** counters, plates, deltas, polls, checklists, progress bars, bubbles, cards

Cues: `"cues": {"burn": {"word": "сгорает"}, "end": 41.2}`; a word cue is where it is spoken (`nth`, `offset`; needs `captions.words`). Scenes with video (`Media`) render slower.

```tsx
import {Counter, Fade, Gradient, Grid, Pop, SceneTrack, Stage, Text} from '../kit';
import {useStyle} from '../style';

type Look = {bg?: string[]; ink?: string; accent?: string; loss?: string; grid?: boolean; font?: 'display' | 'body' | 'mono'};
const col = {position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40} as const;

// Any look through props: {"component": "Budget", "props": {...}}
export default function Budget({bg, ink, accent, loss = '#FF4D5E', grid = true, font = 'display'}: Look) {
  const {colors} = useStyle();
  const [fg, hi] = [ink ?? colors.text, accent ?? colors.accent];
  return (
    <SceneTrack enter={{kind: 'whip', dir: 'bottom'}} scenes={[
      {at: 0, render: () => (
        <Stage>
          <Gradient stops={bg} kind="radial" at={[50, 40]} />
          {grid && <Grid color={hi} opacity={0.3} drift={[0, 30]} />}
          <div style={col}>
            <Fade from={0.2}><Text size={56} color={fg} font={font} caps>Budget</Text></Fade>
            <Counter to={250000} dur={1.4} size={150} color={hi} font={font} />
          </div>
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

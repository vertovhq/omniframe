# Custom components

A custom component is a React component the model writes when no built-in scene fits.
It lives in the project, not in the engine: `<project>/components/<Name>.tsx`. A plan uses it as

```json
{"kind": "custom", "at": 2.0, "until": 6.0, "component": "<Name>", "props": {"label": "x"}}
```

For each render, `render_video` copies `<project>/components/*.tsx` into `custom/job/`, writes
`custom/registry.ts` (name → default export), typechecks everything and bundles the engine.
When the bundle is built it restores the committed empty `registry.ts` and deletes `custom/job/`.
If the code does not compile, the render does not start and the compiler errors come back as
`components/<Name>.tsx(line,col): error TSxxxx: ...`.

## Contract

- The file name (without `.tsx`) is the component name: letters, digits, `_`, starting with a letter.
- `export default` a function component: `FC<Props>`. `props` of the scene are passed as its props
  (JSON values only), so give every prop a default.
- It may import only:
  - `react`
  - `remotion` (`useCurrentFrame`, `useVideoConfig`, `interpolate`, `spring`, `random`, `Img`, `staticFile`, ...)
  - `../style` (`useStyle`, `useLayout`, `fontFor`, `withAlpha`, `resolveMedia`, ...)
  - other files of `components/`, as `./Other`
- No network: no `fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource`, dynamic `import()` or
  `require()`, and no `http(s)://` URLs. Media comes from the plan's files through `resolveMedia()`.
- Deterministic: frames are rendered in parallel. Use `random('seed')` from `remotion` instead of
  `Math.random()`, and `useCurrentFrame()` instead of `Date.now()`.

## Layout

- The component is drawn inside the style's safe area and centered, like the built-in scenes,
  with the same fade in/out. Its size is the content box: give it a width, or let it wrap content.
- `useLayout()` gives `width`, `height`, `short`, `u(n)` (geometry) and `fs(n)` (text, times
  `text_scale`), where `n` is in design pixels for a 1080 short side. Never hardcode the frame size.
- `useStyle()` gives the plan's tokens: `colors.text`, `colors.accent`, `colors.muted`, ...
  Use `fontFor(style, 'display')` for the font.
- `useCurrentFrame()` counts from the start of the scene, not of the video.

## Example

```tsx
import {interpolate, useCurrentFrame} from 'remotion';
import {fontFor, useLayout, useStyle} from '../style';

export default function ScoreBoard({label = 'SCORE', value = 0}: {label?: string; value?: number}) {
  const frame = useCurrentFrame();
  const style = useStyle();
  const {fs, u} = useLayout();
  const shown = Math.round(interpolate(frame, [0, 30], [0, value], {extrapolateRight: 'clamp'}));
  return (
    <div style={{textAlign: 'center', color: style.colors.text, fontFamily: fontFor(style, 'display').css}}>
      <div style={{fontSize: fs(48), color: style.colors.muted}}>{label}</div>
      <div style={{fontSize: fs(220), fontWeight: 900, color: style.colors.accent, marginTop: u(12)}}>{shown}</div>
    </div>
  );
}
```

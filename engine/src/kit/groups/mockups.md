# mockups

Ready-made pictures of software and devices, and a counter pinned to a corner. Import from `'../kit'`.
Colours and fonts come from the style or from props; sizes are design px.

- `AppWindow({title, prompt, typeFrom, cps, width, height, fill, ink}, children)`: a window with a title
  bar. `prompt` is typed into its last line from `typeFrom` seconds at `cps` characters a second, with a
  cursor. Children go above the prompt.
- `ToolCallStack({calls, at, step, width, rowHeight, fill, ink, marker})`: `calls` is a list of
  `{name, args, done}`. Call `i` slides in at `at + i * step`; a done call has a solid marker.
- `ScreenFrame({kind: 'laptop' | 'monitor', width, bezel}, children)`: the frame holds a scene, an image or
  a video (`OffthreadVideo`) that fills the screen. Use `width` 900 to 1100 for a laptop.
- `CounterOverlay({to, from, start, dur, decimals, label, corner, color, size})`: a number that counts
  up inside the safe area. `corner`: `upper-left`, `upper-right`, `lower-left` or `lower-right`.

Example: a prompt typed in an app window, then the tool calls it makes.

```tsx
<AppWindow title="Assistant" prompt="Ship the budget report" typeFrom={0.5} cps={22} width={880} height={460} />
<ToolCallStack at={2.5} step={0.4} calls={[{name: 'read_file', args: 'budget.csv', done: true}, {name: 'run_script', args: 'totals'}]} />
```

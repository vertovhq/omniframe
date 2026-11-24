---
inclusion: fileMatch
fileMatchPattern: 'engine/**'
---

# Engine steering (Remotion)

- Never hardcode the frame size. Use `useVideoConfig().width/height` and the style
  tokens from `useStyle()` (sizes are relative to the short side of the frame).
- Rendering must be deterministic: no `Math.random()` or `Date.now()`; use Remotion's
  `random(seed)`.
- Media and fonts resolve through `resolveMedia()`; the public dir is created per render job.
- `src/types.ts` mirrors the pydantic plan model in `src/omniframe/plan.py`. Change both together.
- No automatic sound effects. The engine plays only the SFX events listed in the plan.
- Layer order: background → clips → full scenes → overlay scenes / HUD → captions → grain.
- Custom components come from `src/custom/registry.ts`, generated per render. The
  committed version exports an empty map and must stay that way.
- Typecheck must pass: `node node_modules/typescript/bin/tsc --noEmit -p .` (cwd `engine`).

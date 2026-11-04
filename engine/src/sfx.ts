import type {Scene, SfxEvent} from './types';

// Default synthesized sound set (created by the Python caller into public/sfx/).
// Users can drop premium sounds into ARGUS_SFX_DIR to override these names.
export const DEFAULT_SFX = {
  whoosh: 'sfx/whoosh.mp3',
  pop: 'sfx/pop.mp3',
  hit: 'sfx/hit.wav',
} as const;

/**
 * Auto sound design: a whoosh on every cut, a pop when something pops in
 * (card/counter/chip), a hit on impact scenes (big/act), a longer whoosh into
 * the CTA. Custom sfx_list events are appended on top.
 */
export function buildSfxTimeline(
  scenes: Scene[],
  opts: {sfx?: boolean; sfx_list?: SfxEvent[]}
): SfxEvent[] {
  const events: SfxEvent[] = [];
  if (opts.sfx !== false) {
    scenes.forEach((scene, i) => {
      if (i > 0) {
        events.push({at: Math.max(0, scene.at - 0.12), src: DEFAULT_SFX.whoosh, volume: 0.55});
      }
      if (scene.kind === 'card' || scene.kind === 'counter' || scene.kind === 'chip') {
        events.push({at: scene.at + 0.05, src: DEFAULT_SFX.pop, volume: 0.85});
      }
      if (scene.kind === 'big' || scene.kind === 'act') {
        events.push({at: scene.at + 0.02, src: DEFAULT_SFX.hit, volume: 0.95});
      }
      if (scene.kind === 'cta') {
        events.push({at: scene.at, src: DEFAULT_SFX.whoosh, volume: 0.8});
      }
    });
  }
  for (const e of opts.sfx_list ?? []) {
    events.push({at: e.at, src: e.src, volume: e.volume ?? 1});
  }
  return events.sort((a, b) => a.at - b.at);
}

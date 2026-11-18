import type {SfxEvent} from './types';

/**
 * Sound effects come only from the plan (`audio.sfx`, and the v1 `sfx_list` that
 * no tool sends any more). The engine adds none of its own: no whoosh on cuts,
 * no pop or hit on scenes. The model decides where a sound goes and which file it is.
 *
 * Merges the given lists, drops events without a usable time or source, fills in the
 * default volume and sorts by time.
 */
export function collectSfx(...lists: Array<readonly SfxEvent[] | undefined>): SfxEvent[] {
  const events: SfxEvent[] = [];
  for (const list of lists) {
    for (const e of list ?? []) {
      if (!e || typeof e.src !== 'string' || e.src === '' || !Number.isFinite(e.at)) {
        continue;
      }
      const volume = typeof e.volume === 'number' && Number.isFinite(e.volume) && e.volume >= 0 ? e.volume : 1;
      events.push({at: Math.max(0, e.at), src: e.src, volume});
    }
  }
  return events.sort((a, b) => a.at - b.at);
}

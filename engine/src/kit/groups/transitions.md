# transitions

`enter` of a `SceneTrack` scene (or of the track): a kind, or `{kind, dur, strength, dir, color, count, shape, soft, seed}`. Pick one per cut by the story's energy; a cross-fade everywhere reads flat.

`fade` soft dissolve · `whip` whip pan with motion blur (`dir`) · `zoom` zoom through the old scene into the new · `wipe` mask reveal (`dir`, `shape`, `soft`) · `slice` the picture cuts into `count` strips that slide · `split` the old scene opens like doors over the new one · `flash` a flash frame (`color`) · `glitch` RGB split with jitter · `shake` a hit that shakes the cut · `ramp` speed-ramp feel: zoom and motion blur build up into the cut and release after it (the picture itself is not time-remapped)

`<Transition spec role='in'|'out' t/>` the machinery, `transitionDur(spec)` seconds a spec lasts. Pair a hard transition with a sound (`audio.sfx`) and, for a strong moment, a burst (`bursts` group).

# camera: moves over the picture

Wrap the whole picture of a scene, background included. Ease names: `inOut` `out` `in` `linear`.

`<Camera zoom pan from to origin/>` slow push · `<Dolly from to pan panTo at dur ease origin/>` zoom and pan between two states with an ease (default `inOut`; `out` for a push that settles) · `<PunchIn at zoom hold release origin/>` jumps in on each hit, holds, eases back · `<RackFocus from to at dur ease breathe/>` pulls focus: blur px from → to (0 = sharp)
Shake and snap (a shake on a cue, a punch with smear) are in `energy`: `<Shake at dur kind/>` `<Snap at dir/>`.

Moves are most useful when they have a reason: push in on the key word, pull focus to the new subject, punch in on a hit.

# bursts: bright accents for a hit

Drawn above the picture. `at` takes seconds, a cue name, or a list of both, and each block shows for `dur` seconds from every hit; `x`, `y` are percent of the parent; `strength` 1 is normal. Colours are any CSS colour.

`<SpeedLines at dur x y color count inner thickness fps strength seed/>` radiating action lines, re-drawn `fps` times a second (no `at` = always on) · `<Shockwave at dur x y color size rings thickness/>` expanding rings · `<GlowBurst at dur x y color size/>` bloom of light (screen blend) · `<Sparks at dur x y colors count speed gravity angle spread/>` · `<LightSweep at dur color angle width/>` a band of light crossing the frame

Combine two or three on the strongest hits (a glow burst with speed lines and a `Shake`), not on every cut. Put a sound on each hit (`audio.sfx`).

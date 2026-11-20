# energy: trailer-style hits and grades

`at` takes seconds, a cue name from `plan.cues`, or a list of both (`at={['hit', 3.2]}`); an unknown name stops the render and lists the defined cues. `strength` 1 = a normal hit, `dur` = how long it rings out, colours are any CSS colour. Keep these for strong moments.

Wrap the picture (children): `<Shake at dur kind='impact'|'camera' every strength zoom/>` · `<Stepped fps/>` on twos · `<Boil strength fps frames scale/>` hand-drawn wobble · `<Snap at dir dist zoom appear/>` punch with motion-blur smear · `<Aberration at dur angle strength/>` RGB split · `<Vhs strength roll/>` · `<FreezeStamp at until label color rotate size/>` freeze frame with a stamp (`at` is one time or cue)
Overlays: `<Flash at hold color invert strength/>` · `<FilmBurn at colors side dur/>` · `<LensFlare x y to at color size ghosts/>` · `<Burst items at dur rate loop/>` montage of rapid frames
Parts: `<MotionBlur x y/>` · `<RgbSplit amount angle/>` · `shakeOffset(frame,seed,amp)`

For the bright accents of a hit (speed lines, shockwave, sparks) see `bursts`; for punch-ins and dollies see `camera`.

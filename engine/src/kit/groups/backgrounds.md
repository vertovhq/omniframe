# backgrounds and ambient light

Fill the parent; put them first in a `Stage`, stack several (a gradient, a grid, grain, a vignette) for depth. All take `opacity`; colours are any CSS colour; none has a look of its own.

`<Solid color/>` · `<Gradient stops angle kind='linear'|'radial' at spin/>` · `<AnimatedGradient stops angle speed period/>` flowing colours · `<Mesh colors base count size speed seed/>` drifting blobs
`<Grid kind='lines'|'dots' color step line drift/>` · `<Stripes color angle width gap drift/>` · `<Noise opacity size rate seed blend/>` grain · `<Paper color grain shade ruling='none'|'lines'|'squares'/>`
`<Starfield count speed streak centre seed/>` stars fly out of a point (travel); `<Particles kind='dust'|'stars' count seed color area/>` stars twinkle in place, dust rises
`<Bokeh colors count size speed seed/>` · `<LightLeaks colors intensity speed seed/>` · `<LightCone x y width height angle color/>` · `<Glow x y size color opacity hz/>` (percent of the parent)
`<Vignette color strength size/>` · `<Scanlines color gap thickness roll/>` · `<Media src fit dim dimColor blur start rate/>` image or video behind the scene (renders slower with video)

Detail layers (HUD, bursts) go on top of these: see the `hud` and `bursts` groups.

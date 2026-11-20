# depth: panels, layers, cards, devices

`<Tilt x y z from at dur sway perspective lift>panel</Tilt>` leans a panel in perspective (centres its child; give the child a size) · `<Parallax layers=[{depth 0..1, node}] drift zoom at dur/>` layers slide at different speeds, near ones move more · `<CardStack items kind='stack'|'fan'|'cascade' at step width height fill radius spread peek/>` cards arrive and pile up · `<Device kind='phone'|'laptop' width color bezel fit at>scene</Device>` puts another scene on a screen (it keeps its own clock; `fit` 'cover' or 'contain')

A `Device` inside a `Tilt` inside a `Dolly` is a typical product shot.

# hud: instrument-panel detail layer

Small details at the edges that keep a scene busy while the main element holds the middle. Text blocks flow like normal elements (stack them in a flex column or row); `x`/`y` (percent of the parent) and `anchor` ('tl' 'tr' 'bl' 'br' 'c') pin one instead. `color` is any CSS colour (default: the style's text colour), `at` the second a block draws in, `size` design px, `font` a style font role.

Fill the parent: `<CornerBrackets color size thickness inset at breathe/>` · `<FrameTicks color edges step length drift/>` ruler ticks · `<ScanLine color period thickness glow vertical/>` · `<Crosshair x y to at dur size spin/>` locks on, can glide to `to`
Text: `<Timecode from label rec recColor/>` mm:ss:ff clock, `rec` adds a blinking REC · `<Scrubber from to marks ticks left right width/>` mini timeline with playhead · `<Readout rows=[{label,value}] hot title step width/>` data rows that type in · `<Ticker items fill speed separator width/>` scrolling strip · `<StatusPill dot solid blink>LIVE</StatusPill>`
One call: `<HudLayer color accent size brackets ticks timecode rec pills readout ticker scrubber scan crosshair at/>` places brackets, ticks, timecode and pills (top), readout, ticker and scrubber (bottom stack), scan line and reticle inside the safe area. A prop left out draws nothing. Put it above the scene's main element; for another arrangement use the blocks.

Match the amount to the story: an explainer or tech promo can carry a full layer, a quiet story a corner or two.

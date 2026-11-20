# type: kinetic text

Text that arrives with a move. Style fonts and colours unless a prop says otherwise. Look props on every block: `size color font weight caps align stroke shadow spacing lineHeight maxWidth` (design px). In `WordSlam` and `LetterCascade` text, `*word*` marks a key word.

`<WordSlam text at step from='scale'|'top'|'bottom'|'left'|'right' mark='box'|'highlight'|'underline'|'none' markColor markTextColor accent skew rotate gap/>` words slam in one by one; key words (starred or listed in `accent`) get the mark
`<Boxed mode at dur color textColor pad rotate>word</Boxed>` marks any inline text · `<Skew x y fromX at dur>` slant · `<Stretch axis kind='scale'|'track' from at dur>` stretches into place · `<LetterCascade text at step from='top'|'bottom'|'scale'|'spin' keyColor/>`
`<Typewriter text at cps cursor cursorColor blink/>` · `<WordSwap words at every kind='slide'|'pop'|'flip' colors loop/>` one word replaced by the next in place · `<PathText text path='arc'|'wave'|'circle'|svgPath width height at dur spin/>` text on a curve

Blocks sit in the normal flow (top of a `Stage`): put them in a full-frame flex `div` to centre them, and keep them clear of `HudLayer` corners.
For spoken words as captions, use `captions.mode: "headline"` in the plan (big kinetic words in the middle, key words boxed in the accent colour; `accent_words` picks them).

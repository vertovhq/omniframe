// Headline caption motion: pure maths, so it can be checked without a browser.

import {eBack} from './kit/motion';

/**
 * How a headline word looks `p` (0 to 1) through its slam, where `p` is the time since the word was
 * spoken divided by the slam length. The word drops into its own slot from above with a small
 * overshoot and a tilt, and it never grows. The earlier version started at 1.9x, which covered the
 * neighbouring words and pushed the first word of a row past the left edge of the safe area.
 */
export function headlineMotion(p: number): {opacity: number; translateEm: number; rotateDeg: number} {
  const q = Math.min(1, Math.max(0, p));
  const land = eBack(q);
  return {
    opacity: Math.min(1, q * 5),
    translateEm: -0.5 * (1 - land),
    rotateDeg: -5 * (1 - land),
  };
}

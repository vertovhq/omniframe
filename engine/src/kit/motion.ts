// Motion kit: pure timing maths. All times are seconds; progress values run 0..1.

/** Limits `v` to `lo..hi` (default 0..1). */
export const clamp = (v: number, lo = 0, hi = 1): number => Math.min(hi, Math.max(lo, v));

/** Progress 0..1 of `t` inside `[a, b]`. Before `a` it is 0, after `b` it is 1. */
export const seg = (t: number, a: number, b: number): number => (b === a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));

/** `a` at `p = 0`, `b` at `p = 1`. */
export const lerp = (a: number, b: number, p: number): number => a + (b - a) * p;

/** Maps `v` from `[inA, inB]` to `[outA, outB]`, clamped. */
export const remap = (v: number, inA: number, inB: number, outA: number, outB: number): number =>
  lerp(outA, outB, seg(v, inA, inB));

// Easings take progress 0..1 and return progress 0..1 (`eBack` and `eElastic` overshoot 1).
export const eLinear = (p: number): number => p;
export const eOut = (p: number): number => 1 - Math.pow(1 - p, 3);
export const eIn = (p: number): number => p * p * p;
export const eInOut = (p: number): number => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
/** Overshoots, then settles: good for pop-ins. */
export const eBack = (p: number): number => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2);
};
/** Springy settle around 1. */
export const eElastic = (p: number): number => {
  if (p <= 0) {
    return 0;
  }
  if (p >= 1) {
    return 1;
  }
  const c4 = (2 * Math.PI) / 3;
  return Math.pow(2, -10 * p) * Math.sin((p * 10 - 0.75) * c4) + 1;
};

/** Start time of item `i` when items follow each other `step` seconds apart, from `start`. */
export const stagger = (i: number, step: number, start = 0): number => start + i * step;

/** 0..1..0 pulse with `hz` beats per second; `phase` is in seconds. Handy for blinking and flashes. */
export const pulse = (t: number, hz = 2, phase = 0): number => 0.5 + 0.5 * Math.sin((t - phase) * hz * Math.PI * 2);

/** 15000000 -> "15 000 000" (no-break spaces by default), rounded to `decimals` places. */
export const formatNumber = (n: number, decimals = 0, sep = '\u00A0'): string => {
  const fixed = Math.abs(n).toFixed(decimals);
  const [whole, frac] = fixed.split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
  const sign = n < 0 && Number(fixed) !== 0 ? '-' : '';
  return `${sign}${grouped}${frac ? `.${frac}` : ''}`;
};

import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill} from 'remotion';
import {useLayout} from '../style';
import {eBack, eInOut, eIn, eOut, lerp, seg} from './motion';
import {useDuration, useT} from './timing';

// Wrappers that show their children inside a time window. `from` and `to` are seconds on the
// clock of the scene (see timing.tsx). Without `to` the children stay. By default a wrapper
// draws nothing while hidden; `keepSpace` keeps its box in the layout so siblings do not jump.

type Window = {
  /** Seconds when the children start to appear. Default 0. */
  from?: number;
  /** Seconds when they start to disappear. Default: never. */
  to?: number;
  /** Keep the box in the layout while hidden. */
  keepSpace?: boolean;
  style?: CSSProperties;
  children?: ReactNode;
};

const hiddenStyle: CSSProperties = {visibility: 'hidden'};

/** Opacity 0..1 for an in-and-out window. */
const windowAlpha = (t: number, from: number, to: number | undefined, inDur: number, outDur: number): number =>
  seg(t, from, from + inDur) * (to === undefined ? 1 : 1 - seg(t, to, to + outDur));

/** Fades the children in at `from` and out at `to`. */
export const Fade = ({from = 0, to, inDur = 0.4, outDur = 0.4, keepSpace, style, children}: Window & {inDur?: number; outDur?: number}) => {
  const t = useT();
  const a = windowAlpha(t, from, to, inDur, outDur);
  if (a <= 0.001) {
    return keepSpace ? <div style={{...style, ...hiddenStyle}}>{children}</div> : null;
  }
  return <div style={{...style, opacity: a}}>{children}</div>;
};

/** Pops the children in with an overshoot (scale from `fromScale` to 1) and fades them out at `to`. */
export const Pop = ({
  from = 0,
  to,
  dur = 0.45,
  outDur = 0.25,
  fromScale = 0.5,
  keepSpace,
  style,
  children,
}: Window & {dur?: number; outDur?: number; fromScale?: number}) => {
  const t = useT();
  const a = windowAlpha(t, from, to, dur * 0.5, outDur);
  if (a <= 0.001) {
    return keepSpace ? <div style={{...style, ...hiddenStyle}}>{children}</div> : null;
  }
  const grow = lerp(fromScale, 1, eBack(seg(t, from, from + dur)));
  const shrink = to === undefined ? 1 : lerp(1, fromScale + (1 - fromScale) * 0.5, eIn(seg(t, to, to + outDur)));
  return <div style={{...style, opacity: a, transform: `scale(${(grow * shrink).toFixed(4)})`}}>{children}</div>;
};

/** The side the children come in from. */
export type Side = 'bottom' | 'top' | 'left' | 'right';

const SIDE_VECTOR: Record<Side, [number, number]> = {bottom: [0, 1], top: [0, -1], left: [-1, 0], right: [1, 0]};

/** Slides the children in from `side` by `dist` design px while fading, and back out at `to`. */
export const Slide = ({
  from = 0,
  to,
  dur = 0.5,
  outDur = 0.35,
  side = 'bottom',
  dist = 120,
  keepSpace,
  style,
  children,
}: Window & {dur?: number; outDur?: number; side?: Side; dist?: number}) => {
  const t = useT();
  const {u} = useLayout();
  const a = windowAlpha(t, from, to, dur * 0.6, outDur);
  if (a <= 0.001) {
    return keepSpace ? <div style={{...style, ...hiddenStyle}}>{children}</div> : null;
  }
  const away = (1 - eOut(seg(t, from, from + dur))) + (to === undefined ? 0 : eIn(seg(t, to, to + outDur)));
  const [vx, vy] = SIDE_VECTOR[side];
  const shift = away * u(dist);
  return (
    <div style={{...style, opacity: a, transform: `translate(${(vx * shift).toFixed(2)}px, ${(vy * shift).toFixed(2)}px)`}}>
      {children}
    </div>
  );
};

/**
 * A full-frame layer for a scene: `bg` is any CSS background (colour or gradient), the children
 * are positioned against the whole frame. Use it as the first thing a scene draws, and inside
 * every `SceneTrack` scene.
 */
export const Stage = ({bg, style, children}: {bg?: string; style?: CSSProperties; children?: ReactNode}) => (
  <AbsoluteFill style={{background: bg, overflow: 'hidden', ...style}}>{children}</AbsoluteFill>
);

/**
 * Slow camera move over its children: zoom in by `zoom` (0.06 = 6 %) and shift by `pan` design
 * px, between `from` and `to` (default: the whole scene). `origin` is the zoom centre.
 */
export const Camera = ({
  zoom = 0.06,
  pan = [0, 0],
  from = 0,
  to,
  origin = '50% 50%',
  children,
}: {
  zoom?: number;
  pan?: [number, number];
  from?: number;
  to?: number;
  origin?: string;
  children?: ReactNode;
}) => {
  const t = useT();
  const d = useDuration();
  const {u} = useLayout();
  const p = eInOut(seg(t, from, to ?? Math.max(from + 0.1, d)));
  const scale = 1 + zoom * p;
  return (
    <AbsoluteFill
      style={{
        transformOrigin: origin,
        transform: `translate(${(pan[0] * p * u(1)).toFixed(2)}px, ${(pan[1] * p * u(1)).toFixed(2)}px) scale(${scale.toFixed(4)})`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

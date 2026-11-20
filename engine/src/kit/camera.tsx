import type {ReactNode} from 'react';
import {AbsoluteFill} from 'remotion';
import {useLayout} from '../style';
import {ageOf, useAt} from './at';
import type {At} from './at';
import {clamp, eIn, eInOut, eLinear, eOut, lerp, seg} from './motion';
import {useDuration, useT} from './timing';

// The camera group: moves of the virtual camera over its children. (`Camera` in wrappers is a slow
// push; `Shake` and `Snap` in the energy group shake and punch.) Each fills its parent and moves
// everything inside it, so wrap the whole picture of a scene, background included.

const EASES = {inOut: eInOut, out: eOut, in: eIn, linear: eLinear} as const;
export type Ease = keyof typeof EASES;

/**
 * A punch-in on each hit: the picture jumps to `1 + zoom` in a few frames, holds `hold` seconds
 * and eases back over `release`. `origin` is the zoom centre.
 */
export const PunchIn = ({
  at,
  zoom = 0.18,
  hold = 0.25,
  release = 0.6,
  origin = '50% 50%',
  children,
}: {
  at: At;
  zoom?: number;
  hold?: number;
  release?: number;
  origin?: string;
  children?: ReactNode;
}) => {
  const age = ageOf(useT(), useAt(at));
  let k = 0;
  if (age !== null) {
    k = age < 0.08 ? eOut(age / 0.08) : age < 0.08 + hold ? 1 : 1 - eInOut(seg(age, 0.08 + hold, 0.08 + hold + Math.max(0.01, release)));
  }
  return <AbsoluteFill style={{transformOrigin: origin, transform: `scale(${1 + zoom * k})`}}>{children}</AbsoluteFill>;
};

/**
 * A move of the camera from `from` zoom to `to` zoom (1 = as drawn) and from `pan` offset to `to_pan`
 * (design px), between `at` and `at + dur` (default: to the end of the scene), with the chosen ease:
 * `inOut` for a gentle move, `out` for a push that settles, `in` for one that gathers speed.
 */
export const Dolly = ({
  from = 1,
  to = 1.18,
  pan = [0, 0],
  panTo = [0, 0],
  at = 0,
  dur,
  ease = 'inOut',
  origin = '50% 50%',
  children,
}: {
  from?: number;
  to?: number;
  pan?: [number, number];
  panTo?: [number, number];
  at?: number;
  dur?: number;
  ease?: Ease;
  origin?: string;
  children?: ReactNode;
}) => {
  const t = useT();
  const d = useDuration();
  const {u} = useLayout();
  const p = EASES[ease](seg(t, at, at + (dur ?? Math.max(0.1, d - at))));
  return (
    <AbsoluteFill style={{transformOrigin: origin, transform: `translate(${lerp(pan[0], panTo[0], p) * u(1)}px, ${lerp(pan[1], panTo[1], p) * u(1)}px) scale(${lerp(from, to, p)})`}}>
      {children}
    </AbsoluteFill>
  );
};

/**
 * Pulls focus: the children go from `from` px of blur to `to` px (design px) between `at` and
 * `at + dur`. `0` is sharp. A hint of zoom (`breathe`) goes with it, as a lens does when it refocuses.
 */
export const RackFocus = ({
  from = 26,
  to = 0,
  at = 0,
  dur = 0.9,
  ease = 'inOut',
  breathe = 0.02,
  children,
}: {
  from?: number;
  to?: number;
  at?: number;
  dur?: number;
  ease?: Ease;
  breathe?: number;
  children?: ReactNode;
}) => {
  const t = useT();
  const {u} = useLayout();
  const p = EASES[ease](seg(t, at, at + Math.max(0.05, dur)));
  const blur = Math.max(0, lerp(from, to, p));
  const widest = Math.max(from, to);
  // the blur fades the edges of the layer, so the layer is a little larger than the frame while it is soft
  const grow = 1 + clamp(blur / Math.max(1, widest)) * breathe + blur * 0.0016;
  return (
    <AbsoluteFill style={{filter: blur > 0.2 ? `blur(${u(blur).toFixed(2)}px)` : undefined, transform: `scale(${grow.toFixed(4)})`}}>
      {children}
    </AbsoluteFill>
  );
};

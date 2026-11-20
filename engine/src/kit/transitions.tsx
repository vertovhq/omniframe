import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {useLayout} from '../style';
import {MotionBlur, RgbSplit, shakeOffset} from './fx';
import {clamp, eIn, eInOut, eOut, lerp, seg} from './motion';
import type {Side} from './wrappers';

// Cuts with motion. `SceneTrack` plays them between its scenes (`enter` on a scene or on the
// track); `<Transition>` is the same thing for any two pieces you place yourself. A transition
// has two halves: the scene that leaves (`role="out"`) and the one that arrives (`role="in"`),
// each told how many seconds `t` have passed since the transition began.

export type TransitionKind = 'fade' | 'whip' | 'zoom' | 'wipe' | 'slice' | 'split' | 'flash' | 'glitch' | 'shake' | 'ramp';

export type TransitionSpec = {
  kind: TransitionKind;
  /** Seconds the transition lasts. Default depends on the kind (0.35 to 0.6). */
  dur?: number;
  /** How hard it hits, 1 = normal. Scales blur, travel, shake and glitch size. */
  strength?: number;
  /** The side the new scene comes from (whip, wipe, slice) or the axis it splits along (split). Default 'right'. */
  dir?: Side;
  /** Flash colour (flash, shake). Default white. */
  color?: string;
  /** Number of strips (slice). Default 5. */
  count?: number;
  /** Wipe shape. Default 'line'. */
  shape?: 'line' | 'circle';
  /** Wipe edge softness 0..1 of the frame. Default 0 (hard edge). */
  soft?: number;
  /** Changes the random pattern of glitch and shake. */
  seed?: string;
};

const DEFAULT_DUR: Record<TransitionKind, number> = {
  fade: 0.5,
  whip: 0.45,
  zoom: 0.6,
  wipe: 0.5,
  slice: 0.6,
  split: 0.6,
  flash: 0.35,
  glitch: 0.45,
  shake: 0.5,
  ramp: 0.6,
};

/** Seconds a transition lasts (`spec.dur`, else the kind's default; `fade` is the fallback for a plain 'fade'). */
export const transitionDur = (spec: TransitionKind | TransitionSpec, fade = 0.5): number => {
  const s = typeof spec === 'string' ? {kind: spec} : spec;
  return Math.max(0, s.dur ?? (s.kind === 'fade' ? fade : DEFAULT_DUR[s.kind]));
};

const ENTRY: Record<Side, [number, number]> = {bottom: [0, 1], top: [0, -1], left: [-1, 0], right: [1, 0]};
const AWAY_CSS: Record<Side, string> = {right: 'to left', left: 'to right', top: 'to bottom', bottom: 'to top'};

const eQuart = (p: number): number => (p < 0.5 ? 8 * p ** 4 : 1 - (-2 * p + 2) ** 4 / 2);

const frame = (style: CSSProperties | undefined, children: ReactNode) => <AbsoluteFill style={style}>{children}</AbsoluteFill>;
const hidden: CSSProperties = {visibility: 'hidden'};

/** Wipes, slices and splits cut the picture with these. */
const strip = (axis: 'rows' | 'cols', i: number, n: number): string => {
  const a = (i / n) * 100;
  const b = 100 - ((i + 1) / n) * 100;
  const [lo, hi] = [Math.max(0, a - 0.06), Math.max(0, b - 0.06)];
  return axis === 'rows' ? `inset(${lo}% 0 ${hi}% 0)` : `inset(0 ${hi}% 0 ${lo}%)`;
};

export const Transition = ({
  spec: given,
  role,
  t,
  fade = 0.5,
  children,
}: {
  spec: TransitionKind | TransitionSpec;
  role: 'in' | 'out';
  /** Seconds since this transition began (before it: negative). */
  t: number;
  /** Duration of a plain 'fade'. */
  fade?: number;
  children?: ReactNode;
}) => {
  const spec: TransitionSpec = typeof given === 'string' ? {kind: given} : given;
  const {width: W, height: H, fps} = useVideoConfig();
  const {u} = useLayout();
  const dur = transitionDur(spec, fade);
  const s = spec.strength ?? 1;
  const dir = spec.dir ?? 'right';
  const [vx, vy] = ENTRY[dir];
  const horizontal = vx !== 0;
  const p = clamp(dur > 0 ? t / dur : t >= 0 ? 1 : 0);
  const f = Math.max(0, Math.round(t * fps));
  const seed = spec.seed ?? 'transition';
  const idle = (role === 'in' && p >= 1) || (role === 'out' && p <= 0);

  // 'flash' keeps its overlay; a shake cuts hard, so the old scene is gone from t = 0.
  const cutsAtOnce = spec.kind === 'shake' && role === 'out' && t >= 0;
  if (idle && spec.kind !== 'flash' && !cutsAtOnce) {
    return frame(undefined, children);
  }

  switch (spec.kind) {
    case 'fade':
      return frame(role === 'in' ? {opacity: eInOut(p)} : undefined, children);

    case 'whip': {
      const e = eQuart(p);
      const k = role === 'in' ? 1 - e : -e;
      const blur = u(90) * s * Math.sin(Math.PI * p);
      return (
        <MotionBlur x={horizontal ? blur : 0} y={horizontal ? 0 : blur} style={{transform: `translate(${vx * W * k}px, ${vy * H * k}px)`}}>
          {children}
        </MotionBlur>
      );
    }

    case 'zoom': {
      const reach = 1.2 * s;
      if (role === 'out') {
        const style: CSSProperties = {
          transform: `scale(${1 + reach * eIn(p)})`,
          opacity: 1 - seg(p, 0.45, 0.85),
          filter: `blur(${u(60) * s * eIn(p)}px)`,
        };
        return frame(style, children);
      }
      const style: CSSProperties = {
        transform: `scale(${lerp(1 - 0.4 * Math.min(1, s), 1, eOut(p))})`,
        opacity: seg(p, 0.3, 0.7),
        filter: `blur(${u(50) * s * (1 - eOut(p))}px)`,
      };
      return frame(style, children);
    }

    case 'wipe': {
      if (role === 'out') {
        return frame(undefined, children);
      }
      const c = eInOut(p);
      if ((spec.shape ?? 'line') === 'circle') {
        const r = c * (Math.hypot(W, H) / 2) * 1.02;
        return frame({clipPath: `circle(${r}px at 50% 50%)`}, children);
      }
      const sp = clamp(spec.soft ?? 0) * 100;
      const mask = `linear-gradient(${AWAY_CSS[dir]}, #000 ${(c * (100 + sp) - sp).toFixed(2)}%, transparent ${(c * (100 + sp)).toFixed(2)}%)`;
      return frame({maskImage: mask, WebkitMaskImage: mask}, children);
    }

    case 'slice': {
      if (role === 'out') {
        return frame(undefined, children);
      }
      const n = Math.max(2, Math.min(8, Math.round(spec.count ?? 5)));
      const axis = horizontal ? 'rows' : 'cols';
      const travel = horizontal ? W : H;
      return (
        <>
          {Array.from({length: n}, (_, i) => {
            const lag = (0.35 * i) / (n - 1);
            const k = 1 - eOut(seg(p, lag, lag + 0.65));
            const sign = i % 2 === 0 ? 1 : -1;
            const shift = sign * (horizontal ? vx : vy) * travel * k;
            const move = horizontal ? `translateX(${shift}px)` : `translateY(${shift}px)`;
            return (
              <AbsoluteFill key={i} style={{clipPath: strip(axis, i, n)}}>
                <AbsoluteFill style={{transform: move}}>{children}</AbsoluteFill>
              </AbsoluteFill>
            );
          })}
        </>
      );
    }

    case 'split': {
      if (role === 'in') {
        return frame(undefined, children);
      }
      const e = eInOut(p);
      // 'left'/'right': two halves slide apart sideways; 'top'/'bottom': up and down.
      const axis = horizontal ? 'cols' : 'rows';
      const travel = (horizontal ? W : H) / 2 * e;
      const half = (i: 0 | 1) => {
        const away = i === 0 ? -travel : travel;
        const move = horizontal ? `translateX(${away}px)` : `translateY(${away}px)`;
        return (
          <AbsoluteFill key={i} style={{clipPath: strip(axis, i, 2)}}>
            <AbsoluteFill style={{transform: move}}>{children}</AbsoluteFill>
          </AbsoluteFill>
        );
      };
      return (
        <>
          {half(0)}
          {half(1)}
        </>
      );
    }

    case 'flash': {
      const cut = 0.3;
      const alpha = Math.min(1, s) * (p < cut ? (p / cut) ** 1.5 : 1 - eOut(seg(p, cut, 1)));
      const show = role === 'in' ? p >= cut : p < cut;
      const body = frame(show ? undefined : hidden, children);
      if (role === 'out') {
        return body;
      }
      return (
        <>
          {body}
          {p < 1 && p > 0 ? <AbsoluteFill style={{background: spec.color ?? '#FFFFFF', opacity: alpha}} /> : null}
        </>
      );
    }

    case 'glitch': {
      const show = role === 'in' ? p >= 0.5 : p < 0.5;
      if (!show) {
        return frame(hidden, children);
      }
      const env = clamp(1.6 * (1 - Math.abs(2 * p - 1)));
      const step = Math.floor(f / 2);
      const bands = 5;
      return (
        <RgbSplit amount={u(28) * s * env} angle={0}>
          {Array.from({length: bands}, (_, i) => {
            const r = (k: string) => shakeOffset(step * 7 + i, `${seed}-${k}`, 1);
            const live = Math.abs(r('on').x) > 0.35;
            const dx = live ? r('dx').x * u(110) * s * env : 0;
            return (
              <AbsoluteFill key={i} style={{clipPath: strip('rows', i, bands)}}>
                <AbsoluteFill style={{transform: `translateX(${dx}px)`}}>{children}</AbsoluteFill>
              </AbsoluteFill>
            );
          })}
        </RgbSplit>
      );
    }

    case 'shake': {
      if (role === 'out') {
        return frame(hidden, children);
      }
      const k = (1 - p) ** 2;
      const o = shakeOffset(f, seed, u(60) * s * k);
      const punch = 1 + 0.05 * s * (1 - p) ** 3;
      const body = frame({transform: `translate(${o.x}px, ${o.y}px) rotate(${o.rot}deg) scale(${punch})`}, children);
      const flash = spec.color && p < 0.25 ? <AbsoluteFill style={{background: spec.color, opacity: (1 - p / 0.25) * Math.min(1, s)}} /> : null;
      return (
        <>
          {body}
          {flash}
        </>
      );
    }

    case 'ramp': {
      const q = role === 'out' ? eIn(seg(p, 0, 0.5)) : 1 - eOut(seg(p, 0.5, 1));
      const alpha = role === 'out' ? 1 - seg(p, 0.46, 0.54) : seg(p, 0.46, 0.54);
      const style: CSSProperties = {
        transform: `scale(${1 + 0.4 * s * q})`,
        opacity: alpha,
        filter: `blur(${u(70) * s * q}px)`,
      };
      return frame(style, children);
    }
  }
};

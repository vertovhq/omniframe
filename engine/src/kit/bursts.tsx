import type {CSSProperties} from 'react';
import {AbsoluteFill, random, useVideoConfig} from 'remotion';
import {useLayout} from '../style';
import {ageOf, useAt} from './at';
import type {At} from './at';
import {clamp, eOut, lerp, seg} from './motion';
import {useT} from './timing';

// The bursts group: short bright accents that sell a hit, drawn above the picture. Each takes
// `at` (seconds, a cue name, or a list of both: see `useAt`) and shows for `dur` seconds from each
// hit. `x`, `y` are percent of the parent. Colours are any CSS colour; no look of its own.

const overlay: CSSProperties = {pointerEvents: 'none', overflow: 'hidden'};

/**
 * Speed lines radiating from (`x`, `y`): thin tapered spikes, re-drawn `fps` times a second like
 * hand-inked action lines. With `at` they flare for `dur` seconds from each hit and die away;
 * without it they stay on. `inner` is the clear space in the middle (0..1 of the frame's half-diagonal).
 */
export const SpeedLines = ({
  at,
  dur = 0.6,
  x = 50,
  y = 50,
  color = '#FFFFFF',
  count = 56,
  inner = 0.28,
  thickness = 16,
  fps = 12,
  strength = 1,
  seed = 'speed',
}: {
  at?: At;
  dur?: number;
  x?: number;
  y?: number;
  color?: string;
  count?: number;
  inner?: number;
  /** Width of a line at the frame edge, design px. */
  thickness?: number;
  /** How many times a second the lines are re-drawn. */
  fps?: number;
  strength?: number;
  seed?: string;
}) => {
  const t = useT();
  const {width, height} = useVideoConfig();
  const {u} = useLayout();
  const times = useAt(at);
  const age = ageOf(t, times);
  if (times !== undefined && (age === null || age >= dur)) {
    return null;
  }
  const env = times === undefined ? 1 : (1 - (age ?? 0) / dur) ** 1.5;
  const cx = (x / 100) * width;
  const cy = (y / 100) * height;
  const reach = Math.hypot(width, height);
  const frame = Math.floor(t * Math.max(1, fps));
  const lines = Array.from({length: Math.max(0, Math.round(count))}, (_, i) => {
    const r = (k: string) => random(`${seed}-${k}-${i}-${frame}`);
    const a = (i / count) * Math.PI * 2 + r('a') * 0.12;
    const r0 = reach * inner * (0.8 + r('i') * 0.5);
    const r1 = reach * (0.75 + r('o') * 0.35);
    const half = (u(thickness) * (0.4 + r('w') * 0.9)) / 2 / r1;
    const p = (rad: number, ang: number) => `${(cx + Math.cos(ang) * rad).toFixed(1)},${(cy + Math.sin(ang) * rad).toFixed(1)}`;
    return <polygon key={i} points={`${p(r0, a)} ${p(r1, a - half)} ${p(r1, a + half)}`} />;
  });
  return (
    <AbsoluteFill style={{...overlay, opacity: clamp(env * strength)}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} fill={color}>
        {lines}
      </svg>
    </AbsoluteFill>
  );
};

/** One or more rings that expand from (`x`, `y`) and thin out and fade over `dur` seconds from each hit. */
export const Shockwave = ({
  at,
  dur = 0.8,
  x = 50,
  y = 50,
  color = '#FFFFFF',
  size = 1500,
  rings = 2,
  thickness = 26,
  strength = 1,
}: {
  at: At;
  dur?: number;
  x?: number;
  y?: number;
  color?: string;
  /** Final diameter, design px. */
  size?: number;
  rings?: number;
  /** Ring width at the start, design px. */
  thickness?: number;
  strength?: number;
}) => {
  const {u} = useLayout();
  const age = ageOf(useT(), useAt(at));
  if (age === null || age >= dur) {
    return null;
  }
  return (
    <AbsoluteFill style={overlay}>
      {Array.from({length: Math.max(1, Math.round(rings))}, (_, i) => {
        const p = seg(age, i * 0.09, dur);
        if (p <= 0) {
          return null;
        }
        const d = u(size) * eOut(p);
        const w = Math.max(0.5, u(thickness) * (1 - p) ** 1.2);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${x}%`,
              top: `${y}%`,
              width: d,
              height: d,
              marginLeft: -d / 2,
              marginTop: -d / 2,
              borderRadius: '50%',
              border: `${w}px solid ${color}`,
              opacity: clamp((1 - p) * strength * (1 - i * 0.25)),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** A soft bloom of light at (`x`, `y`) that flares up fast and fades over `dur` seconds from each hit. Adds light (screen blend). */
export const GlowBurst = ({
  at,
  dur = 0.6,
  x = 50,
  y = 50,
  color = '#FFD27A',
  size = 1200,
  strength = 1,
}: {
  at: At;
  dur?: number;
  x?: number;
  y?: number;
  color?: string;
  /** Diameter at its widest, design px. */
  size?: number;
  strength?: number;
}) => {
  const {u} = useLayout();
  const age = ageOf(useT(), useAt(at));
  if (age === null || age >= dur) {
    return null;
  }
  const p = age / dur;
  const d = u(size) * lerp(0.35, 1, eOut(p));
  const alpha = clamp(Math.min(1, p * 12) * (1 - p) ** 1.6 * strength);
  return (
    <AbsoluteFill style={{...overlay, mixBlendMode: 'screen'}}>
      <div
        style={{
          position: 'absolute',
          left: `${x}%`,
          top: `${y}%`,
          width: d,
          height: d,
          marginLeft: -d / 2,
          marginTop: -d / 2,
          borderRadius: '50%',
          background: `radial-gradient(circle, #FFFFFF 0%, ${color} 22%, transparent 68%)`,
          opacity: alpha,
        }}
      />
    </AbsoluteFill>
  );
};

/** Sparks thrown out of (`x`, `y`) that arc under gravity and burn out over `dur` seconds from each hit. */
export const Sparks = ({
  at,
  dur = 1.1,
  x = 50,
  y = 50,
  colors = ['#FFE27A', '#FF9A3C', '#FFFFFF'],
  count = 44,
  speed = 1100,
  gravity = 1500,
  size = 6,
  angle = 270,
  spread = 360,
  seed = 'sparks',
}: {
  at: At;
  dur?: number;
  x?: number;
  y?: number;
  colors?: string[];
  count?: number;
  /** Top launch speed, design px per second. */
  speed?: number;
  /** Design px per second squared (downwards). */
  gravity?: number;
  /** Spark thickness, design px. */
  size?: number;
  /** Centre direction of the spray in degrees (270 = up, 0 = right). */
  angle?: number;
  /** Width of the spray in degrees (360 = all around). */
  spread?: number;
  seed?: string;
}) => {
  const {width, height} = useVideoConfig();
  const {u} = useLayout();
  const t = useT();
  const times = useAt(at);
  const age = ageOf(t, times);
  if (age === null || age >= dur || colors.length === 0) {
    return null;
  }
  const hit = (times ?? []).filter((a) => a <= t).length;
  return (
    <AbsoluteFill style={overlay}>
      {Array.from({length: Math.max(0, Math.round(count))}, (_, i) => {
        const r = (k: string) => random(`${seed}-${k}-${i}-${hit}`);
        const dir = ((angle + (r('d') - 0.5) * spread) * Math.PI) / 180;
        const v = u(speed) * (0.25 + r('v') * 0.75);
        const life = dur * (0.45 + r('l') * 0.55);
        if (age >= life) {
          return null;
        }
        const px = (x / 100) * width + Math.cos(dir) * v * age;
        const py = (y / 100) * height + Math.sin(dir) * v * age + 0.5 * u(gravity) * age * age;
        const vx = Math.cos(dir) * v;
        const vy = Math.sin(dir) * v + u(gravity) * age;
        const len = Math.min(u(46), Math.hypot(vx, vy) * 0.045);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: px,
              top: py,
              width: len,
              height: u(size) * (0.6 + r('s') * 0.8),
              marginTop: -u(size) / 2,
              borderRadius: u(size),
              background: colors[Math.floor(r('c') * colors.length) % colors.length],
              transform: `rotate(${(Math.atan2(vy, vx) * 180) / Math.PI}deg)`,
              transformOrigin: '100% 50%',
              opacity: clamp(1 - age / life),
              boxShadow: `0 0 ${u(10)}px ${colors[0]}`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** A slanted band of light that sweeps across the frame in `dur` seconds from each hit. Adds light (screen blend). */
export const LightSweep = ({
  at,
  dur = 0.8,
  color = '#FFFFFF',
  angle = 20,
  width = 24,
  strength = 0.7,
}: {
  at: At;
  dur?: number;
  color?: string;
  /** Tilt from vertical, degrees. */
  angle?: number;
  /** Band width, percent of the frame width. */
  width?: number;
  strength?: number;
}) => {
  const age = ageOf(useT(), useAt(at));
  if (age === null || age >= dur) {
    return null;
  }
  const p = eOut(age / dur);
  return (
    <AbsoluteFill style={{...overlay, mixBlendMode: 'screen'}}>
      <div
        style={{
          position: 'absolute',
          top: '-60%',
          height: '220%',
          width: `${width}%`,
          left: `${lerp(-width * 1.3, 100 + width * 0.3, p)}%`,
          transform: `rotate(${angle}deg)`,
          background: `linear-gradient(90deg, transparent, ${color} 50%, transparent)`,
          opacity: clamp(Math.sin(Math.PI * (age / dur)) * strength * 1.4),
        }}
      />
    </AbsoluteFill>
  );
};

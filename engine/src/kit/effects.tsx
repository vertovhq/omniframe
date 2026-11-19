import type {CSSProperties} from 'react';
import {random} from 'remotion';
import {useLayout, useStyle} from '../style';
import {pulse as pulseWave} from './motion';
import {useT} from './timing';

// Decorations. They are positioned against their parent in percent, so put them inside a
// full-frame `Stage` (or any positioned box) and they work in 9:16 and 16:9 alike.

/** A soft round glow centred at (`x`, `y`) percent of the parent. */
export const Glow = ({
  x = 50,
  y = 50,
  size = 700,
  color,
  opacity = 0.6,
  hz = 0,
  style: extra,
}: {
  x?: number;
  y?: number;
  /** Diameter in design px. */
  size?: number;
  /** Any CSS colour. Default: the style's accent. */
  color?: string;
  opacity?: number;
  /** Breathing speed in beats per second; 0 keeps it steady. */
  hz?: number;
  style?: CSSProperties;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const d = u(size);
  const k = hz > 0 ? 0.65 + 0.35 * pulseWave(t, hz) : 1;
  return (
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
        background: `radial-gradient(circle, ${color ?? style.colors.accent} 0%, transparent 68%)`,
        opacity: opacity * k,
        pointerEvents: 'none',
        ...extra,
      }}
    />
  );
};

/** Floating dust (rises through the area) or twinkling stars (fixed), drawn from a seed. */
export const Particles = ({
  kind = 'dust',
  count = 40,
  seed = 'particles',
  color,
  area = {x: 0, y: 0, w: 100, h: 100},
  size = [3, 8],
  speed = 6,
}: {
  kind?: 'dust' | 'stars';
  count?: number;
  /** Same seed, same picture. Change it to get another scatter. */
  seed?: string;
  /** Any CSS colour. Default: the style's text colour. */
  color?: string;
  /** The rectangle the particles live in, in percent of the parent. */
  area?: {x: number; y: number; w: number; h: number};
  /** Smallest and largest particle diameter in design px. */
  size?: [number, number];
  /** Dust: how far it rises, in percent of the area height per second. */
  speed?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const ink = color ?? style.colors.text;
  const items = Array.from({length: Math.max(0, Math.min(400, Math.round(count)))}, (_, i) => {
    const r = (k: string) => random(`${seed}-${k}-${i}`);
    const dia = u(size[0] + r('d') * (size[1] - size[0]));
    if (kind === 'stars') {
      const tw = 0.5 + 0.5 * Math.sin(t * (1.2 + r('s') * 2) + i);
      return {key: i, x: r('x') * 100, y: r('y') * 100, dia, alpha: 0.2 + 0.7 * tw * (0.4 + r('o') * 0.6)};
    }
    const rise = speed * (0.5 + r('v'));
    const y = (((r('y') * 100 - t * rise) % 100) + 100) % 100;
    const sway = Math.sin(t * 0.7 + i * 1.3) * 1.2;
    return {key: i, x: r('x') * 100 + sway, y, dia, alpha: 0.15 + 0.5 * Math.sin((y / 100) * Math.PI)};
  });
  return (
    <div
      style={{
        position: 'absolute',
        left: `${area.x}%`,
        top: `${area.y}%`,
        width: `${area.w}%`,
        height: `${area.h}%`,
        overflow: 'hidden',
        pointerEvents: 'none',
      }}
    >
      {items.map((p) => (
        <div
          key={p.key}
          style={{
            position: 'absolute',
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.dia,
            height: p.dia,
            borderRadius: '50%',
            background: ink,
            opacity: p.alpha,
          }}
        />
      ))}
    </div>
  );
};

/** A cone of light that fades along its length, hanging from (`x`, `y`) percent of the parent. */
export const LightCone = ({
  x = 50,
  y = 0,
  topWidth = 80,
  width = 560,
  height = 900,
  angle = 0,
  color = '#FFE9A8',
  opacity = 0.35,
}: {
  x?: number;
  y?: number;
  /** Width at the source, design px. */
  topWidth?: number;
  /** Width at the far end, design px. */
  width?: number;
  /** Length, design px. */
  height?: number;
  /** Degrees, turned around the source. 0 points straight down. */
  angle?: number;
  color?: string;
  opacity?: number;
}) => {
  const {u} = useLayout();
  const w = u(width);
  const inset = ((w - u(topWidth)) / 2 / w) * 100;
  return (
    <div
      style={{
        position: 'absolute',
        left: `${x}%`,
        top: `${y}%`,
        width: w,
        height: u(height),
        marginLeft: -w / 2,
        transformOrigin: '50% 0',
        transform: angle ? `rotate(${angle}deg)` : undefined,
        clipPath: `polygon(${inset}% 0, ${100 - inset}% 0, 100% 100%, 0 100%)`,
        background: `linear-gradient(to bottom, ${color}, transparent)`,
        opacity,
        pointerEvents: 'none',
      }}
    />
  );
};

import type {CSSProperties} from 'react';
import {AbsoluteFill, Img, OffthreadVideo, random, useVideoConfig} from 'remotion';
import {grainBackgroundImage, resolveMedia, useLayout, useStyle} from '../style';
import {useT} from './timing';

// Full-frame backdrops. Each one fills its parent, so put them first inside a `Stage` (or a
// positioned box) and draw the rest on top. Colours default to the plan style and can all be
// overridden; sizes are design px.

type Layer = {
  /** Extra CSS for the layer. */
  style?: CSSProperties;
};

/** One flat colour. Default: the style's background colour. */
export const Solid = ({color, opacity = 1, style: extra}: Layer & {color?: string; opacity?: number}) => {
  const style = useStyle();
  return <AbsoluteFill style={{background: color ?? style.colors.bg, opacity, ...extra}} />;
};

/** A linear or radial gradient between `stops` (any CSS colours). Default: background to accent. */
export const Gradient = ({
  stops,
  angle = 180,
  kind = 'linear',
  at = [50, 50],
  spin = 0,
  opacity = 1,
  style: extra,
}: Layer & {
  stops?: string[];
  /** Linear: direction in degrees (180 = top to bottom). */
  angle?: number;
  kind?: 'linear' | 'radial';
  /** Radial: the centre in percent of the frame. */
  at?: [number, number];
  /** Linear: degrees per second the direction turns. */
  spin?: number;
  opacity?: number;
}) => {
  const style = useStyle();
  const t = useT();
  const list = stops && stops.length > 0 ? stops : [style.colors.bg, style.colors.accent];
  const colors = (list.length === 1 ? [list[0], list[0]] : list).join(', ');
  const image =
    kind === 'radial'
      ? `radial-gradient(circle at ${at[0]}% ${at[1]}%, ${colors})`
      : `linear-gradient(${(angle + spin * t).toFixed(2)}deg, ${colors})`;
  return <AbsoluteFill style={{backgroundImage: image, opacity, ...extra}} />;
};

/** A grid of lines or dots that can drift, optionally fading out towards the edges. Transparent between the lines. */
export const Grid = ({
  kind = 'lines',
  color,
  opacity = 0.25,
  step = 90,
  line = 2,
  drift = [0, 0],
  fadeEdges = true,
  style: extra,
}: Layer & {
  kind?: 'lines' | 'dots';
  /** Any CSS colour. Default: the style's muted colour. */
  color?: string;
  opacity?: number;
  /** Distance between lines (or dots), design px. */
  step?: number;
  /** Line width (or dot diameter), design px. */
  line?: number;
  /** Drift speed in design px per second, `[x, y]`. */
  drift?: [number, number];
  /** Fade the grid out towards the edges of the frame. */
  fadeEdges?: boolean;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const ink = color ?? style.colors.muted;
  const cell = Math.max(2, u(step));
  const w = Math.max(1, u(line));
  const image =
    kind === 'dots'
      ? `radial-gradient(circle at ${w / 2}px ${w / 2}px, ${ink} ${w / 2}px, transparent ${w / 2 + 0.5}px)`
      : `linear-gradient(to right, ${ink} ${w}px, transparent ${w}px), linear-gradient(to bottom, ${ink} ${w}px, transparent ${w}px)`;
  const mask = fadeEdges ? 'radial-gradient(ellipse at center, #000 25%, transparent 78%)' : undefined;
  return (
    <AbsoluteFill
      style={{
        backgroundImage: image,
        backgroundSize: `${cell}px ${cell}px`,
        backgroundPosition: `${(drift[0] * t * u(1)).toFixed(2)}px ${(drift[1] * t * u(1)).toFixed(2)}px`,
        opacity,
        maskImage: mask,
        WebkitMaskImage: mask,
        pointerEvents: 'none',
        ...extra,
      }}
    />
  );
};

/** Film grain over the layers below it. Static, or re-drawn `rate` times a second. */
export const Noise = ({
  opacity = 0.12,
  size = 240,
  rate = 0,
  seed = 'noise',
  blend = 'normal',
  style: extra,
}: Layer & {
  opacity?: number;
  /** Size of the grain tile, design px. Bigger is coarser. */
  size?: number;
  /** Grain changes per second; 0 keeps it still. */
  rate?: number;
  /** Same seed, same grain pattern sequence. */
  seed?: string;
  /** CSS `mix-blend-mode` (e.g. 'overlay', 'soft-light'). */
  blend?: CSSProperties['mixBlendMode'];
}) => {
  const {u} = useLayout();
  const t = useT();
  const tile = Math.max(8, u(size));
  const step = rate > 0 ? Math.floor(t * rate) : 0;
  const dx = rate > 0 ? random(`${seed}-x-${step}`) * tile : 0;
  const dy = rate > 0 ? random(`${seed}-y-${step}`) * tile : 0;
  return (
    <AbsoluteFill
      style={{
        backgroundImage: grainBackgroundImage,
        backgroundRepeat: 'repeat',
        backgroundSize: `${tile}px ${tile}px`,
        backgroundPosition: `${dx.toFixed(1)}px ${dy.toFixed(1)}px`,
        opacity,
        mixBlendMode: blend,
        pointerEvents: 'none',
        ...extra,
      }}
    />
  );
};

/** A gradient that keeps flowing: the colours of `stops` slide along `angle` and loop without a seam. */
export const AnimatedGradient = ({
  stops,
  angle = 135,
  speed = 0.12,
  period = 1600,
  opacity = 1,
  style: extra,
}: Layer & {
  /** Any CSS colours; the last one blends back into the first. Default: background and accent. */
  stops?: string[];
  /** Direction of the flow in degrees (180 = downwards). */
  angle?: number;
  /** Full colour cycles per second (0.1 = one cycle in 10 s; negative flows backwards). */
  speed?: number;
  /** Length of one cycle across the frame, design px. Bigger is calmer. */
  period?: number;
  opacity?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const list = stops && stops.length > 0 ? stops : [style.colors.bg, style.colors.accent];
  const len = Math.max(100, u(period));
  const phase = (((t * speed) % 1) + 1) % 1 * len;
  const parts = Array.from({length: list.length + 1}, (_, i) => `${list[i % list.length]} ${(phase + (i / list.length) * len).toFixed(1)}px`);
  return <AbsoluteFill style={{backgroundImage: `repeating-linear-gradient(${angle}deg, ${parts.join(', ')})`, opacity, ...extra}} />;
};

/** Soft colour blobs drifting on a base colour (a mesh / aurora gradient). The blobs follow `seed`. */
export const Mesh = ({
  colors,
  base,
  count = 5,
  size = 1100,
  speed = 0.12,
  opacity = 1,
  seed = 'mesh',
  style: extra,
}: Layer & {
  /** Blob colours, used in turn. Default: the style's accent and muted colours. */
  colors?: string[];
  /** Colour behind the blobs. Default: the style's background. */
  base?: string;
  count?: number;
  /** Blob diameter, design px (each blob varies around it). */
  size?: number;
  /** How fast the blobs drift (cycles per second). */
  speed?: number;
  opacity?: number;
  seed?: string;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const palette = colors && colors.length > 0 ? colors : [style.colors.accent, style.colors.muted];
  const blobs = Array.from({length: Math.max(1, Math.min(16, Math.round(count)))}, (_, i) => {
    const r = (k: string) => random(`${seed}-${k}-${i}`);
    const w = t * speed * Math.PI * 2 * (0.6 + r('f'));
    const d = u(size * (0.7 + 0.6 * r('s')));
    return {
      key: i,
      color: palette[i % palette.length],
      d,
      x: 15 + 70 * r('x') + (10 + 12 * r('ox')) * Math.sin(w + r('p') * 6.28),
      y: 15 + 70 * r('y') + (10 + 12 * r('oy')) * Math.cos(w * 0.8 + r('q') * 6.28),
    };
  });
  return (
    <AbsoluteFill style={{background: base ?? style.colors.bg, overflow: 'hidden', opacity, ...extra}}>
      {blobs.map((b) => (
        <div
          key={b.key}
          style={{
            position: 'absolute',
            left: `${b.x}%`,
            top: `${b.y}%`,
            width: b.d,
            height: b.d,
            marginLeft: -b.d / 2,
            marginTop: -b.d / 2,
            borderRadius: '50%',
            background: `radial-gradient(circle, ${b.color} 0%, transparent 68%)`,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

/** Diagonal (or any angle) stripes that can slide. Transparent between the stripes. */
export const Stripes = ({
  color,
  opacity = 0.2,
  angle = 45,
  width = 40,
  gap = 40,
  drift = 30,
  style: extra,
}: Layer & {
  /** Any CSS colour. Default: the style's muted colour. */
  color?: string;
  opacity?: number;
  /** Direction across the stripes in degrees. */
  angle?: number;
  /** Stripe and gap widths, design px. */
  width?: number;
  gap?: number;
  /** Sliding speed, design px per second (negative: the other way). */
  drift?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const ink = color ?? style.colors.muted;
  const w = Math.max(1, u(width));
  const period = w + Math.max(1, u(gap));
  const at = ((((drift * t * u(1)) % period) + period) % period).toFixed(2);
  const to = (Number(at) + w).toFixed(2);
  const end = (Number(at) + period).toFixed(2);
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `repeating-linear-gradient(${angle}deg, ${ink} ${at}px, ${ink} ${to}px, transparent ${to}px, transparent ${end}px)`,
        opacity,
        pointerEvents: 'none',
        ...extra,
      }}
    />
  );
};

/** Darkens (or tints) the edges of the frame. */
export const Vignette = ({
  color = '#000000',
  strength = 0.6,
  size = 55,
  style: extra,
}: Layer & {
  /** Any CSS colour of the edge. */
  color?: string;
  /** 0..1 */
  strength?: number;
  /** Percent of the frame that stays clear in the middle. */
  size?: number;
}) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(ellipse at center, transparent ${size}%, ${color} 118%)`,
      opacity: Math.min(1, strength),
      pointerEvents: 'none',
      ...extra,
    }}
  />
);

/** Warm light washing over the frame from the edges, like film light leaks. Adds light (screen blend). */
export const LightLeaks = ({
  colors = ['#FF7A18', '#FFC15E', '#FF4F7B'],
  intensity = 0.6,
  speed = 0.2,
  count = 3,
  seed = 'leaks',
  blend = 'screen',
  style: extra,
}: Layer & {
  colors?: string[];
  /** 0..1 */
  intensity?: number;
  /** Swell cycles per second. */
  speed?: number;
  count?: number;
  seed?: string;
  blend?: CSSProperties['mixBlendMode'];
}) => {
  const {u} = useLayout();
  const t = useT();
  const list = colors.length > 0 ? colors : ['#FFC15E'];
  return (
    <AbsoluteFill style={{overflow: 'hidden', mixBlendMode: blend, pointerEvents: 'none', ...extra}}>
      {Array.from({length: Math.max(1, Math.min(8, Math.round(count)))}, (_, i) => {
        const r = (k: string) => random(`${seed}-${k}-${i}`);
        const w = t * speed * Math.PI * 2 * (0.5 + r('f'));
        const d = u(1000 + 900 * r('s'));
        const edge = r('e') < 0.5 ? -8 : 108;
        const swell = 0.5 + 0.5 * Math.sin(w + r('p') * 6.28);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${r('h') < 0.5 ? edge : 8 + 84 * r('x') + 14 * Math.sin(w)}%`,
              top: `${r('h') < 0.5 ? 8 + 84 * r('y') + 14 * Math.cos(w) : edge}%`,
              width: d,
              height: d * 0.7,
              marginLeft: -d / 2,
              marginTop: -d * 0.35,
              borderRadius: '50%',
              background: `radial-gradient(ellipse, ${list[i % list.length]} 0%, transparent 70%)`,
              opacity: Math.min(1, intensity) * (0.35 + 0.65 * swell),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** CRT / video scanlines, with an optional bright band that rolls down the frame. */
export const Scanlines = ({
  color = '#000000',
  opacity = 0.25,
  gap = 5,
  thickness = 2,
  roll = 0,
  style: extra,
}: Layer & {
  /** Any CSS colour of the lines. */
  color?: string;
  opacity?: number;
  /** Distance between lines and line width, design px. */
  gap?: number;
  thickness?: number;
  /** Rolling band: frame heights per second (0 = none). */
  roll?: number;
}) => {
  const {u} = useLayout();
  const t = useT();
  const g = Math.max(2, u(gap));
  const th = Math.max(1, Math.min(g - 1, u(thickness)));
  const band = ((t * roll) % 1.3 + 1.3) % 1.3 - 0.15;
  return (
    <AbsoluteFill style={{pointerEvents: 'none', ...extra}}>
      <AbsoluteFill
        style={{
          backgroundImage: `repeating-linear-gradient(to bottom, ${color} 0px, ${color} ${th}px, transparent ${th}px, transparent ${g}px)`,
          opacity,
        }}
      />
      {roll !== 0 ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: `${band * 100}%`,
            height: '16%',
            background: 'linear-gradient(to bottom, transparent, rgba(255, 255, 255, 0.10), transparent)',
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};

/** Stars flying outwards from a point, as when travelling through space. `streak` stretches them into lines. */
export const Starfield = ({
  count = 120,
  speed = 0.3,
  color,
  size = [2, 7],
  streak = 0,
  centre = [50, 50],
  seed = 'starfield',
  style: extra,
}: Layer & {
  count?: number;
  /** Trips from the centre to the edge per second. */
  speed?: number;
  /** Any CSS colour. Default: the style's text colour. */
  color?: string;
  /** Star diameter near the centre and at the edge, design px. */
  size?: [number, number];
  /** Streak length at the edge as a multiple of the star size (0 = round dots). */
  streak?: number;
  /** Where the stars come from, percent of the frame. */
  centre?: [number, number];
  seed?: string;
}) => {
  const style = useStyle();
  const {u, width, height} = useLayout();
  const t = useT();
  const ink = color ?? style.colors.text;
  const reach = Math.hypot(width, height) * 0.6;
  const stars = Array.from({length: Math.max(0, Math.min(500, Math.round(count)))}, (_, i) => {
    const r = (k: string) => random(`${seed}-${k}-${i}`);
    const z = (((r('z') + t * speed) % 1) + 1) % 1;
    const a = r('a') * Math.PI * 2;
    const d = u(size[0] + (size[1] - size[0]) * z);
    const run = z * z * reach;
    return {
      key: i,
      x: (centre[0] / 100) * width + Math.cos(a) * run,
      y: (centre[1] / 100) * height + Math.sin(a) * run,
      d,
      len: d * (1 + streak * z * z * 6),
      deg: (a * 180) / Math.PI,
      alpha: Math.min(1, z * 6) * (0.45 + 0.55 * r('o')),
    };
  });
  return (
    <AbsoluteFill style={{overflow: 'hidden', pointerEvents: 'none', ...extra}}>
      {stars.map((s) => (
        <div
          key={s.key}
          style={{
            position: 'absolute',
            left: s.x,
            top: s.y,
            width: s.len,
            height: s.d,
            marginLeft: -s.len,
            marginTop: -s.d / 2,
            borderRadius: s.d,
            background: streak > 0 ? `linear-gradient(to right, transparent, ${ink})` : ink,
            opacity: s.alpha,
            transformOrigin: '100% 50%',
            transform: `rotate(${s.deg.toFixed(2)}deg)`,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

/** Out-of-focus light discs drifting upwards, as in a night-city background. */
export const Bokeh = ({
  colors,
  count = 18,
  size = [120, 320],
  opacity = 0.35,
  speed = 0.04,
  seed = 'bokeh',
  blend = 'screen',
  style: extra,
}: Layer & {
  /** Disc colours, used in turn. Default: the style's text and accent colours. */
  colors?: string[];
  count?: number;
  /** Smallest and largest disc diameter, design px. */
  size?: [number, number];
  opacity?: number;
  /** Frame heights per second the discs rise (negative: fall). */
  speed?: number;
  seed?: string;
  blend?: CSSProperties['mixBlendMode'];
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const palette = colors && colors.length > 0 ? colors : [style.colors.text, style.colors.accent];
  return (
    <AbsoluteFill style={{overflow: 'hidden', mixBlendMode: blend, pointerEvents: 'none', ...extra}}>
      {Array.from({length: Math.max(0, Math.min(60, Math.round(count)))}, (_, i) => {
        const r = (k: string) => random(`${seed}-${k}-${i}`);
        const d = u(size[0] + (size[1] - size[0]) * r('d'));
        const y = 100 - ((((r('y') + t * speed * (0.5 + r('v'))) % 1) + 1) % 1) * 100;
        const x = r('x') * 100 + 2.5 * Math.sin(t * 0.5 + r('p') * 6.28);
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
              background: `radial-gradient(circle, ${palette[i % palette.length]} 0%, ${palette[i % palette.length]} 55%, transparent 72%)`,
              opacity: opacity * (0.3 + 0.7 * r('o')),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** Paper: a flat colour with grain, soft shading at the edges and optional ruled lines. */
export const Paper = ({
  color = '#F2EDE3',
  grain = 0.35,
  size = 300,
  shade = 0.25,
  ruling = 'none',
  ruleColor = '#6B8AB8',
  ruleGap = 64,
  style: extra,
}: Layer & {
  /** Any CSS colour of the sheet. */
  color?: string;
  /** Grain strength 0..1 and tile size (design px). */
  grain?: number;
  size?: number;
  /** Darkening at the edges 0..1. */
  shade?: number;
  ruling?: 'none' | 'lines' | 'squares';
  ruleColor?: string;
  /** Distance between ruled lines, design px. */
  ruleGap?: number;
}) => {
  const {u} = useLayout();
  const g = Math.max(8, u(ruleGap));
  const line = `${ruleColor} 0px, ${ruleColor} ${Math.max(1, u(2))}px, transparent ${Math.max(1, u(2))}px, transparent ${g}px`;
  return (
    <AbsoluteFill style={{background: color, overflow: 'hidden', ...extra}}>
      <Noise opacity={grain} size={size} blend="multiply" />
      {ruling !== 'none' ? (
        <AbsoluteFill style={{backgroundImage: `repeating-linear-gradient(to bottom, ${line})`, opacity: 0.45}} />
      ) : null}
      {ruling === 'squares' ? (
        <AbsoluteFill style={{backgroundImage: `repeating-linear-gradient(to right, ${line})`, opacity: 0.45}} />
      ) : null}
      <Vignette color="#2B1D0E" strength={shade} size={45} />
    </AbsoluteFill>
  );
};

const VIDEO_EXT = /\.(mp4|m4v|webm|mov)(\?.*)?$/i;

/** An image or a (muted) video filling the frame, with a dim overlay so the content on top stays readable. */
export const Media = ({
  src,
  fit = 'cover',
  dim = 0.35,
  dimColor = '#000000',
  blur = 0,
  start = 0,
  rate = 1,
  style: extra,
}: Layer & {
  /** A file of the plan (resolved like any media) or a URL. The extension tells image from video. */
  src: string;
  fit?: 'cover' | 'contain';
  /** Strength 0..1 of the overlay. */
  dim?: number;
  /** Any CSS colour of the overlay. */
  dimColor?: string;
  /** Blur radius in design px. */
  blur?: number;
  /** Video: second of the file to start from. */
  start?: number;
  /** Video: playback speed. */
  rate?: number;
}) => {
  const {u} = useLayout();
  const {fps} = useVideoConfig();
  const media: CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: fit,
    ...(blur > 0 ? {filter: `blur(${u(blur)}px)`, transform: 'scale(1.1)'} : {}),
  };
  const url = resolveMedia(src);
  return (
    <AbsoluteFill style={{overflow: 'hidden', ...extra}}>
      {VIDEO_EXT.test(src) ? (
        <OffthreadVideo muted src={url} style={media} trimBefore={Math.round(start * fps)} playbackRate={rate} />
      ) : (
        <Img src={url} style={media} />
      )}
      {dim > 0 ? <AbsoluteFill style={{background: dimColor, opacity: Math.min(1, dim)}} /> : null}
    </AbsoluteFill>
  );
};

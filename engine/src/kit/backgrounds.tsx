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

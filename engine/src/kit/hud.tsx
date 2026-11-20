import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {fontFor, useLayout, useStyle} from '../style';
import type {FontRole} from '../style';
import {measureTextWidth, useFontsReady} from '../text';
import {clamp, eInOut, eOut, lerp, pulse, seg} from './motion';
import {useDuration, useT} from './timing';

// The HUD group: small instrument-panel details (brackets, rulers, timecode, readouts, tickers,
// scan lines, reticles, pills) that keep a scene busy at the edges while the main element holds the
// middle. Text blocks flow like normal elements (stack them in a column or row); `x`/`y` (percent of
// the parent) pin one at a place instead. `color` is any CSS colour (default: the style's text
// colour); `at` is the second a block starts to draw in. No look of its own beyond that.

type Pin = {
  /** Pin to a place: percent of the parent. Without `x` and `y` the block flows in its parent. */
  x?: number;
  y?: number;
  /** The point of the block that sits at (`x`, `y`). Default: its top-left corner. */
  anchor?: 'tl' | 'tr' | 'bl' | 'br' | 'c';
};

const ANCHOR_SHIFT: Record<NonNullable<Pin['anchor']>, string> = {
  tl: '0, 0',
  tr: '-100%, 0',
  bl: '0, -100%',
  br: '-100%, -100%',
  c: '-50%, -50%',
};

/** Flows in the parent, or is pinned at (`x`, `y`) when one is given. */
const place = ({x, y, anchor = 'tl'}: Pin, extra?: CSSProperties): CSSProperties =>
  x === undefined && y === undefined
    ? {...extra}
    : {position: 'absolute', left: `${x ?? 0}%`, top: `${y ?? 0}%`, transform: `translate(${ANCHOR_SHIFT[anchor]})`, ...extra};

/** 0..1 draw-in progress of a block that starts at `at`. */
const useIn = (at: number, dur = 0.35): number => eOut(seg(useT(), at, at + dur));

const fill: CSSProperties = {pointerEvents: 'none'};

/** `mm:ss:ff` for `seconds` at `fps`. */
const timecode = (seconds: number, fps: number): string => {
  const total = Math.max(0, seconds);
  const whole = Math.floor(total);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(Math.floor(whole / 60))}:${pad(whole % 60)}:${pad(Math.floor((total - whole) * fps))}`;
};

// ---------------------------------------------------------------------------
// Overlays that fill their parent
// ---------------------------------------------------------------------------

/** Four L-shaped brackets in the corners of the parent; they grow out of the corners from `at`. */
export const CornerBrackets = ({
  color,
  size = 90,
  thickness = 6,
  inset = 0,
  at = 0,
  breathe = 0,
  opacity = 1,
}: {
  color?: string;
  /** Length of each arm, design px. */
  size?: number;
  thickness?: number;
  /** Distance from the edge of the parent, design px. */
  inset?: number;
  at?: number;
  /** Size of a slow in-and-out pulse, 0 = none (0.1 = 10 %). */
  breathe?: number;
  opacity?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const p = useIn(at, 0.45);
  const ink = color ?? style.colors.text;
  const arm = u(size) * p * (1 + breathe * (pulse(t, 0.6) - 0.5));
  const th = u(thickness);
  const corner = (v: 'top' | 'bottom', h: 'left' | 'right') => (
    <div key={`${v}${h}`} style={{position: 'absolute', [v]: u(inset), [h]: u(inset), width: arm, height: arm}}>
      <div style={{position: 'absolute', [v]: 0, [h]: 0, width: arm, height: th, background: ink}} />
      <div style={{position: 'absolute', [v]: 0, [h]: 0, width: th, height: arm, background: ink}} />
    </div>
  );
  return (
    <AbsoluteFill style={{...fill, opacity: opacity * clamp(p * 3)}}>
      {corner('top', 'left')}
      {corner('top', 'right')}
      {corner('bottom', 'left')}
      {corner('bottom', 'right')}
    </AbsoluteFill>
  );
};

/** Ruler ticks along the edges of the parent (every fifth is longer); they slide at `drift` design px per second. */
export const FrameTicks = ({
  color,
  edges = ['top', 'bottom'],
  step = 26,
  length = 18,
  drift = 40,
  at = 0,
  opacity = 0.7,
}: {
  color?: string;
  edges?: Array<'top' | 'bottom' | 'left' | 'right'>;
  /** Distance between ticks, design px. */
  step?: number;
  /** Length of a short tick, design px. */
  length?: number;
  drift?: number;
  at?: number;
  opacity?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const p = useIn(at, 0.5);
  const ink = color ?? style.colors.text;
  const gap = Math.max(4, u(step));
  const shift = (t - at) * u(drift);
  return (
    <AbsoluteFill style={{...fill, opacity: opacity * p}}>
      {edges.map((edge) => {
        const horizontal = edge === 'top' || edge === 'bottom';
        const dir = horizontal ? '90deg' : '180deg';
        const ticks = (period: number, len: number, thick: number) => (
          <div
            style={{
              position: 'absolute',
              [edge]: 0,
              ...(horizontal ? {left: 0, right: 0, height: u(len)} : {top: 0, bottom: 0, width: u(len)}),
              backgroundImage: `repeating-linear-gradient(${dir}, ${ink} 0 ${u(thick)}px, transparent ${u(thick)}px ${period}px)`,
              backgroundPosition: horizontal ? `${shift}px 0` : `0 ${shift}px`,
            }}
          />
        );
        return (
          <div key={edge}>
            {ticks(gap, length, 2)}
            {ticks(gap * 5, length * 2, 3)}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** A bright line that sweeps across the parent every `period` seconds, with a soft glow behind it. */
export const ScanLine = ({
  color,
  period = 2.4,
  thickness = 4,
  glow = 90,
  vertical = false,
  at = 0,
  opacity = 0.8,
}: {
  color?: string;
  period?: number;
  thickness?: number;
  /** Width of the soft trail behind the line, design px. */
  glow?: number;
  /** Sweep sideways instead of downwards. */
  vertical?: boolean;
  at?: number;
  opacity?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  if (t < at) {
    return null;
  }
  const ink = color ?? style.colors.accent;
  const k = (((t - at) / Math.max(0.2, period)) % 1) * 100;
  const dir = vertical ? 'to right' : 'to bottom';
  return (
    <AbsoluteFill style={{...fill, overflow: 'hidden', opacity}}>
      <div
        style={{
          position: 'absolute',
          ...(vertical
            ? {left: `${k}%`, top: 0, bottom: 0, width: u(glow) + u(thickness), transform: `translateX(-100%)`}
            : {top: `${k}%`, left: 0, right: 0, height: u(glow) + u(thickness), transform: `translateY(-100%)`}),
          background: `linear-gradient(${dir}, transparent, ${ink}55 85%, ${ink})`,
        }}
      />
    </AbsoluteFill>
  );
};

/**
 * A targeting reticle at (`x`, `y`) percent that locks on (shrinks from 1.8x to 1x) at `at` and,
 * with `to`, glides to another point over `dur` seconds.
 */
export const Crosshair = ({
  x = 50,
  y = 50,
  to,
  at = 0,
  dur = 0.8,
  size = 170,
  color,
  thickness = 4,
  spin = 20,
}: {
  x?: number;
  y?: number;
  to?: [number, number];
  at?: number;
  dur?: number;
  /** Diameter, design px. */
  size?: number;
  color?: string;
  thickness?: number;
  /** Degrees per second the ring turns. */
  spin?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const p = eOut(seg(t, at, at + 0.35));
  if (p <= 0) {
    return null;
  }
  const ink = color ?? style.colors.accent;
  const go = to ? eInOut(seg(t, at, at + Math.max(0.1, dur))) : 0;
  const cx = to ? lerp(x, to[0], go) : x;
  const cy = to ? lerp(y, to[1], go) : y;
  const d = u(size) * lerp(1.8, 1, p);
  const w = u(thickness);
  const tick = (rot: number) => (
    <div
      key={rot}
      style={{position: 'absolute', left: '50%', top: '50%', width: w, height: d * 0.22, background: ink, transform: `rotate(${rot}deg) translate(-50%, -${d * 0.5 + d * 0.11}px)`, transformOrigin: '0 0'}}
    />
  );
  return (
    <div style={{position: 'absolute', left: `${cx}%`, top: `${cy}%`, width: d, height: d, marginLeft: -d / 2, marginTop: -d / 2, opacity: p, ...fill}}>
      <div style={{position: 'absolute', inset: 0, border: `${w}px solid ${ink}`, borderRadius: '50%', borderStyle: 'dashed', transform: `rotate(${(t - at) * spin}deg)`}} />
      <div style={{position: 'absolute', inset: d * 0.22, border: `${w * 0.6}px solid ${ink}`, borderRadius: '50%', opacity: 0.8}} />
      {[0, 90, 180, 270].map(tick)}
      <div style={{position: 'absolute', left: '50%', top: '50%', width: w * 2.2, height: w * 2.2, marginLeft: -w * 1.1, marginTop: -w * 1.1, borderRadius: '50%', background: ink}} />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Text blocks
// ---------------------------------------------------------------------------

type TextLook = {
  color?: string;
  /** Text size, design px. */
  size?: number;
  font?: FontRole;
  at?: number;
  opacity?: number;
};

const useFace = (font: FontRole) => fontFor(useStyle(), font);

/** `TC 00:03:12` clock of the scene (frames as the last pair), with a blinking REC dot when `rec` is on. */
export const Timecode = ({
  color,
  size = 34,
  font = 'mono',
  at = 0,
  from = 0,
  label = 'TC',
  rec = false,
  recColor = '#FF3B3B',
  opacity = 1,
  ...pin
}: TextLook & Pin & {from?: number; label?: string; rec?: boolean; recColor?: string}) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const {fps} = useVideoConfig();
  const face = useFace(font);
  const t = useT();
  const p = useIn(at);
  const ink = color ?? style.colors.text;
  return (
    <div
      style={place(pin, {
        display: 'flex',
        alignItems: 'center',
        gap: u(14),
        fontFamily: face.css,
        fontWeight: face.weight,
        fontSize: fs(size),
        color: ink,
        opacity: opacity * p,
        fontVariantNumeric: 'tabular-nums',
        letterSpacing: u(2),
        whiteSpace: 'nowrap',
      })}
    >
      {rec ? (
        <>
          <span style={{width: u(size * 0.5), height: u(size * 0.5), borderRadius: '50%', background: recColor, opacity: pulse(t, 1) > 0.35 ? 1 : 0.15}} />
          <span style={{color: recColor}}>REC</span>
        </>
      ) : null}
      <span>
        {label ? `${label} ` : ''}
        {timecode(t - from, fps)}
      </span>
    </div>
  );
};

/**
 * A mini timeline: a track with a playhead that runs from `from` to `to` (default: the whole scene),
 * short ticks, optional `marks` (0..1) as diamonds, and `left`/`right` end labels.
 */
export const Scrubber = ({
  color,
  size = 26,
  font = 'mono',
  at = 0,
  from = 0,
  to,
  marks = [],
  ticks = 20,
  left,
  right,
  width = 100,
  opacity = 1,
  ...pin
}: TextLook &
  Pin & {
    from?: number;
    to?: number;
    marks?: number[];
    ticks?: number;
    left?: string;
    right?: string;
    /** Percent of the parent. */
    width?: number;
  }) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const face = useFace(font);
  const t = useT();
  const d = useDuration();
  const p = useIn(at);
  const ink = color ?? style.colors.text;
  const head = seg(t, from, to ?? Math.max(from + 0.1, d));
  const labels = left !== undefined || right !== undefined;
  return (
    <div style={place(pin, {width: `${width}%`, opacity: opacity * p, fontFamily: face.css, fontWeight: face.weight, fontSize: fs(size), color: ink})}>
      <div style={{position: 'relative', height: u(34)}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: '50%', height: u(3), background: ink, opacity: 0.35, marginTop: -u(1.5)}} />
        <div style={{position: 'absolute', left: 0, width: `${head * 100}%`, top: '50%', height: u(3), background: ink, marginTop: -u(1.5)}} />
        {Array.from({length: Math.max(0, ticks) + 1}, (_, i) => (
          <div key={i} style={{position: 'absolute', left: `${(i / Math.max(1, ticks)) * 100}%`, top: i % 5 === 0 ? '10%' : '30%', bottom: i % 5 === 0 ? '10%' : '30%', width: u(2), background: ink, opacity: 0.5}} />
        ))}
        {marks.map((m, i) => (
          <div key={i} style={{position: 'absolute', left: `${clamp(m) * 100}%`, top: '50%', width: u(16), height: u(16), marginLeft: -u(8), marginTop: -u(8), background: ink, opacity: head >= m ? 1 : 0.5, transform: 'rotate(45deg)'}} />
        ))}
        <div style={{position: 'absolute', left: `${head * 100}%`, top: 0, bottom: 0, width: u(5), marginLeft: -u(2.5), background: style.colors.accent, boxShadow: `0 0 ${u(12)}px ${style.colors.accent}`}} />
      </div>
      {labels ? (
        <div style={{display: 'flex', justifyContent: 'space-between', opacity: 0.75, marginTop: u(4)}}>
          <span>{left ?? ''}</span>
          <span>{right ?? ''}</span>
        </div>
      ) : null}
    </div>
  );
};

export type ReadoutRow = {label: string; value: string};

/**
 * Rows of `LABEL ...... value`. Each row slides in `step` seconds after the one before; its value
 * types out. Labels are dim, values full strength; a row listed in `hot` is drawn in the accent colour.
 */
export const Readout = ({
  rows,
  color,
  hotColor,
  hot = [],
  size = 28,
  font = 'mono',
  at = 0,
  step = 0.18,
  title,
  width = 520,
  opacity = 1,
  ...pin
}: TextLook &
  Pin & {
    rows: ReadoutRow[];
    /** Colour of the rows in `hot`. Default: the style's accent. */
    hotColor?: string;
    /** Row numbers drawn in the hot colour. */
    hot?: number[];
    step?: number;
    title?: string;
    /** Design px. */
    width?: number;
  }) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const face = useFace(font);
  const t = useT();
  const head = useIn(at);
  const ink = color ?? style.colors.text;
  const accent = hotColor ?? style.colors.accent;
  const shown = (text: string, k: number) => text.slice(0, Math.ceil(text.length * clamp(k)));
  return (
    <div style={place(pin, {width: u(width), fontFamily: face.css, fontWeight: face.weight, fontSize: fs(size), color: ink, opacity, borderLeft: `${u(4)}px solid ${ink}`, paddingLeft: u(16), lineHeight: 1.35})}>
      {title ? <div style={{opacity: 0.7 * head, letterSpacing: u(3), marginBottom: u(6)}}>{title}</div> : null}
      {rows.map((row, i) => {
        const start = at + (title ? step : 0) + i * step;
        const p = eOut(seg(t, start, start + 0.3));
        const tint = hot.includes(i) ? accent : ink;
        return (
          <div key={i} style={{display: 'flex', justifyContent: 'space-between', gap: u(16), opacity: p, transform: `translateX(${(1 - p) * -u(24)}px)`}}>
            <span style={{opacity: 0.65}}>{row.label}</span>
            <span style={{color: tint, fontVariantNumeric: 'tabular-nums'}}>{shown(row.value, seg(t, start + 0.1, start + 0.6))}</span>
          </div>
        );
      })}
    </div>
  );
};

/** A news-style strip of `items` that scrolls sideways at `speed` design px per second. */
export const Ticker = ({
  items,
  color,
  fill: plate,
  size = 28,
  font = 'body',
  at = 0,
  speed = 160,
  separator = '   //   ',
  width = 100,
  opacity = 1,
  ...pin
}: TextLook &
  Pin & {
    items: string[];
    /** Strip colour behind the text. Default: none. */
    fill?: string;
    speed?: number;
    separator?: string;
    /** Percent of the parent. */
    width?: number;
  }) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const {width: frameW} = useVideoConfig();
  const face = useFace(font);
  const t = useT();
  const p = useIn(at);
  const ready = useFontsReady();
  const ink = color ?? style.colors.text;
  const unit = items.join(separator) + separator;
  const unitW = Math.max(1, measureTextWidth(unit, face.css, face.weight, fs(size), 0));
  const copies = Math.ceil(frameW / unitW) + 2;
  const shift = ((Math.max(0, t - at) * u(speed)) % unitW) || 0;
  void ready;
  return (
    <div style={place(pin, {width: `${width}%`, overflow: 'hidden', background: plate, opacity: opacity * p, padding: `${u(8)}px 0`})}>
      <div style={{display: 'flex', whiteSpace: 'pre', width: 'max-content', transform: `translateX(${-shift}px)`, fontFamily: face.css, fontWeight: face.weight, fontSize: fs(size), color: ink, letterSpacing: u(1)}}>
        {Array.from({length: copies}, (_, i) => (
          <span key={i}>{unit}</span>
        ))}
      </div>
    </div>
  );
};

/** A rounded status tag with a blinking dot: `LIVE`, `ANALYSING`, `ONLINE`. `solid` fills it instead of outlining. */
export const StatusPill = ({
  children,
  color,
  size = 28,
  font = 'mono',
  at = 0,
  dot = true,
  solid = false,
  blink = 1.2,
  opacity = 1,
  ...pin
}: TextLook & Pin & {children?: ReactNode; dot?: boolean; solid?: boolean; /** Dot blinks per second, 0 = steady. */ blink?: number}) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const face = useFace(font);
  const t = useT();
  const p = useIn(at);
  const ink = color ?? style.colors.accent;
  const on = blink <= 0 || pulse(t, blink) > 0.3;
  return (
    <div
      style={place(pin, {
        display: 'inline-flex',
        alignItems: 'center',
        gap: u(12),
        padding: `${u(8)}px ${u(20)}px`,
        borderRadius: u(999),
        border: `${u(3)}px solid ${ink}`,
        background: solid ? ink : 'transparent',
        color: solid ? style.colors.bg : ink,
        fontFamily: face.css,
        fontWeight: face.weight,
        fontSize: fs(size),
        letterSpacing: u(2),
        opacity: opacity * p,
        transform: `${place(pin).transform ?? ''} scale(${lerp(0.8, 1, p)})`.trim(),
        whiteSpace: 'nowrap',
      })}
    >
      {dot ? <span style={{width: u(size * 0.45), height: u(size * 0.45), borderRadius: '50%', background: solid ? style.colors.bg : ink, opacity: on ? 1 : 0.2}} /> : null}
      <span>{children}</span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// The layer
// ---------------------------------------------------------------------------

/**
 * Several HUD blocks placed around the safe area in one go: corner brackets and ruler ticks at the
 * edges, timecode and pills along the top, a readout, ticker and scrubber stacked along the bottom,
 * a scan line and a reticle over the picture. Switch each on by its prop; a prop that is left out
 * draws nothing. Put it above the scene's main element. For another arrangement, use the blocks directly.
 */
export const HudLayer = ({
  color,
  accent,
  size = 1,
  at = 0,
  brackets = true,
  ticks = false,
  timecode: tc = false,
  rec = false,
  pills = [],
  readout,
  ticker,
  scrubber = false,
  scan = false,
  crosshair = false,
  opacity = 1,
}: {
  color?: string;
  /** Colour of the scan line, reticle and playhead. Default: the style's accent. */
  accent?: string;
  /** Scales the text and details (1 = normal). */
  size?: number;
  at?: number;
  brackets?: boolean;
  ticks?: boolean;
  /** `true` or the label before the clock (`'CAM 2'`). */
  timecode?: boolean | string;
  rec?: boolean;
  /** Tags stacked in the top-right corner. */
  pills?: string[];
  readout?: ReadoutRow[];
  /** Strip texts scrolling along the bottom. */
  ticker?: string[];
  scrubber?: boolean;
  scan?: boolean;
  crosshair?: boolean | {x?: number; y?: number; to?: [number, number]};
  opacity?: number;
}) => {
  const style = useStyle();
  const {safe, u} = useLayout();
  const ink = color ?? style.colors.text;
  const hot = accent ?? style.colors.accent;
  const s = (n: number) => n * size;
  const cross = typeof crosshair === 'object' ? crosshair : {};
  return (
    <AbsoluteFill style={{...fill, opacity}}>
      {ticks ? <FrameTicks color={ink} at={at} /> : null}
      <div style={{position: 'absolute', left: safe.left, top: safe.top, width: safe.width, height: safe.height, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', ...fill}}>
        {brackets ? <CornerBrackets color={ink} size={s(80)} thickness={s(5)} at={at} /> : null}
        {scan ? <ScanLine color={hot} at={at} /> : null}
        {crosshair ? <Crosshair color={hot} size={s(170)} x={cross.x} y={cross.y} to={cross.to} at={at + 0.3} /> : null}
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: `${u(s(24))}px`, gap: u(12)}}>
          <div style={{display: 'flex', flexDirection: 'column', gap: u(s(10))}}>
            {tc || rec ? <Timecode color={ink} size={s(32)} at={at} rec={rec} label={typeof tc === 'string' ? tc : tc ? 'TC' : ''} /> : null}
          </div>
          <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: u(s(10))}}>
            {pills.map((text, i) => (
              <StatusPill key={i} color={i === 0 ? hot : ink} size={s(26)} at={at + 0.15 * i}>
                {text}
              </StatusPill>
            ))}
          </div>
        </div>
        <div style={{display: 'flex', flexDirection: 'column', gap: u(s(14)), padding: `${u(s(24))}px`}}>
          {readout ? <Readout rows={readout} color={ink} hotColor={hot} size={s(26)} width={s(520)} at={at + 0.2} /> : null}
          {ticker ? <Ticker items={ticker} color={ink} size={s(26)} at={at} /> : null}
          {scrubber ? <Scrubber color={ink} size={s(22)} at={at} /> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

import type {CSSProperties, ReactNode} from 'react';
import {interpolateColors} from 'remotion';
import {fontFor, useLayout, useStyle, withAlpha} from '../style';
import {eBack, eOut, formatNumber, lerp, pulse as pulseWave, seg} from './motion';
import {Text, readableOn} from './text';
import {useT} from './timing';
import {Slide} from './wrappers';

// Information blocks: numbers, plates, pop-ups, polls, lists, bars, bubbles, cards.
// Sizes are design px (1080 short side). Times are seconds on the scene's clock.

/** The style's own panel look: translucent background colour with the style's card border. */
const usePanel = () => {
  const style = useStyle();
  return {
    fill: withAlpha(style.colors.bg, 0.9),
    border: style.colors.cardBorder,
    shadow: `0 ${style.isDark ? 12 : 8}px ${style.isDark ? 36 : 24}px rgba(0, 0, 0, ${style.isDark ? 0.45 : 0.14})`,
  };
};

// ---------------------------------------------------------------------------

/** A box with the style's card look. */
export const Card = ({
  children,
  width,
  padding = 32,
  radius = 32,
  fill,
  border,
  borderWidth = 3,
  style: extra,
}: {
  children?: ReactNode;
  /** Design px; default: wraps its content. */
  width?: number;
  padding?: number;
  radius?: number;
  /** Any CSS colour. Default: the style's background, slightly see-through. */
  fill?: string;
  /** Default: the style's card border colour. */
  border?: string;
  borderWidth?: number;
  style?: CSSProperties;
}) => {
  const {u} = useLayout();
  const panel = usePanel();
  return (
    <div
      style={{
        boxSizing: 'border-box',
        width: width ? u(width) : undefined,
        padding: u(padding),
        borderRadius: u(radius),
        background: fill ?? panel.fill,
        border: `${u(borderWidth)}px solid ${border ?? panel.border}`,
        boxShadow: panel.shadow,
        ...extra,
      }}
    >
      {children}
    </div>
  );
};

// ---------------------------------------------------------------------------

/** A number that counts from `from` to `to` between `start` and `start + dur`. */
export const Counter = ({
  to,
  from = 0,
  start = 0,
  dur = 1.2,
  decimals = 0,
  prefix = '',
  suffix = '',
  sep = '\u00A0',
  format,
  size = 120,
  color,
  font = 'display',
  stroke = 0,
  glow = 0,
}: {
  to: number;
  from?: number;
  start?: number;
  dur?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  /** Thousands separator. Default: a no-break space. */
  sep?: string;
  /** Your own formatting; replaces `decimals`, `sep`, `prefix` and `suffix`. */
  format?: (n: number) => string;
  size?: number;
  color?: string;
  font?: 'display' | 'heading' | 'body' | 'mono';
  stroke?: number;
  glow?: number;
}) => {
  const t = useT();
  const n = lerp(from, to, eOut(seg(t, start, start + dur)));
  const shown = format ? format(n) : `${prefix}${formatNumber(n, decimals, sep)}${suffix}`;
  return (
    <Text size={size} color={color} font={font} stroke={stroke} glow={glow} style={{fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap'}}>
      {shown}
    </Text>
  );
};

// ---------------------------------------------------------------------------

export type PlateChange = {
  /** Seconds when the change starts. */
  at: number;
  /** The frame and value colour from now on. */
  color?: string;
  /** The value shown from now on. */
  value?: string;
};

/**
 * A bordered HUD plate: small label above a value. `changes` swap the value and/or fade the frame
 * colour at given times; `alert` makes it flash between `from` and `to`.
 */
export const Plate = ({
  label,
  value,
  color,
  width = 316,
  changes = [],
  alert,
  size = 54,
}: {
  label: string;
  value: string;
  /** Frame and value colour. Default: the style's accent. */
  color?: string;
  width?: number;
  changes?: PlateChange[];
  /** Flashing window: the frame and a wash turn to `color` and back, `hz` times a second. */
  alert?: {from: number; to: number; color: string; hz?: number};
  /** Value size, design px. */
  size?: number;
}) => {
  const style = useStyle();
  const {u, fs} = useLayout();
  const panel = usePanel();
  const t = useT();
  const ordered = [...changes].sort((a, b) => a.at - b.at);
  let tone = color ?? style.colors.accent;
  let shown = value;
  for (const c of ordered) {
    if (t >= c.at) {
      if (c.color) {
        tone = interpolateColors(seg(t, c.at, c.at + 0.3), [0, 1], [tone, c.color]);
      }
      if (c.value !== undefined) {
        shown = c.value;
      }
    }
  }
  const flash = alert && t >= alert.from && t <= alert.to ? pulseWave(t, alert.hz ?? 2, alert.from) : 0;
  const frame = alert && flash > 0 ? interpolateColors(flash, [0, 1], [tone, alert.color]) : tone;
  return (
    <div
      style={{
        position: 'relative',
        boxSizing: 'border-box',
        width: u(width),
        padding: `${u(14)}px ${u(16)}px ${u(18)}px`,
        borderRadius: u(26),
        background: panel.fill,
        border: `${u(5)}px solid ${frame}`,
        boxShadow: panel.shadow,
        textAlign: 'center',
        overflow: 'hidden',
      }}
    >
      {alert ? <div style={{position: 'absolute', inset: 0, background: alert.color, opacity: 0.4 * flash}} /> : null}
      <div style={{position: 'relative'}}>
        <Text size={24} color={style.colors.muted} font="body" weight={800} caps spacing={1.5}>
          {label}
        </Text>
        <Text size={size} color={frame} font="mono" style={{whiteSpace: 'nowrap'}}>
          {shown}
        </Text>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------

/**
 * A pop-up for a change: a signed number (or text) with a small label under it. It slides in at
 * `at`, stays `hold` seconds and leaves. Colour: `positive` for a rise, `negative` for a fall.
 */
export const Delta = ({
  value,
  label,
  at = 0,
  hold = 1.6,
  size = 72,
  positive,
  negative,
  sep = '\u00A0',
}: {
  value: number | string;
  label?: string;
  at?: number;
  hold?: number;
  size?: number;
  /** Colour of a rise. Default: the style's `positive` colour, else its accent. */
  positive?: string;
  /** Colour of a fall. Default: the style's `negative` colour, else a red. */
  negative?: string;
  sep?: string;
}) => {
  const style = useStyle();
  const rising = typeof value === 'number' ? value >= 0 : !value.trim().startsWith('-');
  const tone = rising ? positive ?? style.colors.positive ?? style.colors.accent : negative ?? style.colors.negative ?? '#FF4D5E';
  const text = typeof value === 'number' ? `${value >= 0 ? '+' : '\u2212'}${formatNumber(Math.abs(value), 0, sep)}` : value;
  return (
    <Slide from={at} to={at + hold} side="bottom" dist={60} dur={0.35} outDur={0.4}>
      <Card padding={22} radius={26} border={tone} borderWidth={4} style={{textAlign: 'center'}}>
        <Text size={size} color={tone} style={{whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums'}}>
          {text}
        </Text>
        {label ? (
          <Text size={Math.round(size * 0.36)} font="body" weight={800} caps spacing={1.5} color={style.colors.muted}>
            {label}
          </Text>
        ) : null}
      </Card>
    </Slide>
  );
};

// ---------------------------------------------------------------------------

export type PollOption = {
  label: string;
  /** 0..1. */
  share: number;
  /** Bar colour. Default: the style's accent. */
  color?: string;
};

/** A poll result card: one row per option, bars fill one after another. */
export const PollCard = ({
  title,
  options,
  at = 0,
  fillDur = 1,
  step = 0.2,
  pick,
  width = 860,
}: {
  title?: string;
  options: PollOption[];
  /** Seconds when the first bar starts to fill. */
  at?: number;
  fillDur?: number;
  /** Delay between rows. */
  step?: number;
  /** Index of the option to mark as the chosen one (bright frame, others dimmed). */
  pick?: number;
  width?: number;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  return (
    <Card width={width} padding={36}>
      {title ? (
        <Text size={44} align="left" style={{marginBottom: u(22)}}>
          {title}
        </Text>
      ) : null}
      <div style={{display: 'flex', flexDirection: 'column', gap: u(18)}}>
        {options.map((o, i) => {
          const p = eOut(seg(t, at + i * step, at + i * step + fillDur));
          const tone = o.color ?? style.colors.accent;
          const chosen = pick === undefined || pick === i;
          return (
            <div key={i} style={{opacity: chosen ? 1 : 0.5}}>
              <div style={{display: 'flex', justifyContent: 'space-between'}}>
                <Text size={34} font="body" weight={800} align="left">
                  {o.label}
                </Text>
                <Text size={34} font="mono" style={{fontVariantNumeric: 'tabular-nums'}}>
                  {Math.round(o.share * 100 * p)}%
                </Text>
              </div>
              <div
                style={{
                  marginTop: u(8),
                  height: u(26),
                  borderRadius: u(13),
                  background: withAlpha(style.colors.text, 0.12),
                  overflow: 'hidden',
                  outline: pick === i ? `${u(4)}px solid ${tone}` : undefined,
                  outlineOffset: u(3),
                }}
              >
                <div style={{width: `${Math.min(1, Math.max(0, o.share)) * 100 * p}%`, height: '100%', background: tone, borderRadius: u(13)}} />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

// ---------------------------------------------------------------------------

export type CheckItem = string | {text: string; /** Seconds when the tick is drawn. Default: shortly after the row appears. */ at?: number};

/** A list whose rows appear one after another; each gets a tick drawn at its own time. */
export const Checklist = ({
  items,
  at = 0,
  step = 0.7,
  size = 46,
  color,
  width = 760,
}: {
  items: CheckItem[];
  /** Seconds when the first row appears. */
  at?: number;
  /** Delay between rows. */
  step?: number;
  size?: number;
  /** Tick colour. Default: the style's accent. */
  color?: string;
  width?: number;
}) => {
  const style = useStyle();
  const {u, fs} = useLayout();
  const t = useT();
  const tone = color ?? style.colors.accent;
  const box = fs(size * 1.1);
  return (
    <Card width={width} padding={34}>
      <div style={{display: 'flex', flexDirection: 'column', gap: u(22)}}>
        {items.map((item, i) => {
          const text = typeof item === 'string' ? item : item.text;
          const rowAt = at + i * step;
          const tickAt = typeof item === 'string' || item.at === undefined ? rowAt + 0.4 : item.at;
          const tick = eBack(seg(t, tickAt, tickAt + 0.3));
          return (
            <Slide key={i} from={rowAt} dur={0.35} dist={40} side="left" keepSpace>
              <div style={{display: 'flex', alignItems: 'center', gap: u(24)}}>
                <svg width={box} height={box} viewBox="0 0 24 24" style={{flex: 'none'}}>
                  <rect x="1.5" y="1.5" width="21" height="21" rx="6" fill="none" stroke={style.colors.muted} strokeWidth="2" />
                  <path
                    d="M 6 12.5 L 10.5 17 L 18.5 7"
                    fill="none"
                    stroke={tone}
                    strokeWidth="3.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    pathLength={1}
                    strokeDasharray={1}
                    strokeDashoffset={1 - Math.min(1, tick)}
                  />
                </svg>
                <Text size={size} font="body" weight={700} align="left">
                  {text}
                </Text>
              </div>
            </Slide>
          );
        })}
      </div>
    </Card>
  );
};

// ---------------------------------------------------------------------------

/** A horizontal bar that fills to `value` (0..1) between `at` and `at + dur`. */
export const ProgressBar = ({
  value = 1,
  at = 0,
  dur = 1,
  label,
  width = 760,
  height = 28,
  color,
  showValue = false,
}: {
  value?: number;
  at?: number;
  /** 0 shows the final value at once. */
  dur?: number;
  label?: string;
  width?: number;
  height?: number;
  /** Fill colour. Default: the style's accent. */
  color?: string;
  /** Shows the percentage on the right. */
  showValue?: boolean;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const t = useT();
  const p = dur > 0 ? eOut(seg(t, at, at + dur)) : 1;
  const filled = Math.min(1, Math.max(0, value)) * p;
  return (
    <div style={{width: u(width)}}>
      {label || showValue ? (
        <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: u(8)}}>
          <Text size={32} font="body" weight={800} align="left">
            {label ?? ''}
          </Text>
          {showValue ? (
            <Text size={32} font="mono" style={{fontVariantNumeric: 'tabular-nums'}}>
              {Math.round(filled * 100)}%
            </Text>
          ) : null}
        </div>
      ) : null}
      <div style={{height: u(height), borderRadius: u(height / 2), background: withAlpha(style.colors.text, 0.14), overflow: 'hidden'}}>
        <div style={{width: `${filled * 100}%`, height: '100%', borderRadius: u(height / 2), background: color ?? style.colors.accent}} />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------

/** A speech bubble. `tail` is the side the pointer sticks out of, `tailAt` where along that side (0..1). */
export const Bubble = ({
  children,
  tail = 'bottom',
  tailAt = 0.3,
  size = 46,
  fill,
  color,
  maxWidth = 700,
}: {
  children?: ReactNode;
  tail?: 'bottom' | 'top' | 'left' | 'right';
  tailAt?: number;
  size?: number;
  /** Default: the style's text colour (a light bubble on a dark style). */
  fill?: string;
  /** Default: the style's background colour. */
  color?: string;
  maxWidth?: number;
}) => {
  const style = useStyle();
  const {u, fs} = useLayout();
  const plate = fill ?? style.colors.text;
  const ink = color ?? (fill ? readableOn(fill) : style.colors.bg);
  const tip = fs(size * 0.55);
  const along = `${Math.min(0.9, Math.max(0.1, tailAt)) * 100}%`;
  const place: CSSProperties =
    tail === 'bottom'
      ? {left: along, bottom: -tip / 2}
      : tail === 'top'
        ? {left: along, top: -tip / 2}
        : tail === 'left'
          ? {top: along, left: -tip / 2}
          : {top: along, right: -tip / 2};
  return (
    <div
      style={{
        position: 'relative',
        display: 'inline-block',
        maxWidth: u(maxWidth),
        padding: `${fs(size * 0.4)}px ${fs(size * 0.7)}px`,
        borderRadius: fs(size * 0.6),
        background: plate,
        boxShadow: `0 ${u(8)}px ${u(20)}px rgba(0, 0, 0, 0.3)`,
      }}
    >
      <div style={{position: 'absolute', width: tip, height: tip, background: plate, transform: 'rotate(45deg)', marginLeft: -tip / 2, ...place}} />
      <div style={{position: 'relative', fontFamily: fontFor(style, 'body').css, fontWeight: 800, fontSize: fs(size), lineHeight: 1.15, color: ink, textAlign: 'center'}}>
        {children}
      </div>
    </div>
  );
};

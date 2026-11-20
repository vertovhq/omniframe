import {useId} from 'react';
import type {CSSProperties, ReactNode} from 'react';
import {fontFor, useLayout, useStyle} from '../style';
import type {FontRole} from '../style';
import {clamp, eBack, eElastic, eInOut, eOut, lerp, pulse, seg} from './motion';
import {useT} from './timing';

// The kinetic type group: text that arrives with a move (slams, drops, stretches, types, swaps,
// follows a curve), with key words boxed or marked. All of it takes the style's fonts and colours
// unless a prop says otherwise; sizes are design px (1080 short side). Times are seconds on the
// scene's clock. In `WordSlam` and `LetterCascade` text, a word between asterisks is a key word.

export type TypeLook = {
  /** Design px. */
  size?: number;
  /** Any CSS colour. Default: the style's text colour. */
  color?: string;
  font?: FontRole;
  weight?: number;
  caps?: boolean;
  align?: 'left' | 'center' | 'right';
  /** Outline in design px, in the style's background colour. */
  stroke?: number;
  /** Drop shadow blur, design px. */
  shadow?: number;
  /** Letter spacing, design px. */
  spacing?: number;
  lineHeight?: number;
  /** Design px; longer text wraps. */
  maxWidth?: number;
};

/** The CSS of a text look, for the spans the blocks here draw. */
const useLook = (look: TypeLook): CSSProperties => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const face = fontFor(style, look.font ?? 'display');
  return {
    fontFamily: face.css,
    fontWeight: look.weight ?? face.weight,
    fontSize: fs(look.size ?? 120),
    lineHeight: look.lineHeight ?? 1.05,
    color: look.color ?? style.colors.text,
    textAlign: look.align ?? 'center',
    textTransform: look.caps ? 'uppercase' : undefined,
    letterSpacing: look.spacing ? u(look.spacing) : undefined,
    maxWidth: look.maxWidth ? u(look.maxWidth) : undefined,
    WebkitTextStroke: look.stroke ? `${u(look.stroke)}px ${style.colors.bg}` : undefined,
    paintOrder: 'stroke fill',
    textShadow: look.shadow ? `0 ${u(look.shadow * 0.5)}px ${u(look.shadow)}px rgba(0, 0, 0, ${style.isDark ? 0.55 : 0.3})` : undefined,
  };
};

const HEX6 = /^#[0-9a-f]{6}$/i;

/** Black or white text for a plate of this hex colour; the style's background colour for other colour forms. */
const inkOn = (plate: string, bg: string, given?: string): string => {
  if (given) {
    return given;
  }
  if (!HEX6.test(plate)) {
    return bg;
  }
  const n = parseInt(plate.slice(1), 16);
  const luma = 0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255);
  return luma > 150 ? '#0A0A12' : '#FFFFFF';
};

// ---------------------------------------------------------------------------
// Marked words
// ---------------------------------------------------------------------------

export type MarkMode = 'box' | 'highlight' | 'underline';

/**
 * Marks its children (a key word) from `at`: `box` draws a plate behind them that wipes in, with
 * the text turning to a colour that reads on it; `highlight` is a marker swipe over the lower
 * half; `underline` a line that grows below. The plate colour is `color` (default: the accent).
 */
export const Boxed = ({
  children,
  mode = 'box',
  color,
  textColor,
  at = 0,
  dur = 0.3,
  pad = 0.16,
  rotate = 0,
}: {
  children?: ReactNode;
  mode?: MarkMode;
  color?: string;
  /** Text colour once the box is in. Default: black or white, whichever reads on the plate. */
  textColor?: string;
  at?: number;
  dur?: number;
  /** Space around the text in `box` mode, as a fraction of the font size. */
  pad?: number;
  /** Degrees. */
  rotate?: number;
}) => {
  const style = useStyle();
  const t = useT();
  const p = eOut(seg(t, at, at + dur));
  const plate = color ?? style.colors.accent;
  const boxed = mode === 'box';
  const on = inkOn(plate, style.colors.bg, textColor);
  const shape: CSSProperties =
    mode === 'box'
      ? {inset: 0, borderRadius: '0.14em'}
      : mode === 'highlight'
        ? {left: '-0.05em', right: '-0.05em', top: '48%', bottom: '4%', opacity: 0.85}
        : {left: 0, right: 0, bottom: '-0.04em', height: '0.1em'};
  return (
    <span style={{position: 'relative', display: 'inline-block', padding: boxed ? `0 ${pad}em` : undefined, margin: boxed ? `0 ${-pad * 0.4}em` : undefined, transform: rotate ? `rotate(${rotate}deg)` : undefined}}>
      <span style={{position: 'absolute', background: plate, transformOrigin: 'left center', transform: `scaleX(${p})`, ...shape}} />
      <span style={{position: 'relative', color: boxed && p > 0.45 ? on : undefined}}>{children}</span>
    </span>
  );
};

// ---------------------------------------------------------------------------
// Words that slam in
// ---------------------------------------------------------------------------

type Entry = 'scale' | 'top' | 'bottom' | 'left' | 'right';

const ENTRY_VECTOR: Record<Exclude<Entry, 'scale'>, [number, number]> = {top: [0, -1], bottom: [0, 1], left: [-1, 0], right: [1, 0]};

const bare = (w: string) => w.replace(/[^\p{L}\p{N}]/gu, '').toLowerCase();

/** Splits `text` into words and flags the key ones (between asterisks, or listed in `accent`). */
const wordsOf = (text: string, accent: string[]): Array<{w: string; key: boolean}> =>
  text
    .split(/\s+/)
    .filter((w) => w !== '')
    .map((raw) => {
      const stars = (raw.match(/\*/g) ?? []).length >= 2;
      const w = raw.replace(/\*/g, '');
      return {w, key: stars || accent.some((a) => bare(a) !== '' && bare(a) === bare(w))};
    });

/**
 * A headline whose words slam in one after another, `step` seconds apart from `at`: each word comes
 * from `from` (scale: from big and drops to size; or from a side), with a small overshoot. Key words
 * (`*between asterisks*` or listed in `accent`) get a mark (`mark`). `skew` slants the whole line.
 */
export const WordSlam = ({
  text,
  at = 0,
  step = 0.2,
  from = 'scale',
  mark = 'box',
  markColor,
  markTextColor,
  accent = [],
  skew = 0,
  rotate = 0,
  gap = 0.22,
  ...look
}: TypeLook & {
  text: string;
  at?: number;
  step?: number;
  from?: Entry;
  mark?: MarkMode | 'none';
  markColor?: string;
  markTextColor?: string;
  /** Key words besides the starred ones. */
  accent?: string[];
  /** Degrees of horizontal slant (negative leans right). */
  skew?: number;
  rotate?: number;
  /** Space between words, fraction of the font size. */
  gap?: number;
}) => {
  const t = useT();
  const {u} = useLayout();
  const css = useLook({maxWidth: 980, ...look});
  const words = wordsOf(text, accent);
  return (
    <div style={{...css, display: 'flex', flexWrap: 'wrap', justifyContent: look.align === 'left' ? 'flex-start' : look.align === 'right' ? 'flex-end' : 'center', columnGap: `${gap}em`, rowGap: '0.04em', transform: `skewX(${skew}deg) rotate(${rotate}deg)`}}>
      {words.map(({w, key}, i) => {
        const start = at + i * step;
        const p = seg(t, start, start + 0.28);
        const land = eBack(p);
        const alpha = clamp(p * 4);
        let transform = `scale(${lerp(2.4, 1, land)})`;
        if (from !== 'scale') {
          const [vx, vy] = ENTRY_VECTOR[from];
          transform = `translate(${vx * u(260) * (1 - land)}px, ${vy * u(260) * (1 - land)}px) scale(${lerp(1.3, 1, land)})`;
        }
        const body = key && mark !== 'none' ? (
          <Boxed mode={mark} color={markColor} textColor={markTextColor} at={start + 0.1} dur={0.25}>
            {w}
          </Boxed>
        ) : (
          w
        );
        return (
          <span key={i} style={{display: 'inline-block', opacity: alpha, transform, transformOrigin: '50% 60%'}}>
            {body}
          </span>
        );
      })}
    </div>
  );
};

/** A slanted wrapper: `x` degrees of horizontal skew (negative leans right), `y` of vertical. With `fromX` the slant eases in over `dur` from `at`. */
export const Skew = ({
  x = -10,
  y = 0,
  fromX,
  at = 0,
  dur = 0.4,
  children,
}: {
  x?: number;
  y?: number;
  fromX?: number;
  at?: number;
  dur?: number;
  children?: ReactNode;
}) => {
  const t = useT();
  const angle = fromX === undefined ? x : lerp(fromX, x, eBack(seg(t, at, at + dur)));
  return <div style={{display: 'inline-block', transform: `skew(${angle}deg, ${y}deg)`}}>{children}</div>;
};

/**
 * Stretches its children into place from `at`: `scale` starts them `from` times too long along
 * `axis` and snaps back with a spring; `track` starts with wide letter spacing and closes up.
 */
export const Stretch = ({
  children,
  axis = 'x',
  kind = 'scale',
  from = 3,
  at = 0,
  dur = 0.55,
}: {
  children?: ReactNode;
  axis?: 'x' | 'y';
  kind?: 'scale' | 'track';
  from?: number;
  at?: number;
  dur?: number;
}) => {
  const t = useT();
  const p = seg(t, at, at + dur);
  const k = lerp(from, 1, eElastic(p));
  const style: CSSProperties =
    kind === 'track'
      ? {letterSpacing: `${lerp(from * 0.12, 0, eOut(p))}em`}
      : {transform: axis === 'x' ? `scaleX(${k})` : `scaleY(${k})`};
  return <div style={{display: 'inline-block', opacity: clamp(p * 5), whiteSpace: 'nowrap', ...style}}>{children}</div>;
};

/** Text whose letters drop in one by one, `step` seconds apart from `at`. `from` is where each letter comes from; stars mark key words as in `WordSlam`. */
export const LetterCascade = ({
  text,
  at = 0,
  step = 0.04,
  from = 'top',
  keyColor,
  ...look
}: TypeLook & {
  text: string;
  at?: number;
  step?: number;
  from?: 'top' | 'bottom' | 'scale' | 'spin';
  /** Colour of the letters of key words (starred). Default: the style's accent. */
  keyColor?: string;
}) => {
  const t = useT();
  const style = useStyle();
  const {u} = useLayout();
  const css = useLook({maxWidth: 980, ...look});
  const words = wordsOf(text, []);
  let n = 0;
  return (
    <div style={{...css, display: 'flex', flexWrap: 'wrap', justifyContent: look.align === 'left' ? 'flex-start' : look.align === 'right' ? 'flex-end' : 'center', columnGap: '0.28em'}}>
      {words.map(({w, key}, wi) => (
        <span key={wi} style={{display: 'inline-block', whiteSpace: 'nowrap', color: key ? keyColor ?? style.colors.accent : undefined}}>
          {Array.from(w).map((ch, ci) => {
            const start = at + n++ * step;
            const p = seg(t, start, start + 0.35);
            const e = eBack(p);
            const transform =
              from === 'scale'
                ? `scale(${lerp(0.2, 1, e)})`
                : from === 'spin'
                  ? `rotate(${lerp(-120, 0, e)}deg) scale(${lerp(0.4, 1, e)})`
                  : `translateY(${(from === 'top' ? -1 : 1) * u(130) * (1 - e)}px)`;
            return (
              <span key={ci} style={{display: 'inline-block', opacity: clamp(p * 4), transform}}>
                {ch}
              </span>
            );
          })}
        </span>
      ))}
    </div>
  );
};

/** Types `text` out from `at` at `cps` characters per second, with a blinking cursor (`\n` starts a new line). */
export const Typewriter = ({
  text,
  at = 0,
  cps = 22,
  cursor = true,
  cursorColor,
  blink = 1.6,
  ...look
}: TypeLook & {
  text: string;
  at?: number;
  cps?: number;
  cursor?: boolean;
  cursorColor?: string;
  /** Cursor blinks per second. */
  blink?: number;
}) => {
  const t = useT();
  const style = useStyle();
  const css = useLook({font: 'mono', size: 56, align: 'left', ...look});
  const chars = Array.from(text);
  const shown = Math.min(chars.length, Math.max(0, Math.floor((t - at) * cps)));
  const typing = shown < chars.length && t >= at;
  const on = typing || pulse(t, blink) > 0.35;
  return (
    <div style={{...css, whiteSpace: 'pre-wrap'}}>
      <span>{chars.slice(0, shown).join('')}</span>
      {cursor && t >= at - 0.2 ? (
        <span style={{display: 'inline-block', width: '0.55em', height: '1em', marginLeft: '0.08em', verticalAlign: '-0.12em', background: cursorColor ?? style.colors.accent, opacity: on ? 1 : 0}} />
      ) : null}
    </div>
  );
};

/**
 * One word that is replaced by the next in the same place: `words[0]` from `at`, then every `every`
 * seconds the next. The old word leaves and the new one enters (`slide` up, `pop` scale, `flip` around
 * a horizontal axis). The box is as wide as the widest word, so the text around it does not jump.
 */
export const WordSwap = ({
  words,
  at = 0,
  every = 0.7,
  kind = 'slide',
  colors,
  loop = false,
  ...look
}: TypeLook & {
  words: string[];
  at?: number;
  every?: number;
  kind?: 'slide' | 'pop' | 'flip';
  /** One colour per word. */
  colors?: string[];
  loop?: boolean;
}) => {
  const t = useT();
  const {u} = useLayout();
  const css = useLook(look);
  if (words.length === 0) {
    return null;
  }
  const raw = Math.floor((t - at) / every);
  const index = loop ? ((raw % words.length) + words.length) % words.length : Math.min(words.length - 1, raw);
  const into = seg(t - at - raw * every, 0, 0.22);
  const e = t < at ? 0 : eBack(into);
  const prev = loop ? (index + words.length - 1) % words.length : index - 1;
  const cell = (i: number): CSSProperties => ({gridArea: '1 / 1', whiteSpace: 'nowrap', color: colors?.[i] ?? css.color});
  return (
    <span style={{...css, display: 'inline-grid', justifyItems: 'center', alignItems: 'center'}}>
      {words.map((w, i) => {
        const base = cell(i);
        if (t < at) {
          return <span key={i} style={{...base, visibility: 'hidden'}}>{w}</span>;
        }
        if (i === index) {
          const enter =
            kind === 'pop' ? `scale(${lerp(0.4, 1, e)})` : kind === 'flip' ? `perspective(${u(900)}px) rotateX(${lerp(-90, 0, eOut(into))}deg)` : `translateY(${(1 - e) * u(60)}px)`;
          return (
            <span key={i} style={{...base, opacity: clamp(into * 3), transform: enter}}>
              {w}
            </span>
          );
        }
        if (i === prev && raw > 0 && into < 1) {
          const leave =
            kind === 'pop' ? `scale(${lerp(1, 1.6, into)})` : kind === 'flip' ? `perspective(${u(900)}px) rotateX(${lerp(0, 90, into)}deg)` : `translateY(${-eInOut(into) * u(60)}px)`;
          return (
            <span key={i} style={{...base, opacity: 1 - into, transform: leave}}>
              {w}
            </span>
          );
        }
        return <span key={i} style={{...base, visibility: 'hidden'}}>{w}</span>;
      })}
    </span>
  );
};

/**
 * Text that follows a curve. `path` is `'arc'` (a bend), `'wave'`, `'circle'` (round, turning at
 * `spin` percent of the length per second), or an SVG path in a `width` x `height` design-px box.
 * From `at` the text slides onto the curve over `dur`.
 */
export const PathText = ({
  text,
  path = 'arc',
  width = 900,
  height = 420,
  at = 0,
  dur = 0.9,
  spin = 8,
  ...look
}: TypeLook & {
  text: string;
  path?: 'arc' | 'wave' | 'circle' | string;
  width?: number;
  height?: number;
  at?: number;
  dur?: number;
  spin?: number;
}) => {
  const id = `pt${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const t = useT();
  const style = useStyle();
  const {u} = useLayout();
  const css = useLook({size: 90, ...look});
  const W = u(width);
  const H = u(height);
  const r = Math.min(W, H) * 0.42;
  const d =
    path === 'arc'
      ? `M ${W * 0.04} ${H * 0.9} Q ${W / 2} ${-H * 0.5} ${W * 0.96} ${H * 0.9}`
      : path === 'wave'
        ? `M ${W * 0.02} ${H / 2} C ${W * 0.2} ${-H * 0.1}, ${W * 0.3} ${H * 1.1}, ${W / 2} ${H / 2} S ${W * 0.8} ${-H * 0.1}, ${W * 0.98} ${H / 2}`
        : path === 'circle'
          ? `M ${W / 2 - r} ${H / 2} a ${r} ${r} 0 1 1 ${2 * r} 0 a ${r} ${r} 0 1 1 ${-2 * r} 0`
          : path;
  const p = eOut(seg(t, at, at + dur));
  const round = path === 'circle';
  const offset = round ? `${(Math.max(0, t - at) * spin) % 100}%` : `${lerp(100, 50, p)}%`;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{overflow: 'visible', opacity: clamp(p * 3)}}>
      <defs>
        <path id={id} d={d} fill="none" />
      </defs>
      <text
        style={{
          fontFamily: css.fontFamily,
          fontWeight: css.fontWeight,
          fontSize: css.fontSize,
          letterSpacing: css.letterSpacing,
          textTransform: css.textTransform,
          paintOrder: 'stroke fill',
          stroke: look.stroke ? style.colors.bg : undefined,
          strokeWidth: look.stroke ? u(look.stroke) : undefined,
        }}
        fill={css.color}
        textAnchor={round ? 'start' : 'middle'}
      >
        <textPath href={`#${id}`} startOffset={offset}>
          {text}
        </textPath>
      </text>
    </svg>
  );
};

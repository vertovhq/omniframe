import {useId} from 'react';
import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, Freeze, random, useCurrentFrame, useVideoConfig} from 'remotion';
import {useLayout, useStyle} from '../style';
import {Noise, Scanlines} from './backgrounds';
import {MotionBlur, RgbSplit, shakeOffset} from './fx';
import {clamp, eBack, eOut, lerp, seg} from './motion';
import {Label} from './text';
import {useT} from './timing';

// The energy kit: trailer-style hits and grades. Wrappers (`Shake`, `Snap`, `Stepped`, `Boil`,
// `Aberration`, `Vhs`, `FreezeStamp`) take the scene's picture as children and fill their parent;
// overlays (`Flash`, `FilmBurn`, `LensFlare`, `Burst`) go on top of it. `at` is a time in seconds
// on the scene's clock, usually `useCue('hit')`; most take a list for several hits. `strength` 1 is
// a normal hit, `dur` is how long it rings out, colours are any CSS colour.

type At = number | number[];

/** Seconds since the latest hit in `at` that is not after `t`, or null before the first one. */
const ageOf = (t: number, at: At | undefined): number | null => {
  let age: number | null = null;
  for (const a of at === undefined ? [] : Array.isArray(at) ? at : [at]) {
    if (t >= a && (age === null || t - a < age)) {
      age = t - a;
    }
  }
  return age;
};

const fillStyle = (extra?: CSSProperties): CSSProperties => ({pointerEvents: 'none', ...extra});

/**
 * Shakes the children. `kind='impact'`: a hit at each `at` that rings out over `dur` (jolt, spin
 * and a small zoom punch). `kind='camera'`: a continuous handheld wobble from `at` for `dur`
 * (default: to the end of the scene). `every` holds each jolt for that many frames (2 = on twos).
 */
export const Shake = ({
  at = 0,
  dur,
  strength = 1,
  kind = 'impact',
  zoom = 0.04,
  every = 1,
  seed = 'shake',
  children,
}: {
  at?: At;
  dur?: number;
  strength?: number;
  kind?: 'impact' | 'camera';
  /** Impact: zoom punch at the moment of the hit (0.04 = 4 %). */
  zoom?: number;
  every?: number;
  seed?: string;
  children?: ReactNode;
}) => {
  const t = useT();
  const {fps} = useVideoConfig();
  const {u} = useLayout();
  const age = ageOf(t, at);
  const len = dur ?? (kind === 'camera' ? Infinity : 0.5);
  let transform: string | undefined;
  if (age !== null && age < len) {
    if (kind === 'camera') {
      // smooth: blend between two random poses 12 times a second
      const k = (t * 12) / Math.max(1, every);
      const i = Math.floor(k);
      const a = shakeOffset(i, seed, u(14) * strength);
      const b = shakeOffset(i + 1, seed, u(14) * strength);
      const m = k - i;
      const ease = Number.isFinite(len) ? Math.min(1, seg(age, 0, 0.15), 1 - seg(age, len - 0.15, len)) : 1;
      transform = `translate(${lerp(a.x, b.x, m) * ease}px, ${lerp(a.y, b.y, m) * ease}px) rotate(${lerp(a.rot, b.rot, m) * ease}deg) scale(1.03)`;
    } else {
      const p = age / len;
      const o = shakeOffset(Math.round(t * fps), seed, u(36) * strength * (1 - p) ** 2, every);
      transform = `translate(${o.x}px, ${o.y}px) rotate(${o.rot}deg) scale(${1 + zoom * strength * (1 - p) ** 3})`;
    }
  }
  return <AbsoluteFill style={{transform}}>{children}</AbsoluteFill>;
};

/**
 * Plays the children on twos: their clock moves only `fps` times a second (12 = animation on
 * twos at 24 fps), so everything inside steps instead of gliding.
 */
export const Stepped = ({fps = 12, children}: {fps?: number; children?: ReactNode}) => {
  const frame = useCurrentFrame();
  const {fps: base} = useVideoConfig();
  const n = Math.max(1, Math.round(base / Math.max(1, fps)));
  return (
    <AbsoluteFill>
      <Freeze frame={Math.floor(frame / n) * n}>{children}</Freeze>
    </AbsoluteFill>
  );
};

/** Hand-drawn wobble: the outlines of the children waver and re-draw `fps` times a second, cycling `frames` patterns. */
export const Boil = ({
  strength = 1,
  fps = 10,
  frames = 3,
  scale = 1,
  seed = 'boil',
  children,
}: {
  /** 0 keeps the picture still; 1 is a visible wobble. */
  strength?: number;
  fps?: number;
  /** Number of different wobble patterns that repeat. */
  frames?: number;
  /** Size of the wobble: bigger is coarser. */
  scale?: number;
  seed?: string;
  children?: ReactNode;
}) => {
  const id = `boil${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const t = useT();
  const {u, scale: px} = useLayout();
  const step = Math.floor(t * fps) % Math.max(1, Math.round(frames));
  const pattern = 1 + Math.floor(random(`${seed}-${step}`) * 9000);
  const on = strength > 0;
  return (
    <AbsoluteFill style={{filter: on ? `url(#${id})` : undefined}}>
      {on ? (
        <svg width="0" height="0" style={{position: 'absolute'}}>
          <filter id={id} x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
            <feTurbulence type="turbulence" baseFrequency={0.012 / Math.max(0.1, scale) / px} numOctaves={2} seed={pattern} result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale={u(12) * strength} xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </svg>
      ) : null}
      {children}
    </AbsoluteFill>
  );
};

/**
 * A punch on a cue: at each `at` the children jump `dist` design px from `dir` (and zoom by
 * `zoom`), then snap back to rest with a motion-blur smear. `appear` keeps them hidden until the first hit.
 */
export const Snap = ({
  at,
  dur = 0.3,
  dist = 140,
  dir = 'right',
  zoom = 0.12,
  strength = 1,
  appear = false,
  children,
}: {
  at: At;
  dur?: number;
  dist?: number;
  /** The side the children come in from; 'none' only zooms. */
  dir?: 'left' | 'right' | 'top' | 'bottom' | 'none';
  zoom?: number;
  strength?: number;
  appear?: boolean;
  children?: ReactNode;
}) => {
  const t = useT();
  const {u} = useLayout();
  const age = ageOf(t, at);
  if (age === null) {
    return <AbsoluteFill style={appear ? {visibility: 'hidden'} : undefined}>{children}</AbsoluteFill>;
  }
  const k = age < dur ? 1 - eOut(age / dur) : 0;
  const [vx, vy] = dir === 'left' ? [-1, 0] : dir === 'right' ? [1, 0] : dir === 'top' ? [0, -1] : dir === 'bottom' ? [0, 1] : [0, 0];
  const smear = u(70) * strength * k ** 1.5;
  return (
    <MotionBlur
      x={dir === 'none' || vx !== 0 ? smear : 0}
      y={dir === 'none' || vy !== 0 ? smear : 0}
      style={{transform: `translate(${vx * u(dist) * strength * k}px, ${vy * u(dist) * strength * k}px) scale(${1 + zoom * strength * k})`}}
    >
      {children}
    </MotionBlur>
  );
};

/**
 * Montage burst: from `at` for `dur` seconds, shows `items` one after another, `rate` per second
 * (images, clips, anything), then goes away. `loop` repeats the list; otherwise the last item holds.
 */
export const Burst = ({
  items,
  at = 0,
  dur = 0.6,
  rate = 12,
  loop = true,
}: {
  items: ReactNode[];
  at?: number;
  dur?: number;
  rate?: number;
  loop?: boolean;
}) => {
  const age = useT() - at;
  if (age < 0 || age >= dur || items.length === 0) {
    return null;
  }
  const raw = Math.floor(age * rate);
  const i = loop ? raw % items.length : Math.min(items.length - 1, raw);
  return <AbsoluteFill key={i}>{items[i]}</AbsoluteFill>;
};

/**
 * A flash frame: a full-frame colour at each `at` that fades out over `dur` (after holding at full
 * for `hold` seconds, e.g. one frame). `invert` flips the picture's colours instead of covering it.
 */
export const Flash = ({
  at,
  dur = 0.25,
  hold = 0,
  color = '#FFFFFF',
  strength = 1,
  invert = false,
}: {
  at: At;
  dur?: number;
  hold?: number;
  color?: string;
  strength?: number;
  invert?: boolean;
}) => {
  const age = ageOf(useT(), at);
  if (age === null || age >= dur + hold) {
    return null;
  }
  const alpha = Math.min(1, strength) * (age < hold ? 1 : (1 - (age - hold) / Math.max(0.001, dur)) ** 2);
  return <AbsoluteFill style={fillStyle({background: invert ? '#FFFFFF' : color, opacity: alpha, mixBlendMode: invert ? 'difference' : undefined})} />;
};

/** Chromatic aberration: red and blue split apart on each `at` and settle over `dur`. Without `at` it is a constant split. */
export const Aberration = ({
  at,
  dur = 0.4,
  strength = 1,
  angle = 0,
  children,
}: {
  at?: At;
  dur?: number;
  strength?: number;
  angle?: number;
  children?: ReactNode;
}) => {
  const t = useT();
  const {u} = useLayout();
  const age = ageOf(t, at);
  const k = at === undefined ? 0.35 : age === null || age >= dur ? 0 : (1 - age / dur) ** 2;
  return (
    <RgbSplit amount={u(26) * strength * k} angle={angle}>
      {children}
    </RgbSplit>
  );
};

/**
 * Film burn: warm light floods in from `side` over `dur`, peaks, and burns out, like a camera
 * running out of film. `colors` go from the deep edge to the white-hot core.
 */
export const FilmBurn = ({
  at,
  dur = 1,
  colors = ['#FF4A1C', '#FFA52E', '#FFF0B3'],
  strength = 1,
  side = 'left',
  seed = 'burn',
}: {
  at: At;
  dur?: number;
  colors?: string[];
  strength?: number;
  side?: 'left' | 'right' | 'top' | 'bottom';
  seed?: string;
}) => {
  const age = ageOf(useT(), at);
  const {u} = useLayout();
  if (age === null || age >= dur) {
    return null;
  }
  const p = age / dur;
  const env = Math.sin(Math.PI * p) ** 1.4 * Math.min(1, strength);
  const [vx, vy] = side === 'left' ? [0, 0.5] : side === 'right' ? [1, 0.5] : side === 'top' ? [0.5, 0] : [0.5, 1];
  const list = colors.length > 0 ? colors : ['#FFA52E'];
  const core = list[list.length - 1];
  return (
    <AbsoluteFill style={fillStyle({mixBlendMode: 'screen', overflow: 'hidden', opacity: env})}>
      {list.map((c, i) => {
        const r = (k: string) => random(`${seed}-${k}-${i}`);
        const d = u(1500 + 900 * r('s') - i * 250);
        const x = lerp(vx, 0.5, p * 0.8) * 100 + (r('x') - 0.5) * 40;
        const y = lerp(vy, 0.5, p * 0.8) * 100 + (r('y') - 0.5) * 40;
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
              background: `radial-gradient(circle, ${c} 0%, transparent 66%)`,
            }}
          />
        );
      })}
      <AbsoluteFill style={{background: core, opacity: clamp(env * env * 1.2)}} />
    </AbsoluteFill>
  );
};

/**
 * Lens flare: a bright core with a horizontal streak and ghost discs towards the frame centre,
 * at (`x`, `y`) percent. With `at` it swells over `dur` and travels to `to`; without it it stays on.
 */
export const LensFlare = ({
  x = 30,
  y = 25,
  to,
  at,
  dur = 1.2,
  color = '#FFE9B0',
  size = 520,
  strength = 1,
  ghosts = 3,
}: {
  x?: number;
  y?: number;
  to?: [number, number];
  at?: At;
  dur?: number;
  color?: string;
  /** Core diameter, design px. */
  size?: number;
  strength?: number;
  ghosts?: number;
}) => {
  const age = ageOf(useT(), at);
  const {u} = useLayout();
  if (at !== undefined && (age === null || age >= dur)) {
    return null;
  }
  const p = at === undefined ? 0 : (age ?? 0) / dur;
  const env = (at === undefined ? 1 : Math.sin(Math.PI * p)) * Math.min(1.5, strength);
  const cx = to ? lerp(x, to[0], p) : x;
  const cy = to ? lerp(y, to[1], p) : y;
  const dot = (px: number, py: number, d: number, bg: string, alpha: number, key: string, h = d) => (
    <div
      key={key}
      style={{
        position: 'absolute',
        left: `${px}%`,
        top: `${py}%`,
        width: d,
        height: h,
        marginLeft: -d / 2,
        marginTop: -h / 2,
        borderRadius: '50%',
        background: bg,
        opacity: clamp(alpha * env),
      }}
    />
  );
  const core = u(size);
  return (
    <AbsoluteFill style={fillStyle({mixBlendMode: 'screen', overflow: 'hidden'})}>
      {dot(cx, cy, core, `radial-gradient(circle, #FFFFFF 0%, ${color} 18%, transparent 62%)`, 1, 'core')}
      {dot(cx, cy, core * 5, `radial-gradient(ellipse, ${color} 0%, transparent 65%)`, 0.8, 'streak', Math.max(2, core * 0.07))}
      {Array.from({length: Math.max(0, Math.min(6, Math.round(ghosts)))}, (_, i) => {
        const k = 0.55 + i * 0.45;
        return dot(cx + (50 - cx) * k, cy + (50 - cy) * k, core * (0.18 + 0.1 * ((i * 7) % 3)), `radial-gradient(circle, ${color} 0%, transparent 70%)`, 0.35, `g${i}`);
      })}
    </AbsoluteFill>
  );
};

/** VHS / CRT look over the children: colour fringe, scanlines, grain, a rolling bright band and a small horizontal jitter. */
export const Vhs = ({
  strength = 1,
  roll = 0.12,
  seed = 'vhs',
  children,
}: {
  strength?: number;
  /** Frame heights per second the bright band rolls (0 = none). */
  roll?: number;
  seed?: string;
  children?: ReactNode;
}) => {
  const {u} = useLayout();
  const {fps} = useVideoConfig();
  const t = useT();
  const jolt = random(`${seed}-j-${Math.round(t * fps)}`);
  const jitter = jolt > 0.9 ? (jolt - 0.95) * 20 * u(6) * strength : 0;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{filter: `saturate(${1 + 0.25 * strength}) contrast(${1 + 0.08 * strength}) blur(${u(0.8) * strength}px)`, transform: `translateX(${jitter}px)`}}>
        <RgbSplit amount={u(5) * strength}>{children}</RgbSplit>
      </AbsoluteFill>
      <Scanlines opacity={0.22 * strength} roll={roll} />
      <Noise opacity={0.14 * strength} rate={18} blend="overlay" seed={seed} />
    </AbsoluteFill>
  );
};

/**
 * Freeze frame with a stamp: at `at` the children stop (until `until`, default: for good), the
 * picture gets a white flash, a slow push-in and `tint` of grey, and `label` is slammed on it like a stamp.
 */
export const FreezeStamp = ({
  at,
  until,
  label,
  color,
  textColor,
  rotate = -8,
  size = 130,
  delay = 0.12,
  tint = 0.35,
  children,
}: {
  at: number;
  until?: number;
  label?: string;
  /** Stamp plate colour. Default: the style's accent. */
  color?: string;
  textColor?: string;
  /** Degrees. */
  rotate?: number;
  /** Stamp text size, design px. */
  size?: number;
  /** Seconds after the freeze when the stamp lands. */
  delay?: number;
  /** 0..1 of grey added to the frozen picture. */
  tint?: number;
  children?: ReactNode;
}) => {
  const t = useT();
  const {fps} = useVideoConfig();
  const style = useStyle();
  const frozen = t >= at && (until === undefined || t < until);
  const age = t - at;
  const land = age - delay;
  const push = frozen ? 1 + 0.03 * eOut(seg(age, 0, 0.5)) : 1;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{transform: `scale(${push})`, filter: frozen ? `grayscale(${tint}) contrast(1.08)` : undefined}}>
        <Freeze frame={Math.round(at * fps)} active={frozen}>
          {children}
        </Freeze>
      </AbsoluteFill>
      {frozen && age < 0.18 ? <AbsoluteFill style={fillStyle({background: '#FFFFFF', opacity: (1 - age / 0.18) ** 2})} /> : null}
      {frozen && label && land >= 0 ? (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: seg(land, 0, 0.06)}}>
          <div style={{transform: `scale(${lerp(2.4, 1, eBack(seg(land, 0, 0.22)))})`}}>
            <Label size={size} fill={color ?? style.colors.accent} color={textColor} rotate={rotate} caps>
              {label}
            </Label>
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

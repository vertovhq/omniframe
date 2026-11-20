import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {useLayout, useStyle} from '../style';
import {clamp, eBack, eInOut, eOut, lerp, seg} from './motion';
import {useDuration, useT} from './timing';

// The depth group: things that sit at different distances from the camera. `Tilt` leans a panel
// in perspective, `Parallax` slides layers at different speeds, `CardStack` piles cards up,
// `Device` puts another scene on the screen of a phone or laptop.

type Angles = {x?: number; y?: number; z?: number};

/**
 * A panel leaning in perspective. It turns from `from` to `x`/`y`/`z` degrees between `at` and
 * `at + dur`, then keeps swaying by `sway` degrees if asked. Children are centred; give them a size
 * (a `Card`, a `Device`, a picture). `lift` casts a soft shadow under the panel.
 */
export const Tilt = ({
  x = 8,
  y = -18,
  z = 0,
  from,
  at = 0,
  dur = 0.9,
  sway = 0,
  perspective = 1500,
  lift = 40,
  children,
}: Angles & {
  /** Angles at `at`; default: flat (0, 0, 0). */
  from?: Angles;
  at?: number;
  dur?: number;
  /** Degrees of slow back-and-forth lean once settled. */
  sway?: number;
  /** Distance of the eye, design px; smaller is stronger. */
  perspective?: number;
  /** Shadow size, design px; 0 = none. */
  lift?: number;
  children?: ReactNode;
}) => {
  const t = useT();
  const {u} = useLayout();
  const p = eInOut(seg(t, at, at + Math.max(0.05, dur)));
  const rock = sway * Math.sin(Math.max(0, t - at - dur) * 1.4);
  const a = (target: number, start = 0) => lerp(start, target, p);
  const transform = `perspective(${u(perspective)}px) rotateX(${a(x, from?.x) + rock}deg) rotateY(${a(y, from?.y) - rock}deg) rotateZ(${a(z, from?.z)}deg)`;
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
      <div style={{transform, transformStyle: 'preserve-3d', filter: lift > 0 ? `drop-shadow(0 ${u(lift)}px ${u(lift * 1.2)}px rgba(0, 0, 0, 0.45))` : undefined}}>{children}</div>
    </AbsoluteFill>
  );
};

/**
 * Layers that slide against each other: `depth` 0 is far (moves little), 1 is near (moves with the
 * full `drift`, design px over the scene or from `at` to `at + dur`). A little zoom (`zoom`) grows
 * with depth. Each layer is drawn at full frame size and slightly enlarged so its edges stay out of view.
 */
export const Parallax = ({
  layers,
  drift = [-140, 0],
  zoom = 0.04,
  at = 0,
  dur,
}: {
  layers: Array<{depth: number; node: ReactNode}>;
  drift?: [number, number];
  zoom?: number;
  at?: number;
  dur?: number;
}) => {
  const t = useT();
  const d = useDuration();
  const {u} = useLayout();
  const {width, height} = useVideoConfig();
  const p = eInOut(seg(t, at, at + (dur ?? Math.max(0.1, d - at))));
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      {layers.map((layer, i) => {
        const k = clamp(layer.depth);
        const dx = drift[0] * u(1) * k * (p - 0.5);
        const dy = drift[1] * u(1) * k * (p - 0.5);
        const cover = 1 + (2 * Math.abs(drift[0] * u(1) * k * 0.5)) / width + (2 * Math.abs(drift[1] * u(1) * k * 0.5)) / height + zoom * k;
        return (
          <AbsoluteFill key={i} style={{transform: `translate(${dx}px, ${dy}px) scale(${(cover - zoom * k + zoom * k * p).toFixed(4)})`}}>
            {layer.node}
          </AbsoluteFill>
        );
      })}
    </AbsoluteFill>
  );
};

/**
 * Cards that arrive one after another (`step` seconds apart from `at`) and pile up. `kind`:
 * `stack` keeps older cards peeking out above the newest, `fan` spreads them like a hand,
 * `cascade` steps them diagonally. Each item is drawn on a card of `width` x `height` design px.
 */
export const CardStack = ({
  items,
  kind = 'stack',
  at = 0,
  step = 0.35,
  width = 640,
  height = 400,
  fill,
  radius = 36,
  spread = 9,
  peek = 70,
}: {
  items: ReactNode[];
  kind?: 'stack' | 'fan' | 'cascade';
  at?: number;
  step?: number;
  width?: number;
  height?: number;
  /** Card colour. Default: the style's card colour. */
  fill?: string;
  radius?: number;
  /** `fan`: degrees between neighbours. */
  spread?: number;
  /** `stack` and `cascade`: how far an older card shows, design px. */
  peek?: number;
}) => {
  const t = useT();
  const style = useStyle();
  const {u} = useLayout();
  const progress = items.map((_, i) => seg(t, at + i * step, at + i * step + 0.5));
  const total = progress.reduce((a, b) => a + eOut(b), 0);
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
      {items.map((node, i) => {
        const p = progress[i];
        if (p <= 0) {
          return null;
        }
        const back = Math.max(0, total - 1 - i); // how many cards lie on top of this one
        const e = eBack(p);
        const enter = 1 - e;
        const centre = (items.length - 1) / 2;
        let pose: CSSProperties;
        if (kind === 'fan') {
          pose = {transform: `translate(${(i - centre) * u(peek * 0.6)}px, ${Math.abs(i - centre) * u(10) + enter * u(900)}px) rotate(${(i - centre) * spread * e + enter * 12}deg)`};
        } else if (kind === 'cascade') {
          pose = {transform: `translate(${(-back * peek * 0.8 + enter * 300) * u(1)}px, ${(-back * peek * 0.9 + enter * 700) * u(1)}px) rotate(${enter * 10}deg)`};
        } else {
          pose = {transform: `translate(0, ${-back * u(peek) + enter * u(900)}px) scale(${Math.max(0.6, 1 - back * 0.06)}) rotate(${enter * 8}deg)`};
        }
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              width: u(width),
              height: u(height),
              borderRadius: u(radius),
              background: fill ?? style.colors.bg,
              border: `${u(3)}px solid ${style.colors.cardBorder}`,
              boxShadow: `0 ${u(24)}px ${u(48)}px rgba(0, 0, 0, 0.4)`,
              overflow: 'hidden',
              opacity: clamp(p * 4) * (1 - clamp(back * 0.12)),
              zIndex: i,
              filter: back > 0 ? `brightness(${Math.max(0.5, 1 - back * 0.14)})` : undefined,
              ...pose,
            }}
          >
            {node}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/**
 * A phone or laptop with `children` on its screen. The children are a whole scene: they are drawn
 * at full frame size and scaled to fill the screen (`cover`, or `contain` to see all of it), with
 * their own clock. `width` is the device's width in design px. Put it in a `Tilt` to lean it.
 */
export const Device = ({
  kind = 'phone',
  width,
  color = '#15171C',
  bezel,
  fit = 'cover',
  at = 0,
  children,
}: {
  kind?: 'phone' | 'laptop';
  width?: number;
  /** Body colour. */
  color?: string;
  /** Frame thickness around the screen, design px. */
  bezel?: number;
  fit?: 'cover' | 'contain';
  /** The device pops in at this second. */
  at?: number;
  children?: ReactNode;
}) => {
  const t = useT();
  const {u} = useLayout();
  const {width: W, height: H} = useVideoConfig();
  const phone = kind === 'phone';
  const bodyW = u(width ?? (phone ? 460 : 1000));
  const edge = u(bezel ?? (phone ? 16 : 22));
  const screenW = bodyW - 2 * edge;
  const screenH = phone ? (screenW * 19.5) / 9 : (screenW * 10) / 16;
  const k = (fit === 'cover' ? Math.max : Math.min)(screenW / W, screenH / H);
  const p = eBack(seg(t, at, at + 0.5));
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
      <div style={{transform: `scale(${lerp(0.7, 1, p)})`, opacity: clamp(p * 3), display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        <div style={{width: bodyW, padding: edge, boxSizing: 'border-box', background: color, borderRadius: phone ? u(70) : u(26), boxShadow: `0 ${u(30)}px ${u(60)}px rgba(0, 0, 0, 0.45), inset 0 0 0 ${u(2)}px rgba(255, 255, 255, 0.12)`}}>
          <div style={{position: 'relative', width: screenW, height: screenH, overflow: 'hidden', borderRadius: phone ? u(54) : u(8), background: '#000'}}>
            <div style={{position: 'absolute', left: (screenW - W) / 2, top: (screenH - H) / 2, width: W, height: H, transform: `scale(${k})`, transformOrigin: '50% 50%', overflow: 'hidden'}}>{children}</div>
            {phone ? <div style={{position: 'absolute', top: u(14), left: '50%', width: u(120), height: u(32), marginLeft: -u(60), borderRadius: u(20), background: '#000'}} /> : null}
          </div>
        </div>
        {phone ? null : <div style={{width: bodyW * 1.12, height: u(22), background: color, borderRadius: `0 0 ${u(30)}px ${u(30)}px`, boxShadow: `0 ${u(20)}px ${u(40)}px rgba(0, 0, 0, 0.4)`, marginTop: -u(2)}} />}
      </div>
    </AbsoluteFill>
  );
};

import type {CSSProperties, ReactNode} from 'react';
import {useId} from 'react';
import {AbsoluteFill} from 'remotion';
import {Camera, Gradient, Noise, Pop, Slide, Stage, Transition, Vignette, eBack, seg, useT} from '../kit';
import type {TransitionKind, TransitionSpec} from '../kit';
import {fontFor, useLayout, useStyle} from '../style';

/**
 * Reusable Warm Kraft-Paper & Magazine-Cutout StyleKit.
 * Contains palette tokens, font stacks, caption & plate styling, paper textures,
 * and transition presets — with zero plot, characters, or topic-specific assets.
 * Adapts to both 9:16 and 16:9 via `useLayout()`.
 */

export const STYLE_PALETTE = {
  bg: '#D9BB93',
  bgStops: ['#E0C49E', '#C49B6B'] as const,
  paper: '#F6EFE2',
  newsprint: '#EAE0CC',
  kraftDark: '#BA9263',
  text: '#231710',
  muted: '#6E523D',
  accent: '#EB5E28',
  gold: '#D48F2A',
  olive: '#5A6E45',
  wordActive: '#FFD166',
  captionPlate: 'rgba(35, 23, 16, 0.94)',
  cardBorder: 'rgba(58, 37, 22, 0.24)',
} as const;

export const STYLE_FONTS = {
  display: {family: 'Impact', src: 'fonts/impact.ttf', weight: 700, fallback: "'Impact', 'Arial Black', sans-serif"},
  body: {family: 'Georgia', src: 'fonts/georgiab.ttf', weight: 700, fallback: "'Georgia', 'Times New Roman', serif"},
  mono: {family: 'Consolas', src: 'fonts/consolab.ttf', weight: 700, fallback: "'Consolas', 'Courier New', monospace"},
} as const;

export const CAPTION_PRESET = {
  mode: 'phrase' as const,
  position: 'lower' as const,
  style: {
    font: 'display' as const,
    size: 0.084,
    color: '#F6EFE2',
    active_color: '#FFD166',
    upcoming_color: 'rgba(246, 239, 226, 0.56)',
    outline: 0,
    shadow: 0.004,
    plate: 'rgba(35, 23, 16, 0.94)',
    case: 'upper' as const,
  },
} as const;

export const STYLE_TRANSITIONS = {
  cut: {kind: 'wipe' as const, dir: 'left' as const, dur: 0.28, soft: 0.08},
  slide: {kind: 'whip' as const, dir: 'right' as const, dur: 0.32, strength: 0.6},
  reveal: {kind: 'split' as const, dur: 0.35},
  soft: {kind: 'fade' as const, dur: 0.35},
} as const;

export type StyleTransitionKey = keyof typeof STYLE_TRANSITIONS;

export type StyleKitProps = {
  /** Main cutout headline text shown on the collage sheet. */
  text?: string;
  /** Accent hex/CSS color applied to highlights, stamps, and paper swatches. */
  accent?: string;
  /** Optional small upper magazine tag strip. */
  kicker?: string;
  /** Optional rubber-stamp label in the upper corner. */
  stamp?: string;
  /** Optional sample caption text displayed in the lower caption strip style. */
  caption?: string;
  /** Entry transition preset from STYLE_TRANSITIONS, or a Motion Kit transition spec. */
  transition?: StyleTransitionKey | TransitionKind | TransitionSpec;
  /** Optional custom content placed inside the central paper sheet. */
  children?: ReactNode;
};

/** Full-frame kraft-paper backdrop with fiber texture, paper grain, and warm edge vignette. */
export const KraftBackground = ({seed = 'style-kraft'}: {seed?: string}) => {
  const {u} = useLayout();
  const patId = `sk-fib-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const tile = Math.max(40, u(180));
  return (
    <AbsoluteFill style={{pointerEvents: 'none', overflow: 'hidden'}}>
      <Gradient stops={[...STYLE_PALETTE.bgStops]} angle={155} />
      <Noise opacity={0.18} size={260} seed={seed} blend="multiply" />
      <svg width="100%" height="100%" style={{position: 'absolute', inset: 0, opacity: 0.24}}>
        <defs>
          <pattern id={patId} width={tile} height={tile} patternUnits="userSpaceOnUse">
            <path
              d={`M${u(18)} ${u(32)} Q${u(40)} ${u(24)} ${u(58)} ${u(38)}`}
              stroke={STYLE_PALETTE.muted}
              strokeWidth={u(1.6)}
              fill="none"
              opacity="0.45"
            />
            <path
              d={`M${u(110)} ${u(74)} Q${u(130)} ${u(92)} ${u(152)} ${u(80)}`}
              stroke="#4D3321"
              strokeWidth={u(1.3)}
              fill="none"
              opacity="0.35"
            />
            <path
              d={`M${u(44)} ${u(134)} Q${u(68)} ${u(122)} ${u(82)} ${u(146)}`}
              stroke={STYLE_PALETTE.paper}
              strokeWidth={u(1.4)}
              fill="none"
              opacity="0.5"
            />
            <circle cx={u(142)} cy={u(28)} r={u(2.2)} fill="#4D3321" opacity="0.35" />
            <circle cx={u(28)} cy={u(108)} r={u(1.8)} fill="#4D3321" opacity="0.3" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${patId})`} />
      </svg>
      <Vignette color="#3A2210" strength={0.36} size={48} />
    </AbsoluteFill>
  );
};

/** Translucent beige masking tape strip with serrated cut edges. */
export const TapeStrip = ({
  width = 140,
  height = 36,
  rotate = -8,
  style,
}: {
  width?: number;
  height?: number;
  rotate?: number;
  style?: CSSProperties;
}) => {
  const {u} = useLayout();
  return (
    <div
      style={{
        position: 'absolute',
        width: u(width),
        height: u(height),
        transform: `rotate(${rotate}deg)`,
        filter: `drop-shadow(0 ${u(3)}px ${u(6)}px rgba(43, 25, 14, 0.22))`,
        pointerEvents: 'none',
        ...style,
      }}
    >
      <svg width="100%" height="100%" viewBox="0 0 160 40" preserveAspectRatio="none">
        <polygon
          points="5,0 155,1 160,7 154,14 159,21 153,28 158,35 153,40 6,39 0,33 6,26 1,19 6,12 1,6"
          fill="rgba(241, 223, 182, 0.85)"
          stroke="rgba(165, 134, 88, 0.34)"
          strokeWidth="1.5"
        />
        <line x1="12" y1="8" x2="146" y2="8" stroke="rgba(255,255,255,0.28)" strokeWidth="1.5" />
      </svg>
    </div>
  );
};

/** Torn-edge paper cutout sheet with optional ruled notebook lines or halftone dots. */
export const TornPaperSheet = ({
  width,
  height,
  rotate = 0,
  fill = STYLE_PALETTE.paper,
  ruled = false,
  dots = false,
  tape = 'none',
  style,
  children,
}: {
  width: number;
  height: number;
  rotate?: number;
  fill?: string;
  ruled?: boolean;
  dots?: boolean;
  tape?: 'top' | 'corners' | 'none';
  style?: CSSProperties;
  children?: ReactNode;
}) => {
  const {u} = useLayout();
  const patId = `sk-sheet-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  return (
    <div
      style={{
        position: 'relative',
        width,
        height,
        transform: `rotate(${rotate}deg)`,
        filter: `drop-shadow(${u(4)}px ${u(12)}px ${u(20)}px rgba(35, 23, 16, 0.26))`,
        ...style,
      }}
    >
      <svg
        width="100%"
        height="100%"
        viewBox="0 0 400 400"
        preserveAspectRatio="none"
        style={{position: 'absolute', inset: 0}}
      >
        <defs>
          <pattern id={patId} width="32" height="32" patternUnits="userSpaceOnUse">
            {ruled ? <line x1="0" y1="31" x2="32" y2="31" stroke="#B79E7B" strokeWidth="1.1" opacity="0.48" /> : null}
            {dots ? <circle cx="8" cy="8" r="1.6" fill="#7D6249" opacity="0.22" /> : null}
          </pattern>
        </defs>
        <polygon
          points="4,6 42,2 88,6 142,1 200,5 262,2 324,6 376,2 396,6 398,74 394,145 399,218 395,296 398,370 395,396 340,394 278,399 212,395 144,398 76,394 18,398 3,393 5,315 1,238 5,158 2,82"
          fill={fill}
          stroke="rgba(110, 82, 61, 0.25)"
          strokeWidth="2"
        />
        {(ruled || dots) && <polygon points="6,8 394,8 394,392 6,392" fill={`url(#${patId})`} />}
      </svg>
      <div style={{position: 'relative', width: '100%', height: '100%', boxSizing: 'border-box'}}>{children}</div>
      {tape === 'top' ? <TapeStrip width={150} height={38} rotate={-4} style={{left: '50%', marginLeft: -u(75), top: -u(18)}} /> : null}
      {tape === 'corners' ? (
        <>
          <TapeStrip width={118} height={32} rotate={-32} style={{left: -u(30), top: u(8)}} />
          <TapeStrip width={118} height={32} rotate={28} style={{right: -u(28), top: u(10)}} />
        </>
      ) : null}
    </div>
  );
};

/** Magazine-cutout rectangular plate with offset hard shadow. */
export const CutoutPlate = ({
  text,
  bg = STYLE_PALETTE.text,
  color = STYLE_PALETTE.paper,
  size = 54,
  rotate = -1.5,
  font = 'display',
  padX = 24,
  padY = 10,
  style,
}: {
  text: string;
  bg?: string;
  color?: string;
  size?: number;
  rotate?: number;
  font?: 'display' | 'body' | 'mono';
  padX?: number;
  padY?: number;
  style?: CSSProperties;
}) => {
  const s = useStyle();
  const {u, fs} = useLayout();
  const face = fontFor(s, font);
  const family =
    font === 'display' && s.fonts.display.family === 'Inter'
      ? STYLE_FONTS.display.fallback
      : font === 'body' && s.fonts.body.family === 'Inter'
        ? STYLE_FONTS.body.fallback
        : font === 'mono' && !s.fonts.mono
          ? STYLE_FONTS.mono.fallback
          : face.css;
  return (
    <div
      style={{
        display: 'inline-block',
        background: bg,
        color,
        fontFamily: family,
        fontWeight: face.weight,
        fontSize: fs(size),
        lineHeight: 1.08,
        letterSpacing: u(1.5),
        padding: `${u(padY)}px ${u(padX)}px`,
        transform: `rotate(${rotate}deg)`,
        border: `${u(2.5)}px solid rgba(35, 23, 16, 0.28)`,
        boxShadow: `${u(4)}px ${u(7)}px 0px rgba(35, 23, 16, 0.22)`,
        textAlign: 'center',
        ...style,
      }}
    >
      {text}
    </div>
  );
};

/** Distressed double-bordered ink rubber stamp badge. */
export const StampBadge = ({
  label,
  color = STYLE_PALETTE.accent,
  rotate = -6,
  size = 34,
  at = 0,
  style,
}: {
  label: string;
  color?: string;
  rotate?: number;
  size?: number;
  at?: number;
  style?: CSSProperties;
}) => {
  const s = useStyle();
  const {u, fs} = useLayout();
  const t = useT();
  const p = eBack(seg(t, at, at + 0.28));
  const face = fontFor(s, 'mono');
  if (t < at) {
    return null;
  }
  const scale = 1.4 - 0.4 * p;
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: `${u(8)}px ${u(18)}px`,
        border: `${u(5)}px solid ${color}`,
        outline: `${u(2)}px solid ${color}`,
        outlineOffset: u(4),
        borderRadius: u(8),
        color,
        fontFamily: s.fonts.mono ? face.css : STYLE_FONTS.mono.fallback,
        fontWeight: 800,
        fontSize: fs(size),
        letterSpacing: u(2.2),
        background: 'rgba(246, 239, 226, 0.78)',
        transform: `rotate(${rotate}deg) scale(${scale.toFixed(3)})`,
        opacity: Math.min(1, seg(t, at, at + 0.12)),
        boxShadow: `${u(2)}px ${u(4)}px 0px rgba(35, 23, 16, 0.14)`,
        ...style,
      }}
    >
      {label}
    </div>
  );
};

/** Dark espresso cutout caption strip matching the video's large TikTok caption look. */
export const CaptionPlate = ({
  text,
  accent = STYLE_PALETTE.accent,
  maxWidth,
}: {
  text: string;
  accent?: string;
  maxWidth: number;
}) => {
  const s = useStyle();
  const {u, fs} = useLayout();
  const face = fontFor(s, 'display');
  const family = s.fonts.display.family === 'Inter' ? STYLE_FONTS.display.fallback : face.css;
  const words = text.trim().split(/\s+/).filter(Boolean).slice(0, 6);
  return (
    <div
      style={{
        maxWidth,
        display: 'inline-flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        columnGap: '0.26em',
        rowGap: '0.04em',
        background: CAPTION_PRESET.style.plate,
        padding: `0.16em 0.42em`,
        borderRadius: '0.3em',
        fontFamily: family,
        fontWeight: face.weight,
        fontSize: fs(82),
        lineHeight: 1.12,
        textTransform: 'uppercase',
        boxShadow: `0 ${u(6)}px ${u(18)}px rgba(0, 0, 0, 0.28)`,
      }}
    >
      {words.map((w, i) => (
        <span
          key={i}
          style={{
            color: i === 0 ? accent : i === 1 ? CAPTION_PRESET.style.active_color : CAPTION_PRESET.style.color,
            transform: i === 1 ? 'scale(1.06)' : undefined,
            display: 'inline-block',
          }}
        >
          {w}
        </span>
      ))}
    </div>
  );
};

export default function StyleKit({
  text = 'WARM PAPER COLLAGE',
  accent,
  kicker = 'EDITORIAL CUTOUT',
  stamp = 'STYLE KIT',
  caption,
  transition = 'cut',
  children,
}: StyleKitProps) {
  const s = useStyle();
  const {u, fs, safe, width, height} = useLayout();
  const t = useT();

  const landscape = width > height;
  const hi = accent ?? s.colors.accent ?? STYLE_PALETTE.accent;
  const displayHeadline = text.trim() || 'WARM PAPER COLLAGE';
  const headlineSize = landscape
    ? displayHeadline.length > 26
      ? 52
      : 66
    : displayHeadline.length > 22
      ? 48
      : 62;

  const sheetW = landscape ? safe.width * 0.78 : safe.width * 0.92;
  const sheetH = landscape ? safe.height * 0.62 : safe.height * 0.64;
  const innerW = sheetW * 0.93;
  const innerH = sheetH * 0.86;

  const transSpec: TransitionKind | TransitionSpec =
    typeof transition === 'string' && transition in STYLE_TRANSITIONS
      ? STYLE_TRANSITIONS[transition as StyleTransitionKey]
      : (transition as TransitionKind | TransitionSpec);

  return (
    <Stage>
      <Transition spec={transSpec} role="in" t={t} fade={0.35}>
        <Stage>
          <KraftBackground seed="stylekit-bg" />
          <Camera zoom={0.04} pan={[-6, -8]} origin="50% 48%">
            <div
              style={{
                position: 'absolute',
                left: safe.left,
                top: safe.top,
                width: safe.width,
                height: safe.height,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingTop: u(12),
                paddingBottom: u(8),
                boxSizing: 'border-box',
              }}
            >
              {/* Layered paper collage sheet area */}
              <div
                style={{
                  position: 'relative',
                  width: sheetW,
                  height: sheetH,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {/* Back newsprint dotted sheet */}
                <TornPaperSheet
                  width={sheetW}
                  height={sheetH}
                  rotate={-1.6}
                  fill={STYLE_PALETTE.newsprint}
                  dots
                  tape="corners"
                  style={{position: 'absolute'}}
                />

                {/* Front cream ruled sheet */}
                <TornPaperSheet
                  width={innerW}
                  height={innerH}
                  rotate={1.2}
                  fill={STYLE_PALETTE.paper}
                  ruled
                  tape="top"
                  style={{position: 'absolute'}}
                >
                  <div
                    style={{
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: `${u(36)}px ${u(28)}px`,
                      boxSizing: 'border-box',
                      gap: u(22),
                    }}
                  >
                    {/* Decorative cut paper geometric swatches (palette showcase) */}
                    <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: u(14)}}>
                      <div style={{width: u(42), height: u(16), background: STYLE_PALETTE.kraftDark, border: `${u(2)}px solid ${STYLE_PALETTE.text}`, transform: 'rotate(-4deg)'}} />
                      <div style={{width: u(42), height: u(16), background: hi, border: `${u(2)}px solid ${STYLE_PALETTE.text}`, transform: 'rotate(2deg)'}} />
                      <div style={{width: u(42), height: u(16), background: STYLE_PALETTE.gold, border: `${u(2)}px solid ${STYLE_PALETTE.text}`, transform: 'rotate(-3deg)'}} />
                      <div style={{width: u(42), height: u(16), background: STYLE_PALETTE.olive, border: `${u(2)}px solid ${STYLE_PALETTE.text}`, transform: 'rotate(4deg)'}} />
                    </div>

                    {/* Kicker strip */}
                    <Slide from={0.05} side="left" dist={60} dur={0.36}>
                      <CutoutPlate
                        text={kicker}
                        bg={STYLE_PALETTE.kraftDark}
                        color={STYLE_PALETTE.text}
                        size={landscape ? 28 : 26}
                        rotate={-2}
                        font="mono"
                        padX={18}
                        padY={7}
                      />
                    </Slide>

                    {/* Main cutout headline */}
                    <Pop from={0.14} dur={0.38}>
                      <CutoutPlate
                        text={displayHeadline}
                        bg={STYLE_PALETTE.text}
                        color={STYLE_PALETTE.paper}
                        size={headlineSize}
                        rotate={-1.2}
                        font="display"
                        padX={26}
                        padY={14}
                        style={{maxWidth: innerW * 0.9}}
                      />
                    </Pop>

                    {/* Optional slot for scene elements */}
                    {children ? (
                      <div style={{marginTop: u(8)}}>{children}</div>
                    ) : (
                      <div
                        style={{
                          fontFamily: STYLE_FONTS.body.fallback,
                          fontWeight: 700,
                          fontSize: fs(landscape ? 24 : 26),
                          color: STYLE_PALETTE.muted,
                          letterSpacing: u(1.2),
                          textAlign: 'center',
                        }}
                      >
                        KRAFT • NEWSPRINT • CUTOUT PLATES
                      </div>
                    )}
                  </div>
                </TornPaperSheet>

                {/* Upper-left rubber stamp */}
                <div style={{position: 'absolute', left: u(14), top: -u(18), zIndex: 4}}>
                  <StampBadge label={stamp} color={hi} rotate={-6} size={landscape ? 28 : 30} at={0.05} />
                </div>
              </div>

              {/* Lower caption strip style showcase */}
              <div style={{display: 'flex', justifyContent: 'center', width: '100%'}}>
                <CaptionPlate text={caption ?? displayHeadline} accent={hi} maxWidth={safe.width * 0.94} />
              </div>
            </div>
          </Camera>
        </Stage>
      </Transition>
    </Stage>
  );
}

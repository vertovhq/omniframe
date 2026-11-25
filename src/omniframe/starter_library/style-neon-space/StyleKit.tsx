import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Glow, Noise, Particles, clamp, eInOut, eOut, lerp, seg, useT} from '../kit';

export const STYLE_PALETTE = {
  bgInner: '#151a4a',
  bgMid: '#0a0c26',
  bgOuter: '#04050d',
  surface: 'rgba(8, 11, 40, 0.78)',
  text: '#ffffff',
  muted: '#9ab4ff',
  cyan: '#3df2ff',
  violet: '#b07cff',
  magenta: '#ff3ad8',
} as const;

export const STYLE_FONTS = {
  display: "'Russo One', sans-serif",
  body: "'Russo One', sans-serif",
  mono: "'Consolas', monospace",
} as const;

export const CHROME_GRADIENT =
  'linear-gradient(180deg, #ffffff 0%, #d6e8ff 36%, #6b7d96 49%, #f2fbff 52%, #ffffff 64%, #8aa0bc 100%)';

export type StyleTransitionKind = 'flash' | 'whip' | 'zoom' | 'cut';

export const STYLE_TRANSITIONS: Record<
  StyleTransitionKind,
  {dur: number; ease: (x: number) => number}
> = {
  cut: {dur: 0, ease: (x) => (x > 0 ? 1 : 0)},
  flash: {dur: 0.24, ease: eOut},
  whip: {dur: 0.28, ease: eInOut},
  zoom: {dur: 0.3, ease: eOut},
};

/** Compute normalized transition progress, flash opacity, scale, and whip offset. */
export function useStyleTransition(
  kind: StyleTransitionKind = 'flash',
  at = 0,
): {progress: number; flashOpacity: number; scale: number; translateX: number} {
  const t = useT();
  const spec = STYLE_TRANSITIONS[kind];
  if (spec.dur <= 0) {
    return {progress: t >= at ? 1 : 0, flashOpacity: 0, scale: 1, translateX: 0};
  }
  const p = clamp(spec.ease(seg(t, at, at + spec.dur)), 0, 1);
  return {
    progress: p,
    flashOpacity: kind === 'flash' ? (1 - p) * 0.72 : 0,
    scale: kind === 'zoom' ? lerp(1.12, 1, p) : 1,
    translateX: kind === 'whip' ? lerp(180, 0, p) : 0,
  };
}

const hash = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

const pad2 = (n: number) => String(Math.floor(n)).padStart(2, '0');
const hudClock = (s: number) => `${pad2(Math.floor(s / 60))}:${pad2(s % 60)}.${Math.floor((s % 1) * 10)}`;

/** Tracked neon HUD tag label. */
export function StyleTag({
  children,
  color = STYLE_PALETTE.violet,
  size = 28,
}: {
  children: React.ReactNode;
  color?: string;
  size?: number;
}) {
  return (
    <div
      style={{
        fontFamily: STYLE_FONTS.display,
        fontSize: size,
        letterSpacing: 8,
        color,
        textAlign: 'center',
        textTransform: 'uppercase',
        textShadow: `0 0 12px ${color}, 0 0 28px ${color}`,
      }}
    >
      {children}
    </div>
  );
}

/** Metallic chrome display lettering with neon halo. */
export function StyleChrome({
  children,
  size = 96,
  accent = STYLE_PALETTE.cyan,
}: {
  children: React.ReactNode;
  size?: number;
  accent?: string;
}) {
  return (
    <div style={{textAlign: 'center', maxWidth: '92%'}}>
      <span
        style={{
          fontFamily: STYLE_FONTS.display,
          fontSize: size,
          lineHeight: 1.04,
          textTransform: 'uppercase',
          background: CHROME_GRADIENT,
          WebkitBackgroundClip: 'text',
          backgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          color: 'transparent',
          filter: `drop-shadow(0 0 ${Math.round(size * 0.08)}px ${accent}) drop-shadow(0 0 ${Math.round(size * 0.24)}px ${accent})`,
        }}
      >
        {children}
      </span>
    </div>
  );
}

/** Glowing neon HUD status pill. */
export function StylePill({
  children,
  accent = STYLE_PALETTE.cyan,
  solid = false,
}: {
  children: React.ReactNode;
  accent?: string;
  solid?: boolean;
}) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 22px',
        borderRadius: 999,
        background: solid ? accent : 'rgba(8, 11, 40, 0.85)',
        border: `2px solid ${accent}`,
        boxShadow: `0 0 18px ${accent}55`,
        fontFamily: STYLE_FONTS.display,
        fontSize: 18,
        letterSpacing: 3,
        color: solid ? '#04050d' : STYLE_PALETTE.text,
        textTransform: 'uppercase',
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: solid ? '#04050d' : accent,
          boxShadow: solid ? 'none' : `0 0 8px ${accent}`,
        }}
      />
      <span>{children}</span>
    </div>
  );
}

/** Dark translucent neon-bordered telemetry readout plate. */
export function StylePlate({
  label,
  value,
  accent = STYLE_PALETTE.cyan,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        minWidth: 520,
        maxWidth: '90%',
        borderRadius: 16,
        background: STYLE_PALETTE.surface,
        border: `2px solid ${accent}`,
        boxShadow: `0 0 24px ${accent}33`,
        padding: '20px 30px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 28,
      }}
    >
      <div style={{fontFamily: STYLE_FONTS.mono, fontSize: 22, letterSpacing: 2.5, color: STYLE_PALETTE.muted}}>
        {label}
      </div>
      <div
        style={{
          fontFamily: STYLE_FONTS.display,
          fontSize: 36,
          color: accent,
          textShadow: `0 0 14px ${accent}`,
        }}
      >
        {value}
      </div>
    </div>
  );
}

/** Bold uppercase kinetic TikTok subtitle block with accent-boxed highlight word. */
export function StyleSubtitle({
  text,
  highlightWord,
  accent = STYLE_PALETTE.cyan,
  size = 64,
}: {
  text: string;
  highlightWord?: string;
  accent?: string;
  size?: number;
}) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const target = (highlightWord ?? words[words.length - 1] ?? '').toLowerCase();

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        gap: '12px 16px',
        maxWidth: '88%',
      }}
    >
      {words.map((word, idx) => {
        const isHot = target && word.toLowerCase() === target;
        return (
          <span
            key={idx}
            style={{
              fontFamily: STYLE_FONTS.display,
              fontSize: size,
              lineHeight: 1.05,
              textTransform: 'uppercase',
              fontStyle: 'italic',
              padding: isHot ? '6px 18px' : '2px 4px',
              borderRadius: isHot ? 14 : 0,
              background: isHot ? accent : 'transparent',
              color: isHot ? '#050816' : '#ffffff',
              boxShadow: isHot ? `0 0 22px ${accent}88` : 'none',
              textShadow: isHot ? 'none' : '0 4px 18px rgba(0,0,0,0.85)',
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
}

export type StyleKitProps = {
  text?: string;
  accent?: string;
  label?: string;
  tag?: string;
  subtitle?: string;
  highlightWord?: string;
  transition?: StyleTransitionKind;
  children?: React.ReactNode;
};

/**
 * Extracted dark-space neon HUD style shell (works in 9:16 and 16:9):
 * deep indigo-black radial sky, drifting neon grid & scan sweep, starfield & grain,
 * HUD corner brackets + timer, chrome lettering, neon pills/plates, and bold boxed subtitles.
 */
export default function StyleKit({
  text = 'COSMIC SIGNAL',
  accent = STYLE_PALETTE.cyan,
  label = 'SECTOR 01 // HUD',
  tag = 'DEEP SPACE ARCHIVE',
  subtitle = 'NEON SPACE TELEMETRY',
  highlightWord,
  transition = 'flash',
  children,
}: StyleKitProps) {
  const t = useT();
  const {width, height} = useVideoConfig();
  const isPortrait = height > width;
  const tr = useStyleTransition(transition, 0);

  const scanY = ((t * 220) % (height + 240)) - 240;
  const padX = isPortrait ? 66 : 84;
  const topY = isPortrait ? 150 : 68;
  const botY = isPortrait ? Math.round(height * 0.795) : height - 68;

  const orbs = Array.from({length: 24}, (_, i) => {
    const r = 2 + hash(i + 3) * 6;
    const v = 28 + hash(i + 9) * 52;
    const y = height + 80 - ((t * v + hash(i + 21) * (height + 160)) % (height + 160));
    const x = hash(i + 1) * width + 22 * Math.sin(t * 0.8 + i);
    const c = i % 3 === 0 ? STYLE_PALETTE.magenta : i % 3 === 1 ? accent : STYLE_PALETTE.violet;
    return {r, x, y, c, o: 0.18 + hash(i + 40) * 0.34};
  });

  const vCols = Math.ceil(width / 90);
  const hRows = Math.ceil(height / 150);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse 80% 55% at 50% 38%, ${STYLE_PALETTE.bgInner} 0%, ${STYLE_PALETTE.bgMid} 45%, ${STYLE_PALETTE.bgOuter} 100%)`,
        transform: `translateX(${tr.translateX}px) scale(${tr.scale})`,
      }}
    >
      {/* Grid, scan sweep, drifting neon plasma particles & HUD corner brackets */}
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} style={{position: 'absolute', inset: 0}}>
        <defs>
          <linearGradient id="sns-scan" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={accent} stopOpacity="0" />
            <stop offset="0.5" stopColor={accent} stopOpacity="0.1" />
            <stop offset="1" stopColor={accent} stopOpacity="0" />
          </linearGradient>
        </defs>

        {Array.from({length: vCols}, (_, i) => (
          <line key={`v${i}`} x1={i * 90} y1={0} x2={i * 90} y2={height} stroke={accent} strokeOpacity={0.07} strokeWidth={1.5} />
        ))}
        {Array.from({length: hRows}, (_, i) => {
          const y = (i * 150 + t * 18) % height;
          return <line key={`h${i}`} x1={0} y1={y} x2={width} y2={y} stroke={accent} strokeOpacity={0.07} strokeWidth={1.5} />;
        })}

        <rect x={0} y={scanY} width={width} height={240} fill="url(#sns-scan)" />

        {orbs.map((b, i) => (
          <circle key={i} cx={b.x} cy={b.y} r={b.r} fill="none" stroke={b.c} strokeWidth={1.8} opacity={b.o} />
        ))}

        {/* Corner brackets */}
        {[
          [padX, topY, 1, 1],
          [width - padX, topY, -1, 1],
          [padX, botY, 1, -1],
          [width - padX, botY, -1, -1],
        ].map(([x, y, sx, sy], i) => (
          <path
            key={i}
            d={`M${x + sx * 64} ${y} L${x} ${y} L${x} ${y + sy * 64}`}
            fill="none"
            stroke={accent}
            strokeOpacity={0.62}
            strokeWidth={3}
          />
        ))}

        <text x={padX + 30} y={topY + 46} fontFamily={STYLE_FONTS.display} fontSize={24} letterSpacing={5} fill={accent} fillOpacity={0.8}>
          {label}
        </text>
        <text x={width - padX - 30} y={topY + 46} textAnchor="end" fontFamily={STYLE_FONTS.display} fontSize={24} letterSpacing={5} fill={accent} fillOpacity={0.8}>
          {hudClock(t)}
        </text>
      </svg>

      {/* Starfield, atmospheric glow & analog grain */}
      <Particles kind="stars" count={80} seed="style-neon-space" color="rgba(204, 232, 255, 0.78)" />
      <Glow x={50} y={38} size={isPortrait ? 760 : 900} color={accent} opacity={0.2} hz={0.6} />
      <Noise opacity={0.04} size={2} rate={12} seed="neon-space" />

      {/* Main Content Stage */}
      <div
        style={{
          position: 'absolute',
          left: padX,
          right: padX,
          top: topY + 72,
          bottom: height - botY + 32,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: isPortrait ? '24px 0 36px' : '16px 0 24px',
        }}
      >
        {children ?? (
          <>
            <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18}}>
              <StylePill accent={accent}>{tag}</StylePill>
              <StyleTag color={STYLE_PALETTE.violet} size={isPortrait ? 28 : 24}>
                {isPortrait ? '9:16 // VERTICAL' : '16:9 // WIDESCREEN'}
              </StyleTag>
              <StyleChrome size={isPortrait ? 92 : 84} accent={accent}>
                {text}
              </StyleChrome>
            </div>

            <StylePlate label="SIGNAL // ACCENT" value={accent.toUpperCase()} accent={accent} />

            {subtitle && (
              <StyleSubtitle
                text={subtitle}
                highlightWord={highlightWord}
                accent={accent}
                size={isPortrait ? 64 : 56}
              />
            )}
          </>
        )}
      </div>

      {/* Flash transition overlay */}
      {tr.flashOpacity > 0.01 && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: accent,
            opacity: tr.flashOpacity,
            pointerEvents: 'none',
          }}
        />
      )}
    </AbsoluteFill>
  );
}

import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Noise, clamp, eInOut, eOut, lerp, seg, useT} from '../kit';

export type StyleMode = 'dark' | 'light';

export const STYLE_PALETTE = {
  outer: '#000000',
  dark: {
    bg: '#050809',
    bgGlow: '#0d1a20',
    surface: 'rgba(10, 14, 18, 0.88)',
    glass: 'rgba(255, 255, 255, 0.06)',
    text: '#e8f0f5',
    muted: '#6f8b96',
    border: 'rgba(130, 185, 200, 0.24)',
    warm: '#d29e4a',
    coral: '#ff4f7a',
  },
  light: {
    bg: '#f6f6f7',
    bgGlow: '#e8eef5',
    surface: 'rgba(255, 255, 255, 0.9)',
    glass: 'rgba(17, 17, 19, 0.04)',
    text: '#111113',
    muted: '#666d78',
    border: 'rgba(17, 17, 19, 0.14)',
    warm: '#d96b4d',
    coral: '#e54355',
  },
} as const;

export const STYLE_FONTS = {
  display: "'Inter', 'Helvetica Neue', system-ui, sans-serif",
  body: "'Inter', 'Helvetica Neue', system-ui, sans-serif",
  mono: "'Consolas', 'JetBrains Mono', monospace",
} as const;

export type StyleTransitionKind = 'cut' | 'flash' | 'wipe' | 'zoom';

export const STYLE_TRANSITIONS: Record<
  StyleTransitionKind,
  {dur: number; ease: (x: number) => number}
> = {
  cut: {dur: 0, ease: (x) => (x > 0 ? 1 : 0)},
  flash: {dur: 0.16, ease: eOut},
  wipe: {dur: 0.24, ease: eInOut},
  zoom: {dur: 0.22, ease: eOut},
};

/** Compute normalized transition progress and flash intensity for custom cuts. */
export function useStyleTransition(
  kind: StyleTransitionKind = 'cut',
  at = 0,
): {progress: number; flashOpacity: number; scale: number} {
  const t = useT();
  const spec = STYLE_TRANSITIONS[kind];
  if (spec.dur <= 0) {
    return {progress: t >= at ? 1 : 0, flashOpacity: 0, scale: 1};
  }
  const p = spec.ease(seg(t, at, at + spec.dur));
  const flashOpacity = kind === 'flash' ? (1 - p) * 0.65 : 0;
  const scale = kind === 'zoom' ? lerp(1.08, 1, p) : 1;
  return {progress: clamp(p, 0, 1), flashOpacity, scale};
}

/** Monospace telemetry pill / badge in the edit's hairline glass style. */
export function StylePill({
  children,
  accent = '#52f2ff',
  mode = 'dark',
  solid = false,
}: {
  children: React.ReactNode;
  accent?: string;
  mode?: StyleMode;
  solid?: boolean;
}) {
  const pal = STYLE_PALETTE[mode];
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 18px',
        borderRadius: 999,
        background: solid ? accent : pal.glass,
        border: `1.5px solid ${solid ? accent : pal.border}`,
        fontFamily: STYLE_FONTS.mono,
        fontSize: 16,
        fontWeight: 600,
        letterSpacing: 1.6,
        color: solid ? '#050809' : pal.text,
        textTransform: 'uppercase',
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: solid ? '#050809' : accent,
          boxShadow: solid ? 'none' : `0 0 8px ${accent}`,
        }}
      />
      <span>{children}</span>
    </div>
  );
}

/** Sharp-edged telemetry plate with an accent bottom tab bar. */
export function StylePlate({
  title,
  value,
  tag,
  accent = '#52f2ff',
  mode = 'dark',
}: {
  title: string;
  value: string;
  tag: string;
  accent?: string;
  mode?: StyleMode;
}) {
  const pal = STYLE_PALETTE[mode];
  return (
    <div
      style={{
        background: pal.surface,
        border: `1.5px solid ${accent}`,
        padding: '16px 18px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        minWidth: 230,
      }}
    >
      <div style={{fontFamily: STYLE_FONTS.mono, fontSize: 13, letterSpacing: 1.5, color: pal.muted, textTransform: 'uppercase'}}>
        {title}
      </div>
      <div style={{fontFamily: STYLE_FONTS.mono, fontSize: 30, fontWeight: 700, color: accent}}>
        {value}
      </div>
      <div
        style={{
          background: accent,
          color: '#050809',
          fontFamily: STYLE_FONTS.mono,
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: 1.4,
          padding: '4px 8px',
          textTransform: 'uppercase',
        }}
      >
        {tag}
      </div>
    </div>
  );
}

/** Crisp geometric subtitle strip with accent highlight bar. */
export function StyleSubtitle({
  text,
  accent = '#52f2ff',
  mode = 'dark',
  size = 44,
}: {
  text: string;
  accent?: string;
  mode?: StyleMode;
  size?: number;
}) {
  const pal = STYLE_PALETTE[mode];
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, maxWidth: '88%'}}>
      <div
        style={{
          fontFamily: STYLE_FONTS.display,
          fontSize: size,
          fontWeight: 600,
          lineHeight: 1.12,
          letterSpacing: -0.8,
          textAlign: 'center',
          color: pal.text,
          padding: '10px 24px',
          borderRadius: 12,
          background: mode === 'dark' ? 'rgba(5, 8, 9, 0.72)' : 'rgba(255, 255, 255, 0.82)',
          border: `1px solid ${pal.border}`,
          boxShadow: `0 8px 28px rgba(0, 0, 0, 0.28)`,
        }}
      >
        {text}
      </div>
      <div style={{width: 64, height: 3, borderRadius: 2, background: accent, boxShadow: `0 0 10px ${accent}`}} />
    </div>
  );
}

export type StyleKitProps = {
  text?: string;
  accent?: string;
  label?: string;
  subtitle?: string;
  mode?: StyleMode;
  transition?: StyleTransitionKind;
  children?: React.ReactNode;
};

/**
 * Extracted visual style shell (9:16 letterboxed cinema frame & 16:9 full-bleed):
 * dark obsidian telemetry backdrop, hairline grid & noise texture, Inter + Consolas typography,
 * glass/bordered badges, clean subtitle treatment, and hard-cut/flash transitions.
 */
export default function StyleKit({
  text = 'CLEAN MOTION SYSTEM',
  accent = '#52f2ff',
  label = 'STYLE // TELEMETRY',
  subtitle = 'GEOMETRIC SANS + MONO HUD',
  mode = 'dark',
  transition = 'flash',
  children,
}: StyleKitProps) {
  const t = useT();
  const {width, height} = useVideoConfig();
  const isPortrait = height > width;
  const pal = STYLE_PALETTE[mode];
  const tr = useStyleTransition(transition, 0);

  const viewW = isPortrait ? 1080 : 1920;
  const viewH = isPortrait ? 1040 : 1080;
  const viewTop = isPortrait ? Math.round((height - viewH) / 2) : 0;
  const scanX = ((t * 160) % (viewW + 240)) - 120;
  const padX = isPortrait ? 36 : 72;
  const padY = isPortrait ? 28 : 42;

  return (
    <AbsoluteFill style={{backgroundColor: STYLE_PALETTE.outer}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: viewTop,
          width: viewW,
          height: viewH,
          overflow: 'hidden',
          background: `radial-gradient(ellipse 75% 60% at 50% 42%, ${pal.bgGlow} 0%, ${pal.bg} 78%)`,
          transform: `scale(${tr.scale})`,
        }}
      >
        {/* Subtle coordinate grid & moving scan hairline */}
        <svg viewBox={`0 0 ${viewW} ${viewH}`} width={viewW} height={viewH} style={{position: 'absolute', inset: 0}}>
          <defs>
            <linearGradient id="sk-edge-top" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={accent} stopOpacity="0.22" />
              <stop offset="50%" stopColor={pal.warm} stopOpacity="0.16" />
              <stop offset="100%" stopColor={pal.coral} stopOpacity="0.2" />
            </linearGradient>
          </defs>
          {Array.from({length: 12}, (_, i) => {
            const x = ((i + 1) * viewW) / 13;
            return <line key={`vx${i}`} x1={x} y1={0} x2={x} y2={viewH} stroke={pal.border} strokeWidth="1" strokeOpacity="0.45" />;
          })}
          {Array.from({length: 8}, (_, i) => {
            const y = ((i + 1) * viewH) / 9;
            return <line key={`hy${i}`} x1={0} y1={y} x2={viewW} y2={y} stroke={pal.border} strokeWidth="1" strokeOpacity="0.45" />;
          })}
          <line x1={scanX} y1={0} x2={scanX} y2={viewH} stroke={accent} strokeWidth="1.5" strokeOpacity="0.18" />
          <rect x={0} y={0} width={viewW} height={3} fill="url(#sk-edge-top)" />
          <rect x={0} y={viewH - 3} width={viewW} height={3} fill="url(#sk-edge-top)" />
        </svg>

        {/* Subtle analog grain texture */}
        <Noise opacity={mode === 'dark' ? 0.045 : 0.025} size={2} rate={12} seed="stylekit" />

        {/* Top & bottom hairline HUD frame */}
        <div
          style={{
            position: 'absolute',
            left: padX,
            right: padX,
            top: padY,
            paddingBottom: 14,
            borderBottom: `1px solid ${pal.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <StylePill accent={accent} mode={mode}>{label}</StylePill>
          <div style={{fontFamily: STYLE_FONTS.mono, fontSize: 15, letterSpacing: 2, color: pal.muted}}>
            {isPortrait ? '9:16 // CINEMA' : '16:9 // WIDE'}
          </div>
        </div>

        {/* Center stage (slot for children or clean typography preview) */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: isPortrait ? 32 : 28,
            padding: `0 ${padX}px`,
          }}
        >
          {children ?? (
            <>
              <div
                style={{
                  fontFamily: STYLE_FONTS.display,
                  fontSize: isPortrait ? 86 : 104,
                  fontWeight: 600,
                  letterSpacing: -2.4,
                  lineHeight: 1.05,
                  textAlign: 'center',
                  color: pal.text,
                  maxWidth: '90%',
                }}
              >
                {text}
              </div>

              <div style={{display: 'flex', gap: 18, flexWrap: 'wrap', justifyContent: 'center'}}>
                <StylePlate title="ACCENT TOKEN" value={accent.toUpperCase()} tag="ACTIVE" accent={accent} mode={mode} />
                <StylePlate title="TYPOGRAPHY" value="INTER / MONO" tag="READY" accent={pal.warm} mode={mode} />
              </div>
            </>
          )}
        </div>

        {/* Lower subtitle & footer strip */}
        <div
          style={{
            position: 'absolute',
            left: padX,
            right: padX,
            bottom: padY,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 18,
          }}
        >
          {subtitle && <StyleSubtitle text={subtitle} accent={accent} mode={mode} size={isPortrait ? 36 : 42} />}
          <div
            style={{
              width: '100%',
              paddingTop: 12,
              borderTop: `1px solid ${pal.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              fontFamily: STYLE_FONTS.mono,
              fontSize: 13,
              letterSpacing: 1.6,
              color: pal.muted,
            }}
          >
            <span>01 / BACKDROP &amp; GRID</span>
            <span>02 / PLATES &amp; TYPE</span>
            <span>03 / HARD CUT &amp; FLASH</span>
          </div>
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
      </div>
    </AbsoluteFill>
  );
}

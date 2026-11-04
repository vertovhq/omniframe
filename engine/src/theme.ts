import {loadFont} from '@remotion/fonts';
import {staticFile} from 'remotion';
import type {ThemeName} from './types';

export const FONT_FAMILY = 'Inter';
export const ACCENT_DEFAULT = '#7C5CFA';

export interface ThemeColors {
  name: ThemeName;
  bg: string;
  text: string;
  muted: string;
  accent: string;
  /** Base color of a spoken/plain word (slightly dimmed). */
  wordBase: string;
  /** Color of the currently active word (brighter). */
  wordActive: string;
  /** CSS background (two overlapping radial gradients) for the subtle vignette. */
  vignette: string;
  grainOpacity: number;
  cardBorder: string;
}

export function hexToRgb(hex: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6}|[0-9a-f]{3})$/i.exec((hex ?? '').trim());
  if (!m) {
    return [124, 92, 250];
  }
  let h = m[1];
  if (h.length === 3) {
    h = h
      .split('')
      .map((c) => c + c)
      .join('');
  }
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function withAlpha(hex: string, a: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

export function getTheme(name: ThemeName, accent?: string): ThemeColors {
  const acc = accent && accent.trim() !== '' ? accent.trim() : ACCENT_DEFAULT;
  if (name === 'light') {
    return {
      name: 'light',
      bg: '#F6F7FB',
      text: '#0A0A12',
      muted: '#6B7080',
      accent: acc,
      wordBase: 'rgba(10, 10, 18, 0.62)',
      wordActive: '#0A0A12',
      vignette: `radial-gradient(120% 75% at 50% 30%, ${withAlpha(acc, 0.07)} 0%, rgba(0, 0, 0, 0) 55%), radial-gradient(160% 120% at 50% 55%, rgba(246, 247, 251, 0) 50%, rgba(15, 20, 40, 0.06) 100%)`,
      grainOpacity: 0.035,
      cardBorder: 'rgba(10, 10, 18, 0.10)',
    };
  }
  return {
    name: 'dark',
    bg: '#0A0A12',
    text: '#F5F6FA',
    muted: '#8A8FA3',
    accent: acc,
    wordBase: 'rgba(245, 246, 250, 0.72)',
    wordActive: '#FFFFFF',
    vignette: `radial-gradient(120% 75% at 50% 30%, ${withAlpha(acc, 0.10)} 0%, rgba(0, 0, 0, 0) 55%), radial-gradient(160% 120% at 50% 55%, rgba(10, 10, 18, 0) 45%, rgba(0, 0, 0, 0.55) 100%)`,
    grainOpacity: 0.05,
    cardBorder: 'rgba(255, 255, 255, 0.08)',
  };
}

/**
 * Media/voice sources: absolute URLs and data URIs pass through,
 * everything else is resolved against the public dir via staticFile.
 * The Python caller always rewrites media to "m/<basename>", so this
 * covers the engine-side contract.
 */
export function resolveMedia(src: string): string {
  if (/^(https?:|data:|blob:|file:)/i.test(src)) {
    return src;
  }
  return staticFile(src);
}

let fontsRequested = false;

/**
 * Loads the bundled Inter Display OTFs as family "Inter" with weights
 * 400/500/600/700/900 via @remotion/fonts (which delayRender()s until loaded).
 */
export function ensureFonts(): void {
  if (fontsRequested) {
    return;
  }
  fontsRequested = true;
  const files: Array<[string, string]> = [
    ['400', 'InterDisplay-Regular.otf'],
    ['500', 'InterDisplay-Medium.otf'],
    ['600', 'InterDisplay-Semibold.otf'],
    ['700', 'InterDisplay-Bold.otf'],
    ['900', 'InterDisplay-Black.otf'],
  ];
  for (const [weight, file] of files) {
    loadFont({
      family: FONT_FAMILY,
      url: staticFile(`fonts/${file}`),
      weight,
      style: 'normal',
    }).catch((err) => {
      // eslint-disable-next-line no-console
      console.error(`Failed to load font ${file}:`, err);
    });
  }
}

/**
 * Faint film grain, rendered from a deterministic SVG feTurbulence tile
 * used as a repeating CSS background. Static across frames, no PNG needed.
 */
const grainSvg = `<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='240' height='240' filter='url(#n)'/></svg>`;

export const grainBackgroundImage = `url("data:image/svg+xml,${encodeURIComponent(grainSvg)}")`;

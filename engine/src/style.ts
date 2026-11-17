import {loadFont} from '@remotion/fonts';
import {createContext, useContext, useMemo} from 'react';
import {staticFile, useVideoConfig} from 'remotion';
import type {Background, FontRef, PlanFormat, SafeArea, StyleTokens, ThemeName} from './types';

export const FONT_FAMILY = 'Inter';
export const ACCENT_DEFAULT = '#7C5CFA';

/**
 * All design numbers in the scenes are written for a frame whose short side is this
 * many px; `useLayout()` scales them to the real frame (1080x1920 and 1920x1080 both
 * have a short side of 1080, so both get factor 1).
 */
export const DESIGN_SHORT_SIDE = 1080;

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

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

const isDarkColor = (hex: string): boolean => {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128;
};

// ---------------------------------------------------------------------------
// Presets (mirror STYLE_PRESETS in src/argus/plan.py; the Python side expands
// presets before rendering, the engine needs them for v1 props and the Studio)
// ---------------------------------------------------------------------------

export const STYLE_PRESETS: Record<ThemeName, StyleTokens> = {
  dark: {
    colors: {
      bg: '#0A0A12',
      text: '#F5F6FA',
      muted: '#8A8FA3',
      accent: ACCENT_DEFAULT,
      word_base: 'rgba(245, 246, 250, 0.72)',
      word_active: '#FFFFFF',
      card_border: 'rgba(255, 255, 255, 0.08)',
    },
    fonts: {display: {family: FONT_FAMILY, weight: 900}, body: {family: FONT_FAMILY, weight: 600}},
    grain: 0.05,
    vignette: true,
  },
  light: {
    colors: {
      bg: '#F6F7FB',
      text: '#0A0A12',
      muted: '#6B7080',
      accent: ACCENT_DEFAULT,
      word_base: 'rgba(10, 10, 18, 0.62)',
      word_active: '#0A0A12',
      card_border: 'rgba(10, 10, 18, 0.10)',
    },
    fonts: {display: {family: FONT_FAMILY, weight: 900}, body: {family: FONT_FAMILY, weight: 600}},
    grain: 0.035,
    vignette: true,
  },
};

/** Same defaults as SAFE_AREA_DEFAULTS in plan.py. */
export const SAFE_AREA_DEFAULTS: Record<PlanFormat, SafeArea> = {
  '9:16': {top: 0.08, bottom: 0.2, left: 0.06, right: 0.12},
  '16:9': {top: 0.06, bottom: 0.08, left: 0.05, right: 0.05},
};

// ---------------------------------------------------------------------------
// Resolved style
// ---------------------------------------------------------------------------

export type ResolvedColors = {
  bg: string;
  text: string;
  muted: string;
  accent: string;
  /** Base color of a spoken/plain word (slightly dimmed). Token `word_base`. */
  wordBase: string;
  /** Color of the currently active word. Token `word_active`. */
  wordActive: string;
  /** Token `card_border`. */
  cardBorder: string;
} & Record<string, string>;

/**
 * Where a piece of text takes its font from.
 * - display: headlines (display font, token weight, 900 in the presets)
 * - heading: second-level headlines (display font, at most 700)
 * - body: kickers, captions, labels (body font, token weight)
 * - bodyLight: secondary lines (body font, 100 lighter than body)
 * - mono: numbers in the HUD (mono font when set, otherwise a system monospace)
 */
export type FontRole = 'display' | 'heading' | 'body' | 'bodyLight' | 'mono';

export type ResolvedFont = {
  family: string;
  weight: number;
  /** CSS `font-family` value with fallbacks. */
  css: string;
};

export type ResolvedStyle = {
  /** The background is dark (decides how strong shadows are). */
  isDark: boolean;
  colors: ResolvedColors;
  fonts: {display: FontRef; body: FontRef; mono?: FontRef};
  textScale: number;
  safeArea: SafeArea;
  background: Background;
  /** 0..1 opacity of the grain layer. */
  grain: number;
  /** CSS `background-image` for the vignette, or null when switched off. */
  vignette: string | null;
};

const FALLBACKS = "'Segoe UI', system-ui, sans-serif";
/** Monospace stack for HUD values (tabular digits); Consolas exists on every render host. */
const SYSTEM_MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, 'Roboto Mono', ui-monospace, monospace";

const quoteFamily = (family: string): string => `'${family.replace(/'/g, '')}'`;

export function fontFor(style: ResolvedStyle, role: FontRole): ResolvedFont {
  const {display, body, mono} = style.fonts;
  switch (role) {
    case 'display':
      return {family: display.family, weight: display.weight ?? 900, css: `${quoteFamily(display.family)}, ${FALLBACKS}`};
    case 'heading':
      return {
        family: display.family,
        weight: Math.min(display.weight ?? 900, 700),
        css: `${quoteFamily(display.family)}, ${FALLBACKS}`,
      };
    case 'body':
      return {family: body.family, weight: body.weight ?? 600, css: `${quoteFamily(body.family)}, ${FALLBACKS}`};
    case 'bodyLight':
      return {
        family: body.family,
        weight: Math.max(100, (body.weight ?? 600) - 100),
        css: `${quoteFamily(body.family)}, ${FALLBACKS}`,
      };
    case 'mono':
      return mono
        ? {family: mono.family, weight: mono.weight ?? 800, css: `${quoteFamily(mono.family)}, ${SYSTEM_MONO}`}
        : {family: 'Consolas', weight: 800, css: SYSTEM_MONO};
  }
}

const finitePositive = (v: unknown, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : fallback;

const finiteFraction = (v: unknown, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) && v >= 0 && v < 1 ? v : fallback;

function buildVignette(accent: string, bg: string, dark: boolean): string {
  const glow = withAlpha(accent, dark ? 0.1 : 0.07);
  const edge = dark
    ? `radial-gradient(160% 120% at 50% 55%, ${withAlpha(bg, 0)} 45%, rgba(0, 0, 0, 0.55) 100%)`
    : `radial-gradient(160% 120% at 50% 55%, ${withAlpha(bg, 0)} 50%, rgba(15, 20, 40, 0.06) 100%)`;
  return `radial-gradient(120% 75% at 50% 30%, ${glow} 0%, rgba(0, 0, 0, 0) 55%), ${edge}`;
}

/**
 * Turns a plan's `style` (tokens, or the name of a preset) into what the scenes read.
 * Every missing token falls back to the `dark` preset so a half-filled style still renders.
 * `accent` is the v1 `accent` prop: it overrides the accent color of the tokens.
 */
export function resolveStyle(
  input: StyleTokens | ThemeName | undefined,
  opts: {format: PlanFormat; accent?: string}
): ResolvedStyle {
  const dark = STYLE_PRESETS.dark;
  const tokens: StyleTokens =
    typeof input === 'string' ? STYLE_PRESETS[input] ?? dark : input && typeof input === 'object' ? input : dark;

  const colors: Record<string, string> = {...dark.colors, ...(tokens.colors ?? {})};
  if (opts.accent && opts.accent.trim() !== '') {
    colors.accent = opts.accent.trim();
  }
  const isDark = isDarkColor(colors.bg);
  const resolvedColors: ResolvedColors = {
    ...colors,
    bg: colors.bg,
    text: colors.text,
    muted: colors.muted,
    accent: colors.accent,
    wordBase: colors.word_base ?? withAlpha(colors.text, 0.72),
    wordActive: colors.word_active ?? colors.text,
    cardBorder: colors.card_border ?? withAlpha(colors.text, 0.1),
  };

  const safeDefault = SAFE_AREA_DEFAULTS[opts.format];
  const sa = tokens.safe_area;
  const safeArea: SafeArea = {
    top: finiteFraction(sa?.top, safeDefault.top),
    bottom: finiteFraction(sa?.bottom, safeDefault.bottom),
    left: finiteFraction(sa?.left, safeDefault.left),
    right: finiteFraction(sa?.right, safeDefault.right),
  };

  const grainDefault = typeof input === 'string' ? STYLE_PRESETS[input]?.grain ?? 0.05 : 0.05;
  return {
    isDark,
    colors: resolvedColors,
    fonts: {
      display: tokens.fonts?.display ?? dark.fonts.display,
      body: tokens.fonts?.body ?? dark.fonts.body,
      mono: tokens.fonts?.mono,
    },
    textScale: finitePositive(tokens.text_scale, 1),
    safeArea,
    background: tokens.background ?? {type: 'solid'},
    grain: Math.min(1, Math.max(0, typeof tokens.grain === 'number' ? tokens.grain : grainDefault)),
    vignette: tokens.vignette === false ? null : buildVignette(colors.accent, colors.bg, isDark),
  };
}

// ---------------------------------------------------------------------------
// Context and layout
// ---------------------------------------------------------------------------

export const StyleContext = createContext<ResolvedStyle | null>(null);

/** The style of the plan being rendered. Must be called under `Main`. */
export function useStyle(): ResolvedStyle {
  const style = useContext(StyleContext);
  if (!style) {
    throw new Error('useStyle() needs a StyleContext provider above it');
  }
  return style;
}

export type Layout = {
  width: number;
  height: number;
  /** min(width, height). */
  short: number;
  /** short / 1080. */
  scale: number;
  /** Geometry: n design px (short side 1080) to real px. */
  u: (n: number) => number;
  /** Text: like `u`, times the style's `text_scale`. */
  fs: (n: number) => number;
  /** The frame minus the safe-area margins, in px. Scene content is centered in it. */
  safe: {left: number; top: number; right: number; bottom: number; width: number; height: number};
};

export function useLayout(): Layout {
  const {width, height} = useVideoConfig();
  const style = useStyle();
  return useMemo(() => {
    const short = Math.min(width, height);
    const scale = short / DESIGN_SHORT_SIDE;
    const sa = style.safeArea;
    const left = width * sa.left;
    const right = width * sa.right;
    const top = height * sa.top;
    const bottom = height * sa.bottom;
    return {
      width,
      height,
      short,
      scale,
      u: (n: number) => n * scale,
      fs: (n: number) => n * scale * style.textScale,
      safe: {
        left,
        top,
        right,
        bottom,
        width: Math.max(1, width - left - right),
        height: Math.max(1, height - top - bottom),
      },
    };
  }, [width, height, style]);
}

// ---------------------------------------------------------------------------
// Media and fonts
// ---------------------------------------------------------------------------

/**
 * Media/voice sources: absolute URLs and data URIs pass through,
 * everything else is resolved against the public dir via staticFile.
 * The Python caller rewrites media into the job's public dir, so this
 * covers the engine-side contract.
 */
export function resolveMedia(src: string): string {
  if (/^(https?:|data:|blob:|file:)/i.test(src)) {
    return src;
  }
  return staticFile(src);
}

const fontLoads = new Map<string, Promise<void>>();
let fontsInFlight = 0;

function loadOnce(key: string, load: () => Promise<void>): void {
  if (fontLoads.has(key)) {
    return;
  }
  fontsInFlight++;
  fontLoads.set(
    key,
    load()
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error(`Failed to load font ${key}:`, err);
      })
      .finally(() => {
        fontsInFlight--;
      })
  );
}

/** True while a font requested through `ensureFonts` / `loadStyleFonts` is still loading. */
export const fontsLoading = (): boolean => fontsInFlight > 0;

/**
 * Loads the bundled Inter Display OTFs as family "Inter" with weights
 * 400/500/600/700/900 via @remotion/fonts (which delayRender()s until loaded).
 */
export function ensureFonts(): void {
  const files: Array<[string, string]> = [
    ['400', 'InterDisplay-Regular.otf'],
    ['500', 'InterDisplay-Medium.otf'],
    ['600', 'InterDisplay-Semibold.otf'],
    ['700', 'InterDisplay-Bold.otf'],
    ['900', 'InterDisplay-Black.otf'],
  ];
  for (const [weight, file] of files) {
    loadOnce(`${FONT_FAMILY}:${weight}`, () =>
      loadFont({family: FONT_FAMILY, url: staticFile(`fonts/${file}`), weight, style: 'normal'})
    );
  }
}

/**
 * Registers the font files of a plan (`FontRef.src`, relative to the public dir).
 * Families without `src` are not loaded: Inter comes from `ensureFonts()`, anything else
 * is looked up on the system. A project font is registered for the whole weight range so
 * the browser never fakes a bold from a regular file; a variable font uses the axis.
 */
export function loadStyleFonts(style: ResolvedStyle): void {
  const refs = [style.fonts.display, style.fonts.body, style.fonts.mono];
  for (const ref of refs) {
    if (!ref || !ref.src) {
      continue;
    }
    const src = ref.src;
    loadOnce(`${ref.family}:${src}`, () =>
      loadFont({family: ref.family, url: resolveMedia(src), weight: '100 900', style: 'normal'})
    );
  }
}

/** Resolves when every font requested so far is loaded. */
export function fontsSettled(): Promise<void> {
  return Promise.all([...fontLoads.values()]).then(() => undefined);
}

/**
 * Faint film grain, rendered from a deterministic SVG feTurbulence tile
 * used as a repeating CSS background. Static across frames, no PNG needed.
 */
const grainSvg = `<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='240' height='240' filter='url(#n)'/></svg>`;

export const grainBackgroundImage = `url("data:image/svg+xml,${encodeURIComponent(grainSvg)}")`;

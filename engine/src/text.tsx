import {useEffect, useState} from 'react';
import type {CSSProperties, FC} from 'react';
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Scene, WordTiming} from './types';
import {FONT_FAMILY} from './theme';
import type {ThemeColors} from './theme';

/** A word with absolute timings in seconds. */
export interface TimedWord {
  w: string;
  s: number;
  e: number;
}

/** A word with timings converted to frames local to its scene's Sequence. */
export interface LocalWord {
  w: string;
  appear: number;
  end: number;
}

export interface SceneWindow {
  start: number;
  end: number;
}

const TOKEN_STRIP = /[^\p{L}\p{N}]/gu;

export const normalizeToken = (w: string): string =>
  w.toLowerCase().replace(TOKEN_STRIP, '');

export const splitIntoWords = (text: string): string[] =>
  text.split(/\s+/).filter((t) => t.length > 0);

/** The text of a scene that participates in word sync ("" for card/counter). */
export const textOfScene = (scene: Scene): string => {
  switch (scene.kind) {
    case 'words':
    case 'title':
    case 'big':
    case 'cta':
      return scene.text;
    case 'act':
      return scene.title;
    default:
      return '';
  }
};

export const sceneWindows = (scenes: Scene[], duration: number): SceneWindow[] =>
  scenes.map((scene, i) => {
    const start = Math.max(0, scene.at);
    const next = i < scenes.length - 1 ? scenes[i + 1].at : duration;
    const end = Math.max(start + 0.1, next);
    return {start, end};
  });

/** Fallback: spread the scene's words evenly across the scene window. */
export const evenSpread = (words: string[], start: number, end: number): TimedWord[] => {
  if (words.length === 0) {
    return [];
  }
  const span = Math.max(0.2, end - start);
  const per = span / words.length;
  return words.map((w, i) => ({w, s: start + i * per, e: start + (i + 1) * per}));
};

/**
 * Assigns timings to every scene's words.
 *
 * If a global `words` list is present, scene words are matched against it in
 * order of appearance (case/punctuation-insensitive, small skip tolerance for
 * filler tokens). Words matched keep their global s/e timestamps. Any scene
 * whose matching fails falls back to an even spread across that scene's
 * window. Without a global list everything is evenly spread.
 */
export function assignWordTimings(
  scenes: Scene[],
  words: WordTiming[] | undefined,
  duration: number
): Map<number, TimedWord[]> {
  const result = new Map<number, TimedWord[]>();
  const windows = sceneWindows(scenes, duration);
  const globalWords = words ?? [];

  if (globalWords.length === 0) {
    scenes.forEach((scene, i) => {
      result.set(i, evenSpread(splitIntoWords(textOfScene(scene)), windows[i].start, windows[i].end));
    });
    return result;
  }

  let cursor = 0;
  scenes.forEach((scene, i) => {
    // последовательный курсор ест только речевые сцены: вставные (counter/chip/
    // card/act/cta) со своим текстом иначе крадут тайминги речи — сабы едут вперёд
    if (scene.kind !== 'words') {
      result.set(i, []);
      return;
    }
    const sceneWords = splitIntoWords(textOfScene(scene));
    if (sceneWords.length === 0) {
      result.set(i, []);
      return;
    }
    const matched: TimedWord[] = [];
    let ok = true;
    let c = cursor;
    for (const w of sceneWords) {
      const target = normalizeToken(w);
      let found = -1;
      // Small lookahead tolerance so filler ASR tokens don't desync everything.
      for (let k = 0; k < 3 && c + k < globalWords.length; k++) {
        if (normalizeToken(globalWords[c + k].w) === target) {
          found = c + k;
          break;
        }
      }
      if (found < 0) {
        ok = false;
        break;
      }
      matched.push({w, s: globalWords[found].s, e: globalWords[found].e});
      c = found + 1;
    }
    if (ok) {
      result.set(i, matched);
      cursor = c;
    } else {
      result.set(i, evenSpread(sceneWords, windows[i].start, windows[i].end));
    }
  });

  return result;
}

// ---------------------------------------------------------------------------
// Text measurement (canvas-based, matches the loaded "Inter" family exactly)
// ---------------------------------------------------------------------------

let measureCtx: CanvasRenderingContext2D | null | undefined;

const getMeasureContext = (): CanvasRenderingContext2D | null => {
  if (measureCtx === undefined) {
    try {
      measureCtx = document.createElement('canvas').getContext('2d');
    } catch {
      measureCtx = null;
    }
  }
  return measureCtx;
};

export const measureTextWidth = (
  text: string,
  weight: number,
  sizePx: number,
  letterSpacingEm: number
): number => {
  const ctx = getMeasureContext();
  if (!ctx) {
    return 0;
  }
  ctx.font = `${weight} ${sizePx}px ${FONT_FAMILY}`;
  const width = ctx.measureText(text).width;
  return width + letterSpacingEm * sizePx * Math.max(0, [...text].length - 1);
};

/**
 * True once document.fonts has settled. Canvas measurements made before the
 * webfonts are ready use fallback metrics, so fit-to-width results are only
 * trusted after this flips (fonts are delayRender-guarded by @remotion/fonts,
 * so captured frames always see the corrected values).
 */
export const useFontsReady = (): boolean => {
  const [ready, setReady] = useState<boolean>(
    () => typeof document === 'undefined' || !document.fonts || document.fonts.status === 'loaded'
  );
  useEffect(() => {
    if (ready) {
      return;
    }
    let cancelled = false;
    const done = () => {
      if (!cancelled) {
        setReady(true);
      }
    };
    (document.fonts ? document.fonts.ready : Promise.resolve()).then(done, done);
    return () => {
      cancelled = true;
    };
  }, [ready]);
  return ready;
};

/** interpolate() requires strictly increasing ranges; this guards degenerate ones. */
export const clampRange = (a: number, b: number): [number, number] =>
  b > a ? [a, b] : [a, a + 1];

// ---------------------------------------------------------------------------
// Layout helpers
// ---------------------------------------------------------------------------

/** Splits items into lines, distributing them as evenly as possible. */
export function chunkLines<T>(items: T[], maxPerLine: number): T[][] {
  const n = items.length;
  if (n === 0) {
    return [];
  }
  const lineCount = Math.max(1, Math.ceil(n / Math.max(1, maxPerLine)));
  const base = Math.floor(n / lineCount);
  const extra = n % lineCount;
  const lines: T[][] = [];
  let idx = 0;
  for (let i = 0; i < lineCount; i++) {
    const take = base + (i < extra ? 1 : 0);
    lines.push(items.slice(idx, idx + take));
    idx += take;
  }
  return lines;
}

/** Font size that keeps every line within availableWidth (shrink-only). */
export const fitLines = (
  lines: string[],
  weight: number,
  baseSize: number,
  availableWidth: number,
  letterSpacingEm: number,
  minSize: number
): number => {
  let widest = 0;
  for (const line of lines) {
    widest = Math.max(widest, measureTextWidth(line, weight, baseSize, letterSpacingEm));
  }
  if (widest <= 0 || widest <= availableWidth) {
    return baseSize;
  }
  return Math.max(minSize, (baseSize * availableWidth) / widest);
};

// ---------------------------------------------------------------------------
// Word
// ---------------------------------------------------------------------------

/**
 * One kinetic word: spring pop (scale 0.6 -> 1, opacity 0 -> 1, ~0.35s)
 * at its appearance frame. Active words are brighter and get an accent
 * underline that sweeps in while the word is being spoken, then fades out.
 */
export const Word: FC<{
  word: LocalWord;
  size: number;
  active: boolean;
  colors: ThemeColors;
  underline?: boolean;
}> = ({word, size, active, colors, underline = true}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const pop = spring({
    frame: frame - word.appear,
    fps,
    config: {damping: 13, stiffness: 170, mass: 0.7},
    durationInFrames: Math.max(1, Math.round(fps * 0.35)),
  });
  const scale = 0.6 + 0.4 * pop;
  const opacity = Math.min(1, pop * 1.4);

  let underlineStyle: CSSProperties | null = null;
  if (underline) {
    const sweepEnd = Math.max(word.end, word.appear + 1);
    const sweep = interpolate(frame, clampRange(word.appear, sweepEnd), [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.out(Easing.quad),
    });
    const fade = interpolate(
      frame,
      clampRange(word.end, word.end + Math.round(fps * 0.22)),
      [1, 0],
      {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
    );
    const uOpacity = frame < word.appear ? 0 : frame < sweepEnd ? 1 : fade;
    underlineStyle = {
      position: 'absolute',
      left: '0.06em',
      right: '0.06em',
      bottom: '-0.12em',
      height: Math.max(5, Math.round(size * 0.055)),
      borderRadius: 999,
      background: colors.accent,
      transformOrigin: 'left center',
      transform: `scaleX(${sweep.toFixed(3)})`,
      opacity: uOpacity,
    };
  }

  return (
    <span
      style={{
        position: 'relative',
        display: 'inline-block',
        margin: '0 0.13em',
        color: active ? colors.wordActive : colors.wordBase,
        transform: `scale(${scale.toFixed(4)})`,
        transformOrigin: 'center bottom',
        opacity,
      }}
    >
      {word.w}
      {underlineStyle ? <span style={underlineStyle} /> : null}
    </span>
  );
};

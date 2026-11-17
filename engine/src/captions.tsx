import {useMemo} from 'react';
import type {CSSProperties, FC} from 'react';
import {AbsoluteFill, Sequence, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {CaptionStyle, Captions, WordTiming} from './types';
import {DESIGN_SHORT_SIDE, fontFor, useLayout, useStyle} from './style';
import {fitLines, fitSizeToHeight, normalizeToken, useFontsReady} from './text';

// Same limits as `group_phrases` in src/argus/captions.py: change both together.
export const PHRASE_MAX_WORDS = 4;
export const PHRASE_MAX_CHARS = 26;
export const PHRASE_GAP_S = 0.45;

/** Phrase mode shows a line this long before its first word is spoken. */
const PHRASE_LEAD_S = 0.06;
/** A phrase stays this long after its last word (or until the next phrase starts). */
const PHRASE_HOLD_S = 0.35;
/** Word mode keeps a word up until the next one if the pause is at most this long. */
const WORD_BRIDGE_S = 0.4;
/** Word mode: how long a word stays after it ends when the pause is longer. */
const WORD_HOLD_S = 0.18;
/** The active word stays highlighted up to this long after it ends, if no word follows. */
const ACTIVE_TAIL_S = 0.15;

const DEFAULT_SIZE_PHRASE = 0.065;
const DEFAULT_SIZE_WORD = 0.1;
const DEFAULT_OUTLINE = 0.006;
const DEFAULT_SHADOW = 0.004;
const LINE_HEIGHT = 1.12;
const MAX_ROWS = 2;
/** Active word grows by this factor (word mode and phrase mode). */
const ACTIVE_SCALE = 1.08;

export type CaptionMode = 'word' | 'phrase';

/** One on-screen caption: a single word (word mode) or a short phrase. Seconds, absolute. */
export type CaptionLine = {
  words: WordTiming[];
  start: number;
  end: number;
};

// ---------------------------------------------------------------------------
// Words -> lines (pure)
// ---------------------------------------------------------------------------

/** Drops broken entries, sorts by start and gives every word a minimal length. */
export function sanitizeWords(words: readonly WordTiming[] | undefined): WordTiming[] {
  const out: WordTiming[] = [];
  for (const x of words ?? []) {
    if (!x || typeof x.w !== 'string' || x.w.trim() === '') {
      continue;
    }
    if (!Number.isFinite(x.s) || !Number.isFinite(x.e)) {
      continue;
    }
    out.push({w: x.w.trim(), s: Math.max(0, x.s), e: Math.max(x.e, x.s + 0.05)});
  }
  return out.sort((a, b) => a.s - b.s);
}

/** Short on-screen phrases: breaks on sentence end, pause, word or character budget. */
export function groupPhrases(words: WordTiming[]): WordTiming[][] {
  const lines: WordTiming[][] = [];
  let cur: WordTiming[] = [];
  for (const w of words) {
    if (cur.length > 0) {
      const chars = cur.reduce((n, x) => n + x.w.length + 1, 0) + w.w.length;
      const pause = w.s - cur[cur.length - 1].e;
      const lastChar = cur[cur.length - 1].w.slice(-1);
      if (
        cur.length >= PHRASE_MAX_WORDS ||
        chars > PHRASE_MAX_CHARS ||
        pause > PHRASE_GAP_S ||
        '.!?…'.includes(lastChar)
      ) {
        lines.push(cur);
        cur = [];
      }
    }
    cur.push(w);
  }
  if (cur.length > 0) {
    lines.push(cur);
  }
  return lines;
}

/** Word mode shows a word without the punctuation that trails it. */
const stripTrailing = (w: string): string => {
  const s = w.replace(/[,.;:]+$/u, '');
  return s === '' ? w : s;
};

/**
 * Turns timed words into lines with a visible window each. Windows never overlap: a line
 * ends at the latest when the next one starts.
 */
export function buildCaptionLines(words: readonly WordTiming[] | undefined, mode: CaptionMode): CaptionLine[] {
  const clean = sanitizeWords(words);
  const groups: WordTiming[][] =
    mode === 'word'
      ? clean.map((w) => [{...w, w: stripTrailing(w.w)}])
      : groupPhrases(clean);

  const lines: CaptionLine[] = [];
  let prevEnd = 0;
  groups.forEach((ws, i) => {
    const first = ws[0].s;
    const last = ws[ws.length - 1].e;
    const nextStart = i + 1 < groups.length ? groups[i + 1][0].s : Infinity;
    const lead = mode === 'word' ? 0 : PHRASE_LEAD_S;
    const start = Math.min(first, Math.max(first - lead, prevEnd));
    let end: number;
    if (mode === 'word') {
      end = nextStart - last <= WORD_BRIDGE_S ? nextStart : last + WORD_HOLD_S;
    } else {
      end = Math.min(last + PHRASE_HOLD_S, nextStart);
    }
    end = Math.max(end, start + 0.05);
    lines.push({words: ws, start, end});
    prevEnd = end;
  });
  return lines;
}

/**
 * Whether `word` is an accent word. A pattern is an exact word, a prefix ending in `*`,
 * or `*` for every word. Case and punctuation are ignored.
 */
export function matchesAccent(word: string, patterns: readonly string[] | undefined): boolean {
  const token = normalizeToken(word);
  for (const raw of patterns ?? []) {
    const p = (raw ?? '').trim();
    if (p === '*') {
      return true;
    }
    if (p.endsWith('*')) {
      const prefix = normalizeToken(p.slice(0, -1));
      if (prefix !== '' && token.startsWith(prefix)) {
        return true;
      }
    } else {
      const exact = normalizeToken(p);
      if (exact !== '' && token === exact) {
        return true;
      }
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

type CaptionLook = {
  mode: CaptionMode;
  position: 'upper' | 'center' | 'lower';
  /** Size as a fraction of the short side. */
  size: number;
  fontRole: 'display' | 'body';
  color: string;
  activeColor: string;
  /** Explicit upcoming color; without one, upcoming words are the base color at half opacity. */
  upcomingColor?: string;
  outline: number;
  shadow: number;
  plate?: string;
  accentWords: string[];
};

const isFiniteNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

function useCaptionLook(captions: Captions): CaptionLook {
  const {colors} = useStyle();
  const mode: CaptionMode = captions.mode === 'word' ? 'word' : 'phrase';
  const st: CaptionStyle = captions.style ?? {};
  return {
    mode,
    position: captions.position ?? 'lower',
    size: isFiniteNumber(st.size) && st.size > 0 ? st.size : mode === 'word' ? DEFAULT_SIZE_WORD : DEFAULT_SIZE_PHRASE,
    fontRole: st.font === 'body' ? 'body' : 'display',
    color: st.color ?? colors.text,
    activeColor: st.active_color ?? colors.wordActive,
    upcomingColor: st.upcoming_color,
    outline: isFiniteNumber(st.outline) && st.outline >= 0 ? st.outline : DEFAULT_OUTLINE,
    shadow: isFiniteNumber(st.shadow) && st.shadow >= 0 ? st.shadow : DEFAULT_SHADOW,
    plate: st.plate,
    accentWords: captions.accent_words ?? [],
  };
}

const CaptionLineView: FC<{
  line: CaptionLine;
  /** Frame of the line's Sequence on the timeline, to get absolute time from the local frame. */
  fromFrame: number;
  look: CaptionLook;
}> = ({line, fromFrame, look}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const style = useStyle();
  const {fs, safe} = useLayout();
  useFontsReady();

  const font = fontFor(style, look.fontRole);
  const wordMode = look.mode === 'word';
  const plateX = look.plate ? 0.4 : 0;

  // Size in px, shrunk when a word is wider than the safe width or the phrase needs more
  // than MAX_ROWS rows.
  const size = useMemo(() => {
    const base = fs(look.size * DESIGN_SHORT_SIDE);
    const available = Math.max(1, safe.width * 0.96 - plateX * 2 * base);
    const texts = line.words.map((w) => w.w);
    let s = fitLines(texts, font.css, font.weight, base, available, 0, base * 0.4);
    if (!wordMode) {
      s = fitSizeToHeight(
        texts.join(' '),
        font.css,
        font.weight,
        s,
        0,
        available,
        LINE_HEIGHT,
        s * LINE_HEIGHT * MAX_ROWS + 1,
        base * 0.5
      );
    }
    return s;
  }, [fs, look.size, safe.width, plateX, line, font.css, font.weight, wordMode]);

  const pop = spring({
    frame,
    fps,
    config: {damping: 14, stiffness: 220, mass: 0.6},
    durationInFrames: Math.max(1, Math.round(fps * 0.25)),
  });
  const lineScale = wordMode ? 0.7 + 0.3 * pop : 0.9 + 0.1 * pop;
  const t = (frame + fromFrame) / fps;

  const stroke = Math.max(0, fs(look.outline * DESIGN_SHORT_SIDE));
  const shadowPx = Math.max(0, fs(look.shadow * DESIGN_SHORT_SIDE));

  const justify = look.position === 'upper' ? 'flex-start' : look.position === 'center' ? 'center' : 'flex-end';

  const wordNodes = line.words.map((w, i) => {
    const next = line.words[i + 1];
    const accent = matchesAccent(w.w, look.accentWords);
    let state: 'upcoming' | 'active' | 'spoken';
    if (wordMode) {
      state = 'active';
    } else if (t < w.s) {
      state = 'upcoming';
    } else if (t < (next ? next.s : w.e + ACTIVE_TAIL_S)) {
      state = 'active';
    } else {
      state = 'spoken';
    }

    const base = accent ? style.colors.accent : state === 'active' ? look.activeColor : look.color;
    const wordStyle: CSSProperties = {
      display: 'inline-block',
      color: base,
      transform: state === 'active' && !wordMode ? `scale(${ACTIVE_SCALE})` : undefined,
      transformOrigin: 'center bottom',
    };
    if (state === 'upcoming') {
      if (look.upcomingColor && !accent) {
        wordStyle.color = look.upcomingColor;
      } else {
        wordStyle.opacity = accent ? 0.65 : 0.5;
      }
    }
    return (
      <span key={i} style={wordStyle}>
        {w.w}
      </span>
    );
  });

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: safe.left,
          top: safe.top,
          width: safe.width,
          height: safe.height,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: justify,
          alignItems: 'center',
        }}
      >
        <div
          style={{
            boxSizing: 'border-box',
            maxWidth: safe.width,
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            columnGap: '0.26em',
            rowGap: '0.04em',
            textAlign: 'center',
            fontFamily: font.css,
            fontWeight: font.weight,
            fontSize: size,
            lineHeight: LINE_HEIGHT,
            padding: look.plate ? `0.16em ${plateX}em` : undefined,
            borderRadius: look.plate ? '0.3em' : undefined,
            background: look.plate,
            WebkitTextStroke: stroke > 0 ? `${stroke.toFixed(2)}px ${style.colors.bg}` : undefined,
            paintOrder: 'stroke fill',
            textShadow:
              shadowPx > 0
                ? `0 ${shadowPx.toFixed(2)}px ${(shadowPx * 2.5).toFixed(2)}px rgba(0, 0, 0, ${style.isDark ? 0.55 : 0.28})`
                : undefined,
            opacity: Math.min(1, pop * 1.6),
            transform: `scale(${lineScale.toFixed(4)})`,
            transformOrigin: 'center bottom',
          }}
        >
          {wordNodes}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/**
 * Captions from timed words, above the scenes and the HUD. `captions.words` must already be
 * a word list: the Python side loads files and remaps clip transcripts before it renders,
 * so a path or `{source, remap}` here draws nothing.
 */
export const CaptionsLayer: FC<{captions: Captions}> = ({captions}) => {
  const {fps} = useVideoConfig();
  const look = useCaptionLook(captions);
  const words = Array.isArray(captions.words) ? captions.words : undefined;

  const lines = useMemo(() => buildCaptionLines(words, look.mode), [words, look.mode]);

  return (
    <>
      {lines.map((line, i) => {
        const from = Math.max(0, Math.round(line.start * fps));
        const dur = Math.max(1, Math.round(line.end * fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`caption-${i}`}>
            <CaptionLineView line={line} fromFrame={from} look={look} />
          </Sequence>
        );
      })}
    </>
  );
};

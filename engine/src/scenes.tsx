import {useMemo} from 'react';
import type {CSSProperties, FC, ReactNode} from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  OffthreadVideo,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {
  ActScene,
  BigScene,
  CardScene,
  CounterScene,
  CtaScene,
  TitleScene,
  WordsScene,
} from './types';
import {resolveMedia, withAlpha} from './theme';
import type {ThemeColors} from './theme';
import {
  chunkLines,
  clampRange,
  fitLines,
  measureTextWidth,
  useFontsReady,
  Word,
} from './text';
import type {LocalWord} from './text';

const CLAMP = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// ---------------------------------------------------------------------------
// SceneShell: shared entrance (fade in from slight blur/scale) and exit
// (fade + slide up during the last 0.25s before the next scene's `at`).
// Sequences never overlap, so two texts are never stacked.
// ---------------------------------------------------------------------------

export const SceneShell: FC<{
  durationInFrames: number;
  children: ReactNode;
}> = ({durationInFrames, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const enterDur = Math.max(1, Math.round(fps * 0.35));
  const exitDur = Math.max(1, Math.round(fps * 0.25));

  const enter = interpolate(frame, [0, enterDur], [0, 1], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });
  const exitStart = Math.max(0, durationInFrames - exitDur);
  const exit = interpolate(frame, clampRange(exitStart, Math.max(exitStart + 1, durationInFrames - 1)), [0, 1], {
    ...CLAMP,
    easing: Easing.in(Easing.quad),
  });

  const opacity = enter * (1 - exit);
  const blur = (1 - enter) * 10;
  const scale = 1 + (1 - enter) * 0.03;
  const y = -56 * exit;

  return (
    <AbsoluteFill
      style={{
        opacity,
        filter: blur > 0.15 ? `blur(${blur.toFixed(2)}px)` : undefined,
        transform: `translateY(${y.toFixed(2)}px) scale(${scale.toFixed(4)})`,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 1. words — the workhorse: word-by-word text at ~42% height, Black,
//    max 3 words per line (re-chunked to 2/1 if that avoids shrinking),
//    active word brighter + accent underline sweep.
// ---------------------------------------------------------------------------

const WORDS_BASE = 104;
const WORDS_TRACKING = -0.03;

export const WordsSceneView: FC<{
  scene: WordsScene;
  words: LocalWord[];
  colors: ThemeColors;
}> = ({words, colors}) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady();

  const layout = useMemo(() => {
    if (!ready || words.length === 0) {
      return null;
    }
    const avail = 1080 * 0.9;
    let best: {lines: LocalWord[][]; size: number} | null = null;
    for (const maxPer of [3, 2, 1]) {
      const lines = chunkLines(words, maxPer);
      const size = fitLines(
        lines.map((l) => l.map((x) => x.w).join(' ')),
        900,
        WORDS_BASE,
        avail,
        WORDS_TRACKING,
        40
      );
      if (!best || size > best.size) {
        best = {lines, size};
      }
      if (size >= 88) {
        break;
      }
    }
    return best;
  }, [words, ready]);

  if (!layout) {
    return null;
  }

  const activeIdx = words.findIndex((w) => frame >= w.appear && frame < w.end);
  let flat = 0;

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', paddingBottom: '16%'}}>
      <div style={{textAlign: 'center'}}>
        {layout.lines.map((line, li) => (
          <div
            key={li}
            style={{
              whiteSpace: 'nowrap',
              fontSize: layout.size,
              lineHeight: 1.18,
              letterSpacing: `${WORDS_TRACKING}em`,
              fontWeight: 900,
            }}
          >
            {line.map((w) => {
              const idx = flat++;
              return (
                <Word key={idx} word={w} size={layout.size} active={idx === activeIdx} colors={colors} underline />
              );
            })}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 2. title — small uppercase kicker (0.2em tracking, muted) above a huge
//    Black headline. Kicker appears first, headline springs in after.
// ---------------------------------------------------------------------------

export const TitleSceneView: FC<{
  scene: TitleScene;
  colors: ThemeColors;
}> = ({scene, colors}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();

  const headWords = useMemo(() => scene.text.split(/\s+/).filter(Boolean), [scene.text]);
  const size = useMemo(() => {
    if (!ready || headWords.length === 0) {
      return null;
    }
    const avail = 1080 * 0.86;
    let widest = 0;
    for (const w of headWords) {
      widest = Math.max(widest, measureTextWidth(w, 900, 118, -0.035));
    }
    if (widest <= avail) {
      return 118;
    }
    return Math.max(72, (118 * avail) / widest);
  }, [headWords, ready]);

  const kIn = interpolate(frame, [0, Math.max(1, Math.round(fps * 0.3))], [0, 1], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });
  const hSpring = spring({
    frame: frame - Math.round(fps * 0.18),
    fps,
    config: {damping: 16, stiffness: 130, mass: 0.8},
    durationInFrames: Math.max(1, Math.round(fps * 0.45)),
  });

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', paddingBottom: '8%'}}>
      <div style={{textAlign: 'center', maxWidth: '88%'}}>
        {scene.kicker ? (
          <div
            style={{
              fontSize: 44,
              fontWeight: 600,
              letterSpacing: '0.2em',
              textTransform: 'uppercase',
              color: colors.muted,
              opacity: kIn,
              transform: `translateY(${((1 - kIn) * 18).toFixed(2)}px)`,
              marginBottom: 34,
            }}
          >
            {scene.kicker}
          </div>
        ) : null}
        <div
          style={{
            fontSize: size ?? 118,
            fontWeight: 900,
            lineHeight: 1.05,
            letterSpacing: '-0.035em',
            opacity: hSpring,
            transform: `translateY(${((1 - hSpring) * 30).toFixed(2)}px)`,
          }}
        >
          {scene.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 3. card — rounded 32px media card (image or video), 78% width, 1px border,
//    accent glow on entrance, slow Ken Burns zoom 1.0 -> 1.06, caption below.
// ---------------------------------------------------------------------------

export const CardSceneView: FC<{
  scene: CardScene;
  colors: ThemeColors;
}> = ({scene, colors}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const enter = spring({
    frame,
    fps,
    config: {damping: 18, stiffness: 110, mass: 0.9},
    durationInFrames: Math.max(1, Math.round(fps * 0.5)),
  });
  const kenBurns = interpolate(frame, [0, Math.max(1, durationInFrames)], [1, 1.06], CLAMP);
  const glow = Math.max(0, 1 - enter);
  const isVideo = /\.(mp4|m4v|webm|mov)(\?.*)?$/i.test(scene.media);
  const fit = scene.fit === 'contain' ? 'contain' : 'cover';

  const mediaStyle: CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: fit,
  };

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          width: '78%',
          opacity: enter,
          transform: `scale(${(0.94 + 0.06 * enter).toFixed(4)})`,
        }}
      >
        <div
          style={{
            position: 'relative',
            width: '100%',
            height: 1150,
            borderRadius: 32,
            overflow: 'hidden',
            border: `1px solid ${colors.cardBorder}`,
            boxShadow: `0 30px 90px rgba(0, 0, 0, ${colors.name === 'dark' ? 0.45 : 0.1}), 0 0 ${Math.round(70 * glow)}px ${withAlpha(colors.accent, 0.4 * glow)}`,
          }}
        >
          <div style={{position: 'absolute', inset: 0, transform: `scale(${kenBurns.toFixed(4)})`}}>
            {isVideo ? (
              <OffthreadVideo muted src={resolveMedia(scene.media)} style={mediaStyle} />
            ) : (
              <Img src={resolveMedia(scene.media)} style={mediaStyle} />
            )}
          </div>
        </div>
        {scene.caption ? (
          <div
            style={{
              marginTop: 40,
              fontSize: 46,
              fontWeight: 600,
              color: colors.text,
              opacity: 0.92,
              textAlign: 'center',
              letterSpacing: '-0.01em',
            }}
          >
            {scene.caption}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 4. big — one word/short phrase, accent color, fit-to-width: starts at
//    200px, shrinks to fit 90% width; wraps only if it would go below 90px.
// ---------------------------------------------------------------------------

export const BigSceneView: FC<{
  scene: BigScene;
  colors: ThemeColors;
}> = ({scene, colors}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();

  const layout = useMemo(() => {
    if (!ready) {
      return null;
    }
    const avail = 1080 * 0.9;
    const width = measureTextWidth(scene.text, 900, 200, -0.04);
    if (width <= 0 || width <= avail) {
      return {size: 200, wrap: false};
    }
    const size = (200 * avail) / width;
    if (size >= 90) {
      return {size, wrap: false};
    }
    // Wrap into lines; make sure the longest single word still fits.
    const ws = scene.text.split(/\s+/).filter(Boolean);
    let widest = 0;
    for (const w of ws) {
      widest = Math.max(widest, measureTextWidth(w, 900, 90, -0.04));
    }
    const lineAvail = 1080 * 0.86;
    return {
      size: widest > lineAvail ? Math.max(40, (90 * lineAvail) / widest) : 90,
      wrap: true,
    };
  }, [scene.text, ready]);

  const pop = spring({
    frame,
    fps,
    config: {damping: 14, stiffness: 140, mass: 0.8},
    durationInFrames: Math.max(1, Math.round(fps * 0.45)),
  });

  if (!layout) {
    return null;
  }

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', paddingBottom: '8%'}}>
      <div
        style={{
          fontSize: layout.size,
          fontWeight: 900,
          color: colors.accent,
          letterSpacing: '-0.04em',
          lineHeight: 1.02,
          textAlign: 'center',
          whiteSpace: layout.wrap ? 'normal' : 'nowrap',
          maxWidth: layout.wrap ? '86%' : undefined,
          opacity: pop,
          transform: `scale(${(0.9 + 0.1 * pop).toFixed(4)})`,
        }}
      >
        {scene.text}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 5. counter — huge number counting 0 -> value with easeOut over 0.9s
//    starting 0.2s into the scene; accent suffix beside, muted sub below.
// ---------------------------------------------------------------------------

export const CounterSceneView: FC<{
  scene: CounterScene;
  colors: ThemeColors;
}> = ({scene, colors}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const start = Math.round(fps * 0.2);
  const countDur = Math.max(1, Math.round(fps * 0.9));
  const p = interpolate(frame, [start, start + countDur], [0, 1], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });
  const shown = scene.value * p;
  const valueText = Number.isFinite(scene.value)
    ? Number.isInteger(scene.value)
      ? String(Math.round(shown))
      : shown.toFixed(1)
    : '0';

  const subStart = start + countDur;
  const subIn = interpolate(frame, [subStart, subStart + Math.max(1, Math.round(fps * 0.35))], [0, 1], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', paddingBottom: '9%'}}>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        <div style={{display: 'flex', alignItems: 'baseline'}}>
          <span
            style={{
              fontSize: 220,
              fontWeight: 900,
              letterSpacing: '-0.04em',
              lineHeight: 1,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {valueText}
          </span>
          {scene.suffix ? (
            <span
              style={{
                fontSize: 96,
                fontWeight: 600,
                color: colors.accent,
                marginLeft: 14,
                letterSpacing: '-0.02em',
              }}
            >
              {scene.suffix}
            </span>
          ) : null}
        </div>
        {scene.sub ? (
          <div
            style={{
              marginTop: 34,
              fontSize: 52,
              fontWeight: 500,
              color: colors.muted,
              textAlign: 'center',
              maxWidth: 860,
              letterSpacing: '-0.01em',
              opacity: subIn,
              transform: `translateY(${((1 - subIn) * 20).toFixed(2)}px)`,
            }}
          >
            {scene.sub}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 6. act — accent index "02 /" then chapter title words pop in (Bold 92px).
// ---------------------------------------------------------------------------

export const ActSceneView: FC<{
  scene: ActScene;
  words: LocalWord[];
  colors: ThemeColors;
}> = ({scene, words, colors}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const idxIn = spring({
    frame: frame - Math.round(fps * 0.1),
    fps,
    config: {damping: 200, stiffness: 100},
    durationInFrames: Math.max(1, Math.round(fps * 0.35)),
  });
  const activeIdx = words.findIndex((w) => frame >= w.appear && frame < w.end);

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', paddingBottom: '9%'}}>
      <div style={{textAlign: 'center', maxWidth: '88%'}}>
        <div
          style={{
            fontSize: 64,
            fontWeight: 600,
            letterSpacing: '0.08em',
            marginBottom: 30,
            opacity: idxIn,
            transform: `translateY(${((1 - idxIn) * 16).toFixed(2)}px)`,
          }}
        >
          <span style={{color: colors.accent}}>{scene.index ?? '01'}</span>
          <span style={{color: colors.muted}}> /</span>
        </div>
        <div style={{fontSize: 92, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.16}}>
          {words.map((w, i) => (
            <Word key={i} word={w} size={92} active={i === activeIdx} colors={colors} underline={false} />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// 7. cta — centered text (Bold 100px), accent handle 0.4s later, subtle
//    pulsing arrow-down ring below.
// ---------------------------------------------------------------------------

export const CtaSceneView: FC<{
  scene: CtaScene;
  colors: ThemeColors;
}> = ({scene, colors}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();

  const size = useMemo(() => {
    if (!ready) {
      return null;
    }
    const avail = 1080 * 0.84;
    const ws = scene.text.split(/\s+/).filter(Boolean);
    let widest = 0;
    for (const w of ws) {
      widest = Math.max(widest, measureTextWidth(w, 700, 100, -0.03));
    }
    return widest > avail ? Math.max(60, (100 * avail) / widest) : 100;
  }, [scene.text, ready]);

  const tIn = spring({
    frame,
    fps,
    config: {damping: 16, stiffness: 130, mass: 0.8},
    durationInFrames: Math.max(1, Math.round(fps * 0.45)),
  });
  const hIn = spring({
    frame: frame - Math.round(fps * 0.4),
    fps,
    config: {damping: 15, stiffness: 130, mass: 0.8},
    durationInFrames: Math.max(1, Math.round(fps * 0.4)),
  });
  const ringIn = interpolate(frame, [Math.round(fps * 0.6), Math.round(fps * 1.1)], [0, 1], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });
  const pulse = 1 + 0.07 * Math.sin((frame / fps) * ((Math.PI * 2) / 1.6));

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', paddingBottom: '4%'}}>
      <div style={{textAlign: 'center'}}>
        <div
          style={{
            fontSize: size ?? 100,
            fontWeight: 700,
            letterSpacing: '-0.03em',
            lineHeight: 1.08,
            maxWidth: '86%',
            opacity: tIn,
            transform: `translateY(${((1 - tIn) * 26).toFixed(2)}px)`,
          }}
        >
          {scene.text}
        </div>
        {scene.handle ? (
          <div
            style={{
              marginTop: 40,
              fontSize: 64,
              fontWeight: 600,
              color: colors.accent,
              letterSpacing: '-0.01em',
              opacity: hIn,
              transform: `translateY(${((1 - hIn) * 18).toFixed(2)}px)`,
            }}
          >
            {scene.handle}
          </div>
        ) : null}
        <div
          style={{
            marginTop: 46,
            display: 'flex',
            justifyContent: 'center',
            opacity: ringIn,
            transform: `scale(${pulse.toFixed(4)})`,
          }}
        >
          <svg width="84" height="84" viewBox="0 0 84 84">
            <circle cx="42" cy="42" r="40" fill="none" stroke={colors.accent} strokeOpacity="0.5" strokeWidth="2.5" />
            <path
              d="M42 24 v30 M30 44 l12 12 12 -12"
              fill="none"
              stroke={colors.accent}
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>
    </AbsoluteFill>
  );
};

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
  ChipItem,
  ChipScene,
  CounterScene,
  CtaScene,
  TitleScene,
  WordsScene,
} from './types';
import {fontFor, resolveMedia, useLayout, useStyle, withAlpha} from './style';
import {
  chunkLines,
  clampRange,
  fitLines,
  fitSizeToHeight,
  measureTextWidth,
  useFontsReady,
  Word,
} from './text';
import type {LocalWord} from './text';

const CLAMP = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// Every size below is a design number for a frame with a 1080 px short side. `u(n)` (geometry)
// and `fs(n)` (text, also times `text_scale`) from `useLayout()` turn it into real pixels, and
// `layout.safe` is the area text may use.

// ---------------------------------------------------------------------------
// SceneShell: shared entrance (fade in from slight blur/scale) and exit
// (fade + slide up during the last 0.25s of the scene's window). It also centers the
// scene's content inside the safe area.
// ---------------------------------------------------------------------------

export const SceneShell: FC<{
  durationInFrames: number;
  children: ReactNode;
}> = ({durationInFrames, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {u, safe} = useLayout();

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
  const blur = (1 - enter) * u(10);
  const scale = 1 + (1 - enter) * 0.03;
  const y = -u(56) * exit;

  return (
    <AbsoluteFill
      style={{
        boxSizing: 'border-box',
        paddingTop: safe.top,
        paddingBottom: safe.bottom,
        paddingLeft: safe.left,
        paddingRight: safe.right,
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
// 1. words — the workhorse: word-by-word text, Black, max 3 words per line
//    (re-chunked to 2/1 if that avoids shrinking), active word brighter + accent
//    underline sweep.
// ---------------------------------------------------------------------------

const WORDS_BASE = 104;
const WORDS_LINE_HEIGHT = 1.18;
const WORDS_TRACKING = -0.03;

export const WordsSceneView: FC<{
  scene: WordsScene;
  words: LocalWord[];
}> = ({words}) => {
  const frame = useCurrentFrame();
  const ready = useFontsReady();
  const style = useStyle();
  const {fs, safe} = useLayout();
  const font = fontFor(style, 'display');

  const layout = useMemo(() => {
    if (!ready || words.length === 0) {
      return null;
    }
    let best: {lines: LocalWord[][]; size: number} | null = null;
    for (const maxPer of [3, 2, 1]) {
      const lines = chunkLines(words, maxPer);
      let size = fitLines(
        lines.map((l) => l.map((x) => x.w).join(' ')),
        font.css,
        font.weight,
        fs(WORDS_BASE),
        safe.width,
        WORDS_TRACKING,
        fs(40)
      );
      size = Math.min(size, safe.height / (lines.length * WORDS_LINE_HEIGHT));
      if (!best || size > best.size) {
        best = {lines, size};
      }
      if (size >= fs(88)) {
        break;
      }
    }
    return best;
  }, [words, ready, font.css, font.weight, fs, safe.width, safe.height]);

  if (!layout) {
    return null;
  }

  const activeIdx = words.findIndex((w) => frame >= w.appear && frame < w.end);
  let flat = 0;

  return (
    <div style={{textAlign: 'center', maxWidth: '100%', fontFamily: font.css}}>
      {layout.lines.map((line, li) => (
        <div
          key={li}
          style={{
            whiteSpace: 'nowrap',
            fontSize: layout.size,
            lineHeight: WORDS_LINE_HEIGHT,
            letterSpacing: `${WORDS_TRACKING}em`,
            fontWeight: font.weight,
          }}
        >
          {line.map((w) => {
            const idx = flat++;
            return <Word key={idx} word={w} size={layout.size} active={idx === activeIdx} underline />;
          })}
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 2. title — small uppercase kicker (0.2em tracking, muted) above a huge
//    headline. Kicker appears first, headline springs in after.
// ---------------------------------------------------------------------------

const TITLE_BASE = 118;
const TITLE_LINE_HEIGHT = 1.05;
const TITLE_TRACKING = -0.035;

export const TitleSceneView: FC<{
  scene: TitleScene;
}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {fs, safe} = useLayout();
  const display = fontFor(style, 'display');
  const body = fontFor(style, 'body');
  const {colors} = style;

  const size = useMemo(() => {
    const words = scene.text.split(/\s+/).filter(Boolean);
    if (!ready || words.length === 0) {
      return null;
    }
    let widest = 0;
    for (const w of words) {
      widest = Math.max(widest, measureTextWidth(w, display.css, display.weight, fs(TITLE_BASE), TITLE_TRACKING));
    }
    // shrink to the widest word, then until the wrapped headline and its kicker fit the height
    const byWidth = widest <= safe.width ? fs(TITLE_BASE) : Math.max(fs(72), (fs(TITLE_BASE) * safe.width) / widest);
    const kickerBlock = scene.kicker ? fs(44) * 1.3 + fs(34) : 0;
    return fitSizeToHeight(
      scene.text,
      display.css,
      display.weight,
      byWidth,
      TITLE_TRACKING,
      safe.width,
      TITLE_LINE_HEIGHT,
      safe.height - kickerBlock,
      fs(40)
    );
  }, [scene.text, scene.kicker, ready, display.css, display.weight, fs, safe.width, safe.height]);

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
    <div style={{textAlign: 'center', maxWidth: '100%'}}>
      {scene.kicker ? (
        <div
          style={{
            fontFamily: body.css,
            fontSize: fs(44),
            fontWeight: body.weight,
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            color: colors.muted,
            opacity: kIn,
            transform: `translateY(${((1 - kIn) * fs(18)).toFixed(2)}px)`,
            marginBottom: fs(34),
          }}
        >
          {scene.kicker}
        </div>
      ) : null}
      <div
        style={{
          fontFamily: display.css,
          fontSize: size ?? fs(TITLE_BASE),
          fontWeight: display.weight,
          lineHeight: TITLE_LINE_HEIGHT,
          letterSpacing: `${TITLE_TRACKING}em`,
          opacity: hSpring,
          transform: `translateY(${((1 - hSpring) * fs(30)).toFixed(2)}px)`,
        }}
      >
        {scene.text}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 3. card — rounded media card (image or video), 78% of the frame width (never wider
//    than the safe area), 1px border, accent glow on entrance, slow Ken Burns zoom
//    1.0 -> 1.06, caption below. The card gives up height when the caption needs room.
// ---------------------------------------------------------------------------

export const CardSceneView: FC<{
  scene: CardScene;
}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const style = useStyle();
  const {u, fs, width, safe} = useLayout();
  const {colors} = style;
  const body = fontFor(style, 'body');

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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        width: Math.min(width * 0.78, safe.width),
        maxHeight: safe.height,
        opacity: enter,
        transform: `scale(${(0.94 + 0.06 * enter).toFixed(4)})`,
      }}
    >
      <div
        style={{
          position: 'relative',
          width: '100%',
          flex: `0 1 ${u(1150)}px`,
          minHeight: 0,
          borderRadius: u(32),
          overflow: 'hidden',
          border: `${Math.max(1, u(1))}px solid ${colors.cardBorder}`,
          boxShadow: `0 ${u(30)}px ${u(90)}px rgba(0, 0, 0, ${style.isDark ? 0.45 : 0.1}), 0 0 ${Math.round(u(70) * glow)}px ${withAlpha(colors.accent, 0.4 * glow)}`,
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
            flexShrink: 0,
            marginTop: u(40),
            fontFamily: body.css,
            fontSize: fs(46),
            fontWeight: body.weight,
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
  );
};

// ---------------------------------------------------------------------------
// 4. big — one word/short phrase, accent color, fit-to-width: starts large,
//    shrinks to fit the safe width; wraps only if it would go below the wrap size.
// ---------------------------------------------------------------------------

const BIG_BASE = 200;
const BIG_WRAP_SIZE = 90;
const BIG_TRACKING = -0.04;
const BIG_LINE_HEIGHT = 1.02;

export const BigSceneView: FC<{
  scene: BigScene;
}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {fs, safe} = useLayout();
  const display = fontFor(style, 'display');

  const layout = useMemo(() => {
    if (!ready) {
      return null;
    }
    const width = measureTextWidth(scene.text, display.css, display.weight, fs(BIG_BASE), BIG_TRACKING);
    if (width <= 0 || width <= safe.width) {
      return {size: fs(BIG_BASE), wrap: false};
    }
    const size = (fs(BIG_BASE) * safe.width) / width;
    if (size >= fs(BIG_WRAP_SIZE)) {
      return {size, wrap: false};
    }
    // Wrap into lines; make sure the longest single word still fits, and the block fits the height.
    const ws = scene.text.split(/\s+/).filter(Boolean);
    let widest = 0;
    for (const w of ws) {
      widest = Math.max(widest, measureTextWidth(w, display.css, display.weight, fs(BIG_WRAP_SIZE), BIG_TRACKING));
    }
    const byWidth = widest > safe.width ? Math.max(fs(40), (fs(BIG_WRAP_SIZE) * safe.width) / widest) : fs(BIG_WRAP_SIZE);
    return {
      size: fitSizeToHeight(
        scene.text,
        display.css,
        display.weight,
        byWidth,
        BIG_TRACKING,
        safe.width,
        BIG_LINE_HEIGHT,
        safe.height,
        fs(30)
      ),
      wrap: true,
    };
  }, [scene.text, ready, display.css, display.weight, fs, safe.width, safe.height]);

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
    <div
      style={{
        fontFamily: display.css,
        fontSize: layout.size,
        fontWeight: display.weight,
        color: style.colors.accent,
        letterSpacing: `${BIG_TRACKING}em`,
        lineHeight: BIG_LINE_HEIGHT,
        textAlign: 'center',
        whiteSpace: layout.wrap ? 'normal' : 'nowrap',
        maxWidth: layout.wrap ? '100%' : undefined,
        opacity: pop,
        transform: `scale(${(0.9 + 0.1 * pop).toFixed(4)})`,
      }}
    >
      {scene.text}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 5. counter — huge number counting 0 -> value with easeOut over 0.9s
//    starting 0.2s into the scene; accent suffix beside, muted sub below.
// ---------------------------------------------------------------------------

const COUNTER_TRACKING = -0.04;

export const CounterSceneView: FC<{
  scene: CounterScene;
}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {u, fs, safe} = useLayout();
  const {colors} = style;
  const display = fontFor(style, 'display');
  const body = fontFor(style, 'body');
  const light = fontFor(style, 'bodyLight');

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

  // The number and its suffix shrink together when the final value is wider than the safe area.
  const k = useMemo(() => {
    if (!ready || !Number.isFinite(scene.value)) {
      return 1;
    }
    const finalText = Number.isInteger(scene.value) ? String(scene.value) : scene.value.toFixed(1);
    const numW = measureTextWidth(finalText, display.css, display.weight, fs(220), COUNTER_TRACKING, true);
    const sufW = scene.suffix
      ? fs(14) + measureTextWidth(scene.suffix, body.css, body.weight, fs(96), -0.02)
      : 0;
    const total = numW + sufW;
    return total > safe.width ? safe.width / total : 1;
  }, [ready, scene.value, scene.suffix, display.css, display.weight, body.css, body.weight, fs, safe.width]);

  const subStart = start + countDur;
  const subIn = interpolate(frame, [subStart, subStart + Math.max(1, Math.round(fps * 0.35))], [0, 1], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });

  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', maxWidth: '100%'}}>
      <div style={{display: 'flex', alignItems: 'baseline'}}>
        <span
          style={{
            fontFamily: display.css,
            fontSize: fs(220) * k,
            fontWeight: display.weight,
            letterSpacing: `${COUNTER_TRACKING}em`,
            lineHeight: 1,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {valueText}
        </span>
        {scene.suffix ? (
          <span
            style={{
              fontFamily: body.css,
              fontSize: fs(96) * k,
              fontWeight: body.weight,
              color: colors.accent,
              marginLeft: fs(14) * k,
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
            marginTop: fs(34),
            fontFamily: light.css,
            fontSize: fs(52),
            fontWeight: light.weight,
            color: colors.muted,
            textAlign: 'center',
            maxWidth: Math.min(u(860), safe.width),
            letterSpacing: '-0.01em',
            opacity: subIn,
            transform: `translateY(${((1 - subIn) * fs(20)).toFixed(2)}px)`,
          }}
        >
          {scene.sub}
        </div>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 6. act — accent index "02 /" then chapter title words pop in.
// ---------------------------------------------------------------------------

const ACT_TRACKING = -0.03;
const ACT_LINE_HEIGHT = 1.16;

export const ActSceneView: FC<{
  scene: ActScene;
  words: LocalWord[];
}> = ({scene, words}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {fs, safe} = useLayout();
  const {colors} = style;
  const body = fontFor(style, 'body');
  const heading = fontFor(style, 'heading');

  const size = useMemo(() => {
    if (!ready) {
      return fs(92);
    }
    return fitSizeToHeight(
      scene.title,
      heading.css,
      heading.weight,
      fs(92),
      ACT_TRACKING,
      safe.width,
      ACT_LINE_HEIGHT,
      safe.height - (fs(64) * 1.3 + fs(30)),
      fs(36)
    );
  }, [ready, scene.title, heading.css, heading.weight, fs, safe.width, safe.height]);

  const idxIn = spring({
    frame: frame - Math.round(fps * 0.1),
    fps,
    config: {damping: 200, stiffness: 100},
    durationInFrames: Math.max(1, Math.round(fps * 0.35)),
  });
  const activeIdx = words.findIndex((w) => frame >= w.appear && frame < w.end);

  return (
    <div style={{textAlign: 'center', maxWidth: '100%'}}>
      <div
        style={{
          fontFamily: body.css,
          fontSize: fs(64),
          fontWeight: body.weight,
          letterSpacing: '0.08em',
          marginBottom: fs(30),
          opacity: idxIn,
          transform: `translateY(${((1 - idxIn) * fs(16)).toFixed(2)}px)`,
        }}
      >
        <span style={{color: colors.accent}}>{scene.index ?? '01'}</span>
        <span style={{color: colors.muted}}> /</span>
      </div>
      <div
        style={{
          fontFamily: heading.css,
          fontSize: size,
          fontWeight: heading.weight,
          letterSpacing: `${ACT_TRACKING}em`,
          lineHeight: ACT_LINE_HEIGHT,
        }}
      >
        {words.map((w, i) => (
          <Word key={i} word={w} size={size} active={i === activeIdx} underline={false} />
        ))}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 7. cta — centered text, accent handle 0.4s later, subtle pulsing arrow-down ring below.
// ---------------------------------------------------------------------------

const CTA_BASE = 100;
const CTA_TRACKING = -0.03;
const CTA_LINE_HEIGHT = 1.08;

export const CtaSceneView: FC<{
  scene: CtaScene;
}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {u, fs, safe} = useLayout();
  const {colors} = style;
  const heading = fontFor(style, 'heading');
  const body = fontFor(style, 'body');

  const size = useMemo(() => {
    if (!ready) {
      return null;
    }
    const ws = scene.text.split(/\s+/).filter(Boolean);
    let widest = 0;
    for (const w of ws) {
      widest = Math.max(widest, measureTextWidth(w, heading.css, heading.weight, fs(CTA_BASE), CTA_TRACKING));
    }
    const byWidth = widest > safe.width ? Math.max(fs(60), (fs(CTA_BASE) * safe.width) / widest) : fs(CTA_BASE);
    // the handle is one unbreakable string: shrink it to the safe width, then reserve its height
    let handleSize = fs(64);
    if (scene.handle) {
      const handleW = measureTextWidth(scene.handle, body.css, body.weight, handleSize, -0.01);
      if (handleW > safe.width) {
        handleSize = (handleSize * safe.width) / handleW;
      }
    }
    const below = (scene.handle ? fs(40) + handleSize * 1.3 : 0) + u(46) + u(84);
    const textSize = fitSizeToHeight(
      scene.text,
      heading.css,
      heading.weight,
      byWidth,
      CTA_TRACKING,
      safe.width,
      CTA_LINE_HEIGHT,
      safe.height - below,
      fs(40)
    );
    return {text: textSize, handle: handleSize};
  }, [scene.text, scene.handle, ready, heading.css, heading.weight, body.css, body.weight, u, fs, safe.width, safe.height]);

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
    <div style={{textAlign: 'center', maxWidth: '100%'}}>
      <div
        style={{
          fontFamily: heading.css,
          fontSize: size?.text ?? fs(CTA_BASE),
          fontWeight: heading.weight,
          letterSpacing: `${CTA_TRACKING}em`,
          lineHeight: CTA_LINE_HEIGHT,
          opacity: tIn,
          transform: `translateY(${((1 - tIn) * fs(26)).toFixed(2)}px)`,
        }}
      >
        {scene.text}
      </div>
      {scene.handle ? (
        <div
          style={{
            marginTop: fs(40),
            fontFamily: body.css,
            fontSize: size?.handle ?? fs(64),
            fontWeight: body.weight,
            color: colors.accent,
            letterSpacing: '-0.01em',
            whiteSpace: 'nowrap',
            opacity: hIn,
            transform: `translateY(${((1 - hIn) * fs(18)).toFixed(2)}px)`,
          }}
        >
          {scene.handle}
        </div>
      ) : null}
      <div
        style={{
          marginTop: u(46),
          display: 'flex',
          justifyContent: 'center',
          opacity: ringIn,
          transform: `scale(${pulse.toFixed(4)})`,
        }}
      >
        <svg width={u(84)} height={u(84)} viewBox="0 0 84 84">
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
  );
};

// ---------------------------------------------------------------------------
// 8. chip — floating pill badges ("плашки"): dot + label (+ accent value),
//    stacked with a staggered spring pop. `items` wins over text/value.
//    The whole stack shrinks when it would not fit the safe area.
// ---------------------------------------------------------------------------

export const ChipSceneView: FC<{
  scene: ChipScene;
}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {u, fs, safe} = useLayout();
  const {colors} = style;
  const body = fontFor(style, 'body');
  const display = fontFor(style, 'display');

  const items: ChipItem[] = useMemo(
    () =>
      scene.items && scene.items.length > 0
        ? scene.items
        : [{text: scene.text ?? '', value: scene.value}],
    [scene.items, scene.text, scene.value]
  );

  const k = useMemo(() => {
    if (!ready) {
      return 1;
    }
    const pillH = fs(50) * 1.25 + fs(48);
    const totalH = items.length * pillH + (items.length - 1) * fs(24);
    let widest = 0;
    for (const item of items) {
      const label = measureTextWidth(item.text, body.css, body.weight, fs(50), -0.01);
      const value = item.value ? fs(18) + measureTextWidth(item.value, display.css, display.weight, fs(50), 0) : 0;
      widest = Math.max(widest, fs(44) * 2 + fs(14) + fs(18) + label + value);
    }
    return Math.min(1, safe.height / totalH, widest > 0 ? safe.width / widest : 1);
  }, [ready, items, body.css, body.weight, display.css, display.weight, fs, safe.width, safe.height]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: fs(24) * k,
        alignItems: 'center',
        maxWidth: '100%',
      }}
    >
      {items.map((item, i) => {
        const delay = Math.round(fps * 0.14 * i);
        const p = spring({
          frame: frame - delay,
          fps,
          config: {damping: 14, stiffness: 170, mass: 0.7},
        });
        return (
          <div
            key={i}
            style={{
              opacity: p,
              transform: `translateY(${((1 - p) * fs(46) * k).toFixed(2)}px) scale(${(0.82 + p * 0.18).toFixed(4)})`,
              display: 'flex',
              alignItems: 'center',
              gap: fs(18) * k,
              padding: `${fs(24) * k}px ${fs(44) * k}px`,
              borderRadius: 999,
              border: `${Math.max(1, u(1))}px solid ${withAlpha(colors.text, 0.14)}`,
              background: withAlpha(colors.text, 0.06),
              boxShadow: `0 ${fs(18) * k}px ${fs(50) * k}px ${withAlpha('#000000', 0.35)}`,
            }}
          >
            <span
              style={{
                width: fs(14) * k,
                height: fs(14) * k,
                borderRadius: 999,
                background: colors.accent,
                boxShadow: `0 0 ${fs(18) * k}px ${withAlpha(colors.accent, 0.85)}`,
              }}
            />
            <span
              style={{
                fontFamily: body.css,
                fontSize: fs(50) * k,
                fontWeight: body.weight,
                letterSpacing: '-0.01em',
              }}
            >
              {item.text}
            </span>
            {item.value ? (
              <span
                style={{
                  fontFamily: display.css,
                  fontSize: fs(50) * k,
                  fontWeight: display.weight,
                  color: colors.accent,
                }}
              >
                {item.value}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

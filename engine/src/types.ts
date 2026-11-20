export type ThemeName = 'dark' | 'light';

/** A single word timing from the ASR/voice sync layer. Seconds, absolute on the timeline. */
export type WordTiming = {
  w: string;
  s: number;
  e: number;
};

export type WordsScene = {
  kind: 'words';
  at: number;
  text: string;
};

export type TitleScene = {
  kind: 'title';
  at: number;
  kicker?: string;
  text: string;
};

export type CardScene = {
  kind: 'card';
  at: number;
  /** Relative to the public dir, e.g. "m/demo.jpg" (caller rewrites to m/<basename>). */
  media: string;
  caption?: string;
  fit?: 'cover' | 'contain';
};

export type BigScene = {
  kind: 'big';
  at: number;
  text: string;
};

export type CounterScene = {
  kind: 'counter';
  at: number;
  value: number;
  suffix?: string;
  sub?: string;
};

export type ActScene = {
  kind: 'act';
  at: number;
  index?: string;
  title: string;
};

export type CtaScene = {
  kind: 'cta';
  at: number;
  text: string;
  handle?: string;
};

export type ChipItem = {
  text: string;
  value?: string;
};

/** Floating pill badges ("плашки"), stacked with a staggered spring. */
export type ChipScene = {
  kind: 'chip';
  at: number;
  text?: string;
  value?: string;
  items?: ChipItem[];
};

/** Timing fields every scene accepts (plan v2). */
export type SceneTiming = {
  /** Seconds, absolute. Default: the next full scene's `at`. */
  until?: number;
  /** Transparent background, drawn above clips and full scenes. */
  overlay?: boolean;
};

/** A React component the model wrote into `<project>/components`, looked up by name. */
export type CustomScene = {
  kind: 'custom';
  at: number;
  component: string;
  props?: Record<string, unknown>;
};

export type SceneKind =
  | 'words'
  | 'title'
  | 'card'
  | 'big'
  | 'counter'
  | 'act'
  | 'cta'
  | 'chip'
  | 'custom';

export type Scene = (
  | WordsScene
  | TitleScene
  | CardScene
  | BigScene
  | CounterScene
  | ActScene
  | CtaScene
  | ChipScene
  | CustomScene
) &
  SceneTiming;

/** One extra sound event (src relative to the public dir, e.g. "sfx/x.mp3"). */
export type SfxEvent = {
  at: number;
  src: string;
  volume?: number;
};

export type HudRow = {
  label: string;
  value: string;
};

/** Timed value swap inside the HUD: from `at` on, `row` shows `value` in accent. */
export type HudAccentChange = {
  /** Seconds, absolute on the timeline. */
  at: number;
  /** Index into `rows`. */
  row: number;
  value: string;
};

/**
 * HUD overlay ("game UI" strip): a semi-transparent dark plate with
 * monospace values, drawn OVER every scene between `at` and `until`
 * without touching them. Not a Scene — it lives at the root of the props.
 */
export type HudOverlay = {
  /** Appearance time, seconds, absolute on the timeline. */
  at: number;
  /** Disappearance time, seconds (the plate fades out approaching it). */
  until: number;
  rows: HudRow[];
  /** Anchor edge of the plate. Default "top". */
  pos?: 'top' | 'bottom';
  /** Timed value swaps; the new value is accent-highlighted. */
  accent_changes?: HudAccentChange[];
};

export type MusicTrack = {
  /** Relative to the public dir. */
  src: string;
  /** 0..1, default 0.12 — sits well under a voice track. */
  volume?: number;
  /** Seconds of fade-out at the end of the video, default 1.5. */
  fade_out?: number;
};

/**
 * Root props of the engine. Declared as a type alias (not an interface) so it
 * satisfies Remotion's `Composition` generic constraint `Record<string, unknown>`.
 */
export type KineticProps = {
  fps?: number;
  /** Total duration in seconds. */
  duration?: number;
  theme?: ThemeName;
  accent?: string;
  /** Optional audio track, relative to the public dir, played full length. */
  voice?: string;
  /** Optional global word timings for sync. */
  words?: WordTiming[];
  scenes: Scene[];
  /**
   * Optional HUD overlay drawn over all scenes between `at` and `until`
   * (semi-transparent dark plate, monospace values, accent swaps).
   */
  hud?: HudOverlay;
  /** v1 flag for the automatic sound design. Ignored: the engine adds no sound effects. */
  sfx?: boolean;
  /** Global multiplier for every sound event. Default 1. */
  sfx_volume?: number;
  /** v1 sound events (same as `audio.sfx` in a plan). */
  sfx_list?: SfxEvent[];
  /** Background music bed, auto-faded out at the end. */
  music?: MusicTrack;
};

// ---------------------------------------------------------------------------
// Plan v2. Mirrors `src/argus/plan.py` (the source of truth): change both together.
// The Python side validates the plan and fills defaults (`Plan.resolved()`) before it
// reaches the engine, but every field with a default is optional here.
// ---------------------------------------------------------------------------

export type PlanFormat = '9:16' | '16:9';

/** 1080x1920 for 9:16, 1920x1080 for 16:9. */
export const FORMAT_SIZES: Record<PlanFormat, {width: number; height: number}> = {
  '9:16': {width: 1080, height: 1920},
  '16:9': {width: 1920, height: 1080},
};

export type FontRef = {
  family: string;
  /** Font file inside the project; the family is registered from it. */
  src?: string;
  weight?: number;
};

/** Fractions of the frame that stay free of text on each side. */
export type SafeArea = {top: number; bottom: number; left: number; right: number};

export type Background =
  | {type: 'solid'}
  | {type: 'gradient'; stops: string[]; angle?: number}
  | {type: 'media'; src: string; fit?: 'cover' | 'contain'};

export type StyleTokens = {
  /** Required: bg, text, muted, accent. Extra names are free (e.g. word_base, word_active, card_border). */
  colors: {bg: string; text: string; muted: string; accent: string} & Record<string, string>;
  fonts: {display: FontRef; body: FontRef; mono?: FontRef};
  /** Multiplies all text sizes. Default 1. */
  text_scale?: number;
  /** Default for the format: 9:16 {.08, .20, .06, .12}, 16:9 {.06, .08, .05, .05}. */
  safe_area?: SafeArea;
  /** Default: solid `colors.bg`. */
  background?: Background;
  /** 0..1 opacity. Default 0.05. */
  grain?: number;
  /** Default true. */
  vignette?: boolean;
};

export type ZoomKey = {
  /** Seconds from the start of the clip on the timeline. */
  t: number;
  scale: number;
  /** Focus point as fractions of the frame. */
  x?: number;
  y?: number;
  ease?: 'linear' | 'inOut';
};

export type Clip = {
  src: string;
  /** Seconds on the output timeline. */
  at: number;
  /** Source seconds. */
  in?: number;
  out?: number;
  fit?: 'cover' | 'contain';
  volume?: number;
  muted?: boolean;
  zoom?: ZoomKey[];
  clean_audio?: boolean;
  /**
   * Engine props only, not in the plan (`plan.py` has no such field). Set by the render for a
   * clip without `out`: seconds the clip lasts (source length minus `in`). A clip with neither
   * `out` nor `length` runs until the end of the video.
   */
  length?: number;
};

/** `words` file path, inline words, or a transcript to move onto the kept clips. */
export type CaptionWords =
  | string
  | WordTiming[]
  | {source: string; remap: 'clips'; media?: string};

export type CaptionStyle = {
  font?: 'display' | 'body';
  /** Fractions of the frame's short side. */
  size?: number;
  color?: string;
  active_color?: string;
  upcoming_color?: string;
  outline?: number;
  shadow?: number;
  /** Background color behind the text. */
  plate?: string;
  /** 'as_is' (default) keeps the words as written; 'upper' draws them in capitals. */
  case?: 'upper' | 'as_is';
};

export type Captions = {
  words: CaptionWords;
  /**
   * Default 'phrase'. 'headline': big words in the middle of the frame, slammed in as they are
   * spoken, `accent_words` boxed in the accent colour.
   */
  mode?: 'word' | 'phrase' | 'headline';
  /** Default 'lower'; the Python side sets 'center' for 'headline' when the plan gives none. */
  position?: 'upper' | 'center' | 'lower';
  style?: CaptionStyle;
  /** Exact words, "prefix*" or "*". */
  accent_words?: string[];
};

export type AudioRef = {
  src: string;
  volume?: number;
};

export type Music = {
  src: string;
  /** 0..1, default 0.12. */
  volume?: number;
  /** Volume multiplier while words are spoken, 0..1, default 1 (no ducking). */
  duck?: number;
  /** Seconds, default 0. */
  fade_in?: number;
  /** Seconds, default 1.5. */
  fade_out?: number;
};

export type PlanAudio = {
  voice?: AudioRef;
  music?: Music;
  sfx?: SfxEvent[];
};

/** A moment found in the voice: where word is spoken (nth time, default 1) plus offset seconds. */
export type WordCue = {word: string; nth?: number; offset?: number};

export type Plan = {
  version: 2;
  format: PlanFormat;
  /** Default 30. */
  fps?: 24 | 25 | 30 | 50 | 60;
  /** Seconds; derived when absent. */
  duration?: number;
  /** Presets are expanded to tokens by the Python side. */
  style: StyleTokens;
  clips?: Clip[];
  scenes?: Scene[];
  hud?: HudOverlay;
  captions?: Captions;
  audio?: PlanAudio;
  /** Named moments for custom scenes: seconds, or a spoken word. */
  cues?: Record<string, number | WordCue>;
};

/**
 * What the `Kinetic` composition receives: a plan v2 (`format`, `style` tokens) or the
 * v1 props (`theme`, `accent`), which no tool sends any more but the Studio's sample props
 * still use. With v1 props the format is 9:16 and the style is the `theme` preset. `style` may also be a
 * preset name, which is handy in the Studio.
 */
export type EngineProps = Omit<KineticProps, 'scenes'> &
  Partial<Pick<Plan, 'version' | 'format' | 'clips' | 'captions' | 'audio'>> & {
    scenes?: Scene[];
    style?: StyleTokens | ThemeName;
    /** The plan's `cues`, resolved to seconds on the video timeline by the Python side. */
    cues?: Record<string, number>;
  };

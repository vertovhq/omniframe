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

export type Scene =
  | WordsScene
  | TitleScene
  | CardScene
  | BigScene
  | CounterScene
  | ActScene
  | CtaScene
  | ChipScene;

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
  /** Auto sound design (whoosh on cuts, pop/hit on scenes). Default true. */
  sfx?: boolean;
  /** Global multiplier for every sound event. Default 1. */
  sfx_volume?: number;
  /** Extra custom sounds on top of the auto ones. */
  sfx_list?: SfxEvent[];
  /** Background music bed, auto-faded out at the end. */
  music?: MusicTrack;
};

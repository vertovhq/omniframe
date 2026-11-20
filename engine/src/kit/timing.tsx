import {useContext, useMemo} from 'react';
import type {ReactNode} from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {ClockContext, PlanTimingContext} from '../timing';
import {Transition, transitionDur} from './transitions';
import type {TransitionKind, TransitionSpec} from './transitions';

// Timing for custom scenes. Every time here is in seconds on the clock of the component that
// asks, the same clock as `useT()` and `useCurrentFrame()`: 0 is the start of the scene (inside
// a `SceneTrack` scene, the start of that track scene). Compare them freely.

/** Seconds since the start of the scene (or track scene) this component is drawn in. */
export const useT = (): number => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return frame / fps;
};

/** Seconds from the clock's 0 to the end of the scene (or track scene). */
export const useDuration = (): number => {
  const {fps} = useVideoConfig();
  const clock = useContext(ClockContext);
  return Math.max(0, (clock.end - clock.origin) / fps);
};

/** The plan's `cues` as seconds on this component's clock. A cue before the scene is negative. */
export const useCues = (): Record<string, number> => {
  const {cues} = useContext(PlanTimingContext);
  const clock = useContext(ClockContext);
  const {fps} = useVideoConfig();
  return useMemo(() => {
    const shift = clock.origin / fps;
    return Object.fromEntries(Object.entries(cues).map(([name, s]) => [name, s - shift]));
  }, [cues, clock.origin, fps]);
};

/**
 * One cue of the plan (`plan.cues`) in seconds on this component's clock. Without a `fallback`,
 * a cue the plan does not define stops the render with a message that lists the defined ones.
 */
export const useCue = (name: string, fallback?: number): number => {
  const cues = useCues();
  const value = cues[name];
  if (value !== undefined) {
    return value;
  }
  if (fallback !== undefined) {
    return fallback;
  }
  throw new Error(`cue "${name}" is not in plan.cues (defined: ${Object.keys(cues).join(', ') || 'none'})`);
};

export type SpokenWord = {w: string; s: number; e: number};

/** The voice words (`captions.words`) as `{w, s, e}` seconds on this component's clock. */
export const useWords = (): SpokenWord[] => {
  const {words} = useContext(PlanTimingContext);
  const clock = useContext(ClockContext);
  const {fps} = useVideoConfig();
  return useMemo(() => {
    const shift = clock.origin / fps;
    return words.map((x) => ({w: x.w, s: x.s - shift, e: x.e - shift}));
  }, [words, clock.origin, fps]);
};

export type TrackInfo = {
  /** Seconds since this track scene started. */
  t: number;
  /** Seconds this track scene lasts (until the next one starts). */
  d: number;
  /** Index in `scenes`. */
  i: number;
};

export type TrackScene = {
  /** Start in seconds on the clock of the `SceneTrack`, or the name of a plan cue. */
  at: number | string;
  render: (info: TrackInfo) => ReactNode;
  /** How this scene replaces the previous one (a kind, or a spec with `dur`, `strength`, `dir`...). Default: the track's `enter`. */
  enter?: TransitionKind | TransitionSpec;
};

const TrackSceneView = ({
  info,
  enter,
  leave,
  fade,
  from,
  render,
}: {
  info: Omit<TrackInfo, 't'>;
  /** The transition that brings this scene in (none for the first scene). */
  enter: TransitionKind | TransitionSpec | null;
  /** The transition of the next scene, which takes this one out. */
  leave: TransitionKind | TransitionSpec | null;
  fade: number;
  from: number;
  render: TrackScene['render'];
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const clock = useContext(ClockContext);
  const t = frame / fps;
  const origin = clock.origin + from;
  const end = origin + Math.round(info.d * fps);
  const leaving = leave !== null && t >= info.d;
  const kind = (spec: TransitionKind | TransitionSpec) => (typeof spec === 'string' ? spec : spec.kind);
  let node: ReactNode = render({...info, t});
  if (leave !== null) {
    node = (
      <Transition spec={leave} role="out" t={t - info.d} fade={fade}>
        {node}
      </Transition>
    );
  }
  if (enter !== null) {
    node = (
      <Transition spec={enter} role="in" t={t} fade={fade}>
        {node}
      </Transition>
    );
  }
  return (
    <ClockContext.Provider value={{origin, end}}>
      {/* A split opens the old scene like doors, so the old scene is drawn on top of the new one. */}
      <AbsoluteFill style={{zIndex: leaving && kind(leave) === 'split' ? 2 : undefined}}>{node}</AbsoluteFill>
    </ClockContext.Provider>
  );
};

/**
 * The scenes of a custom component one after the other. A scene starts at `at` (seconds or a cue
 * name), lasts until the next one starts, and comes in on top of the previous scene. How it comes
 * in is its `enter` (else the track's `enter`, else a cross-fade of `fade` seconds): a kind such as
 * 'whip' or a spec such as `{kind: 'glitch', dur: 0.3, strength: 1.5}` (see transitions.tsx).
 * The previous scene is removed once the transition is over: give each scene its own full-frame
 * backdrop (`Stage`). Inside `render`, `useT()`, `useCue()` and the other kit blocks use the track
 * scene's own clock.
 */
export const SceneTrack = ({
  scenes,
  fade = 0.5,
  enter: trackEnter,
}: {
  scenes: TrackScene[];
  fade?: number;
  enter?: TransitionKind | TransitionSpec;
}) => {
  const {fps} = useVideoConfig();
  const clock = useContext(ClockContext);
  const cues = useCues();
  const end = Math.max(0, (clock.end - clock.origin) / fps);
  const starts = scenes.map((s) => {
    if (typeof s.at === 'number') {
      return Math.max(0, s.at);
    }
    const cue = cues[s.at];
    if (cue === undefined) {
      throw new Error(`SceneTrack: cue "${s.at}" is not in plan.cues (defined: ${Object.keys(cues).join(', ') || 'none'})`);
    }
    return Math.max(0, cue);
  });
  // scene i (i > 0) comes in with enters[i]; scene i - 1 stays underneath until it is over
  const enters = scenes.map((scene, i) => (i === 0 ? null : scene.enter ?? trackEnter ?? 'fade'));
  return (
    <>
      {scenes.map((scene, i) => {
        const last = i + 1 >= scenes.length;
        const start = starts[i];
        const stop = last ? end : Math.max(start, starts[i + 1]);
        const from = Math.round(start * fps);
        const leave = last ? null : enters[i + 1];
        const tail = leave === null ? 0 : transitionDur(leave, fade);
        const dur = Math.max(1, Math.round((stop - start + tail) * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={dur} layout="none" name={`track-${i + 1}`}>
            <TrackSceneView info={{d: stop - start, i}} enter={enters[i]} leave={leave} fade={fade} from={from} render={scene.render} />
          </Sequence>
        );
      })}
    </>
  );
};

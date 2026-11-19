import {useContext, useMemo} from 'react';
import type {ReactNode} from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {ClockContext, PlanTimingContext} from '../timing';
import {eInOut, seg} from './motion';

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
};

const TrackSceneView = ({
  info,
  fade,
  from,
  render,
}: {
  info: Omit<TrackInfo, 't'>;
  fade: number;
  from: number;
  render: TrackScene['render'];
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const clock = useContext(ClockContext);
  const t = frame / fps;
  const alpha = info.i === 0 || fade <= 0 ? 1 : eInOut(seg(t, 0, fade));
  const origin = clock.origin + from;
  const end = origin + Math.round(info.d * fps);
  return (
    <ClockContext.Provider value={{origin, end}}>
      <AbsoluteFill style={{opacity: alpha}}>{render({...info, t})}</AbsoluteFill>
    </ClockContext.Provider>
  );
};

/**
 * The scenes of a custom component one after the other. A scene starts at `at` (seconds or a cue
 * name), lasts until the next one starts, and fades in over `fade` seconds on top of the previous
 * scene, so the picture never dips to the background colour. The previous scene is removed once
 * the new one is fully visible: give each scene its own full-frame backdrop (`Stage`).
 * Inside `render`, `useT()`, `useCue()` and the other kit blocks use the track scene's own clock.
 */
export const SceneTrack = ({scenes, fade = 0.5}: {scenes: TrackScene[]; fade?: number}) => {
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
  return (
    <>
      {scenes.map((scene, i) => {
        const last = i + 1 >= scenes.length;
        const start = starts[i];
        const stop = last ? end : Math.max(start, starts[i + 1]);
        const from = Math.round(start * fps);
        const dur = Math.max(1, Math.round((stop - start + (last ? 0 : fade)) * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={dur} layout="none" name={`track-${i + 1}`}>
            <TrackSceneView info={{d: stop - start, i}} fade={fade} from={from} render={scene.render} />
          </Sequence>
        );
      })}
    </>
  );
};

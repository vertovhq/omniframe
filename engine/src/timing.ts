import {createContext} from 'react';

/**
 * What a custom scene may know about the plan's timing (read by the motion kit, `kit/timing.tsx`).
 * All times are seconds on the video timeline; the kit converts them to the scene's own clock.
 */
export type PlanTiming = {
  /** Voice words (caption words, else the v1 `words`). */
  words: Array<{w: string; s: number; e: number}>;
  /** The plan's cues, already resolved to seconds by the Python side. */
  cues: Record<string, number>;
};

export const PlanTimingContext = createContext<PlanTiming>({words: [], cues: {}});

/**
 * The clock of the component that reads it: `origin` is the video frame where
 * `useCurrentFrame()` is 0, `end` the video frame where the scene (or the part of it the
 * component draws) stops. `Main` sets it per scene, `SceneTrack` per track scene.
 */
export type Clock = {origin: number; end: number};

export const ClockContext = createContext<Clock>({origin: 0, end: 0});

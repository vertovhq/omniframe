import {useCues} from './timing';

// Moments for the blocks that react to a hit. A moment is seconds on the scene's clock, the name
// of a plan cue (`plan.cues`), or a list of both: `at={['hit', 3.2]}`. A name that the plan does
// not define stops the render and lists the cues that exist, like `useCue`.

export type At = number | string | ReadonlyArray<number | string>;

/** `at` as a list of seconds on this component's clock (cue names looked up), or undefined without `at`. */
export const useAt = (at: At | undefined): number[] | undefined => {
  const cues = useCues();
  if (at === undefined) {
    return undefined;
  }
  const list: ReadonlyArray<number | string> = typeof at === 'number' || typeof at === 'string' ? [at] : at;
  return list.map((a) => {
    if (typeof a === 'number') {
      return a;
    }
    const value = cues[a];
    if (value === undefined) {
      throw new Error(`cue "${a}" is not in plan.cues (defined: ${Object.keys(cues).join(', ') || 'none'})`);
    }
    return value;
  });
};

/** Seconds since the latest moment in `at` that is not after `t`, or null before the first one. */
export const ageOf = (t: number, at: number | ReadonlyArray<number> | undefined): number | null => {
  let age: number | null = null;
  for (const a of at === undefined ? [] : typeof at === 'number' ? [at] : at) {
    if (t >= a && (age === null || t - a < age)) {
      age = t - a;
    }
  }
  return age;
};

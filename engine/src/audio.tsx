import type {FC} from 'react';
import {Audio, Sequence, useVideoConfig} from 'remotion';
import type {AudioRef, Music, SfxEvent, WordTiming} from './types';
import {resolveMedia} from './style';

/** Music goes down and up over this long when speech starts and stops (design §9). */
export const DUCK_RAMP_S = 0.25;
/** Pauses between words up to this long do not let the music come back up. */
export const SPEECH_MERGE_GAP_S = 0.35;

/** A stretch of speech, seconds on the timeline. */
export type SpeechWindow = {start: number; end: number};

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Speech windows from word timings: sorted, with short pauses merged. */
export function speechWindows(
  words: ReadonlyArray<{s: number; e: number}> | undefined,
  mergeGap: number = SPEECH_MERGE_GAP_S
): SpeechWindow[] {
  const valid = (words ?? [])
    .filter((w) => w && Number.isFinite(w.s) && Number.isFinite(w.e))
    .map((w) => ({start: Math.max(0, w.s), end: Math.max(w.s, w.e)}))
    .sort((a, b) => a.start - b.start);
  const out: SpeechWindow[] = [];
  for (const w of valid) {
    const last = out[out.length - 1];
    if (last && w.start - last.end <= mergeGap) {
      last.end = Math.max(last.end, w.end);
    } else {
      out.push({...w});
    }
  }
  return out;
}

/**
 * 0..1: how far the music is pulled down at time `t`. It reaches 1 when a window starts
 * (the ramp runs `ramp` seconds before it), stays 1 inside, and falls to 0 over `ramp`
 * seconds after the window ends. `windows` must be sorted by start (`speechWindows` is).
 */
export function speechLevel(t: number, windows: readonly SpeechWindow[], ramp: number = DUCK_RAMP_S): number {
  let level = 0;
  for (const w of windows) {
    if (t < w.start - ramp) {
      break;
    }
    if (t > w.end + ramp) {
      continue;
    }
    const up = (t - (w.start - ramp)) / ramp;
    const down = (w.end + ramp - t) / ramp;
    level = Math.max(level, clamp01(Math.min(up, down)));
    if (level >= 1) {
      break;
    }
  }
  return level;
}

/** Music volume at time `t`: base volume, ducked while speech plays, with fades at the ends. */
export function musicGain(
  t: number,
  o: {
    volume: number;
    /** Multiplier while speech plays; 1 = no ducking. */
    duck: number;
    fadeIn: number;
    fadeOut: number;
    duration: number;
    windows: readonly SpeechWindow[];
  }
): number {
  const duck = clamp01(o.duck);
  let g = o.volume * (1 - (1 - duck) * (duck < 1 ? speechLevel(t, o.windows) : 0));
  if (o.fadeIn > 0) {
    g *= clamp01(t / o.fadeIn);
  }
  if (o.fadeOut > 0) {
    g *= clamp01((o.duration - t) / o.fadeOut);
  }
  return g;
}

const finiteOr = (v: unknown, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : fallback;

/**
 * Everything you hear: the voice, the music bed and the plan's sound effects.
 *
 * `speech` are the word timings the ducking follows (the caption words, or the v1 `words`
 * prop); without them the music is not ducked. `sfxVolume` multiplies every effect (v1 prop).
 */
export const AudioTracks: FC<{
  voice?: AudioRef;
  music?: Music;
  sfx: readonly SfxEvent[];
  speech?: ReadonlyArray<WordTiming>;
  sfxVolume?: number;
  /** Seconds. */
  duration: number;
}> = ({voice, music, sfx, speech, sfxVolume = 1, duration}) => {
  const {fps} = useVideoConfig();
  const windows = speechWindows(speech);

  return (
    <>
      {voice ? <Audio src={resolveMedia(voice.src)} volume={finiteOr(voice.volume, 1)} /> : null}
      {music ? (
        <Audio
          src={resolveMedia(music.src)}
          volume={(f) =>
            musicGain(f / fps, {
              volume: finiteOr(music.volume, 0.12),
              duck: finiteOr(music.duck, 1),
              fadeIn: finiteOr(music.fade_in, 0),
              fadeOut: finiteOr(music.fade_out, 1.5),
              duration,
              windows,
            })
          }
        />
      ) : null}
      {sfx.map((e, i) => (
        <Sequence key={`sfx-${i}`} from={Math.max(0, Math.round(e.at * fps))} name={`sfx-${i}`}>
          <Audio src={resolveMedia(e.src)} volume={(e.volume ?? 1) * sfxVolume} />
        </Sequence>
      ))}
    </>
  );
};

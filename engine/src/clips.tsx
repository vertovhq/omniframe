import {useMemo} from 'react';
import type {CSSProperties, FC} from 'react';
import {AbsoluteFill, Easing, Img, OffthreadVideo, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Clip, ZoomKey} from './types';
import {resolveMedia} from './style';

const IMAGE_EXT = /\.(png|jpe?g|webp|gif|bmp)(\?.*)?$/i;

export type ZoomState = {scale: number; x: number; y: number};

const NEUTRAL: ZoomState = {scale: 1, x: 0.5, y: 0.5};

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

type Stop = ZoomState & {t: number; ease: 'linear' | 'inOut'};

/**
 * Zoom keyframes of a clip as a list of stops. `t` is seconds from the start of the clip.
 * Before the first key the picture is neutral (scale 1): a lone key at 2.5 s means a push-in
 * that reaches the key's scale at 2.5 s. A key without `x`/`y` keeps the previous focus point
 * (the first one starts at the frame center). After the last key the zoom holds.
 */
function zoomStops(keys: ZoomKey[] | undefined): Stop[] {
  const valid = (keys ?? []).filter((k) => k && finite(k.t) && finite(k.scale) && k.scale > 0);
  valid.sort((a, b) => a.t - b.t);
  const stops: Stop[] = [];
  let prev: ZoomState = NEUTRAL;
  if (valid.length > 0 && valid[0].t > 0) {
    stops.push({...NEUTRAL, t: 0, ease: 'linear'});
  }
  for (const k of valid) {
    const stop: Stop = {
      t: Math.max(0, k.t),
      scale: k.scale,
      x: finite(k.x) ? k.x : prev.x,
      y: finite(k.y) ? k.y : prev.y,
      ease: k.ease === 'linear' ? 'linear' : 'inOut',
    };
    stops.push(stop);
    prev = stop;
  }
  return stops;
}

/** Scale and focus point (fractions of the frame) of a clip's zoom at `t` seconds into the clip. */
export function zoomAt(keys: ZoomKey[] | undefined, t: number): ZoomState {
  const stops = zoomStops(keys);
  if (stops.length === 0) {
    return NEUTRAL;
  }
  if (t <= stops[0].t) {
    return stops[0];
  }
  const last = stops[stops.length - 1];
  if (t >= last.t) {
    return last;
  }
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (t >= a.t && t < b.t) {
      const span = b.t - a.t;
      const raw = span > 1e-6 ? (t - a.t) / span : 1;
      // The ease belongs to the key the picture is moving to.
      const p = b.ease === 'inOut' ? Easing.inOut(Easing.cubic)(raw) : raw;
      return {
        scale: a.scale + (b.scale - a.scale) * p,
        x: a.x + (b.x - a.x) * p,
        y: a.y + (b.y - a.y) * p,
      };
    }
  }
  return last;
}

/** Seconds a clip plays on the timeline, or null when nothing in the plan says how long. */
export function clipLengthSeconds(clip: Clip): number | null {
  if (finite(clip.out)) {
    return Math.max(0, clip.out - (clip.in ?? 0));
  }
  if (finite(clip.length) && clip.length > 0) {
    return clip.length;
  }
  return null;
}

const ClipView: FC<{clip: Clip}> = ({clip}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const zoom = zoomAt(clip.zoom, frame / fps);
  const objectFit: CSSProperties['objectFit'] = clip.fit === 'contain' ? 'contain' : 'cover';
  const media: CSSProperties = {width: '100%', height: '100%', objectFit};
  const src = resolveMedia(clip.src);
  const zoomed = Math.abs(zoom.scale - 1) > 1e-4;

  return (
    <AbsoluteFill
      style={{
        transformOrigin: `${(zoom.x * 100).toFixed(3)}% ${(zoom.y * 100).toFixed(3)}%`,
        transform: zoomed ? `scale(${zoom.scale.toFixed(5)})` : undefined,
        overflow: 'visible',
      }}
    >
      {IMAGE_EXT.test(clip.src) ? (
        <Img src={src} style={media} />
      ) : (
        <OffthreadVideo
          src={src}
          style={media}
          trimBefore={Math.max(0, Math.round((clip.in ?? 0) * fps))}
          volume={clip.muted ? 0 : finite(clip.volume) ? clip.volume : 1}
          muted={Boolean(clip.muted)}
        />
      )}
    </AbsoluteFill>
  );
};

/**
 * The video/image track (design §8, §9 "Engine changes"): every clip plays from its `at`
 * for `out - in` seconds (or its probed `length`; a clip with neither runs to the end of the
 * video). Later clips are drawn above earlier ones. The track sits above the background and
 * below the scenes, so a full scene hides it and an overlay scene is drawn on it.
 *
 * Zoom: scale around the focus point (`x`, `y`), so the focus point stays where it is and the
 * frame stays covered. Sizes never use pixels; the clip fills the frame (`fit`).
 */
export const ClipsLayer: FC<{clips?: Clip[]; duration: number}> = ({clips, duration}) => {
  const {fps} = useVideoConfig();
  const entries = useMemo(() => {
    const list = (clips ?? []).filter((c) => c && c.src && finite(c.at));
    return list
      .map((clip, index) => {
        const from = Math.max(0, Math.round(clip.at * fps));
        const seconds = clipLengthSeconds(clip) ?? Math.max(0, duration - clip.at);
        const dur = Math.round((clip.at + seconds) * fps) - from;
        return {clip, index, from, dur};
      })
      .filter((e) => e.dur >= 1)
      // Stable sort: equal `at` keeps the plan order, so later clips stay on top.
      .sort((a, b) => a.from - b.from || a.index - b.index);
  }, [clips, fps, duration]);

  return (
    <>
      {entries.map((e) => (
        <Sequence
          key={`clip-${e.index}`}
          from={e.from}
          durationInFrames={e.dur}
          name={`clip-${String(e.index + 1).padStart(2, '0')}`}
        >
          <ClipView clip={e.clip} />
        </Sequence>
      ))}
    </>
  );
};

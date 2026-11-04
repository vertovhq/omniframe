import {useMemo} from 'react';
import type {FC} from 'react';
import {AbsoluteFill, Audio, Sequence, interpolate, useVideoConfig} from 'remotion';
import type {KineticProps, Scene} from './types';
import {FONT_FAMILY, getTheme, grainBackgroundImage, resolveMedia} from './theme';
import {assignWordTimings} from './text';
import type {LocalWord} from './text';
import {buildSfxTimeline} from './sfx';
import {
  ActSceneView,
  BigSceneView,
  CardSceneView,
  ChipSceneView,
  CounterSceneView,
  CtaSceneView,
  SceneShell,
  TitleSceneView,
  WordsSceneView,
} from './scenes';

const SceneView: FC<{
  scene: Scene;
  words: LocalWord[];
  colors: ReturnType<typeof getTheme>;
}> = ({scene, words, colors}) => {
  switch (scene.kind) {
    case 'words':
      return <WordsSceneView scene={scene} words={words} colors={colors} />;
    case 'title':
      return <TitleSceneView scene={scene} colors={colors} />;
    case 'card':
      return <CardSceneView scene={scene} colors={colors} />;
    case 'big':
      return <BigSceneView scene={scene} colors={colors} />;
    case 'counter':
      return <CounterSceneView scene={scene} colors={colors} />;
    case 'act':
      return <ActSceneView scene={scene} words={words} colors={colors} />;
    case 'cta':
      return <CtaSceneView scene={scene} colors={colors} />;
    case 'chip':
      return <ChipSceneView scene={scene} colors={colors} />;
    default:
      return null;
  }
};

/**
 * Kinetic: JSON-driven vertical video. Each scene becomes a non-overlapping
 * Sequence from its `at` to the next scene's `at` (last scene runs to
 * `duration`); transitions are handled inside SceneShell so two texts never
 * stack. Optional voice audio plays full length from the public dir.
 */
export const Main: FC<KineticProps> = ({
  duration,
  theme = 'dark',
  accent,
  voice,
  words,
  scenes,
  sfx = true,
  sfx_volume = 1,
  sfx_list,
  music,
}) => {
  const {fps} = useVideoConfig();
  const colors = useMemo(() => getTheme(theme, accent), [theme, accent]);
  const safeDuration = duration && duration > 0 ? duration : 12.5;

  const orderedScenes = useMemo(() => {
    const list = [...(scenes ?? [])].filter(
      (s): s is Scene => Boolean(s) && typeof s.at === 'number'
    );
    list.sort((a, b) => a.at - b.at);
    return list;
  }, [scenes]);

  const timings = useMemo(
    () => assignWordTimings(orderedScenes, words, safeDuration),
    [orderedScenes, words, safeDuration]
  );

  const sfxEvents = useMemo(
    () => buildSfxTimeline(orderedScenes, {sfx, sfx_list}),
    [orderedScenes, sfx, sfx_list]
  );

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.bg,
        backgroundImage: colors.vignette,
        color: colors.text,
        fontFamily: `${FONT_FAMILY}, 'Segoe UI', system-ui, sans-serif`,
      }}
    >
      {voice ? <Audio src={resolveMedia(voice)} /> : null}
      {music ? (
        <Audio
          src={resolveMedia(music.src)}
          volume={(f) => {
            const base = music.volume ?? 0.12;
            const fade = music.fade_out ?? 1.5;
            const t = f / fps;
            const k = interpolate(t, [safeDuration - fade, safeDuration], [1, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return base * k;
          }}
        />
      ) : null}
      {sfxEvents.map((e, i) => (
        <Sequence key={`sfx-${i}`} from={Math.max(0, Math.round(e.at * fps))} name={`sfx-${i}`}>
          <Audio src={resolveMedia(e.src)} volume={(e.volume ?? 1) * sfx_volume} />
        </Sequence>
      ))}
      {orderedScenes.map((scene, i) => {
        const start = Math.max(0, scene.at);
        const end =
          i < orderedScenes.length - 1
            ? Math.max(start + 0.1, orderedScenes[i + 1].at)
            : Math.max(start + 0.1, safeDuration);
        const from = Math.round(start * fps);
        const dur = Math.max(1, Math.round(end * fps) - from);
        const localWords: LocalWord[] = (timings.get(i) ?? []).map((t) => {
          const appear = Math.round(t.s * fps) - from;
          return {w: t.w, appear, end: Math.max(appear + 1, Math.round(t.e * fps) - from)};
        });
        return (
          <Sequence
            key={`${i}-${scene.kind}`}
            from={from}
            durationInFrames={dur}
            name={`${String(i + 1).padStart(2, '0')}-${scene.kind}`}
          >
            <SceneShell durationInFrames={dur}>
              <SceneView scene={scene} words={localWords} colors={colors} />
            </SceneShell>
          </Sequence>
        );
      })}
      <AbsoluteFill
        style={{
          pointerEvents: 'none',
          backgroundImage: grainBackgroundImage,
          backgroundRepeat: 'repeat',
          backgroundSize: '240px 240px',
          opacity: colors.grainOpacity,
        }}
      />
    </AbsoluteFill>
  );
};

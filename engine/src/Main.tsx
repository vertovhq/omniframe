import {useMemo} from 'react';
import type {FC} from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import type {EngineProps, PlanFormat, Scene} from './types';
import {AudioTracks} from './audio';
import {Background, Grain} from './background';
import {CaptionsLayer} from './captions';
import {ClipsLayer} from './clips';
import {HudLayer} from './hud';
import {fontFor, loadStyleFonts, resolveMedia, resolveStyle, StyleContext} from './style';
import {assignWordTimings, sceneWindows} from './text';
import type {LocalWord} from './text';
import {collectSfx} from './sfx';
import {registry} from './custom/registry';
import {ClockContext, PlanTimingContext} from './timing';
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
}> = ({scene, words}) => {
  switch (scene.kind) {
    case 'words':
      return <WordsSceneView scene={scene} words={words} />;
    case 'title':
      return <TitleSceneView scene={scene} />;
    case 'card':
      return <CardSceneView scene={scene} />;
    case 'big':
      return <BigSceneView scene={scene} />;
    case 'counter':
      return <CounterSceneView scene={scene} />;
    case 'act':
      return <ActSceneView scene={scene} words={words} />;
    case 'cta':
      return <CtaSceneView scene={scene} />;
    case 'chip':
      return <ChipSceneView scene={scene} />;
    case 'custom': {
      // The registry holds the components of this render only (see custom/README.md).
      const Component = registry[scene.component];
      if (!Component) {
        throw new Error(`custom component "${scene.component}" is not in the registry`);
      }
      return <Component {...(scene.props ?? {})} />;
    }
    default:
      return null;
  }
};

type SceneEntry = {
  scene: Scene;
  index: number;
  from: number;
  dur: number;
  words: LocalWord[];
};

/**
 * Kinetic: JSON-driven video in 9:16 or 16:9 (`format`), styled by tokens (`style`).
 *
 * Layers, bottom to top: background (colors, gradient or media, vignette) → clips
 * (`clips.tsx`: video/image track with zoom keyframes) → full scenes
 * (each opaque, from `at` until its `until` or the next full scene) → overlay scenes and the
 * HUD (transparent, drawn above) → captions → grain. Scene content is centered inside the
 * style's safe area; sizes scale with the short side of the frame and `text_scale`.
 *
 * Audio (`audio.tsx`): voice, music (volume, ducking under speech, fades) and the plan's
 * `audio.sfx`. The engine adds no sound effects of its own. The v1 props `voice`, `music`
 * and `sfx_list` are still read, though no tool sends them any more; the v1 `sfx` flag (automatic sound design) is ignored.
 *
 * Custom scenes (`kind: 'custom'`) come from `custom/registry.ts`, generated per render.
 */
export const Main: FC<EngineProps> = ({
  duration,
  theme,
  accent,
  style: styleInput,
  format: formatInput,
  version,
  voice,
  words,
  scenes,
  hud,
  clips,
  sfx_volume = 1,
  sfx_list,
  music,
  captions,
  audio,
  cues,
}) => {
  const {fps, width, height} = useVideoConfig();
  const format: PlanFormat = formatInput ?? (width > height ? '16:9' : '9:16');

  const style = useMemo(() => {
    const resolved = resolveStyle(styleInput ?? theme ?? 'dark', {format, accent});
    loadStyleFonts(resolved);
    return resolved;
  }, [styleInput, theme, accent, format]);

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

  // Sound: plan `audio` first, v1 props as a fallback. Only listed SFX events play.
  const sfxEvents = useMemo(() => collectSfx(audio?.sfx, sfx_list), [audio?.sfx, sfx_list]);
  const voiceRef = audio?.voice ?? (voice ? {src: voice} : undefined);
  const musicRef = audio?.music ?? music;
  // Ducking follows the caption words (already loaded by the Python side), else v1 `words`.
  const speechWords = Array.isArray(captions?.words) ? captions.words : words;
  // What custom scenes may read: the voice words and the plan's cues (kit/timing.tsx).
  const planTiming = useMemo(() => ({words: speechWords ?? [], cues: cues ?? {}}), [speechWords, cues]);

  const entries = useMemo<SceneEntry[]>(() => {
    const windows = sceneWindows(orderedScenes, safeDuration);
    return orderedScenes.map((scene, index) => {
      const from = Math.round(windows[index].start * fps);
      const dur = Math.max(1, Math.round(windows[index].end * fps) - from);
      const local: LocalWord[] = (timings.get(index) ?? []).map((t) => {
        const appear = Math.round(t.s * fps) - from;
        return {w: t.w, appear, end: Math.max(appear + 1, Math.round(t.e * fps) - from)};
      });
      return {scene, index, from, dur, words: local};
    });
  }, [orderedScenes, safeDuration, fps, timings]);

  const hudWindow = useMemo(() => {
    if (!hud || typeof hud.at !== 'number' || typeof hud.until !== 'number') {
      return null;
    }
    if (hud.until <= hud.at) {
      return null;
    }
    const from = Math.max(0, Math.round(hud.at * fps));
    const dur = Math.max(1, Math.round(hud.until * fps) - from);
    return {from, dur};
  }, [hud, fps]);

  const renderScene = (e: SceneEntry, opaque: boolean) => (
    <Sequence
      key={`${e.index}-${e.scene.kind}`}
      from={e.from}
      durationInFrames={e.dur}
      name={`${String(e.index + 1).padStart(2, '0')}-${e.scene.kind}${opaque ? '' : '-overlay'}`}
    >
      {opaque ? <Background /> : null}
      <SceneShell durationInFrames={e.dur}>
        <ClockContext.Provider value={{origin: e.from, end: e.from + e.dur}}>
          <SceneView scene={e.scene} words={e.words} />
        </ClockContext.Provider>
      </SceneShell>
    </Sequence>
  );

  return (
    <StyleContext.Provider value={style}>
      <PlanTimingContext.Provider value={planTiming}>
        <AbsoluteFill
          style={{
            backgroundColor: style.colors.bg,
            color: style.colors.text,
            fontFamily: fontFor(style, 'body').css,
          }}
        >
          <Background />
          <AudioTracks
            voice={voiceRef}
            music={musicRef}
            sfx={sfxEvents}
            speech={speechWords}
            sfxVolume={sfx_volume}
            duration={safeDuration}
          />
          <ClipsLayer clips={clips} duration={safeDuration} />
          {entries.filter((e) => !e.scene.overlay).map((e) => renderScene(e, true))}
          {entries.filter((e) => e.scene.overlay).map((e) => renderScene(e, false))}
          {hudWindow ? (
            <Sequence from={hudWindow.from} durationInFrames={hudWindow.dur} name="hud">
              <AbsoluteFill style={{pointerEvents: 'none'}}>
                <HudLayer hud={hud!} durationInFrames={hudWindow.dur} />
              </AbsoluteFill>
            </Sequence>
          ) : null}
          {captions ? <CaptionsLayer captions={captions} /> : null}
          <Grain />
        </AbsoluteFill>
      </PlanTimingContext.Provider>
    </StyleContext.Provider>
  );
};

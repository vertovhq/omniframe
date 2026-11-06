import type {FC} from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {HudAccentChange, HudOverlay} from './types';
import {withAlpha} from './theme';
import type {ThemeColors} from './theme';

const CLAMP = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** Monospace stack for HUD values (tabular digits); Consolas exists on every render host. */
const HUD_MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, 'Roboto Mono', ui-monospace, monospace";

/** Safe-area margins: the plate sits below the platform's top UI / above its caption zone. */
const MARGIN_TOP = 170;
const MARGIN_BOTTOM = 300;

/**
 * HUD overlay layer: a semi-transparent dark plate ("game UI") with
 * label/monospace-value rows, anchored to the top or bottom edge. Drawn
 * over every scene without touching them — lives in its own Sequence and
 * never blocks scene transitions. After an accent_change fires, that row's
 * value swaps to the new one, turns accent-colored and pops once.
 */
export const HudLayer: FC<{
  hud: HudOverlay;
  durationInFrames: number;
  colors: ThemeColors;
}> = ({hud, durationInFrames, colors}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  // Accent changes are absolute on the timeline; inside this Sequence the
  // frame is local, so map back: absolute time = hud.at + frame/fps.
  const absT = hud.at + frame / fps;
  const changeOf = (i: number): HudAccentChange | null => {
    let active: HudAccentChange | null = null;
    for (const c of hud.accent_changes ?? []) {
      if (c && c.row === i && typeof c.at === 'number' && absT >= c.at) {
        active = c;
      }
    }
    return active;
  };

  const enterDur = Math.max(1, Math.round(fps * 0.3));
  const exitDur = Math.max(1, Math.round(fps * 0.25));
  const enter = interpolate(frame, [0, enterDur], [0, 1], {...CLAMP, easing: Easing.out(Easing.cubic)});
  const exitStart = Math.max(0, durationInFrames - exitDur);
  const exit = interpolate(frame, [exitStart, Math.max(exitStart + 1, durationInFrames - 1)], [0, 1], {
    ...CLAMP,
    easing: Easing.in(Easing.quad),
  });
  const dir = hud.pos === 'bottom' ? 1 : -1;
  const y = dir * 42 * ((1 - enter) + exit);

  return (
    <AbsoluteFill
      style={{
        display: 'flex',
        flexDirection: 'row', // AbsoluteFill по умолчанию column — нужен горизонтальный ряд
        justifyContent: 'center',
        alignItems: hud.pos === 'bottom' ? 'flex-end' : 'flex-start',
        paddingTop: hud.pos === 'bottom' ? undefined : MARGIN_TOP,
        paddingBottom: hud.pos === 'bottom' ? MARGIN_BOTTOM : undefined,
        opacity: enter * (1 - exit),
        transform: `translateY(${y.toFixed(2)}px)`,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '34px 58px',
          borderRadius: 28,
          background: 'rgba(6, 6, 12, 0.62)',
          border: '1px solid rgba(255, 255, 255, 0.14)',
          boxShadow: '0 24px 70px rgba(0, 0, 0, 0.45)',
        }}
      >
        {hud.rows.map((row, i) => (
          <div key={i} style={{display: 'flex', alignItems: 'center'}}>
            {i > 0 ? (
              <div
                style={{
                  width: 1,
                  alignSelf: 'stretch',
                  margin: '6px 56px',
                  background: 'rgba(255, 255, 255, 0.16)',
                }}
              />
            ) : null}
            <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14}}>
              <div
                style={{
                  fontSize: 33,
                  fontWeight: 600,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                  color: 'rgba(255, 255, 255, 0.58)',
                }}
              >
                {row?.label ?? ''}
              </div>
              {(() => {
                const change = changeOf(i);
                const changeFrame =
                  change !== null ? Math.max(0, Math.round((change.at - hud.at) * fps)) : -1;
                const flash = interpolate(
                  frame,
                  [changeFrame, changeFrame + Math.max(1, Math.round(fps * 0.35))],
                  [1, 0],
                  CLAMP
                );
                return (
                  <div
                    style={{
                      fontSize: 72,
                      fontWeight: 800,
                      fontFamily: HUD_MONO,
                      fontVariantNumeric: 'tabular-nums',
                      letterSpacing: '-0.01em',
                      whiteSpace: 'nowrap',
                      color: change !== null ? colors.accent : '#F5F6FA',
                      textShadow:
                        change !== null ? `0 0 26px ${withAlpha(colors.accent, 0.45 * flash)}` : undefined,
                      transform: `scale(${(1 + 0.12 * flash).toFixed(4)})`,
                    }}
                  >
                    {change !== null && change.value ? change.value : row?.value ?? ''}
                  </div>
                );
              })()}
            </div>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

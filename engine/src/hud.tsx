import {useMemo} from 'react';
import type {FC} from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {HudAccentChange, HudOverlay} from './types';
import {fontFor, useLayout, useStyle, withAlpha} from './style';
import {measureTextWidth, useFontsReady} from './text';

const CLAMP = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/**
 * HUD overlay layer: a semi-transparent dark plate ("game UI") with
 * label/monospace-value rows, anchored to the top or bottom edge of the safe area
 * (below the platform's top UI / above its caption zone). Drawn over every scene
 * without touching them — lives in its own Sequence and never blocks scene
 * transitions. After an accent_change fires, that row's value swaps to the new
 * one, turns accent-colored and pops once. The plate shrinks when its rows would
 * be wider than the safe area.
 */
export const HudLayer: FC<{
  hud: HudOverlay;
  durationInFrames: number;
}> = ({hud, durationInFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ready = useFontsReady();
  const style = useStyle();
  const {u, fs, safe} = useLayout();
  const {colors} = style;
  const label = fontFor(style, 'body');
  const mono = fontFor(style, 'mono');

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

  // Width of the plate at design size, from the widest text each row will ever show.
  const k = useMemo(() => {
    if (!ready) {
      return 1;
    }
    let total = fs(58) * 2;
    hud.rows.forEach((row, i) => {
      const labelW = measureTextWidth((row?.label ?? '').toUpperCase(), label.css, label.weight, fs(33), 0.16);
      let valueW = measureTextWidth(row?.value ?? '', mono.css, mono.weight, fs(72), -0.01, true);
      for (const c of hud.accent_changes ?? []) {
        if (c && c.row === i && c.value) {
          valueW = Math.max(valueW, measureTextWidth(c.value, mono.css, mono.weight, fs(72), -0.01, true));
        }
      }
      total += Math.max(labelW, valueW) + (i > 0 ? fs(56) * 2 + 1 : 0);
    });
    return total > safe.width ? safe.width / total : 1;
  }, [ready, hud.rows, hud.accent_changes, label.css, label.weight, mono.css, mono.weight, fs, safe.width]);

  const enterDur = Math.max(1, Math.round(fps * 0.3));
  const exitDur = Math.max(1, Math.round(fps * 0.25));
  const enter = interpolate(frame, [0, enterDur], [0, 1], {...CLAMP, easing: Easing.out(Easing.cubic)});
  const exitStart = Math.max(0, durationInFrames - exitDur);
  const exit = interpolate(frame, [exitStart, Math.max(exitStart + 1, durationInFrames - 1)], [0, 1], {
    ...CLAMP,
    easing: Easing.in(Easing.quad),
  });
  const dir = hud.pos === 'bottom' ? 1 : -1;
  const y = dir * u(42) * ((1 - enter) + exit);

  return (
    <AbsoluteFill
      style={{
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'row', // AbsoluteFill по умолчанию column — нужен горизонтальный ряд
        justifyContent: 'center',
        alignItems: hud.pos === 'bottom' ? 'flex-end' : 'flex-start',
        paddingTop: hud.pos === 'bottom' ? undefined : safe.top,
        paddingBottom: hud.pos === 'bottom' ? safe.bottom : undefined,
        paddingLeft: safe.left,
        paddingRight: safe.right,
        opacity: enter * (1 - exit),
        transform: `translateY(${y.toFixed(2)}px)`,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: `${fs(34) * k}px ${fs(58) * k}px`,
          borderRadius: fs(28) * k,
          // The plate stays dark on every style: it is a game-UI chip over whatever is below.
          background: 'rgba(6, 6, 12, 0.62)',
          border: `${Math.max(1, u(1))}px solid rgba(255, 255, 255, 0.14)`,
          boxShadow: `0 ${fs(24) * k}px ${fs(70) * k}px rgba(0, 0, 0, 0.45)`,
        }}
      >
        {hud.rows.map((row, i) => (
          <div key={i} style={{display: 'flex', alignItems: 'center'}}>
            {i > 0 ? (
              <div
                style={{
                  width: Math.max(1, u(1)),
                  alignSelf: 'stretch',
                  margin: `${fs(6) * k}px ${fs(56) * k}px`,
                  background: 'rgba(255, 255, 255, 0.16)',
                }}
              />
            ) : null}
            <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: fs(14) * k}}>
              <div
                style={{
                  fontFamily: label.css,
                  fontSize: fs(33) * k,
                  fontWeight: label.weight,
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
                      fontSize: fs(72) * k,
                      fontWeight: mono.weight,
                      fontFamily: mono.css,
                      fontVariantNumeric: 'tabular-nums',
                      letterSpacing: '-0.01em',
                      whiteSpace: 'nowrap',
                      color: change !== null ? colors.accent : '#F5F6FA',
                      textShadow:
                        change !== null
                          ? `0 0 ${fs(26) * k}px ${withAlpha(colors.accent, 0.45 * flash)}`
                          : undefined,
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

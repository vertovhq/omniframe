import type {ReactNode} from 'react';
import {useVideoConfig} from 'remotion';
import {fontFor, useLayout, useStyle, withAlpha} from '../style';
import {Counter} from './info';
import {useT} from './timing';

// Mock-ups: an app window with a typed prompt, a stack of tool calls, a laptop or monitor frame that
// holds a scene or a video, and a counter pinned to a corner. Colours and fonts come from props; the
// defaults are the style's own colours, so a block brings no look of its own. Times are seconds on
// the scene's clock; sizes are design px (1080 short side).

/** Seconds since `at`, 0 before it. */
const since = (t: number, at: number): number => Math.max(0, t - at);

/** A window with a title bar and a body. `prompt` is typed in after `typeFrom`, one character at a time. */
export const AppWindow = ({
  title = '',
  prompt = '',
  typeFrom = 0,
  cps = 18,
  width = 900,
  height = 520,
  fill,
  ink,
  children,
}: {
  title?: string;
  /** The text typed into the prompt line. */
  prompt?: string;
  /** Seconds on the scene clock when typing starts. */
  typeFrom?: number;
  /** Characters per second. */
  cps?: number;
  width?: number;
  height?: number;
  /** Any CSS colour. Default: the style's background. */
  fill?: string;
  /** Text and chrome colour. Default: the style's text colour. */
  ink?: string;
  children?: ReactNode;
}) => {
  const t = useT();
  const style = useStyle();
  const {u, fs} = useLayout();
  const font = fontFor(style, 'body');
  const colour = ink ?? style.colors.text;
  const typed = prompt.slice(0, Math.floor(since(t, typeFrom) * cps));
  const cursorOn = Math.floor(t * 2) % 2 === 0;
  return (
    <div
      style={{
        boxSizing: 'border-box',
        width: u(width),
        height: u(height),
        borderRadius: u(18),
        overflow: 'hidden',
        background: fill ?? withAlpha(style.colors.bg, 0.96),
        border: `${u(2)}px solid ${withAlpha(colour, 0.25)}`,
        display: 'flex',
        flexDirection: 'column',
        fontFamily: font.css,
        fontWeight: font.weight,
        color: colour,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: u(10),
          padding: `${u(14)}px ${u(18)}px`,
          background: withAlpha(colour, 0.08),
        }}
      >
        {[0, 1, 2].map((i) => (
          <span key={i} style={{width: u(14), height: u(14), borderRadius: '50%', background: withAlpha(colour, 0.35)}} />
        ))}
        <span style={{marginLeft: u(12), fontSize: fs(26), opacity: 0.75}}>{title}</span>
      </div>
      <div style={{flex: 1, padding: u(24), fontSize: fs(34), lineHeight: 1.35}}>
        {children}
        {prompt ? (
          <div style={{display: 'flex', alignItems: 'center'}}>
            <span>{typed}</span>
            <span
              style={{
                display: 'inline-block',
                width: u(14),
                height: fs(34),
                marginLeft: u(4),
                background: cursorOn ? style.colors.accent : 'transparent',
              }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};

/** One tool call in a ToolCallStack: its name, its arguments as text, and whether it has finished. */
export type ToolCall = {name: string; args?: string; done?: boolean};

/**
 * Tool calls stacked top to bottom. Call `i` slides in at `at + i * step` seconds; a finished call
 * shows a solid marker, a running one a ring.
 */
export const ToolCallStack = ({
  calls,
  at = 0,
  step = 0.3,
  width = 760,
  rowHeight = 118,
  fill,
  ink,
  marker,
}: {
  calls: ToolCall[];
  at?: number;
  step?: number;
  width?: number;
  rowHeight?: number;
  fill?: string;
  ink?: string;
  /** Marker colour. Default: the style's accent. */
  marker?: string;
}) => {
  const t = useT();
  const style = useStyle();
  const {u, fs} = useLayout();
  const font = fontFor(style, 'body');
  const colour = ink ?? style.colors.text;
  const dot = marker ?? style.colors.accent;
  return (
    <div style={{position: 'relative', width: u(width), height: u(calls.length * rowHeight), fontFamily: font.css, color: colour}}>
      {calls.map((call, i) => {
        const p = Math.min(1, since(t, at + i * step) / 0.25);
        const eased = 1 - Math.pow(1 - p, 3);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              top: u(i * rowHeight),
              left: u((1 - eased) * -40),
              width: u(width),
              boxSizing: 'border-box',
              padding: `${u(18)}px ${u(24)}px`,
              borderRadius: u(16),
              background: fill ?? withAlpha(style.colors.bg, 0.9),
              border: `${u(2)}px solid ${withAlpha(colour, 0.2)}`,
              opacity: eased,
              display: 'flex',
              alignItems: 'center',
              gap: u(18),
            }}
          >
            <span
              style={{
                width: u(20),
                height: u(20),
                borderRadius: '50%',
                flex: 'none',
                background: call.done ? dot : 'transparent',
                border: `${u(3)}px solid ${dot}`,
              }}
            />
            <div style={{minWidth: 0}}>
              <div style={{fontSize: fs(34), fontWeight: 700}}>{call.name}</div>
              {call.args ? <div style={{fontSize: fs(24), opacity: 0.7}}>{call.args}</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/**
 * A laptop or monitor frame. The children fill the screen (a scene, an image or a video), so the
 * picture inside keeps its own size and fits the screen.
 */
export const ScreenFrame = ({
  kind = 'laptop',
  width = 1000,
  bezel,
  children,
}: {
  kind?: 'laptop' | 'monitor';
  /** Design px of the whole frame, bezel included. */
  width?: number;
  /** Bezel colour. Default: the style's text colour at 85 %. */
  bezel?: string;
  children?: ReactNode;
}) => {
  const style = useStyle();
  const {u} = useLayout();
  const ratio = kind === 'laptop' ? 0.625 : 0.5625; // screen height / width: 16:10 laptop, 16:9 monitor
  const bezelPx = 22;
  const screenW = width - bezelPx * 2;
  const screenH = screenW * ratio;
  const frame = bezel ?? withAlpha(style.colors.text, 0.85);
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
      <div
        style={{
          boxSizing: 'border-box',
          width: u(width),
          padding: u(bezelPx),
          borderRadius: u(kind === 'laptop' ? 22 : 16),
          background: frame,
        }}
      >
        <div style={{position: 'relative', width: u(screenW), height: u(screenH), overflow: 'hidden', borderRadius: u(6), background: '#000'}}>
          <div style={{position: 'absolute', inset: 0}}>{children}</div>
        </div>
      </div>
      {kind === 'laptop' ? (
        <div style={{width: u(width * 1.12), height: u(16), borderRadius: `0 0 ${u(18)}px ${u(18)}px`, background: frame}} />
      ) : null}
    </div>
  );
};

/**
 * A number that counts up, pinned to a corner of the safe area, with a label under it. It uses
 * `Counter`, so `from`, `to`, `start`, `dur` and `decimals` mean what they mean there.
 */
export const CounterOverlay = ({
  to,
  from = 0,
  start = 0,
  dur = 1.2,
  decimals = 0,
  label,
  corner = 'upper-right',
  color,
  size = 120,
}: {
  to: number;
  from?: number;
  start?: number;
  dur?: number;
  decimals?: number;
  label?: string;
  corner?: 'upper-left' | 'upper-right' | 'lower-left' | 'lower-right';
  /** Number colour. Default: the style's accent. */
  color?: string;
  /** Number size in design px. */
  size?: number;
}) => {
  const style = useStyle();
  const {fs, safe} = useLayout();
  const {width} = useVideoConfig();
  const display = fontFor(style, 'display');
  const right = corner.endsWith('right');
  const upper = corner.startsWith('upper');
  const ink = color ?? style.colors.accent;
  return (
    <div
      style={{
        position: 'absolute',
        left: right ? undefined : safe.left,
        right: right ? width - (safe.left + safe.width) : undefined,
        top: upper ? safe.top : undefined,
        bottom: upper ? undefined : safe.top,
        textAlign: right ? 'right' : 'left',
        color: ink,
      }}
    >
      <div
        style={{
          fontFamily: display.css,
          fontWeight: display.weight,
          fontSize: fs(size),
          lineHeight: 1,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        <Counter to={to} from={from} start={start} dur={dur} decimals={decimals} />
      </div>
      {label ? <div style={{fontSize: fs(30), opacity: 0.8, marginTop: 6}}>{label}</div> : null}
    </div>
  );
};

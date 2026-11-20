import {useId} from 'react';
import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, random} from 'remotion';

// Two picture filters (built from inline SVG) and a seeded shake. The transitions and the energy
// kit are made of them; they work on any children and know nothing about the clock.

/** `url(#id)` safe id from React's `useId` (which contains colons). */
const filterId = (raw: string): string => `fx${raw.replace(/[^a-zA-Z0-9_-]/g, '')}`;

type Fill = {style?: CSSProperties; children?: ReactNode};

/**
 * Blurs the children along one axis (`x`, `y` in real px): a motion-blur smear. Both zero draws
 * the children untouched. Fills its parent.
 */
export const MotionBlur = ({x = 0, y = 0, style, children}: Fill & {x?: number; y?: number}) => {
  const id = filterId(useId());
  const on = x > 0.4 || y > 0.4;
  return (
    <AbsoluteFill style={{...style, filter: on ? `url(#${id})` : style?.filter}}>
      {on ? (
        <svg width="0" height="0" style={{position: 'absolute'}}>
          <filter id={id} x="-10%" y="-10%" width="120%" height="120%" colorInterpolationFilters="sRGB">
            <feGaussianBlur stdDeviation={`${x.toFixed(2)} ${y.toFixed(2)}`} edgeMode="duplicate" />
          </filter>
        </svg>
      ) : null}
      {children}
    </AbsoluteFill>
  );
};

/**
 * Chromatic aberration: the red and blue channels of the children move apart by `amount` real px
 * along `angle` degrees (0 = sideways). Fills its parent.
 */
export const RgbSplit = ({amount = 8, angle = 0, style, children}: Fill & {amount?: number; angle?: number}) => {
  const id = filterId(useId());
  const on = amount > 0.2;
  const rad = (angle * Math.PI) / 180;
  const dx = Math.cos(rad) * amount;
  const dy = Math.sin(rad) * amount;
  return (
    <AbsoluteFill style={{...style, filter: on ? `url(#${id})` : style?.filter}}>
      {on ? (
        <svg width="0" height="0" style={{position: 'absolute'}}>
          <filter id={id} x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
            <feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r" />
            <feOffset in="r" dx={-dx} dy={-dy} result="ro" />
            <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="g" />
            <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="b" />
            <feOffset in="b" dx={dx} dy={dy} result="bo" />
            <feBlend in="ro" in2="g" mode="screen" result="rg" />
            <feBlend in="rg" in2="bo" mode="screen" />
          </filter>
        </svg>
      ) : null}
      {children}
    </AbsoluteFill>
  );
};

/**
 * A repeatable shake for frame `frame`: `{x, y}` in real px (at most `amp`) and `rot` in degrees.
 * The same seed and frame always give the same offset. `every` holds each value for that many frames.
 */
export const shakeOffset = (frame: number, seed: string, amp: number, every = 1): {x: number; y: number; rot: number} => {
  const i = Math.floor(frame / Math.max(1, every));
  const r = (k: string) => random(`${seed}-${k}-${i}`) * 2 - 1;
  return {x: r('x') * amp, y: r('y') * amp, rot: r('r') * amp * 0.03};
};

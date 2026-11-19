import type {CSSProperties, ReactNode} from 'react';
import {fontFor, hexToRgb, useLayout, useStyle} from '../style';
import type {FontRole} from '../style';

/** Black or white, whichever reads better on the hex colour `bg`. */
export const readableOn = (bg: string): string => {
  const [r, g, b] = hexToRgb(bg);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 150 ? '#0A0A12' : '#FFFFFF';
};

export type TextProps = {
  children?: ReactNode;
  /** Design px for a 1080 short side; scaled by the frame and by the style's `text_scale`. */
  size?: number;
  /** Any CSS colour. Default: the style's `text` colour. */
  color?: string;
  /** Font role of the style. Default `display`. */
  font?: FontRole;
  /** Overrides the weight of the role. */
  weight?: number;
  /** Outline width in design px, drawn behind the fill. */
  stroke?: number;
  /** Default: the style's background colour. */
  strokeColor?: string;
  /** Soft drop shadow, blur in design px. */
  shadow?: number;
  /** Coloured halo around the letters, blur in design px. */
  glow?: number;
  /** Default: `color`. */
  glowColor?: string;
  /** Capital letters. */
  caps?: boolean;
  align?: 'left' | 'center' | 'right';
  /** Letter spacing in design px. */
  spacing?: number;
  lineHeight?: number;
  /** Maximum width in design px; longer text wraps. */
  maxWidth?: number;
  style?: CSSProperties;
};

/** Text in the style's fonts, with the usual treatments: stroke, shadow, glow, capitals. */
export const Text = ({
  children,
  size = 64,
  color,
  font = 'display',
  weight,
  stroke = 0,
  strokeColor,
  shadow = 0,
  glow = 0,
  glowColor,
  caps = false,
  align = 'center',
  spacing = 0,
  lineHeight = 1.1,
  maxWidth,
  style: extra,
}: TextProps) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const face = fontFor(style, font);
  const ink = color ?? style.colors.text;
  const shadows: string[] = [];
  if (glow > 0) {
    shadows.push(`0 0 ${u(glow)}px ${glowColor ?? ink}`, `0 0 ${u(glow * 2)}px ${glowColor ?? ink}`);
  }
  if (shadow > 0) {
    shadows.push(`0 ${u(shadow * 0.5)}px ${u(shadow)}px rgba(0, 0, 0, ${style.isDark ? 0.55 : 0.3})`);
  }
  return (
    <div
      style={{
        fontFamily: face.css,
        fontWeight: weight ?? face.weight,
        fontSize: fs(size),
        lineHeight,
        color: ink,
        textAlign: align,
        textTransform: caps ? 'uppercase' : undefined,
        letterSpacing: spacing ? u(spacing) : undefined,
        maxWidth: maxWidth ? u(maxWidth) : undefined,
        WebkitTextStroke: stroke > 0 ? `${u(stroke)}px ${strokeColor ?? style.colors.bg}` : undefined,
        paintOrder: 'stroke fill',
        textShadow: shadows.length ? shadows.join(', ') : undefined,
        ...extra,
      }}
    >
      {children}
    </div>
  );
};

/** A rounded plate with a short text on it (a tag, a stamp, a name board). */
export const Label = ({
  children,
  size = 48,
  fill,
  color,
  border,
  borderWidth = 4,
  rotate = 0,
  caps = false,
  style: extra,
}: {
  children?: ReactNode;
  size?: number;
  /** Plate colour. Default: the style's accent. */
  fill?: string;
  /** Text colour. Default: black or white, whichever reads on `fill`. */
  color?: string;
  /** Outline colour. Default: none. */
  border?: string;
  /** Outline width in design px. */
  borderWidth?: number;
  /** Degrees. */
  rotate?: number;
  caps?: boolean;
  style?: CSSProperties;
}) => {
  const style = useStyle();
  const {fs, u} = useLayout();
  const plate = fill ?? style.colors.accent;
  return (
    <div
      style={{
        display: 'inline-block',
        padding: `${fs(size * 0.22)}px ${fs(size * 0.55)}px`,
        borderRadius: fs(size * 0.35),
        background: plate,
        border: border ? `${u(borderWidth)}px solid ${border}` : undefined,
        boxShadow: `0 ${u(8)}px ${u(18)}px rgba(0, 0, 0, ${style.isDark ? 0.45 : 0.2})`,
        transform: rotate ? `rotate(${rotate}deg)` : undefined,
        ...extra,
      }}
    >
      <Text size={size} color={color ?? readableOn(plate)} caps={caps} lineHeight={1.05}>
        {children}
      </Text>
    </div>
  );
};

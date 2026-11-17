import type {CSSProperties, FC} from 'react';
import {AbsoluteFill, Img, OffthreadVideo} from 'remotion';
import {grainBackgroundImage, resolveMedia, useStyle} from './style';

const VIDEO_EXT = /\.(mp4|m4v|webm|mov)(\?.*)?$/i;

/**
 * The plan's background from `style.background` (solid color, gradient or image/video),
 * with the vignette on top. Drawn once at the bottom of the frame, and again under every
 * full scene so that a full scene hides the clips below it.
 */
export const Background: FC = () => {
  const {colors, background, vignette} = useStyle();

  const base: CSSProperties = {backgroundColor: colors.bg};
  let media: JSX.Element | null = null;

  if (background.type === 'gradient' && background.stops.length > 0) {
    const stops = background.stops.length === 1 ? [background.stops[0], background.stops[0]] : background.stops;
    const angle = typeof background.angle === 'number' && Number.isFinite(background.angle) ? background.angle : 180;
    base.backgroundImage = `linear-gradient(${angle}deg, ${stops.join(', ')})`;
  } else if (background.type === 'media') {
    const style: CSSProperties = {
      width: '100%',
      height: '100%',
      objectFit: background.fit === 'contain' ? 'contain' : 'cover',
    };
    media = VIDEO_EXT.test(background.src) ? (
      <OffthreadVideo muted src={resolveMedia(background.src)} style={style} />
    ) : (
      <Img src={resolveMedia(background.src)} style={style} />
    );
  }

  return (
    <AbsoluteFill style={base}>
      {media}
      {vignette ? <AbsoluteFill style={{backgroundImage: vignette}} /> : null}
    </AbsoluteFill>
  );
};

/** Faint film grain over everything (static tile, opacity from `style.grain`). */
export const Grain: FC = () => {
  const {grain} = useStyle();
  if (grain <= 0) {
    return null;
  }
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        backgroundImage: grainBackgroundImage,
        backgroundRepeat: 'repeat',
        backgroundSize: '240px 240px',
        opacity: grain,
      }}
    />
  );
};

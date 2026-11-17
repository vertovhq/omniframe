import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Main';
import {ensureFonts} from './style';
import {FORMAT_SIZES} from './types';
import type {EngineProps, PlanFormat} from './types';

ensureFonts();

const defaultProps: EngineProps = {
  version: 2,
  format: '9:16',
  fps: 30,
  duration: 6,
  style: 'dark',
  scenes: [
    {at: 0, kind: 'words', text: 'это движок кинетического видео'},
    {at: 2.4, kind: 'title', kicker: 'глава 01', text: 'собери ролик из json'},
    {at: 4.2, kind: 'big', text: 'ARGUS'},
  ],
};

const sizeOf = (format: PlanFormat | undefined) => FORMAT_SIZES[format ?? '9:16'] ?? FORMAT_SIZES['9:16'];

export const RemotionRoot: React.FC = () => {
  const initial = sizeOf(defaultProps.format);
  return (
    <Composition
      id="Kinetic"
      component={Main}
      width={initial.width}
      height={initial.height}
      fps={30}
      durationInFrames={180}
      defaultProps={defaultProps}
      calculateMetadata={({props}: {props: EngineProps}) => {
        const fps = props.fps && props.fps > 0 ? Math.round(props.fps) : 30;
        const dur = props.duration && props.duration > 0 ? props.duration : 12.5;
        const {width, height} = sizeOf(props.format);
        return {
          width,
          height,
          fps,
          durationInFrames: Math.max(1, Math.ceil(dur * fps)),
        };
      }}
    />
  );
};

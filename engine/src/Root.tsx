import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Main';
import {ensureFonts} from './theme';
import type {KineticProps} from './types';

ensureFonts();

const defaultProps: KineticProps = {
  fps: 30,
  duration: 6,
  theme: 'dark',
  scenes: [
    {at: 0, kind: 'words', text: 'это движок кинетического видео'},
    {at: 2.4, kind: 'title', kicker: 'глава 01', text: 'собери ролик из json'},
    {at: 4.2, kind: 'big', text: 'ARGUS'},
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Kinetic"
      component={Main}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={180}
      defaultProps={defaultProps}
      calculateMetadata={({props}) => {
        const fps = props.fps && props.fps > 0 ? Math.round(props.fps) : 30;
        const dur = props.duration && props.duration > 0 ? props.duration : 12.5;
        return {
          fps,
          durationInFrames: Math.max(1, Math.ceil(dur * fps)),
        };
      }}
    />
  );
};

import React from 'react';
import {Composition} from 'remotion';
import {HorrorTitle} from './HorrorTitle';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="HorrorTitle"
    component={HorrorTitle}
    durationInFrames={72}
    fps={24}
    width={1920}
    height={1080}
    defaultProps={{title: 'HOLLOW LANE', subtitle: 'a short horror film'}}
  />
);

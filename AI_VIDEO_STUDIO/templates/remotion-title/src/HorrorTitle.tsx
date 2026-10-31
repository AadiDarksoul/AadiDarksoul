import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, random} from 'remotion';

export const HorrorTitle: React.FC<{title: string; subtitle: string}> = ({title, subtitle}) => {
  const f = useCurrentFrame();
  const fade = interpolate(f, [0, 24, 60, 72], [0, 1, 1, 0], {extrapolateRight: 'clamp'});
  const scale = interpolate(f, [0, 72], [1.08, 1.0]);
  const flicker = random(`flicker-${f}`) > 0.92 ? 0.35 : 1;
  return (
    <AbsoluteFill style={{background: 'radial-gradient(circle at 50% 45%, #2a0d0d 0%, #050304 70%)', justifyContent: 'center', alignItems: 'center'}}>
      <div style={{opacity: fade * flicker, transform: `scale(${scale})`, textAlign: 'center', fontFamily: 'DejaVu Serif, serif'}}>
        <div style={{color: '#d8c8b0', fontSize: 150, letterSpacing: 24, textShadow: '0 0 40px #8b0000'}}>{title}</div>
        <div style={{color: '#8a7a6a', fontSize: 44, letterSpacing: 10, marginTop: 20}}>{subtitle}</div>
      </div>
    </AbsoluteFill>
  );
};

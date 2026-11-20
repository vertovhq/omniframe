import type {ReactNode} from 'react';
import {AbsoluteFill} from 'remotion';
import {useLayout} from '../style';
import {Gradient, SceneTrack, Stage, Text} from '../kit';

// Shared by the kit previews (`<group>.tsx` next to this file). ARGUS renders one still per block
// to build a group's contact strip (`studio_guide(kit_group=...)`); it copies this file and the
// group's file into a throw-away project as components and plays them as one `custom` scene.
// A group file lists `{name: 'Block', at: seconds, node: () => ...}` entries: one slot of `SLOT`
// seconds each, and the still is taken `at` seconds into the slot.

export const SLOT = 2;

export type Block = {name: string; at: number; node: () => ReactNode};

/** Every block of a group, one slot after another, each on its own dark backdrop. */
export function Sheet({blocks}: {blocks: Block[]}) {
  return (
    <SceneTrack
      enter={{kind: 'fade', dur: 0.04}}
      scenes={blocks.map((block, i) => ({
        at: i * SLOT,
        render: () => <Stage bg="linear-gradient(160deg, #0A0F1E, #1B2447)">{block.node()}</Stage>,
      }))}
    />
  );
}

/** Centres its children in the frame. */
export const Mid = ({children}: {children?: ReactNode}) => (
  <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>{children}</AbsoluteFill>
);

/** Pads its children away from the frame edges, so flowing blocks (a timecode, a readout) have room. */
export const Pad = ({children, align = 'flex-start'}: {children?: ReactNode; align?: 'flex-start' | 'flex-end' | 'center'}) => {
  const {u} = useLayout();
  return <AbsoluteFill style={{padding: u(70), alignItems: align, justifyContent: 'flex-start'}}>{children}</AbsoluteFill>;
};

/** A stand-in picture to put the effects on: a tinted panel with a word and a few shapes, detailed enough to show blur, zoom and shake. */
export const Sample = ({label = 'ARGUS', hue = '#2F6BFF'}: {label?: string; hue?: string}) => {
  const {u} = useLayout();
  return (
    <Stage bg={`linear-gradient(135deg, ${hue}, #0C1226)`}>
      <Gradient stops={['#FFFFFF22', '#00000000']} kind="radial" at={[30, 25]} />
      <AbsoluteFill style={{backgroundImage: 'repeating-linear-gradient(90deg, #FFFFFF14 0 2px, transparent 2px 120px)'}} />
      <Mid>
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u(30)}}>
          <div style={{width: u(220), height: u(220), borderRadius: '50%', border: `${u(14)}px solid #FFFFFF`}} />
          <Text size={150} color="#FFFFFF" caps>
            {label}
          </Text>
        </div>
      </Mid>
    </Stage>
  );
};

import {SceneTrack} from '../kit';
import type {TransitionKind} from '../kit';
import {Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

// Each tile is a cut from scene A to scene B, caught halfway (the cut starts at 0.5 s and lasts 0.5 s).
const cut = (kind: TransitionKind) => (
  <SceneTrack
    scenes={[
      {at: 0, render: () => <Sample label="A" hue="#E4572E" />},
      {at: 0.5, enter: {kind, dur: 0.5}, render: () => <Sample label="B" hue="#1FA37A" />},
    ]}
  />
);

const BLOCKS: Block[] = [
  {name: 'fade', at: 0.75, node: () => cut('fade')},
  {name: 'whip', at: 0.75, node: () => cut('whip')},
  {name: 'zoom', at: 0.75, node: () => cut('zoom')},
  {name: 'wipe', at: 0.75, node: () => cut('wipe')},
  {name: 'slice', at: 0.75, node: () => cut('slice')},
  {name: 'split', at: 0.75, node: () => cut('split')},
  {name: 'flash', at: 0.7, node: () => cut('flash')},
  {name: 'glitch', at: 0.75, node: () => cut('glitch')},
  {name: 'shake', at: 0.7, node: () => cut('shake')},
  {name: 'ramp', at: 0.75, node: () => cut('ramp')},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

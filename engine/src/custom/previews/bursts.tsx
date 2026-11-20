import {GlowBurst, LightSweep, Shockwave, Sparks, SpeedLines} from '../kit';
import {Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'SpeedLines', at: 0.4, node: () => <><Sample /><SpeedLines at={0.3} dur={1.2} /></>},
  {name: 'Shockwave', at: 0.6, node: () => <><Sample /><Shockwave at={0.3} dur={1.2} color="#7CF0FF" /></>},
  {name: 'GlowBurst', at: 0.5, node: () => <><Sample /><GlowBurst at={0.3} dur={1.2} /></>},
  {name: 'Sparks', at: 0.8, node: () => <><Sample /><Sparks at={0.3} y={70} angle={270} spread={120} /></>},
  {name: 'LightSweep', at: 0.7, node: () => <><Sample /><LightSweep at={0.3} dur={1.2} /></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

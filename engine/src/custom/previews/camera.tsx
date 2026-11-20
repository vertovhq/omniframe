import {Camera, Dolly, PunchIn, RackFocus} from '../kit';
import {Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'Camera', at: 1.9, node: () => <Camera zoom={0.25}><Sample /></Camera>},
  {name: 'Dolly', at: 1.2, node: () => <Dolly from={1} to={1.5} at={0.2} dur={2} ease="out" panTo={[-80, 0]}><Sample /></Dolly>},
  {name: 'PunchIn', at: 0.5, node: () => <PunchIn at={0.3} zoom={0.35} hold={1}><Sample /></PunchIn>},
  {name: 'RackFocus', at: 0.9, node: () => <RackFocus from={34} to={0} at={0.2} dur={1.4}><Sample /></RackFocus>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

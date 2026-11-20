import {CardStack, Device, Parallax, Text, Tilt} from '../kit';
import {Mid, Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const card = (label: string, color: string) => (
  <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: color}}>
    <Text size={70} color="#FFFFFF" caps>{label}</Text>
  </div>
);

const BLOCKS: Block[] = [
  {name: 'Tilt', at: 1.2, node: () => <><Sample label="" /><Tilt x={10} y={-22} from={{x: 0, y: 0}}><div style={{width: 760, height: 460, borderRadius: 30, overflow: 'hidden'}}>{card('PANEL', '#E4572E')}</div></Tilt></>},
  {name: 'Parallax', at: 1.5, node: () => (
    <Parallax drift={[-260, 0]} layers={[
      {depth: 0, node: <Sample label="" hue="#1B2A6B" />},
      {depth: 0.5, node: <Mid><Text size={260} color="#FFFFFF33" caps>far</Text></Mid>},
      {depth: 1, node: <Mid><Text size={150} color="#FFFFFF" caps>near</Text></Mid>},
    ]} />
  )},
  {name: 'CardStack', at: 1.4, node: () => <><Sample label="" /><CardStack width={560} height={340} items={[card('ONE', '#2F6BFF'), card('TWO', '#E4572E'), card('THREE', '#1FA37A')]} /></>},
  {name: 'Device', at: 1.0, node: () => <><Sample label="" hue="#101830" /><Device kind="phone"><Sample label="APP" hue="#E4572E" /></Device></>},
  {name: 'Device_laptop', at: 1.0, node: () => <><Sample label="" hue="#101830" /><Device kind="laptop"><Sample label="APP" hue="#1FA37A" /></Device></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

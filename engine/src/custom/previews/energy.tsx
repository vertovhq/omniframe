import {Aberration, Boil, Burst, FilmBurn, Flash, FreezeStamp, LensFlare, Shake, Snap, Stepped, Vhs} from '../kit';
import {Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'Shake', at: 0.53, node: () => <Shake at={0.5}><Sample /></Shake>},
  {name: 'Stepped', at: 1.0, node: () => <Stepped fps={6}><Sample label="on twos" /></Stepped>},
  {name: 'Boil', at: 1.0, node: () => <Boil strength={1.4}><Sample label="boil" /></Boil>},
  {name: 'Snap', at: 0.55, node: () => <Snap at={0.5} dir="right"><Sample /></Snap>},
  {name: 'Aberration', at: 0.56, node: () => <Aberration at={0.5} strength={1.6}><Sample /></Aberration>},
  {name: 'Vhs', at: 1.0, node: () => <Vhs><Sample label="vhs" /></Vhs>},
  {name: 'FreezeStamp', at: 1.2, node: () => <FreezeStamp at={0.4} label="FROZEN"><Sample /></FreezeStamp>},
  {name: 'Flash', at: 0.54, node: () => <><Sample /><Flash at={0.5} color="#FF3D6E" strength={0.8} /></>},
  {name: 'FilmBurn', at: 0.8, node: () => <><Sample /><FilmBurn at={0.2} dur={1.4} /></>},
  {name: 'LensFlare', at: 1.0, node: () => <><Sample /><LensFlare x={28} y={30} /></>},
  {name: 'Burst', at: 0.9, node: () => <Burst at={0.2} dur={1.6} rate={8} items={[<Sample key="a" label="1" hue="#E4572E" />, <Sample key="b" label="2" hue="#1FA37A" />, <Sample key="c" label="3" hue="#7B2FF7" />]} />},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

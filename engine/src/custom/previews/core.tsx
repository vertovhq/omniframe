import {Fade, Label, Pop, Slide, Stage, Text} from '../kit';
import {Mid, Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'Fade', at: 0.55, node: () => <Mid><Fade from={0.2} inDur={0.8}><Text size={160} caps>Fade</Text></Fade></Mid>},
  {name: 'Pop', at: 0.35, node: () => <Mid><Pop from={0.2} dur={0.6}><Text size={160} caps>Pop</Text></Pop></Mid>},
  {name: 'Slide', at: 0.45, node: () => <Mid><Slide from={0.2} dur={0.7} side="left" dist={400}><Text size={160} caps>Slide</Text></Slide></Mid>},
  {name: 'Stage', at: 1.0, node: () => <Stage bg="linear-gradient(120deg, #E4572E, #2F6BFF)"><Mid><Text size={120} color="#FFFFFF" caps>Stage bg</Text></Mid></Stage>},
  {name: 'Text', at: 1.0, node: () => <Mid><Text size={150} color="#FFFFFF" stroke={6} strokeColor="#E4572E" glow={30} glowColor="#E4572E" caps>Text</Text></Mid>},
  {name: 'Label', at: 1.0, node: () => <><Sample label="" /><Mid><Label size={90} fill="#E4572E" rotate={-6} caps>Label</Label></Mid></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

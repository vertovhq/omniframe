import {Bubble, Card, Checklist, Counter, Delta, Plate, PollCard, ProgressBar, Text} from '../kit';
import {Mid, Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'Counter', at: 1.6, node: () => <><Sample label="" /><Mid><Counter to={250000} dur={1.2} size={190} color="#FFFFFF" suffix=" $" /></Mid></>},
  {name: 'Plate', at: 1.0, node: () => <><Sample label="" /><Mid><Plate label="SPEED" value="312 km/h" /></Mid></>},
  {name: 'Delta', at: 1.0, node: () => <><Sample label="" /><Mid><Delta value="+24%" label="vs last week" at={0.2} hold={1.5} /></Mid></>},
  {name: 'PollCard', at: 1.8, node: () => <><Sample label="" /><Mid><PollCard title="Which one?" options={[{label: 'Option A', share: 0.62}, {label: 'Option B', share: 0.38}]} pick={0} at={0.2} /></Mid></>},
  {name: 'Checklist', at: 1.8, node: () => <><Sample label="" /><Mid><Checklist items={['Record', 'Edit', 'Publish']} at={0.2} /></Mid></>},
  {name: 'ProgressBar', at: 1.4, node: () => <><Sample label="" /><Mid><ProgressBar value={0.72} at={0.2} dur={1.2} label="Upload" /></Mid></>},
  {name: 'Bubble', at: 1.0, node: () => <><Sample label="" /><Mid><Bubble tail="bottom"><Text size={70} color="#0A0A12">Hello there!</Text></Bubble></Mid></>},
  {name: 'Card', at: 1.0, node: () => <><Sample label="" /><Mid><Card width={620}><Text size={64}>A card with the style's panel look</Text></Card></Mid></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

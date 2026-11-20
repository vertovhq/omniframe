import {Boxed, LetterCascade, PathText, Skew, Stretch, Text, Typewriter, WordSlam, WordSwap} from '../kit';
import {Mid, Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'WordSlam', at: 1.5, node: () => <><Sample label="" /><Mid><WordSlam text="THIS CHANGES *EVERYTHING* NOW" size={150} skew={-8} /></Mid></>},
  {name: 'Boxed', at: 1.0, node: () => <><Sample label="" /><Mid><Text size={110} caps>make it <Boxed at={0.3}>loud</Boxed></Text></Mid></>},
  {name: 'Skew', at: 1.0, node: () => <><Sample label="" /><Mid><Skew x={-14} fromX={0} at={0.2}><Text size={170} caps>FASTER</Text></Skew></Mid></>},
  {name: 'Stretch', at: 0.5, node: () => <><Sample label="" /><Mid><Stretch axis="x" from={2.4} at={0.2}><Text size={170} caps>SLAM</Text></Stretch></Mid></>},
  {name: 'LetterCascade', at: 0.7, node: () => <><Sample label="" /><Mid><LetterCascade text="Letters *fall* in" size={130} /></Mid></>},
  {name: 'Typewriter', at: 1.3, node: () => <><Sample label="" /><Mid><Typewriter text={'> loading the future_\n> 100% ready'} size={64} /></Mid></>},
  {name: 'WordSwap', at: 1.1, node: () => <><Sample label="" /><Mid><Text size={100} caps>Made for <WordSwap words={['creators', 'teams', 'everyone']} every={0.5} at={0.1} size={100} /></Text></Mid></>},
  {name: 'PathText', at: 1.2, node: () => <><Sample label="" /><Mid><PathText text="TEXT ON A CURVE" path="arc" size={96} /></Mid></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

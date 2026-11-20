import {CornerBrackets, Crosshair, FrameTicks, HudLayer, Readout, ScanLine, Scrubber, StatusPill, Ticker, Timecode} from '../kit';
import {Mid, Pad, Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'CornerBrackets', at: 1.2, node: () => <><Sample /><CornerBrackets inset={50} breathe={0.08} /></>},
  {name: 'FrameTicks', at: 1.2, node: () => <><Sample /><FrameTicks edges={['top', 'bottom', 'left', 'right']} /></>},
  {name: 'Timecode', at: 1.2, node: () => <><Sample /><Pad><Timecode rec /></Pad></>},
  {name: 'Scrubber', at: 1.3, node: () => <><Sample /><Mid><Scrubber width={80} marks={[0.2, 0.55, 0.85]} left="00:00" right="00:30" /></Mid></>},
  {name: 'Readout', at: 1.6, node: () => <><Sample /><Pad><Readout title="SCAN" rows={[{label: 'SIGNAL', value: '98.4%'}, {label: 'LATENCY', value: '12 ms'}, {label: 'NODES', value: '4 096'}]} hot={[0]} /></Pad></>},
  {name: 'Ticker', at: 1.2, node: () => <><Sample /><Mid><Ticker items={['BREAKING', 'LIVE FEED', 'ALL SYSTEMS GO']} fill="#00000088" /></Mid></>},
  {name: 'ScanLine', at: 0.9, node: () => <><Sample /><ScanLine /></>},
  {name: 'Crosshair', at: 1.2, node: () => <><Sample /><Crosshair x={35} y={40} to={[65, 58]} /></>},
  {name: 'StatusPill', at: 1.0, node: () => <><Sample /><Pad><StatusPill>LIVE</StatusPill></Pad></>},
  {name: 'HudLayer', at: 1.5, node: () => <><Sample /><HudLayer ticks timecode="CAM 2" rec pills={['LIVE', '4K']} readout={[{label: 'SIGNAL', value: '98%'}, {label: 'ZOOM', value: '2.4x'}]} ticker={['BREAKING', 'LIVE']} scrubber scan crosshair /></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

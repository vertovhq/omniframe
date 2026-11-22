import {AppWindow, CounterOverlay, ScreenFrame, ToolCallStack} from '../kit';
import {Mid, Pad, Sample, Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BLOCKS: Block[] = [
  {name: 'AppWindow', at: 1.6, node: () => <Pad><AppWindow title="Assistant" prompt="Ship the budget report" typeFrom={0.3} cps={22} width={880} height={460} /></Pad>},
  {name: 'ToolCallStack', at: 1.6, node: () => <Pad><ToolCallStack at={0.2} step={0.4} calls={[{name: 'read_file', args: 'budget.csv', done: true}, {name: 'run_script', args: 'totals', done: true}, {name: 'render_video', args: '9:16'}]} /></Pad>},
  {name: 'ScreenFrame', at: 1.6, node: () => <Mid><ScreenFrame kind="laptop" width={1000}><Sample label="DEMO" /></ScreenFrame></Mid>},
  {name: 'CounterOverlay', at: 1.6, node: () => <><Sample label="SALES" /><CounterOverlay to={1280} start={0.2} dur={1.2} label="leads" corner="upper-right" /></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

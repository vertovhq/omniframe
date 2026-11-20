import {AnimatedGradient, Bokeh, Glow, Gradient, Grid, LightCone, LightLeaks, Mesh, Noise, Paper, Particles, Scanlines, Solid, Starfield, Stripes, Vignette} from '../kit';
import {Sheet} from './KitSheet';
import type {Block} from './KitSheet';

const BASE = ['#0B1230', '#2A3A8A'];
const Base = () => <Gradient stops={BASE} angle={160} />;

const BLOCKS: Block[] = [
  {name: 'Solid', at: 1.0, node: () => <Solid color="#E4572E" />},
  {name: 'Gradient', at: 1.0, node: () => <Gradient stops={['#FF7A18', '#7B2FF7', '#0B1230']} angle={150} />},
  {name: 'AnimatedGradient', at: 1.0, node: () => <AnimatedGradient stops={['#00F0FF', '#7B2FF7', '#FF2E93']} speed={0.4} />},
  {name: 'Mesh', at: 1.0, node: () => <Mesh colors={['#FF4F7B', '#2F6BFF', '#00D1B2']} base="#0B1230" />},
  {name: 'Grid', at: 1.0, node: () => <><Base /><Grid color="#7CF0FF" opacity={0.5} /></>},
  {name: 'Stripes', at: 1.0, node: () => <><Base /><Stripes color="#FFFFFF" opacity={0.18} angle={35} /></>},
  {name: 'Noise', at: 1.0, node: () => <><Base /><Noise opacity={0.35} /></>},
  {name: 'Paper', at: 1.0, node: () => <Paper ruling="lines" />},
  {name: 'Starfield', at: 1.0, node: () => <><Solid color="#05060F" /><Starfield streak={0.5} /></>},
  {name: 'Bokeh', at: 1.0, node: () => <><Solid color="#0A0A1E" /><Bokeh colors={['#FFB347', '#FF5E8A', '#5EC8FF']} /></>},
  {name: 'LightLeaks', at: 1.0, node: () => <><Solid color="#101020" /><LightLeaks intensity={0.9} /></>},
  {name: 'Vignette', at: 1.0, node: () => <><Gradient stops={['#E9E4D8', '#CFC7B4']} /><Vignette strength={0.8} /></>},
  {name: 'Scanlines', at: 1.0, node: () => <><Base /><Scanlines opacity={0.5} roll={0.15} /></>},
  {name: 'Glow', at: 1.0, node: () => <><Solid color="#080A18" /><Glow x={50} y={45} size={900} color="#7CF0FF" /></>},
  {name: 'Particles', at: 1.0, node: () => <><Base /><Particles kind="stars" count={90} color="#FFFFFF" /></>},
  {name: 'LightCone', at: 1.0, node: () => <><Solid color="#080A18" /><LightCone x={50} y={0} color="#FFF3C4" /></>},
];

export default function KitPreview() {
  return <Sheet blocks={BLOCKS} />;
}

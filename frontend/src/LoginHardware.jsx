// Isometric hardware sitting on the circuit board behind the sign-in card:
// an Apple-silicon style package, an internal SSD, an external drive and a
// small NAS — the four things this tool actually watches.
//
// Drawn as flat polygons rather than art, so they inherit the theme tokens and
// stay sharp at any size.

// A 2:1 isometric projection. `P` is the top corner of the slab's top face;
// width runs down-right, depth down-left, and the body drops straight down.
const R = [0.866, 0.5]
const L = [-0.866, 0.5]
const pt = ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`
const add = (p, v, n) => [p[0] + v[0] * n, p[1] + v[1] * n]

function Slab({ x, y, w, d, h, opacity = 1, accent = false }) {
  const top = [x, y]
  const right = add(top, R, w)
  const front = add(right, L, d)
  const left = add(top, L, d)
  const drop = (p) => [p[0], p[1] + h]

  const stroke = 'var(--circuit-line)'
  return (
    <g opacity={opacity}>
      {/* Left and right walls first, so the lit top face sits over them. */}
      <polygon points={[left, front, drop(front), drop(left)].map(pt).join(' ')}
               fill="var(--iso-side-dark)" stroke={stroke} strokeWidth="1" strokeOpacity="0.5" />
      <polygon points={[right, front, drop(front), drop(right)].map(pt).join(' ')}
               fill="var(--iso-side)" stroke={stroke} strokeWidth="1" strokeOpacity="0.5" />
      <polygon points={[top, right, front, left].map(pt).join(' ')}
               fill={accent ? 'var(--iso-top-accent)' : 'var(--iso-top)'}
               stroke={stroke} strokeWidth="1.2" strokeOpacity="0.85" />
    </g>
  )
}

// The lit pad each object stands on — what makes them read as sitting on the
// board rather than floating over it.
function Platform({ x, y, w, d }) {
  const top = [x, y]
  const right = add(top, R, w)
  const front = add(right, L, d)
  const left = add(top, L, d)
  return (
    <polygon points={[top, right, front, left].map(pt).join(' ')}
             fill="var(--iso-platform)" stroke="var(--circuit-pulse)"
             strokeWidth="1.5" strokeOpacity="0.55" filter="url(#iso-glow)" />
  )
}

// An SoC package: a chip die on a substrate, with contact rows down each side.
function Chip({ x, y, scale = 1, opacity = 0.9 }) {
  const pins = []
  for (let i = 1; i <= 5; i++) {
    const a = add(add([x, y], R, 62), L, i * 10)
    const b = add(a, R, 9)
    pins.push(<line key={`r${i}`} x1={a[0]} y1={a[1] + 13} x2={b[0]} y2={b[1] + 13}
                    stroke="var(--circuit-line)" strokeOpacity="0.6" strokeWidth="1.4" />)
    const c = add(add([x, y], L, 62), R, i * 10)
    const e = add(c, L, 9)
    pins.push(<line key={`l${i}`} x1={c[0]} y1={c[1] + 13} x2={e[0]} y2={e[1] + 13}
                    stroke="var(--circuit-line)" strokeOpacity="0.6" strokeWidth="1.4" />)
  }
  return (
    <g transform={`translate(${x} ${y}) scale(${scale}) translate(${-x} ${-y})`} opacity={opacity}>
      <Platform x={x} y={y + 26} w={74} d={74} />
      {pins}
      <Slab x={x} y={y} w={62} d={62} h={13} />
      {/* The die, inset on the package. */}
      <Slab x={add(add([x, y], R, 16), L, 16)[0]}
            y={add(add([x, y], R, 16), L, 16)[1] - 13}
            w={30} d={30} h={6} accent />
    </g>
  )
}

function Drive({ x, y, scale = 1, opacity = 0.85, accent = false }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale}) translate(${-x} ${-y})`} opacity={opacity}>
      <Platform x={x} y={y + 20} w={96} d={54} />
      <Slab x={x} y={y} w={88} d={48} h={11} accent={accent} />
    </g>
  )
}

// Three drives in a bay: the shared storage the dashboard also watches.
function Nas({ x, y, scale = 1, opacity = 0.8 }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale}) translate(${-x} ${-y})`} opacity={opacity}>
      <Platform x={x} y={y + 46} w={70} d={70} />
      {[0, 1, 2].map(i => (
        <Slab key={i} x={x} y={y + i * 15} w={62} d={62} h={11} accent={i === 0} />
      ))}
    </g>
  )
}

// Each piece gets its own small viewBox so it lays out as an ordinary element
// beside its label. Drawing them all into one page-sized, slice-scaled canvas
// meant their position drifted with the window while the HTML labels did not,
// which is what made the corners look misaligned.
const Frame = ({ children }) => (
  <svg className="node-art" viewBox="0 0 200 170" aria-hidden="true">
    <defs>
      <filter id="iso-glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="5" result="b" />
        <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
      </filter>
    </defs>
    {children}
  </svg>
)

export const ChipArt = () => <Frame><Chip x={100} y={18} scale={1} /></Frame>
export const NasArt = () => <Frame><Nas x={100} y={16} scale={0.95} /></Frame>
export const DriveArt = ({ accent }) => (
  <Frame><Drive x={100} y={52} scale={1} accent={accent} /></Frame>
)

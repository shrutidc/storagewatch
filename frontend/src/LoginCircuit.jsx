// Circuit traces behind the sign-in card: a board seen from above, with
// current running along it.
//
// One SVG of static paths plus a second copy of each path drawn as a short
// dash that travels its length. Animating stroke-dashoffset moves the pulse
// without scripting a single frame, so this costs nothing per frame in JS.
function LoginCircuit() {
  // Each trace is an L-shaped run with rounded corners, heading inward from an
  // edge. `len` is roughly the path length, used to size the travelling dash.
  const traces = [
    { d: 'M0 120 H180 Q200 120 200 140 V300 Q200 320 220 320 H400', len: 620, delay: 0 },
    { d: 'M0 420 H120 Q140 420 140 400 V240 Q140 220 160 220 H300', len: 540, delay: 2.4 },
    { d: 'M1440 90 H1280 Q1260 90 1260 110 V260 Q1260 280 1240 280 H1080', len: 600, delay: 1.2 },
    { d: 'M1440 460 H1320 Q1300 460 1300 440 V340 Q1300 320 1280 320 H1120', len: 520, delay: 3.1 },
    { d: 'M240 540 V420 Q240 400 260 400 H520', len: 420, delay: 4.0 },
    { d: 'M1200 540 V440 Q1200 420 1180 420 H960', len: 400, delay: 1.8 },
    { d: 'M0 260 H80 Q100 260 100 280 V540', len: 420, delay: 5.2 },
    { d: 'M1440 200 H1380 Q1360 200 1360 220 V540', len: 400, delay: 3.6 },
    { d: 'M0 0 V60 Q0 80 20 80 H240 Q260 80 260 100 V180', len: 440, delay: 6.1 },
    { d: 'M1440 560 V500 Q1440 480 1420 480 H1180 Q1160 480 1160 460 V380', len: 460, delay: 2.7 },
    { d: 'M480 0 V100 Q480 120 500 120 H660', len: 300, delay: 4.6 },
    { d: 'M980 0 V140 Q980 160 960 160 H820', len: 320, delay: 0.9 },
  ]

  // Pads where traces terminate, as on a board.
  const pads = [
    [400, 320], [300, 220], [1080, 280], [1120, 320],
    [520, 400], [960, 420], [200, 140], [1260, 110],
    [260, 180], [1160, 380], [660, 120], [820, 160],
  ]

  return (
    <svg className="login-circuit" viewBox="0 0 1440 560" preserveAspectRatio="xMidYMid slice"
         aria-hidden="true">
      <defs>
        <linearGradient id="trace-fade" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--circuit-line)" stopOpacity="0.25" />
          <stop offset="50%" stopColor="var(--circuit-line)" stopOpacity="0.85" />
          <stop offset="100%" stopColor="var(--circuit-line)" stopOpacity="0.25" />
        </linearGradient>
        <filter id="trace-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {traces.map((t, i) => (
        <g key={i}>
          <path d={t.d} fill="none" stroke="url(#trace-fade)" strokeWidth="1.5" />
          {/* The travelling pulse: a short dash chased by a long gap. */}
          <path
            className="trace-pulse"
            d={t.d}
            fill="none"
            stroke="var(--circuit-pulse)"
            strokeWidth="2"
            strokeLinecap="round"
            filter="url(#trace-glow)"
            style={{
              strokeDasharray: `60 ${t.len}`,
              animationDuration: `${t.len / 90}s`,
              animationDelay: `${t.delay}s`,
              '--trace-len': `${t.len + 60}`,
            }}
          />
        </g>
      ))}

      {pads.map(([x, y], i) => (
        <g key={`pad-${i}`}>
          <rect x={x - 4} y={y - 4} width="8" height="8" rx="1.5"
                fill="none" stroke="var(--circuit-line)" strokeOpacity="0.9" strokeWidth="1.2" />
          <circle className="pad-blink" cx={x} cy={y} r="1.8" fill="var(--circuit-pulse)"
                  style={{ animationDelay: `${i * 0.7}s` }} />
        </g>
      ))}
    </svg>
  )
}

export default LoginCircuit

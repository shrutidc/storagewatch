// Callout cards naming what sits on the board behind the sign-in panel, plus
// the small type in the margins. Decoration, but honest decoration: each one
// names something the dashboard genuinely monitors.
//
// Each node is one flex row: the isometric piece and its card side by side, so
// they stay aligned to each other at every window size. They were previously
// two independent layers — a slice-scaled SVG and percentage-positioned HTML —
// which drifted apart as the window changed shape.

import { ChipArt, NasArt, DriveArt } from './LoginHardware.jsx'

const DiskIcon = () => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
       strokeWidth="1.6" aria-hidden="true">
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="12" cy="12" r="1" />
  </svg>
)

const LayersIcon = () => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
       strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
    <ellipse cx="12" cy="6" rx="8" ry="3" />
    <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
    <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
  </svg>
)

const DriveIcon = () => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
       strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="3" width="16" height="18" rx="2" />
    <circle cx="12" cy="9" r="3" />
    <line x1="8" y1="17" x2="16" y2="17" />
  </svg>
)

const ServerIcon = () => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
       strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="4" width="18" height="7" rx="1.5" />
    <rect x="3" y="13" width="18" height="7" rx="1.5" />
    <line x1="7" y1="7.5" x2="7" y2="7.5" strokeLinecap="round" strokeWidth="2" />
    <line x1="7" y1="16.5" x2="7" y2="16.5" strokeLinecap="round" strokeWidth="2" />
  </svg>
)

function Callout({ icon, title, lines, muted }) {
  return (
    <div className="login-callout">
      <div className="login-callout-head">
        <span className="login-callout-icon">{icon}</span>
        <span className="login-callout-title">{title}</span>
      </div>
      {muted ? (
        <p className="login-callout-muted">{muted}</p>
      ) : (
        <ul className="login-callout-list">
          {lines.map(l => (
            <li key={l}><span className="login-dot" />{l}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

// The art sits on the outside of each corner and the card on the inside, so
// all four read as pointing at the panel in the middle.
function Node({ place, art, children }) {
  return (
    <div className={`login-node login-node-${place}`}>
      {art}
      {children}
    </div>
  )
}

function LoginLabels() {
  return (
    <div className="login-labels" aria-hidden="true">
      <Node place="tl" art={<ChipArt />}>
        <Callout icon={<DiskIcon />} title="macOS Storage" muted="Local · Secure" />
      </Node>
      <Node place="tr" art={<NasArt />}>
        <Callout icon={<LayersIcon />} title="APFS Volumes"
                 lines={['Encrypted', 'Snapshots', 'Smart Insights']} />
      </Node>
      <Node place="bl" art={<DriveArt />}>
        <Callout icon={<DriveIcon />} title="External Storage"
                 lines={['USB-C / Thunderbolt', 'Health Monitoring', 'Performance']} />
      </Node>
      <Node place="br" art={<DriveArt accent />}>
        <Callout icon={<ServerIcon />} title="Network Storage"
                 lines={['NFS / SMB', 'Real-time Monitoring', 'Unified View']} />
      </Node>

      <p className="login-margin login-margin-left">Analyze<br />Understand<br />Optimize</p>
      <p className="login-margin login-margin-right">Your Mac's<br />storage.<br />In focus.</p>
      <p className="login-margin login-margin-bottom">Built for a cleaner tomorrow</p>
    </div>
  )
}

export default LoginLabels

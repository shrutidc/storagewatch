import { lazy, Suspense } from 'react'
import { useOutletContext } from 'react-router-dom'

// Recharts is by far the largest dependency here, and only this one section
// uses it. Loading it on demand keeps it out of the first paint — and off the
// sign-in page entirely, which needs no chart at all.
const Performance = lazy(() => import('./Performance.jsx'))
import Alerts from './Alerts.jsx'
import Volumes from './Volumes.jsx'
import Disks from './Disks.jsx'
import Apfs from './Apfs.jsx'
import NetworkVolumes from './NetworkVolumes.jsx'
import Users from './Users.jsx'

const gb = (bytes) => `${(bytes / 1e9).toFixed(1)} GB`
const mbps = (bytes) => (bytes / 1e6).toFixed(0)

// The single page (PRD §21): headline storage and throughput, then every
// section that used to be its own tab. Questions go to the Ask AI chat.
function Dashboard() {
  const { metrics } = useOutletContext()

  return (
    <>
      <div className="metrics-grid">
        <div className="metric-card">
          <h3>Storage</h3>
          <p className="metric-value">{metrics.used_percent.toFixed(1)}%</p>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${Math.min(metrics.used_percent, 100)}%` }}></div>
          </div>
          <p className="metric-detail">
            {gb(metrics.used_bytes)} used · {gb(metrics.free_bytes)} available · {gb(metrics.total_bytes)} total
          </p>
          <p className="metric-detail">
            <code>{metrics.filesystem}</code> · {metrics.filesystem_type}
          </p>
        </div>

        <div className="metric-card">
          <h3>Read</h3>
          <p className="metric-value">{mbps(metrics.read_bytes_per_sec)}</p>
          <p className="metric-unit">MB/s</p>
        </div>

        <div className="metric-card">
          <h3>Write</h3>
          <p className="metric-value">{mbps(metrics.write_bytes_per_sec)}</p>
          <p className="metric-unit">MB/s</p>
        </div>
      </div>

      {/* Each fact appears once: the cards above carry current storage and
          throughput, and every section below adds only what they can't. */}
      <Alerts />
      <Suspense fallback={
        <div className="detail-section">
          <h2>I/O performance</h2>
          <p className="section-sub">Loading chart…</p>
        </div>
      }>
        <Performance />
      </Suspense>
      <Apfs />
      <Volumes />
      <Disks />
      <Users />
      {/* Last: most Macs have no shared volumes, so an empty panel should not
          sit between sections that always have something to show. */}
      <NetworkVolumes />
    </>
  )
}

export default Dashboard

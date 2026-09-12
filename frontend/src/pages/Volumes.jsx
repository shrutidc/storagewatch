import { useOutletContext } from 'react-router-dom'

const gb = (bytes) => `${(bytes / 1e9).toFixed(1)} GB`

function statusOf(percent) {
  if (percent >= 90) return { label: 'Critical', cls: 'bad' }
  if (percent >= 80) return { label: 'Warning', cls: 'warn' }
  return { label: 'Healthy', cls: 'good' }
}

function Volumes() {
  const { volumes, systemInfo } = useOutletContext()
  const props = systemInfo?.volume_properties || []
  const propsFor = (mountpoint) => props.find(p => p.mountpoint === mountpoint) || {}

  const totalBytes = volumes.reduce((sum, v) => sum + v.total_bytes, 0)
  const usedBytes = volumes.reduce((sum, v) => sum + v.used_bytes, 0)
  const freeBytes = volumes.reduce((sum, v) => sum + v.free_bytes, 0)

  return (
    <>
      <div className="detail-section">
        <h2>Storage Capacity</h2>
        <p className="section-sub">Aggregate across {volumes.length} monitored volume{volumes.length === 1 ? '' : 's'}</p>
        <div className="metrics-grid">
          <div className="metric-card">
            <h3>Total Capacity</h3>
            <p className="metric-value">{gb(totalBytes)}</p>
          </div>
          <div className="metric-card">
            <h3>Used</h3>
            <p className="metric-value">{gb(usedBytes)}</p>
          </div>
          <div className="metric-card">
            <h3>Free</h3>
            <p className="metric-value">{gb(freeBytes)}</p>
          </div>
          <div className="metric-card">
            <h3>Usage</h3>
            <p className="metric-value">
              {totalBytes ? ((usedBytes / totalBytes) * 100).toFixed(1) : '0.0'}%
            </p>
          </div>
        </div>
      </div>

      {volumes.map(v => {
        const p = propsFor(v.filesystem)
        const status = statusOf(v.used_percent)
        return (
          <div key={v.filesystem} className="detail-section">
            <h2>{p.volume_name || v.filesystem}</h2>
            <p className="section-sub">
              {v.filesystem} · <span className={`pill ${status.cls}`}>{status.label}</span>
            </p>

            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${v.used_percent}%` }}></div>
            </div>
            <p className="metric-detail" style={{ margin: '8px 0 16px' }}>
              {gb(v.used_bytes)} used · {gb(v.free_bytes)} free · {gb(v.total_bytes)} total ({v.used_percent.toFixed(1)}%)
            </p>

            <table className="detail-table kv-table">
              <tbody>
                <tr><td>Volume name</td><td>{p.volume_name || '—'}</td></tr>
                <tr><td>Mount point</td><td>{v.filesystem}</td></tr>
                <tr><td>Filesystem type</td><td>{v.filesystem_type}</td></tr>
                <tr><td>Device</td><td>{p.device || '—'}</td></tr>
                <tr><td>Access</td><td>{p.read_only === undefined ? '—' : (p.read_only ? 'Read-only' : 'Writable')}</td></tr>
                <tr><td>Location</td><td>{p.is_local === undefined ? '—' : (p.is_local ? 'Local' : 'Network')}</td></tr>
                <tr><td>Host</td><td>{v.hostname}</td></tr>
                <tr><td>Last sample</td><td>{new Date(v.time).toLocaleString()}</td></tr>
              </tbody>
            </table>
          </div>
        )
      })}
    </>
  )
}

export default Volumes

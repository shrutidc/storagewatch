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

  // Volumes in the same APFS container share one capacity pool, so summing
  // every volume's total would count that pool more than once.
  const seen = new Set()
  const distinctPools = volumes.filter(v => {
    const key = propsFor(v.filesystem).container_ref || v.filesystem
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  const totalBytes = distinctPools.reduce((sum, v) => sum + v.total_bytes, 0)
  const usedBytes = distinctPools.reduce((sum, v) => sum + v.used_bytes, 0)
  const freeBytes = distinctPools.reduce((sum, v) => sum + v.free_bytes, 0)

  return (
    <>
      <div className="detail-section">
        <h2>Storage Capacity</h2>
        <p className="section-sub">
          Across {distinctPools.length} storage pool{distinctPools.length === 1 ? '' : 's'} ·
          {' '}{volumes.length} monitored volume{volumes.length === 1 ? '' : 's'}
        </p>
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
        const isApfs = Boolean(p.container_ref)
        return (
          <div key={v.filesystem} className="detail-section">
            <h2>{p.volume_name || v.filesystem}</h2>
            <p className="section-sub">
              {v.filesystem} · <span className={`pill ${status.cls}`}>{status.label}</span>
            </p>

            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${v.used_percent}%` }}></div>
            </div>
            <p className="metric-detail" style={{ margin: '8px 0 4px' }}>
              {gb(v.used_bytes)} used · {gb(v.free_bytes)} free · {gb(v.total_bytes)} total ({v.used_percent.toFixed(1)}%)
            </p>
            {isApfs && (
              <p className="section-sub">
                Capacity is shared across APFS container {p.container_ref}
                {p.volume_used_bytes != null
                  ? ` — this volume's own data accounts for ${gb(p.volume_used_bytes)}`
                  : ''}
              </p>
            )}

            <table className="detail-table kv-table">
              <tbody>
                <tr><td>Volume name</td><td>{p.volume_name || '—'}</td></tr>
                <tr><td>Mount point</td><td>{v.filesystem}</td></tr>
                <tr><td>Filesystem type</td><td>{v.filesystem_type}</td></tr>
                <tr><td>Device</td><td>{p.device || '—'}</td></tr>
                <tr><td>APFS container</td><td>{p.container_ref || 'Not APFS'}</td></tr>
                <tr>
                  <td>This volume's data</td>
                  <td>{p.volume_used_bytes != null ? gb(p.volume_used_bytes) : '—'}</td>
                </tr>
                <tr><td>Mount access</td><td>{p.read_only === undefined ? '—' : (p.read_only ? 'Read-only' : 'Writable')}</td></tr>
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

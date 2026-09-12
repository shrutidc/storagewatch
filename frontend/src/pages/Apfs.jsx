import { useOutletContext } from 'react-router-dom'

const gb = (bytes) => `${(bytes / 1e9).toFixed(1)} GB`

function Apfs() {
  const { systemInfo } = useOutletContext()
  const containers = systemInfo?.apfs_containers || []

  if (!systemInfo) {
    return (
      <div className="detail-section">
        <h2>APFS</h2>
        <p className="section-sub">Waiting for APFS info from the collector (refreshes every ~60s)...</p>
      </div>
    )
  }

  return (
    <>
      <div className="detail-section">
        <h2>APFS Overview</h2>
        <p className="section-sub">
          Reported by <code>diskutil apfs list</code> on {systemInfo.hostname} ·
          {' '}macOS-internal containers (iSCPreboot, bare Recovery) are omitted
        </p>
        <div className="metrics-grid">
          <div className="metric-card">
            <h3>Containers</h3>
            <p className="metric-value">{containers.length}</p>
          </div>
          <div className="metric-card">
            <h3>APFS Volumes</h3>
            <p className="metric-value">{containers.reduce((n, c) => n + c.volumes.length, 0)}</p>
          </div>
          <div className="metric-card">
            <h3>FileVault</h3>
            <p className="metric-value">{systemInfo.filevault_enabled ? 'On' : 'Off'}</p>
          </div>
          <div className="metric-card">
            <h3>Local Snapshots</h3>
            <p className="metric-value">{systemInfo.snapshot_count}</p>
          </div>
        </div>
      </div>

      {containers.map(c => {
        const used = c.capacity_ceiling - c.capacity_free
        const usedPct = c.capacity_ceiling ? (used / c.capacity_ceiling) * 100 : 0
        return (
          <div key={c.container_reference} className="detail-section">
            <h2>Container {c.container_reference}</h2>
            <p className="section-sub">Physical store: {c.physical_store || '—'}</p>

            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${usedPct}%` }}></div>
            </div>
            <p className="metric-detail" style={{ margin: '8px 0 16px' }}>
              {gb(used)} in use · {gb(c.capacity_free)} free · {gb(c.capacity_ceiling)} capacity ({usedPct.toFixed(1)}%)
            </p>

            <table className="detail-table kv-table">
              <tbody>
                <tr><td>Container reference</td><td>{c.container_reference}</td></tr>
                <tr><td>Container UUID</td><td>{c.uuid || '—'}</td></tr>
                <tr><td>Physical backing store</td><td>{c.physical_store || '—'}</td></tr>
                <tr><td>Capacity (ceiling)</td><td>{gb(c.capacity_ceiling)}</td></tr>
                <tr><td>Free space</td><td>{gb(c.capacity_free)}</td></tr>
              </tbody>
            </table>

            <h3>Volumes ({c.volumes.length})</h3>
            <div className="table-scroll">
              <table className="detail-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Device</th>
                    <th>Roles</th>
                    <th>In use</th>
                    <th>Encryption</th>
                    <th>FileVault</th>
                  </tr>
                </thead>
                <tbody>
                  {c.volumes.map(v => (
                    <tr key={v.device_identifier || v.name}>
                      <td>{v.name}</td>
                      <td>{v.device_identifier || '—'}</td>
                      <td>{v.roles.length ? v.roles.join(', ') : '—'}</td>
                      <td>{gb(v.capacity_in_use)}</td>
                      <td>
                        <span className={`pill ${v.encrypted ? 'good' : ''}`}>
                          {v.encrypted ? 'Encrypted' : 'None'}
                        </span>
                      </td>
                      <td>
                        <span className={`pill ${v.filevault ? 'good' : ''}`}>
                          {v.filevault ? 'Protected' : '—'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </>
  )
}

export default Apfs

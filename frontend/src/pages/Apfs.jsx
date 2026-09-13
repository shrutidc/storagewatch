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
          Reported by <code>diskutil apfs list</code> and <code>diskutil info</code> on
          {' '}{systemInfo.hostname} · macOS-internal containers (iSCPreboot, bare
          Recovery) are omitted
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
        // On a sealed system volume the Mac runs from a snapshot, not from the
        // volume, which is why that volume reports no mount point of its own.
        const booted = c.volumes.find(v => v.snapshot)?.snapshot
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
                <tr><td>Physical store UUID</td><td>{c.physical_store_uuid || '—'}</td></tr>
                <tr><td>Physical store size</td><td>{c.physical_store_size ? gb(c.physical_store_size) : '—'}</td></tr>
                <tr><td>Capacity (ceiling)</td><td>{gb(c.capacity_ceiling)}</td></tr>
                <tr><td>Free space (not allocated)</td><td>{gb(c.capacity_free)}</td></tr>
                {booted && (
                  <>
                    <tr>
                      <td>Booted snapshot</td>
                      <td><code>{booted.device_identifier}</code> mounted at <code>{booted.mount_point}</code></td>
                    </tr>
                    <tr><td>Snapshot UUID</td><td>{booted.uuid || '—'}</td></tr>
                    <tr><td>Snapshot name</td><td className="wrap-anywhere">{booted.name || '—'}</td></tr>
                  </>
                )}
              </tbody>
            </table>

            <h3>Volumes ({c.volumes.length})</h3>
            <div className="table-scroll">
              <table className="detail-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Device</th>
                    <th>Mount point</th>
                    <th>Roles</th>
                    <th>In use</th>
                    <th>Encryption</th>
                    <th>FileVault</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {c.volumes.map(v => (
                    <tr key={v.device_identifier || v.name}>
                      <td>{v.name}</td>
                      <td><code>{v.device_identifier || '—'}</code></td>
                      <td>
                        {v.mount_point ? (
                          <code>{v.mount_point}</code>
                        ) : v.snapshot ? (
                          <>
                            <code>{v.snapshot.mount_point}</code>
                            <span className="cell-note">via snapshot {v.snapshot.device_identifier}</span>
                          </>
                        ) : (
                          <span className="cell-note">Not mounted</span>
                        )}
                      </td>
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
                      <td className="pill-stack">
                        {v.sealed && <span className="pill good">Sealed</span>}
                        {v.locked && <span className="pill bad">Locked</span>}
                        {/* Only meaningful for a mounted volume: diskutil
                            reports an unmounted one as unwritable either way. */}
                        {v.mount_point && !v.writable && <span className="pill">Read-only</span>}
                        {!v.sealed && !v.locked && (!v.mount_point || v.writable) && '—'}
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

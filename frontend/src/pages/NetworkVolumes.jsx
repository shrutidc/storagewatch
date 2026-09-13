import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'

// Shared storage: NFS (including pNFS), SMB and AFP.
function NetworkVolumes() {
  const { systemInfo } = useOutletContext()
  if (!systemInfo) return null
  const mounts = systemInfo.network_mounts || []
  // Only the operations that have actually happened — the full table is ~80
  // counters, almost all of them zero on any given machine.
  const activeOps = Object.entries(systemInfo.nfs_client_stats || {})
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)

  return (
    <div className="detail-section">
      <h2>Shared volumes</h2>
      {mounts.length === 0 && activeOps.length === 0 ? (
        <p className="empty-state">
          No NFS, SMB or AFP shares mounted — they appear here within a minute of mounting.
        </p>
      ) : (
        <p className="section-sub">
          Found by <code>mount</code> and <code>nfsstat</code>. A share whose server stops
          answering is marked Not responding instead of stalling the collector.
        </p>
      )}

      {mounts.length > 0 && (
        <div className="table-scroll">
          <table className="detail-table">
            <thead>
              <tr>
                <th>Mount point</th><th>Server</th><th>Export</th><th>Type</th>
                <th>Version</th><th>Capacity</th><th>State</th>
              </tr>
            </thead>
            <tbody>
              {mounts.map(m => (
                <tr key={m.mountpoint}>
                  <td><code>{m.mountpoint}</code></td>
                  <td>{m.server || '—'}</td>
                  <td><code>{m.export || m.device}</code></td>
                  <td>{m.fstype.toUpperCase()}</td>
                  <td>
                    {m.nfs_version ? `v${m.nfs_version}` : '—'}
                    {m.pnfs && <span className="pill good" style={{ marginLeft: 6 }}>pNFS</span>}
                  </td>
                  <td>
                    {m.reachable
                      ? `${bytes(m.used_bytes)} of ${bytes(m.total_bytes)} (${m.used_percent}%)`
                      : <span className="cell-note">unknown</span>}
                  </td>
                  <td className="pill-stack">
                    <span className={`pill ${m.reachable ? 'good' : 'bad'}`}>
                      {m.reachable ? 'Responding' : 'Not responding'}
                    </span>
                    {m.read_only && <span className="pill">Read-only</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeOps.length > 0 && (
        <>
          <h3>NFS client activity since boot</h3>
          <div className="table-scroll">
            <table className="detail-table">
              <thead><tr><th>Operation</th><th>Count</th></tr></thead>
              <tbody>
                {activeOps.map(([name, count]) => (
                  <tr key={name}>
                    <td><code>{name}</code></td>
                    <td>{count.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default NetworkVolumes

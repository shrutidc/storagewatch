import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'


// Shared storage: NFS (including pNFS), SMB and AFP.
//
// psutil's default partition list keeps only local devices, so these were
// invisible to the dashboard entirely until the collector started asking for
// them by name.
function NetworkVolumes() {
  const { systemInfo } = useOutletContext()
  const mounts = systemInfo?.network_mounts || []
  const nfsStats = systemInfo?.nfs_client_stats || {}

  // Only the operations that have actually happened — the full table is ~80
  // counters, almost all of them zero on any given machine.
  const activeOps = Object.entries(nfsStats)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)

  if (!systemInfo) return null

  return (
    <div className="detail-section">
      <h2>Shared volumes</h2>
      <p className="section-sub">
        NFS, pNFS, SMB and AFP mounts on this Mac, reported by <code>mount</code> and{' '}
        <code>nfsstat</code>. They are sampled for capacity and throughput exactly like
        local volumes, with a five-second limit on every call — a share whose server
        stops answering is marked unreachable instead of stalling the collector.
      </p>

      {mounts.length === 0 ? (
        <p className="no-alerts">
          No shared volumes mounted. NFS, SMB and AFP mounts appear here automatically.
        </p>
      ) : (
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

      <h3>NFS client activity</h3>
      {activeOps.length === 0 ? (
        <p className="section-sub">
          No NFS operations recorded since boot — this Mac has not talked to an NFS
          server.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="detail-table">
            <thead><tr><th>Operation</th><th>Count since boot</th></tr></thead>
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
      )}
    </div>
  )
}

export default NetworkVolumes

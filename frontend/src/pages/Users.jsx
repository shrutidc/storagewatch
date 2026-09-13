import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'


// Who is using the disk, under what quota, and how fast their usage is moving.
//
// Sizing a home directory means walking it — 77 seconds for a 68 GB home on
// the machine this was written on — so the collector measures on a background
// thread every half hour. These figures are therefore a recent measurement,
// not a live reading, and the page says when it was taken.
function Users() {
  const { users, systemInfo } = useOutletContext()
  const rows = users || []

  const measured = rows.length ? rows[0].time : null
  const totalUsed = rows.reduce((n, u) => n + (u.used_bytes || 0), 0)

  // Growth is only meaningful against the interval it happened over: two
  // measurements an hour apart say something a raw byte count does not.
  const perHour = (u) => {
    if (!u.growth_bytes || !u.previous_time || !u.time) return null
    const hours = (new Date(u.time) - new Date(u.previous_time)) / 3.6e6
    return hours > 0 ? u.growth_bytes / hours : null
  }

  const quotaCell = (u) => {
    const limit = u.quota_soft_bytes || u.quota_hard_bytes
    if (!u.quota_enabled || !limit) {
      // macOS ships with quotas off, and saying so is a real answer.
      return <span className="cell-note">Not enabled</span>
    }
    // The bar stops at full; the label must not, or a user 42% over their
    // quota reads as exactly at it.
    const pct = (u.used_bytes / limit) * 100
    return (
      <>
        <div className="progress-bar quota-bar">
          <div
            className="progress-fill"
            style={{
              width: `${Math.min(pct, 100)}%`,
              background: pct >= 100 ? '#d32f2f' : pct >= 90 ? '#f57c00' : undefined,
            }}
          />
        </div>
        <span className={`cell-note${pct >= 100 ? ' over-quota' : ''}`}>
          {bytes(u.used_bytes)} of {bytes(limit)} ({pct.toFixed(0)}%)
        </span>
      </>
    )
  }

  return (
    <div className="detail-section">
      <h2>Users and quotas</h2>
      <p className="section-sub">
        Home directory usage, quota limits from <code>quota(1)</code>, and growth since
        the previous measurement. Measured on a background thread — walking a home
        directory takes minutes — so these are a recent reading rather than a live one.
        {measured && <> Last measured {new Date(measured).toLocaleString()}.</>}
      </p>

      {rows.length === 0 ? (
        <p className="section-sub">
          No measurement yet. The collector sizes every home directory shortly after it
          starts and then every 30 minutes; the first pass on a large disk can take
          several minutes.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="detail-table">
            <thead>
              <tr>
                <th>User</th><th>Home</th><th>Used</th><th>Share of total</th>
                <th>Quota</th><th>Growth</th><th>Largest folders</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(u => {
                const rate = perHour(u)
                const share = totalUsed ? (u.used_bytes / totalUsed) * 100 : 0
                return (
                  <tr key={u.username}>
                    <td>{u.username}<span className="cell-note">uid {u.uid}</span></td>
                    <td><code>{u.home}</code></td>
                    <td>{bytes(u.used_bytes)}</td>
                    <td>
                      <span className={`pill ${share >= 60 ? 'warn' : ''}`}>
                        {share.toFixed(0)}%
                      </span>
                    </td>
                    <td>{quotaCell(u)}</td>
                    <td>
                      {u.growth_bytes == null ? (
                        <span className="cell-note">first measurement</span>
                      ) : (
                        <>
                          <span className={u.growth_bytes > 0 ? 'growth-up' : 'growth-down'}>
                            {u.growth_bytes > 0 ? '+' : ''}{bytes(u.growth_bytes)}
                          </span>
                          {rate != null && <span className="cell-note">{bytes(rate)}/hour</span>}
                        </>
                      )}
                    </td>
                    <td>
                      {(u.largest_folders || []).slice(0, 3).map(f => (
                        <span key={f.path} className="cell-note">
                          {f.path.replace(u.home, '~')} — {bytes(f.used_bytes)}
                        </span>
                      ))}
                      {!(u.largest_folders || []).length && <span className="cell-note">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {systemInfo?.inode_usage?.length > 0 && (
        <>
          <h3>Inodes</h3>
          <p className="section-sub">
            APFS allocates inodes on demand, so this rarely constrains a Mac — but a
            shared volume exported from another system can exhaust them while still
            reporting free space.
          </p>
          <div className="table-scroll">
            <table className="detail-table">
              <thead><tr><th>Mount point</th><th>Used</th><th>Free</th><th>Used %</th></tr></thead>
              <tbody>
                {systemInfo.inode_usage.map(i => (
                  <tr key={i.mountpoint}>
                    <td><code>{i.mountpoint}</code></td>
                    <td>{i.inodes_used.toLocaleString()}</td>
                    <td>{i.inodes_free.toLocaleString()}</td>
                    <td>
                      <span className={`pill ${i.inodes_used_percent >= 80 ? 'warn' : 'good'}`}>
                        {i.inodes_used_percent}%
                      </span>
                    </td>
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

export default Users

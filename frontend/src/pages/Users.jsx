import { useOutletContext } from 'react-router-dom'
import { bytes } from '../format.js'

// Who has an account on the Mac, and — on a Mac that opts in to per-user
// sizing — how much each holds. Accounts, admin rights, sign-ins and quotas come
// from the directory service, who(1) and quota(1), none of which opens a file.
// Sizes mean walking every home directory, which makes macOS ask for access to
// personal folders, so they are off unless the Mac opts in.
function Users() {
  const { users, systemInfo } = useOutletContext()
  const rows = users || []
  const accounts = systemInfo?.user_accounts || []
  // Collectors older than the switch don't send it, so only an explicit false
  // means sizing is off.
  const sizingOff = systemInfo?.user_sizing === false

  const measured = rows.length ? rows[0].time : null
  const totalUsed = rows.reduce((n, u) => n + (u.used_bytes || 0), 0)

  // Growth is only meaningful against the interval it happened over.
  const perHour = (u) => {
    if (!u.growth_bytes || !u.previous_time || !u.time) return null
    const hours = (new Date(u.time) - new Date(u.previous_time)) / 3.6e6
    return hours > 0 ? u.growth_bytes / hours : null
  }

  const sizedQuota = (u) => {
    const limit = u.quota_soft_bytes || u.quota_hard_bytes
    // macOS ships with quotas off, and saying so is a real answer.
    if (!u.quota_enabled || !limit) return <span className="cell-note">Not enabled</span>
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

  const accountQuota = (q) => {
    const fs = q?.enabled && q.filesystems?.[0]
    if (!fs) return <span className="cell-note">Not enabled</span>
    const limit = fs.soft_limit_bytes || fs.hard_limit_bytes
    return <span className="cell-note">{bytes(fs.used_bytes)} of {limit ? bytes(limit) : 'no limit'}</span>
  }

  return (
    <div className="detail-section">
      <h2>Users and quotas</h2>

      {sizingOff ? (
        <>
          <p className="section-sub">
            Accounts from the directory service and quotas from <code>quota(1)</code>.
            Per-user disk usage is off: it means reading every folder in each home, which
            makes macOS ask for access to Documents, Desktop, Photos and more. A Mac can opt
            in by installing with <code>STORAGEWATCH_SIZE_HOMES=1</code>.
          </p>
          {accounts.length === 0 ? (
            <p className="empty-state">No accounts reported yet — they arrive with the next system report.</p>
          ) : (
            <div className="table-scroll">
              <table className="detail-table">
                <thead>
                  <tr><th>User</th><th>Home</th><th>Account</th><th>Signed in</th><th>Quota</th></tr>
                </thead>
                <tbody>
                  {accounts.map(a => (
                    <tr key={a.username}>
                      <td>{a.username}<span className="cell-note">uid {a.uid}</span></td>
                      <td><code>{a.home}</code></td>
                      <td>{a.admin == null ? '—' : <span className="pill">{a.admin ? 'Admin' : 'Standard'}</span>}</td>
                      <td>{a.signed_in ? <span className="pill good">Signed in</span> : '—'}</td>
                      <td>{accountQuota(a.quota)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : rows.length === 0 ? (
        <p className="section-sub">
          No measurement yet. The collector sizes every home directory shortly after it
          starts and then every 30 minutes; the first pass on a large disk takes minutes.
        </p>
      ) : (
        <>
          <p className="section-sub">
            Home directory usage, quotas and growth since the previous measurement — a recent
            reading, since walking a home takes minutes.
            {measured && <> Last measured {new Date(measured).toLocaleString()}.</>}
          </p>
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
                      <td>
                        {bytes(u.used_bytes)}
                        {u.complete === false && (
                          <span className="cell-note">partial — some folders unreadable</span>
                        )}
                      </td>
                      <td>
                        <span className={`pill ${share >= 60 ? 'warn' : ''}`}>{share.toFixed(0)}%</span>
                      </td>
                      <td>{sizedQuota(u)}</td>
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
          {rows.some(u => u.complete === false) && (
            <p className="section-sub">
              Partial sizes leave out folders the collector may not read: other users' homes,
              and — until Python has Full Disk Access (System Settings → Privacy &amp; Security) —
              Documents, Desktop, Mail and similar. They are a lower bound.
            </p>
          )}
        </>
      )}

      {systemInfo?.inode_usage?.length > 0 && (
        <>
          <h3>Inodes</h3>
          <p className="section-sub">
            APFS allocates inodes on demand; a shared volume from another system can run out
            of them while still showing free space.
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

import { useOutletContext } from 'react-router-dom'

const label = (type) => type.replaceAll('_', ' ')

// An overview first — one line per kind of alert, with its count and the most
// recent one — and the full list behind a disclosure that starts closed on every
// page load, so a pile of alerts doesn't bury the rest of the dashboard.
function Alerts() {
  const { alerts } = useOutletContext()

  if (alerts.length === 0) {
    return (
      <div className="detail-section">
        <h2>Alerts</h2>
        <p className="no-alerts">✓ No active alerts</p>
      </div>
    )
  }

  // Alerts arrive newest first, so the first of each type is its latest.
  const groups = []
  for (const a of alerts) {
    const group = groups.find(g => g.type === a.alert_type)
    if (group) {
      group.count += 1
      if (a.severity === 'critical') group.severity = 'critical'
    } else {
      groups.push({ type: a.alert_type, count: 1, latest: a, severity: a.severity })
    }
  }
  const critical = alerts.filter(a => a.severity === 'critical').length

  return (
    <div className="detail-section">
      <h2>Alerts</h2>
      <p className="section-sub">
        {alerts.length} unresolved{critical ? `, ${critical} critical` : ''} · ask the AI
        (bottom right) about any of them
      </p>

      <ul className="alert-overview">
        {groups.map(g => (
          <li key={g.type} className={g.severity === 'critical' ? 'critical' : ''}>
            <span className="alert-type">{label(g.type)}</span>
            <span className="pill">×{g.count}</span>
            <span className="cell-note">
              latest {new Date(g.latest.created_at).toLocaleString()} — {g.latest.message}
            </span>
          </li>
        ))}
      </ul>

      <details className="alert-details">
        <summary>All {alerts.length} alerts, newest first</summary>
        <div className="alerts-list">
          {alerts.map(a => (
            <div key={a.id} className={`alert-item alert-${a.severity.toLowerCase()}`}>
              <div className="alert-header">
                <span className="alert-type">{label(a.alert_type)}</span>
                <span className="alert-time">
                  {a.severity} · {new Date(a.created_at).toLocaleString()}
                </span>
              </div>
              <p className="alert-message">{a.message}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  )
}

export default Alerts

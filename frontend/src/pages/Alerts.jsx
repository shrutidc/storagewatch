import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

const label = (type) => type.replaceAll('_', ' ')
// Matches the .leaving animation in App.css.
const SLIDE_MS = 420
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// An overview first — one line per kind of alert, with its count and the most
// recent one — and the full list behind a disclosure that starts closed on every
// page load, so a pile of alerts doesn't bury the rest of the dashboard.
//
// Nothing closes an alert on its own, so each can be cleared by hand: one at a
// time, a whole type, or all of them. Cleared alerts stay on record; they only
// stop showing as open.
function Alerts() {
  const { alerts: open, authConfig } = useOutletContext()
  // Sliding away right now, and already gone (hidden before the next poll).
  const [leaving, setLeaving] = useState(() => new Set())
  const [cleared, setCleared] = useState(() => new Set())
  const [error, setError] = useState(null)
  const alerts = open.filter(a => !cleared.has(a.id))

  const clear = async (ids) => {
    setError(null)
    setLeaving(prev => new Set([...prev, ...ids]))
    try {
      // Removed once the slide has played and the server has agreed, so the
      // list below closes up smoothly instead of jumping.
      await Promise.all([
        (async () => axios.post('/api/alerts/resolve', { ids }, await authConfig()))(),
        sleep(SLIDE_MS),
      ])
      setCleared(prev => new Set([...prev, ...ids]))
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      // On failure this brings the alerts back.
      setLeaving(prev => {
        const next = new Set(prev)
        ids.forEach(id => next.delete(id))
        return next
      })
    }
  }

  const clearAll = () => {
    if (window.confirm(`Clear all ${alerts.length} alerts? They stay on record but stop showing as open.`)) {
      clear(alerts.map(a => a.id))
    }
  }

  if (alerts.length === 0) {
    return (
      <div className="detail-section">
        <h2>Alerts</h2>
        <p className="no-alerts fade-in">✓ No active alerts</p>
        {error && <p className="alert-ai-explanation">Error: {error}</p>}
      </div>
    )
  }

  // Alerts arrive newest first, so the first of each type is its latest.
  const groups = []
  for (const a of alerts) {
    const group = groups.find(g => g.type === a.alert_type)
    if (group) {
      group.ids.push(a.id)
      if (a.severity === 'critical') group.severity = 'critical'
    } else {
      groups.push({ type: a.alert_type, ids: [a.id], latest: a, severity: a.severity })
    }
  }
  const critical = alerts.filter(a => a.severity === 'critical').length
  const classes = (...names) => names.filter(Boolean).join(' ')

  return (
    <div className="detail-section">
      <h2>Alerts</h2>
      <div className="alerts-toolbar">
        <p className="section-sub">
          {alerts.length} unresolved{critical ? `, ${critical} critical` : ''} · ask the AI
          (bottom right) about any of them
        </p>
        <button className="link-btn" onClick={clearAll}>Clear all</button>
      </div>
      {error && <p className="alert-ai-explanation">Error: {error}</p>}

      <ul className="alert-overview">
        {groups.map(g => (
          <li
            key={g.type}
            className={classes(g.severity === 'critical' && 'critical',
                               g.ids.every(id => leaving.has(id)) && 'leaving')}
          >
            <span className="alert-type">{label(g.type)}</span>
            <span className="pill">×{g.ids.length}</span>
            <span className="cell-note">
              latest {new Date(g.latest.created_at).toLocaleString()} — {g.latest.message}
            </span>
            <button className="link-btn" onClick={() => clear(g.ids)}>Clear</button>
          </li>
        ))}
      </ul>

      <details className="alert-details">
        <summary>All {alerts.length} alerts, newest first</summary>
        <div className="alerts-list">
          {alerts.map(a => (
            <div
              key={a.id}
              className={classes('alert-item', `alert-${a.severity.toLowerCase()}`,
                                 leaving.has(a.id) && 'leaving')}
            >
              <div className="alert-header">
                <span className="alert-type">{label(a.alert_type)}</span>
                <span className="alert-time">
                  {a.severity} · {new Date(a.created_at).toLocaleString()}
                  <button className="link-btn" onClick={() => clear([a.id])}>Dismiss</button>
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

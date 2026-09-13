import { useOutletContext } from 'react-router-dom'

// Every unresolved alert, newest first. Severity is the colour and the label in
// each header, so no separate counts or breakdown table repeat it.
function Alerts() {
  const { alerts } = useOutletContext()
  const critical = alerts.filter(a => a.severity === 'critical').length

  return (
    <div className="detail-section">
      <h2>Alerts</h2>
      {alerts.length === 0 ? (
        <p className="no-alerts">✓ No active alerts</p>
      ) : (
        <>
          <p className="section-sub">
            {alerts.length} unresolved{critical ? `, ${critical} critical` : ''} · newest
            first · ask the AI (bottom right) about any of them
          </p>
          <div className="alerts-list">
            {alerts.map(a => (
              <div key={a.id} className={`alert-item alert-${a.severity.toLowerCase()}`}>
                <div className="alert-header">
                  <span className="alert-type">{a.alert_type.replaceAll('_', ' ')}</span>
                  <span className="alert-time">
                    {a.severity} · {new Date(a.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="alert-message">{a.message}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default Alerts

import { useOutletContext } from 'react-router-dom'

function Alerts() {
  const { alerts } = useOutletContext()

  const bySeverity = alerts.reduce((acc, a) => {
    acc[a.severity] = (acc[a.severity] || 0) + 1
    return acc
  }, {})

  const byType = alerts.reduce((acc, a) => {
    acc[a.alert_type] = (acc[a.alert_type] || 0) + 1
    return acc
  }, {})

  return (
    <>
      <div className="detail-section">
        <h2>Alerts</h2>
        <p className="section-sub">{alerts.length} unresolved alert{alerts.length === 1 ? '' : 's'}</p>
        <div className="metrics-grid">
          <div className="metric-card">
            <h3>Critical</h3>
            <p className="metric-value">{bySeverity.critical || 0}</p>
          </div>
          <div className="metric-card">
            <h3>Warning</h3>
            <p className="metric-value">{bySeverity.warning || 0}</p>
          </div>
          <div className="metric-card">
            <h3>Distinct Types</h3>
            <p className="metric-value">{Object.keys(byType).length}</p>
          </div>
        </div>

        {Object.keys(byType).length > 0 && (
          <>
            <h3>Breakdown by type</h3>
            <table className="detail-table">
              <thead><tr><th>Alert type</th><th>Count</th></tr></thead>
              <tbody>
                {Object.entries(byType).map(([type, count]) => (
                  <tr key={type}><td>{type}</td><td>{count}</td></tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="detail-section">
        <h2>Alert Detail</h2>
        <p className="section-sub">Each alert is explained automatically by the AI as it fires</p>
        {alerts.length === 0 ? (
          <p className="no-alerts">✓ No active alerts</p>
        ) : (
          <div className="alerts-list">
            {alerts.map(a => (
              <div key={a.id} className={`alert-item alert-${a.severity.toLowerCase()}`}>
                <div className="alert-header">
                  <span className="alert-type">{a.alert_type}</span>
                  <span className="alert-time">{new Date(a.created_at).toLocaleString()}</span>
                </div>
                <p className="alert-message">{a.message}</p>
                <p className="metric-detail">
                  Severity: {a.severity} · Host: {a.hostname}
                  {a.metric_value != null ? ` · Value: ${a.metric_value.toFixed(2)}` : ''}
                </p>
                <p className="alert-ai-explanation">
                  {a.ai_explanation ? `💡 ${a.ai_explanation}` : '💭 Generating AI explanation...'}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

export default Alerts

import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const gb = (bytes) => `${(bytes / 1e9).toFixed(1)} GB`
const mbps = (bytes) => (bytes / 1e6).toFixed(0)
const label = (alertType) => alertType.replaceAll('_', ' ')

// The single-page view from PRD §21: storage and throughput, the I/O graph,
// and alerts beside their AI analysis. A demo never has to leave this page.
function Dashboard() {
  const { metrics, history, alerts, lastRefresh, authConfig } = useOutletContext()
  const [selectedId, setSelectedId] = useState(null)
  const [answers, setAnswers] = useState({})
  const [explaining, setExplaining] = useState(false)
  const [error, setError] = useState(null)

  // Follow the newest alert until the administrator picks one.
  const selected = alerts.find(a => a.id === selectedId) || alerts[0]
  const explanation = selected && (answers[selected.id] || selected.ai_explanation)

  const explain = async () => {
    const id = selected.id
    setExplaining(true)
    setError(null)
    try {
      const res = await axios.post('/api/ai/explain', { alert_id: id }, await authConfig())
      setAnswers(prev => ({ ...prev, [id]: res.data.explanation }))
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setExplaining(false)
    }
  }

  return (
    <>
      <div className="metrics-grid">
        <div className="metric-card">
          <h3>Storage</h3>
          <p className="metric-value">{metrics.used_percent.toFixed(1)}%</p>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${Math.min(metrics.used_percent, 100)}%` }}></div>
          </div>
          <p className="metric-detail">
            {gb(metrics.used_bytes)} used · {gb(metrics.free_bytes)} available · {gb(metrics.total_bytes)} total
          </p>
          <p className="metric-detail">
            <code>{metrics.filesystem}</code> · {metrics.filesystem_type}
          </p>
        </div>

        <div className="metric-card">
          <h3>Read</h3>
          <p className="metric-value">{mbps(metrics.read_bytes_per_sec)}</p>
          <p className="metric-unit">MB/s</p>
        </div>

        <div className="metric-card">
          <h3>Write</h3>
          <p className="metric-value">{mbps(metrics.write_bytes_per_sec)}</p>
          <p className="metric-unit">MB/s</p>
        </div>
      </div>

      <div className="chart-container">
        <h2>I/O Performance</h2>
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Legend />
              {/* No animation: data refreshes every 5 s and would redraw each time. */}
              <Line type="monotone" dataKey="read" stroke="#8884d8" name="Read" dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="write" stroke="#82ca9d" name="Write" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p>Loading chart data...</p>
        )}
        <p className="metric-detail">
          Last {history.length} samples · refreshed {lastRefresh ? lastRefresh.toLocaleTimeString() : '—'}
        </p>
      </div>

      <div className="two-col">
        <div className="alerts-container">
          <h2>Alerts</h2>
          {alerts.length === 0 ? (
            <p className="no-alerts">✓ No active alerts</p>
          ) : (
            <div className="alerts-list">
              {alerts.map(a => (
                <button
                  key={a.id}
                  type="button"
                  className={`alert-item alert-${a.severity.toLowerCase()}${a.id === selected.id ? ' selected' : ''}`}
                  onClick={() => setSelectedId(a.id)}
                >
                  <div className="alert-header">
                    <span className="alert-type">{label(a.alert_type)}</span>
                    <span className="alert-time">{new Date(a.created_at).toLocaleTimeString()}</span>
                  </div>
                  <p className="alert-message">{a.message}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="alerts-container">
          <h2>AI Analysis</h2>
          {!selected ? (
            <p className="section-sub">Nothing to analyze — no active alerts.</p>
          ) : (
            <>
              <p className="section-sub">{label(selected.alert_type)} · {selected.message}</p>
              {explanation && <p className="ai-analysis">{explanation}</p>}
              {error && <p className="alert-ai-explanation">Error: {error}</p>}
              <button className="explain-btn" onClick={explain} disabled={explaining}>
                {explaining ? 'Analyzing…' : explanation ? 'Explain again' : 'Explain with AI'}
              </button>
            </>
          )}
        </div>
      </div>
    </>
  )
}

export default Dashboard

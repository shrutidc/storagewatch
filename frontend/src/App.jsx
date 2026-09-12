import { useAuth0 } from '@auth0/auth0-react'
import { useState, useEffect } from 'react'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import './App.css'

function App() {
  const { loginWithRedirect, logout, user, isAuthenticated, isLoading } = useAuth0()
  const [metrics, setMetrics] = useState(null)
  const [history, setHistory] = useState([])
  const [alerts, setAlerts] = useState([])
  const [explaining, setExplaining] = useState(false)
  const [explanation, setExplanation] = useState(null)

  useEffect(() => {
    if (isAuthenticated) {
      fetchMetrics()
      const interval = setInterval(fetchMetrics, 5000)
      return () => clearInterval(interval)
    }
  }, [isAuthenticated])

  const fetchMetrics = async () => {
    try {
      const [current, hist, alertsData] = await Promise.all([
        axios.get('/api/metrics/current'),
        axios.get('/api/metrics/history?limit=100'),
        axios.get('/api/alerts'),
      ])
      setMetrics(current.data)

      if (hist.data && Array.isArray(hist.data)) {
        setHistory(hist.data.map(m => ({
          time: new Date(m.time).toLocaleTimeString(),
          read: (m.read_bytes_per_sec / 1e6).toFixed(1),
          write: (m.write_bytes_per_sec / 1e6).toFixed(1),
        })))
      }

      if (alertsData.data && Array.isArray(alertsData.data)) {
        setAlerts(alertsData.data)
      }
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    }
  }

  const getSystemStatus = () => {
    if (!metrics) return 'Unknown'
    if (metrics.used_percent >= 90) return 'Critical'
    if (metrics.used_percent >= 80) return 'Warning'
    return 'Healthy'
  }

  const getStatusColor = () => {
    const status = getSystemStatus()
    return status === 'Critical' ? '#d32f2f' : status === 'Warning' ? '#f57c00' : '#388e3c'
  }

  const handleExplainAI = async () => {
    if (!metrics) return

    setExplaining(true)
    try {
      const payload = {
        filesystem_type: metrics.filesystem_type,
        used_percent: metrics.used_percent,
        read_throughput: metrics.read_bytes_per_sec,
        write_throughput: metrics.write_bytes_per_sec,
        hostname: metrics.hostname,
      }

      if (alerts.length > 0) {
        const latestAlert = alerts[0]
        payload.alert_type = latestAlert.alert_type
        payload.alert_message = latestAlert.message
        payload.alert_severity = latestAlert.severity
      }

      const response = await axios.post('/api/ai/explain', payload)
      setExplanation(response.data.explanation || 'Analysis complete.')
    } catch (err) {
      setExplanation(`Unable to get AI analysis: ${err.message}`)
    } finally {
      setExplaining(false)
    }
  }

  if (isLoading) return <div className="loading">Loading...</div>

  if (!isAuthenticated) {
    return (
      <div className="login-container">
        <div className="login-box">
          <h1>StorageWatch</h1>
          <p>Monitor your macOS storage with AI-powered insights</p>
          <button className="login-btn" onClick={() => loginWithRedirect()}>Login with Auth0</button>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <header>
        <div className="header-left">
          <h1>StorageWatch</h1>
          {metrics && (
            <div className="status-badge" style={{ backgroundColor: getStatusColor() }}>
              {getSystemStatus()}
            </div>
          )}
        </div>
        <div className="user-info">
          <span>{user.name}</span>
          <button onClick={() => logout()}>Logout</button>
        </div>
      </header>

      <main>
        {metrics ? (
          <>
            <div className="metrics-grid">
              <div className="metric-card">
                <h3>Storage Usage</h3>
                <p className="metric-value">{metrics.used_percent.toFixed(1)}%</p>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${metrics.used_percent}%` }}></div>
                </div>
                <p className="metric-detail">
                  {(metrics.used_bytes / 1e9).toFixed(1)} GB / {(metrics.total_bytes / 1e9).toFixed(1)} GB
                </p>
              </div>

              <div className="metric-card">
                <h3>Read Throughput</h3>
                <p className="metric-value">{(metrics.read_bytes_per_sec / 1e6).toFixed(0)}</p>
                <p className="metric-unit">MB/s</p>
              </div>

              <div className="metric-card">
                <h3>Write Throughput</h3>
                <p className="metric-value">{(metrics.write_bytes_per_sec / 1e6).toFixed(0)}</p>
                <p className="metric-unit">MB/s</p>
              </div>
            </div>

            <div className="chart-container">
              <h2>Performance Graph (Last 100 samples)</h2>
              {history.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={history}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="read" stroke="#8884d8" name="Read" dot={false} />
                    <Line type="monotone" dataKey="write" stroke="#82ca9d" name="Write" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p>Loading chart data...</p>
              )}
            </div>

            <div className="ai-container">
              <h2>AI Analysis</h2>
              <button
                className="explain-btn"
                onClick={handleExplainAI}
                disabled={explaining}
              >
                {explaining ? 'Loading...' : 'Explain with AI'}
              </button>
              {explanation && (
                <div className="explanation-box">
                  <pre>{explanation}</pre>
                </div>
              )}
            </div>

            <div className="alerts-container">
              <h2>Recent Alerts</h2>
              {alerts.length === 0 ? (
                <p className="no-alerts">✓ No active alerts</p>
              ) : (
                <div className="alerts-list">
                  {alerts.map(a => (
                    <div key={a.id} className={`alert-item alert-${a.severity.toLowerCase()}`}>
                      <div className="alert-header">
                        <span className="alert-type">{a.alert_type}</span>
                        <span className="alert-time">
                          {new Date(a.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="alert-message">{a.message}</p>
                      {a.metric_value && (
                        <p className="alert-value">Value: {a.metric_value.toFixed(2)}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <p className="no-data">No metrics available yet. Backend may be starting up...</p>
        )}
      </main>
    </div>
  )
}

export default App

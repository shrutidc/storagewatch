import { useOutletContext } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

function Dashboard() {
  const { metrics, history, alerts, volumes, systemInfo, lastRefresh } = useOutletContext()

  const getSystemStatus = () => {
    if (metrics.used_percent >= 90) return 'Critical'
    if (metrics.used_percent >= 80) return 'Warning'
    return 'Healthy'
  }

  return (
    <>
      <div className="chart-container">
        <h2>System / Storage Health</h2>
        <div className="metrics-grid">
          <div className="metric-card">
            <h3>Overall Status</h3>
            <p className="metric-value">{getSystemStatus()}</p>
          </div>
          <div className="metric-card">
            <h3>Mounted Volumes</h3>
            <p className="metric-value">{volumes.length}</p>
          </div>
          <div className="metric-card">
            <h3>Physical Disks</h3>
            <p className="metric-value">{systemInfo?.physical_disks?.length ?? '—'}</p>
          </div>
          <div className="metric-card">
            <h3>Active Alerts</h3>
            <p className="metric-value">{alerts.length}</p>
          </div>
        </div>
        <p className="metric-detail" style={{ marginTop: '10px' }}>
          Last refresh: {lastRefresh ? lastRefresh.toLocaleTimeString() : '—'}
        </p>
      </div>

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
        <h2>Performance (Last 100 samples)</h2>
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Line type="monotone" dataKey="read" stroke="#8884d8" name="Read" dot={false} />
              <Line type="monotone" dataKey="write" stroke="#82ca9d" name="Write" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p>Loading chart data...</p>
        )}
      </div>

      <div className="alerts-container">
        <h2>Recent Alerts</h2>
        {alerts.length === 0 ? (
          <p className="no-alerts">✓ No active alerts</p>
        ) : (
          <div className="alerts-list">
            {alerts.slice(0, 3).map(a => (
              <div key={a.id} className={`alert-item alert-${a.severity.toLowerCase()}`}>
                <div className="alert-header">
                  <span className="alert-type">{a.alert_type}</span>
                  <span className="alert-time">{new Date(a.created_at).toLocaleTimeString()}</span>
                </div>
                <p className="alert-message">{a.message}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

export default Dashboard

import { useAuth0 } from '@auth0/auth0-react'
import { useState, useEffect } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const { loginWithRedirect, logout, user, isAuthenticated, isLoading } = useAuth0()
  const [metrics, setMetrics] = useState(null)
  const [history, setHistory] = useState([])
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    if (isAuthenticated) {
      fetchMetrics()
      const interval = setInterval(fetchMetrics, 5000)
      return () => clearInterval(interval)
    }
  }, [isAuthenticated])

  const fetchMetrics = async () => {
    try {
      const [current, hist] = await Promise.all([
        axios.get('/api/metrics/current'),
        axios.get('/api/metrics/history?limit=100'),
      ])
      setMetrics(current.data)
      setHistory(hist.data)
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    }
  }

  if (isLoading) return <div>Loading...</div>

  if (!isAuthenticated) {
    return (
      <div className="login-container">
        <h1>StorageWatch</h1>
        <button onClick={() => loginWithRedirect()}>Login</button>
      </div>
    )
  }

  return (
    <div className="app">
      <header>
        <h1>StorageWatch</h1>
        <div className="user-info">
          <span>{user.name}</span>
          <button onClick={() => logout()}>Logout</button>
        </div>
      </header>

      <main>
        {metrics && (
          <>
            <div className="metrics-grid">
              <div className="metric-card">
                <h3>Storage</h3>
                <p className="metric-value">{metrics.used_percent.toFixed(1)}%</p>
                <p className="metric-detail">{(metrics.used_bytes / 1e9).toFixed(1)} GB / {(metrics.total_bytes / 1e9).toFixed(1)} GB</p>
              </div>

              <div className="metric-card">
                <h3>Read Throughput</h3>
                <p className="metric-value">{(metrics.read_bytes_per_sec / 1e6).toFixed(0)} MB/s</p>
              </div>

              <div className="metric-card">
                <h3>Write Throughput</h3>
                <p className="metric-value">{(metrics.write_bytes_per_sec / 1e6).toFixed(0)} MB/s</p>
              </div>
            </div>

            <div className="chart-container">
              <h2>Performance Graph</h2>
              {/* Recharts will go here */}
            </div>

            <div className="alerts-container">
              <h2>Alerts</h2>
              {alerts.length === 0 ? <p>No alerts</p> : <ul>{/* Alert list */}</ul>}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

export default App

import { useAuth0 } from '@auth0/auth0-react'
import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import axios from 'axios'
import './App.css'

function App() {
  const { loginWithRedirect, logout, user, isAuthenticated, isLoading } = useAuth0()
  const [metrics, setMetrics] = useState(null)
  const [history, setHistory] = useState([])
  const [alerts, setAlerts] = useState([])
  const [volumes, setVolumes] = useState([])
  const [systemInfo, setSystemInfo] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)

  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatThreadId, setChatThreadId] = useState(null)
  const [chatSending, setChatSending] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)

  useEffect(() => {
    if (isAuthenticated) {
      fetchAll()
      const interval = setInterval(fetchAll, 5000)
      return () => clearInterval(interval)
    }
  }, [isAuthenticated])

  const fetchAll = async () => {
    try {
      const [current, hist, alertsData, volumesData] = await Promise.all([
        axios.get('/api/metrics/current'),
        axios.get('/api/metrics/history?limit=100'),
        axios.get('/api/alerts'),
        axios.get('/api/volumes'),
      ])
      setMetrics(current.data)

      if (hist.data && Array.isArray(hist.data)) {
        // API returns newest-first; charts need oldest-first so time reads
        // left-to-right.
        setHistory(hist.data.slice().reverse().map(m => ({
          time: new Date(m.time).toLocaleTimeString(),
          read: (m.read_bytes_per_sec / 1e6).toFixed(1),
          write: (m.write_bytes_per_sec / 1e6).toFixed(1),
        })))
      }

      if (alertsData.data && Array.isArray(alertsData.data)) {
        setAlerts(alertsData.data)
      }

      if (volumesData.data && Array.isArray(volumesData.data)) {
        setVolumes(volumesData.data)
      }

      // System info (disk/APFS) refreshes slowly on the collector side (~60s)
      // and may 404 briefly on first load — don't let that break the main poll.
      try {
        const sysInfo = await axios.get('/api/system-info')
        setSystemInfo(sysInfo.data)
      } catch (err) {
        // not received yet — fine, keep previous value
      }

      setLastRefresh(new Date())
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

  const handleSendChat = async (e) => {
    e.preventDefault()
    const text = chatInput.trim()
    if (!text || chatSending) return

    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', content: text }])
    setChatSending(true)

    try {
      const response = await axios.post('/api/ai/chat', {
        message: text,
        thread_id: chatThreadId,
      })
      setChatThreadId(response.data.thread_id)
      setChatMessages(prev => [...prev, { role: 'assistant', content: response.data.message }])
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setChatSending(false)
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
    <div className="app-shell">
      <nav className="sidebar">
        <h2 className="sidebar-title">StorageWatch</h2>
        <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Dashboard</NavLink>
        <NavLink to="/volumes" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Volumes</NavLink>
        <NavLink to="/disks" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Disks</NavLink>
        <NavLink to="/apfs" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>APFS</NavLink>
        <NavLink to="/performance" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Performance</NavLink>
        <NavLink to="/alerts" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
          Alerts{alerts.length > 0 ? ` (${alerts.length})` : ''}
        </NavLink>
      </nav>

      <div className="main-column">
        <header>
          <div className="header-left">
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
            <Outlet context={{ metrics, history, alerts, volumes, systemInfo, lastRefresh }} />
          ) : (
            <p className="no-data">No metrics available yet. Backend may be starting up...</p>
          )}
        </main>
      </div>

      <button className="chat-toggle" onClick={() => setChatOpen(o => !o)}>
        {chatOpen ? '✕' : '💬 Ask AI'}
      </button>

      {chatOpen && (
        <div className="chat-widget">
          <div className="chat-widget-header">StorageWatch AI</div>
          <div className="chat-messages">
            {chatMessages.length === 0 ? (
              <p className="no-alerts">Ask about your storage — available on every page.</p>
            ) : (
              chatMessages.map((m, i) => (
                <div key={i} className={`chat-message chat-${m.role}`}>
                  <strong>{m.role === 'user' ? 'You' : 'AI'}:</strong> {m.content}
                </div>
              ))
            )}
            {chatSending && <div className="chat-message chat-assistant"><em>Thinking...</em></div>}
          </div>
          <form className="chat-input-row" onSubmit={handleSendChat}>
            <input
              type="text"
              className="chat-input"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              placeholder="Ask a question..."
              disabled={chatSending}
            />
            <button type="submit" className="explain-btn" disabled={chatSending || !chatInput.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

export default App

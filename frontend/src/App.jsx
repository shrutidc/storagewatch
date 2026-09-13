import { useAuth0 } from '@auth0/auth0-react'
import { useState, useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import axios from 'axios'
import './App.css'
import InstallCommand from './InstallCommand.jsx'

// The one-line collector installer. In development the API runs on :8000
// rather than Vite's :3000, so the installer is pointed there explicitly.
const API_ORIGIN = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin
const INSTALL_COMMAND = import.meta.env.DEV
  ? `curl -fsSL ${API_ORIGIN}/install.sh | STORAGEWATCH_URL=${API_ORIGIN} sh`
  : `curl -fsSL ${API_ORIGIN}/install.sh | sh`

function App() {
  const { loginWithRedirect, logout, user, isAuthenticated, isLoading,
          getAccessTokenSilently } = useAuth0()
  const location = useLocation()
  const [metrics, setMetrics] = useState(null)
  const [history, setHistory] = useState([])
  const [alerts, setAlerts] = useState([])
  const [volumes, setVolumes] = useState([])
  const [systemInfo, setSystemInfo] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [hosts, setHosts] = useState([])
  // null = follow whichever machine reported most recently
  const [selectedHost, setSelectedHost] = useState(null)
  const [authError, setAuthError] = useState(null)
  // False until the first poll returns, so loading isn't mistaken for "no data".
  const [fetched, setFetched] = useState(false)

  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatThreadId, setChatThreadId] = useState(null)
  const [chatSending, setChatSending] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)

  const onSettings = location.pathname === '/settings'
  const onConnect = location.pathname === '/connect'

  const hasMetrics = Boolean(metrics)
  useEffect(() => {
    if (isAuthenticated) {
      fetchPage()
      // Until the first sample exists — e.g. just after connecting a Mac —
      // check every 2 s so the dashboard fills in as soon as data lands.
      const interval = setInterval(fetchPage, hasMetrics ? 5000 : 2000)
      return () => clearInterval(interval)
    }
  }, [isAuthenticated, selectedHost, location.pathname, hasMetrics])

  // The machine list changes rarely, so it loads at sign-in and when Settings
  // opens rather than on every poll — the query scans the whole history.
  useEffect(() => {
    if (isAuthenticated) fetchHosts()
  }, [isAuthenticated, onSettings])

  // The backend verifies this token, so every API call has to carry it.
  const authConfig = async () => ({
    headers: { Authorization: `Bearer ${await getAccessTokenSilently()}` },
  })

  const fetchHosts = async () => {
    try {
      const res = await axios.get('/api/hosts', await authConfig())
      if (Array.isArray(res.data)) setHosts(res.data)
    } catch (err) {
      console.error('Failed to fetch hosts:', err)
    }
  }

  const fetchPage = async () => {
    // A tab left open in the background would otherwise poll around the clock.
    if (document.hidden) return

    let cfg
    try {
      cfg = await authConfig()
      setAuthError(null)
    } catch (err) {
      // Usually means VITE_AUTH0_AUDIENCE doesn't match a registered API in
      // the Auth0 tenant, so no verifiable access token can be issued.
      setAuthError(err.message || String(err))
      return
    }

    // Scope every request to one machine, otherwise a user running two
    // collectors sees both machines' readings interleaved as if they were one
    // disk. Omitting it lets the backend pick the most recent reporter.
    const host = selectedHost
      ? { params: { hostname: selectedHost } }
      : {}
    try {
      // One request for everything the page shows. The server has a tenth of
      // a CPU, so per-request overhead — not the queries — was the bottleneck.
      const { data } = await axios.get('/api/dashboard', { ...cfg, ...host })
      setMetrics(data.current)  // null until the first sample: shows the install step
      setAlerts(data.alerts)
      setVolumes(data.volumes)
      setSystemInfo(data.system_info)
      // Already oldest-first, so time reads left-to-right.
      setHistory(data.history.map(m => ({
        time: new Date(m.time).toLocaleTimeString(),
        // Numbers, not toFixed() strings: Recharts sizes the axis from these,
        // and strings compare as text ("9.8" > "15.2"), clipping the line.
        read: Math.round(m.read_bytes_per_sec / 1e5) / 10,
        write: Math.round(m.write_bytes_per_sec / 1e5) / 10,
      })))
      setLastRefresh(new Date())
    } catch (err) {
      console.error('Failed to fetch dashboard:', err)
    } finally {
      setFetched(true)
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
      }, await authConfig())
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
          {/* Come back to the page that asked, e.g. /connect with its query. */}
          <button className="login-btn" onClick={() => loginWithRedirect({
            appState: { returnTo: location.pathname + location.search },
          })}>Login with Auth0</button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <h2 className="sidebar-title">StorageWatch</h2>
        <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Dashboard</NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Settings</NavLink>
      </nav>

      <div className="main-column">
        <header>
          <div className="header-left">
            {metrics && (
              <>
                <div className="status-badge" style={{ backgroundColor: getStatusColor() }}>
                  System {getSystemStatus()}
                </div>
                <span className="header-host">{metrics.hostname}</span>
              </>
            )}
          </div>
          <div className="user-info">
            {hosts.length > 1 && (
              <select
                className="host-select"
                value={selectedHost || ''}
                onChange={e => setSelectedHost(e.target.value || null)}
              >
                <option value="">Most recent machine</option>
                {hosts.map(h => (
                  <option key={h.hostname} value={h.hostname}>{h.hostname}</option>
                ))}
              </select>
            )}
            <span>{user.name}</span>
            {/* Without returnTo, Auth0 sends everyone to the first Allowed Logout
                URL in the tenant — which was http://localhost:3000. */}
            <button onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>
              Logout
            </button>
          </div>
        </header>

        <main>
          {authError ? (
            <div className="detail-section">
              <h2>Cannot authenticate to the API</h2>
              <p className="section-sub">
                Auth0 could not issue an access token for audience{' '}
                <code>{import.meta.env.VITE_AUTH0_AUDIENCE}</code>. That audience must exist
                under Applications &rarr; APIs in the Auth0 dashboard, otherwise the token
                is opaque and the backend cannot verify it.
              </p>
              <p className="alert-ai-explanation">{authError}</p>
            </div>
          ) : (metrics || onSettings || onConnect) ? (
            // Settings and Connect must render without metrics: a new user has
            // no data until their first collector connects.
            <Outlet context={{ metrics, history, alerts, volumes, systemInfo, lastRefresh, hosts,
                               authConfig, installCommand: INSTALL_COMMAND }} />
          ) : !fetched ? (
            <p className="no-data">Loading metrics…</p>
          ) : (
            <div className="detail-section">
              <h2>Analyze this Mac</h2>
              <p className="section-sub">
                StorageWatch reads the disk of the Mac it runs on, so that Mac needs its small
                collector. A website can't start programs on your Mac, so copy this command and
                run it once in Terminal: it connects the Mac to your account, then keeps
                reporting in the background whenever you are logged in to it.
              </p>
              <InstallCommand command={INSTALL_COMMAND} />
              <p className="section-sub">
                Waiting for this Mac to report — this page updates by itself.
              </p>
            </div>
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

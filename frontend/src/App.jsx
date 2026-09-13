import { useAuth0 } from '@auth0/auth0-react'
import { useState, useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import axios from 'axios'
import './App.css'
import InstallCommand from './InstallCommand.jsx'
import LoginParticles from './LoginParticles.jsx'
import LoginCircuit from './LoginCircuit.jsx'
import LoginLabels from './LoginLabels.jsx'
import ThemeToggleButton from './ThemeToggleButton.jsx'

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
  const [preferences, setPreferences] = useState(null)
  const [users, setUsers] = useState([])
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
      setPreferences(data.preferences)
      setUsers(data.users || [])
      // Already oldest-first, so time reads left-to-right.
      setHistory(data.history.map(m => ({
        // Epoch milliseconds, not a pre-formatted string: the axis needs a
        // short label and the tooltip a precise one, and a string can only be
        // one of those.
        time: new Date(m.time).getTime(),
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
        <ThemeToggleButton />
        <LoginCircuit />
        <LoginLabels />
        <LoginParticles />
        <div className="login-box">
          <h1>StorageWatch</h1>
          <p>Monitor your macOS storage with AI-powered insights</p>
          {/* Come back to the page that asked, e.g. /connect with its query. */}
          <button className="login-btn" onClick={() => loginWithRedirect({
            appState: { returnTo: location.pathname + location.search },
          })}>
            <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor" aria-hidden="true">
              <path d="M12 2 4 5.2v6.1c0 5 3.4 9.7 8 10.7 4.6-1 8-5.7 8-10.7V5.2L12 2zm0 2.2 6 2.4v4.7c0 4-2.6 7.8-6 8.7-3.4-.9-6-4.7-6-8.7V6.6l6-2.4z" />
            </svg>
            Login
            <svg className="login-btn-arrow" viewBox="0 0 24 24" width="18" height="18"
                 fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                 strokeLinejoin="round" aria-hidden="true">
              <line x1="5" y1="12" x2="18" y2="12" />
              <polyline points="13 7 18 12 13 17" />
            </svg>
          </button>
          {/* The Mac app, with the collector inside, for anyone setting up a
              machine — downloadable before signing in. */}
          <a className="login-btn" href="/StorageWatch-Mac.zip" download
             style={{ textDecoration: 'none', marginTop: 12 }}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v12" />
              <polyline points="7 10 12 15 17 10" />
              <path d="M5 21h14" />
            </svg>
            Download for Mac
          </a>
          <p className="login-foot">Local · Encrypted · Observable</p>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <h2 className="sidebar-title">
          <img src="/logo.svg" alt="" className="brand-logo" />
          StorageWatch
        </h2>
        <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Dashboard</NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>Settings</NavLink>

        {/* Pushed to the bottom of the sidebar, which is sticky, so signing out
            is reachable from anywhere on a long page. */}
        <div className="sidebar-footer">
          <span className="sidebar-user" title={user.name}>{user.name}</span>
          {/* Without returnTo, Auth0 sends everyone to the first Allowed Logout
              URL in the tenant — which was http://localhost:3000. */}
          <button
            className="sidebar-logout"
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Log out
          </button>
        </div>
      </nav>

      <div className="main-column">
        <main>
          {metrics && (
            <div className="system-card">
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
              <span className="system-host">{metrics.hostname}</span>
              <span className="system-sep">:</span>
              {/* The glow is mixed from the same colour the pill is filled
                  with, so it follows the state rather than being a fixed
                  green that would contradict a warning. */}
              <span
                className="system-status"
                style={{
                  backgroundColor: getStatusColor(),
                  boxShadow: `0 0 18px ${getStatusColor()}70, 0 0 6px ${getStatusColor()}90`,
                }}
              >
                System {getSystemStatus()}
              </span>
            </div>
          )}

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
            <div className="page" key={location.pathname}>
              <Outlet context={{ metrics, history, alerts, volumes, systemInfo, preferences,
                                 users, lastRefresh, hosts, authConfig,
                                 installCommand: INSTALL_COMMAND }} />
            </div>
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

      <button
        className={`chat-toggle${chatOpen ? ' open' : ''}`}
        onClick={() => setChatOpen(o => !o)}
        aria-label={chatOpen ? 'Close the assistant' : 'Ask Anything'}
      >
        {chatOpen ? (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              {/* The gradient id must be unique on the page, and this button is
                  rendered once, so a fixed id is safe here. */}
              <linearGradient id="sparkle" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#e935c1" />
                <stop offset="100%" stopColor="#4f46e5" />
              </linearGradient>
              <path fill="url(#sparkle)"
                    d="M11.2 2.6a.6.6 0 0 1 1.12 0l1.36 3.5a4 4 0 0 0 2.3 2.3l3.5 1.36a.6.6 0 0 1 0 1.12l-3.5 1.36a4 4 0 0 0-2.3 2.3l-1.36 3.5a.6.6 0 0 1-1.12 0l-1.36-3.5a4 4 0 0 0-2.3-2.3l-3.5-1.36a.6.6 0 0 1 0-1.12l3.5-1.36a4 4 0 0 0 2.3-2.3z" />
              <path fill="url(#sparkle)"
                    d="M17.9 16.1a.35.35 0 0 1 .66 0l.53 1.37a2 2 0 0 0 1.14 1.14l1.37.53a.35.35 0 0 1 0 .66l-1.37.53a2 2 0 0 0-1.14 1.14l-.53 1.37a.35.35 0 0 1-.66 0l-.53-1.37a2 2 0 0 0-1.14-1.14l-1.37-.53a.35.35 0 0 1 0-.66l1.37-.53a2 2 0 0 0 1.14-1.14z" />
            </svg>
            Ask Anything
          </>
        )}
      </button>

      {chatOpen && (
        <div className="chat-widget">
          <div className="chat-widget-header">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <linearGradient id="chat-sparkle" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#e935c1" />
                <stop offset="100%" stopColor="#4f46e5" />
              </linearGradient>
              <path fill="url(#chat-sparkle)"
                    d="M11.2 2.6a.6.6 0 0 1 1.12 0l1.36 3.5a4 4 0 0 0 2.3 2.3l3.5 1.36a.6.6 0 0 1 0 1.12l-3.5 1.36a4 4 0 0 0-2.3 2.3l-1.36 3.5a.6.6 0 0 1-1.12 0l-1.36-3.5a4 4 0 0 0-2.3-2.3l-3.5-1.36a.6.6 0 0 1 0-1.12l3.5-1.36a4 4 0 0 0 2.3-2.3z" />
            </svg>
            StorageWatch AI
          </div>

          <div className="chat-messages">
            {chatMessages.length === 0 ? (
              <div className="chat-empty">
                <p className="chat-empty-title">Ask about this Mac</p>
                {/* Concrete openers: a blank box invites nothing, and these are
                    questions the telemetry on this page can actually answer. */}
                <div className="chat-suggestions">
                  {['What is using my disk space?',
                    'Is my SSD healthy?',
                    'Why did write activity spike?'].map(q => (
                    <button key={q} type="button" className="chat-suggestion"
                            onClick={() => setChatInput(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              chatMessages.map((m, i) => (
                <div key={i} className={`chat-row chat-row-${m.role}`}>
                  <div className={`chat-bubble chat-bubble-${m.role}`}>{m.content}</div>
                </div>
              ))
            )}
            {chatSending && (
              <div className="chat-row chat-row-assistant">
                <div className="chat-bubble chat-bubble-assistant chat-typing">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </div>

          <form className="chat-input-row" onSubmit={handleSendChat}>
            <input
              type="text"
              className="chat-input"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              placeholder="Ask a question…"
              disabled={chatSending}
            />
            <button type="submit" className="chat-send"
                    disabled={chatSending || !chatInput.trim()} aria-label="Send">
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

export default App

import { useState, useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'
import InstallCommand from '../InstallCommand.jsx'
import MenuBarSetting from '../MenuBarSetting.jsx'
import ThemeSetting from '../ThemeSetting.jsx'

function Settings() {
  const { hosts, authConfig, installCommand, uninstallCommand } = useOutletContext()
  const [uninstallCopied, setUninstallCopied] = useState(false)
  const [tokens, setTokens] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get('/api/agent-tokens', await authConfig())
        setTokens(res.data)
      } catch (err) {
        setError(err.message)
      }
    })()
  }, [])

  return (
    <>
      <div className="detail-section">
        <h2>Your Machines</h2>
        <p className="section-sub">
          Only machines connected to your account appear here. Other people's
          machines are never visible to you, and yours are never visible to them.
        </p>
        {hosts.length === 0 ? (
          <p className="no-alerts">No machines reporting yet.</p>
        ) : (
          <table className="detail-table">
            <thead><tr><th>Hostname</th><th>Last seen</th></tr></thead>
            <tbody>
              {hosts.map(h => (
                <tr key={h.hostname}>
                  <td>{h.hostname}</td>
                  <td>{new Date(h.last_seen).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="detail-section">
        <h2>Connect a Mac</h2>
        <p className="section-sub">
          Run this once in Terminal on the Mac to monitor. It opens this site to connect
          the Mac to your account, then keeps reporting in the background whenever you
          are logged in to that Mac.
        </p>
        <InstallCommand command={installCommand} />

        {error && <p className="alert-ai-explanation">Error: {error}</p>}

        {tokens.length > 0 && (
          <>
            <h3>Connected collectors</h3>
            <table className="detail-table">
              <thead><tr><th>Machine</th><th>Connected</th><th>Last report</th></tr></thead>
              <tbody>
                {tokens.map((t, i) => (
                  <tr key={i}>
                    <td>{t.label || '—'}</td>
                    <td>{new Date(t.created_at).toLocaleString()}</td>
                    <td>{t.last_used_at ? new Date(t.last_used_at).toLocaleString() : 'never'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="detail-section">
        <h2>Stop monitoring a Mac</h2>
        <p className="section-sub">
          The collector keeps running in the background even after you sign out here or
          close Terminal. Run this in Terminal on the Mac to stop it and remove
          StorageWatch, including the downloaded app.
        </p>
        <button className="explain-btn" onClick={() =>
          navigator.clipboard.writeText(uninstallCommand).then(() => setUninstallCopied(true), () => {})}>
          {uninstallCopied ? '✓ Copied — now paste it into Terminal' : 'Copy command'}
        </button>
        <pre className="command-box">{uninstallCommand}</pre>
      </div>

      <MenuBarSetting />
      <ThemeSetting />

      <div className="detail-section">
        <h2>Privacy</h2>
        <p className="section-sub">
          What this agent collects from your Mac, where it is stored, and what it never
          reads.
        </p>
        <a className="explain-btn" href="/privacy">Read the privacy page</a>
      </div>
    </>
  )
}

export default Settings

import { useState, useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'
import InstallCommand from '../InstallCommand.jsx'

function Settings() {
  const { hosts, authConfig, installCommand } = useOutletContext()
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
    </>
  )
}

export default Settings

import { useState, useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

function Settings() {
  const { hosts, authConfig } = useOutletContext()
  const [tokens, setTokens] = useState([])
  // Held only in component state: the server stores a hash, so this plaintext
  // exists nowhere else and is gone as soon as the page is left.
  const [newToken, setNewToken] = useState(null)
  const [minting, setMinting] = useState(false)
  const [error, setError] = useState(null)

  const loadTokens = async () => {
    try {
      const res = await axios.get('/api/agent-tokens', await authConfig())
      setTokens(res.data)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { loadTokens() }, [])

  const mint = async () => {
    setMinting(true)
    setError(null)
    try {
      const res = await axios.post('/api/agent-tokens', { label: 'collector' }, await authConfig())
      setNewToken(res.data.token)
      loadTokens()
    } catch (err) {
      setError(err.message)
    } finally {
      setMinting(false)
    }
  }

  return (
    <>
      <div className="detail-section">
        <h2>Your Machines</h2>
        <p className="section-sub">
          Only machines reporting with your own agent tokens appear here. Other
          people's machines are never visible to you, and yours are never visible to them.
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
        <h2>Agent Token</h2>
        <p className="section-sub">
          The collector on each Mac authenticates with one of these. It has no
          user to sign in as, so the token is what ties its telemetry to your account.
        </p>

        <button className="explain-btn" onClick={mint} disabled={minting}>
          {minting ? 'Generating…' : 'Generate agent token'}
        </button>

        {error && <p className="alert-ai-explanation">Error: {error}</p>}

        {newToken && (
          <div className="alert-item alert-warning">
            <p className="alert-message">
              Copy this now — it is shown once and only its hash is stored,
              so it cannot be retrieved later.
            </p>
            <pre className="token-box">{newToken}</pre>
            <p className="metric-detail">
              Put it in <code>.env</code> on the monitored Mac as{' '}
              <code>AGENT_TOKEN=…</code>, then restart the collector.
            </p>
          </div>
        )}

        {tokens.length > 0 && (
          <>
            <h3>Existing tokens</h3>
            <table className="detail-table">
              <thead><tr><th>Label</th><th>Created</th><th>Last used</th></tr></thead>
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

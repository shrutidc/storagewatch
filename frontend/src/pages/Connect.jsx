import { useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import axios from 'axios'

// Where the collector's browser sign-in lands. Mints an agent token and hands
// it to the collector's one-shot listener on this machine's loopback address,
// so nobody copies a token by hand.
function Connect() {
  const { authConfig } = useOutletContext()
  const [params] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const port = Number(params.get('port'))
  const host = params.get('host') || 'this Mac'

  // The token only ever goes to 127.0.0.1 on a numeric port, so a crafted
  // link cannot send it anywhere else.
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    return (
      <p className="no-data">
        This link is incomplete. Start the collector on the Mac to monitor (the
        command is under Settings) and it opens the right page.
      </p>
    )
  }

  const connect = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await axios.post('/api/agent-tokens', { label: host }, await authConfig())
      const answer = new URLSearchParams({ token: res.data.token, state: params.get('state') || '' })
      window.location.href = `http://127.0.0.1:${port}/callback?${answer}`
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
      setBusy(false)
    }
  }

  return (
    <div className="detail-section">
      <h2>Connect {host}</h2>
      <p className="section-sub">
        The StorageWatch collector on {host} is asking to report to your account.
        Continue only if you just started it.
      </p>
      <button className="explain-btn" onClick={connect} disabled={busy}>
        {busy ? 'Connecting…' : `Connect ${host}`}
      </button>
      {error && <p className="alert-ai-explanation">Error: {error}</p>}
    </div>
  )
}

export default Connect

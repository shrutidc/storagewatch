import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import Privacy from './pages/Privacy.jsx'

// Shown after signing in, before the dashboard, until this account has accepted
// the current revision of the privacy page.
//
// The button stays disabled until the text has actually been scrolled to the
// end. That does not prove anyone read it, and it is not meant to — it means
// nobody can agree without the page having passed in front of them, which is
// the difference between consent and a reflex click.
function PolicyGate({ authConfig, onAccepted, version }) {
  const scrollerRef = useRef(null)
  const [reachedEnd, setReachedEnd] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    const check = () => {
      // A short viewport can show the whole page without scrolling, in which
      // case it has been seen and the button should not be stuck disabled.
      const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 24
      if (atEnd) setReachedEnd(true)
    }
    check()
    el.addEventListener('scroll', check, { passive: true })
    window.addEventListener('resize', check)
    return () => {
      el.removeEventListener('scroll', check)
      window.removeEventListener('resize', check)
    }
  }, [])

  const accept = async () => {
    setSaving(true)
    setError(null)
    try {
      await axios.post('/api/policy/accept', {}, await authConfig())
      onAccepted()
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
      setSaving(false)
    }
  }

  return (
    <div className="policy-gate">
      <div className="policy-gate-panel">
        <div className="policy-gate-head">
          <h1>Before you continue</h1>
          <p>
            StorageWatch reads your Mac's storage. Please read what it collects, then
            accept to continue.
          </p>
        </div>

        <div className="policy-gate-scroll" ref={scrollerRef}>
          <Privacy />
        </div>

        <div className="policy-gate-foot">
          <span className="policy-gate-hint">
            {reachedEnd
              ? `Revision ${version}`
              : 'Scroll to the end to continue'}
          </span>
          <button
            className="login-btn policy-accept"
            onClick={accept}
            disabled={!reachedEnd || saving}
          >
            {saving ? 'Saving…' : 'I have read and accept this'}
          </button>
        </div>

        {error && <p className="alert-ai-explanation">Error: {error}</p>}
      </div>
    </div>
  )
}

export default PolicyGate

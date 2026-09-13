import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

// Whether the monitored Mac shows StorageWatch in its menu bar.
//
// This page cannot reach that Mac, so the switch saves the choice on the server
// and the collector applies it there with its next report — a few seconds. Until
// that collector confirms what it actually did, the switch says so rather than
// claiming a change it has not seen take effect.
function MenuBarSetting() {
  const { preferences, authConfig } = useOutletContext()
  // What this browser just asked for, held until the poll catches up: without
  // it the switch snaps back to the old value for up to five seconds. Tagged
  // with the machine it was meant for, because the header's machine selector
  // can change which one this card is showing while a change is in flight.
  const [pending, setPending] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const host = preferences?.hostname
  const saved = preferences?.menu_bar_enabled
  useEffect(() => {
    if (pending && (pending.hostname !== host || pending.value === saved)) setPending(null)
  }, [host, saved, pending])

  // No machine has reported yet, so there is nothing to configure.
  if (!preferences) return null

  const { hostname, menu_bar_applied: applied } = preferences
  const enabled = pending?.hostname === hostname ? pending.value : saved

  const choose = async (next) => {
    setPending({ hostname, value: next })
    setSaving(true)
    setError(null)
    try {
      await axios.put('/api/preferences',
        { hostname, menu_bar_enabled: next }, await authConfig())
    } catch (err) {
      setPending(null)
      setError(err.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  // applied is null on a machine whose collector predates this setting, which
  // reads the same way as a change still in flight: neither has confirmed.
  const status = applied === enabled
    ? (enabled ? `Showing in ${hostname}'s menu bar.` : `Not shown on ${hostname}.`)
    : `${enabled ? 'Adding to' : 'Removing from'} ${hostname} — the collector there `
      + `applies this with its next report, within a few seconds.`

  return (
    <div className="detail-section">
      <h2>Menu bar app</h2>
      <p className="section-sub">
        Storage, throughput and alerts at a glance in the Mac's menu bar, without signing
        in. Monitoring runs either way.
      </p>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={enabled}
          disabled={saving}
          onChange={e => choose(e.target.checked)}
        />
        <span>Show StorageWatch in the menu bar on {hostname}</span>
      </label>
      <p className="section-sub toggle-status">{status}</p>
      {error && <p className="alert-ai-explanation">Error: {error}</p>}
    </div>
  )
}

export default MenuBarSetting

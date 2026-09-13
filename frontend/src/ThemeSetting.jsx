import { useState } from 'react'
import { THEMES, readTheme, applyTheme, resolveTheme } from './theme.js'

const LABEL = { light: 'Light', dark: 'Dark', system: 'System' }

// Appearance is a per-browser preference, not a per-machine one: it is stored
// in localStorage rather than sent to the backend, so it never travels to
// another user or waits on a collector to apply it.
function ThemeSetting() {
  const [choice, setChoice] = useState(readTheme)

  const choose = (next) => {
    setChoice(next)
    applyTheme(next)
  }

  return (
    <div className="detail-section">
      <h2>Appearance</h2>
      <p className="section-sub">
        Applies to this browser only. <strong>System</strong> follows your Mac's
        appearance and keeps following it if you change it.
      </p>
      <div className="theme-picker" role="group" aria-label="Theme">
        {THEMES.map(t => (
          <button
            key={t}
            type="button"
            className={`theme-option${choice === t ? ' active' : ''}`}
            aria-pressed={choice === t}
            onClick={() => choose(t)}
          >
            {LABEL[t]}
          </button>
        ))}
      </div>
      <p className="section-sub toggle-status">
        {choice === 'system'
          ? `Following your Mac, which is currently ${resolveTheme('system')}.`
          : `Pinned to ${LABEL[choice].toLowerCase()}.`}
      </p>
    </div>
  )
}

export default ThemeSetting

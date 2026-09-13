import { useState } from 'react'
import { readTheme, applyTheme, resolveTheme } from './theme.js'

// A compact light/dark switch for the sign-in page, where the full Appearance
// panel in Settings isn't reachable yet.
//
// It shows what clicking will do, not what is currently set: a sun means
// "switch to light". "System" collapses to whichever it currently resolves to,
// so one click always lands somewhere definite.
function ThemeToggleButton() {
  const [choice, setChoice] = useState(readTheme)
  const effective = resolveTheme(choice)
  const next = effective === 'dark' ? 'light' : 'dark'

  const toggle = () => {
    setChoice(next)
    applyTheme(next)
  }

  return (
    <button
      type="button"
      className="theme-toggle-btn"
      onClick={toggle}
      aria-label={`Switch to ${next} appearance`}
      title={`Switch to ${next} appearance`}
    >
      {effective === 'dark' ? (
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  )
}

export default ThemeToggleButton

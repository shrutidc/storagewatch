// Theme selection, applied as data-theme on <html> so CSS variables switch.
//
// "system" is the default and is not a stored colour: it follows the OS, and
// keeps following it if the user changes it while the page is open. Choosing
// light or dark pins it against that.
const KEY = 'storagewatch-theme'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

export const THEMES = ['light', 'dark', 'system']

export function readTheme() {
  try {
    const saved = localStorage.getItem(KEY)
    return THEMES.includes(saved) ? saved : 'system'
  } catch {
    // Private browsing and blocked site data both throw on access rather
    // than returning null.
    return 'system'
  }
}

export function resolveTheme(choice) {
  return choice === 'system' ? (media().matches ? 'dark' : 'light') : choice
}

export function applyTheme(choice) {
  document.documentElement.setAttribute('data-theme', resolveTheme(choice))
  try {
    localStorage.setItem(KEY, choice)
  } catch {
    // The theme still applies for this page; it just won't be remembered.
  }
}

// Applied before React renders so the first paint is already the right theme
// — mounting first would flash white on a dark-mode machine.
export function initTheme() {
  const choice = readTheme()
  document.documentElement.setAttribute('data-theme', resolveTheme(choice))
  media().addEventListener('change', () => {
    if (readTheme() === 'system') {
      document.documentElement.setAttribute('data-theme', resolveTheme('system'))
    }
  })
  return choice
}

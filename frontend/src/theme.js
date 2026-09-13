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

// Long enough to read as a fade, short enough not to feel like waiting.
const FADE_MS = 260
let fadeTimer

// The transition is applied by a class held only while the swap happens, not
// by a permanent rule: a standing `transition` on every element would also
// slow every hover and focus change on the page.
function fade(set) {
  const root = document.documentElement
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    set()
    return
  }
  root.classList.add('theme-fading')
  set()
  clearTimeout(fadeTimer)
  fadeTimer = setTimeout(() => root.classList.remove('theme-fading'), FADE_MS)
}

export function applyTheme(choice) {
  fade(() => document.documentElement.setAttribute('data-theme', resolveTheme(choice)))
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
      fade(() => document.documentElement.setAttribute('data-theme', resolveTheme('system')))
    }
  })
  return choice
}

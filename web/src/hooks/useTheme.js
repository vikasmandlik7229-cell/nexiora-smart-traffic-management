import { useEffect, useState } from 'react'

// Renamed from 'nexiora-theme' on the Smart Traffic AI rebrand so visitors who
// saved "dark" under the old key (when dark was the default) land on the new
// light-default look instead of a stale preference silently overriding it.
const STORAGE_KEY = 'smart-traffic-ai-theme'

function getInitialTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* localStorage unavailable (private browsing etc) - fall through to default */
  }
  return 'light' // light/white dashboard background per the Smart Traffic AI design spec
}

export function useTheme() {
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* ignore - per-viewer convenience only */
    }
  }, [theme])

  return { theme, toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')) }
}

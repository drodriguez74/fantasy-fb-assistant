import { useCallback, useEffect, useState } from 'react'

type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'axis-theme'

function systemTheme(): ResolvedTheme {
  return typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function storedTheme(): ResolvedTheme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'dark' || v === 'light' ? v : null
  } catch {
    return null
  }
}

/**
 * Resolved light/dark theme + a toggle.
 *
 * The `data-theme` attribute on <html> is the single source of truth the CSS
 * reads (see src/index.css). It's set before first paint by an inline script
 * in index.html; this hook keeps React in sync and drives the toggle. With no
 * explicit choice we follow the OS setting and stay subscribed to changes.
 */
export function useTheme() {
  const [theme, setTheme] = useState<ResolvedTheme>(
    () => storedTheme() ?? systemTheme()
  )

  // Follow OS changes only while the user hasn't made an explicit choice.
  useEffect(() => {
    if (storedTheme()) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setTheme(mq.matches ? 'dark' : 'light')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  // Mirror state -> <html data-theme> (and drop the attribute when the choice
  // matches the OS, so we go back to following it).
  useEffect(() => {
    const root = document.documentElement
    if (storedTheme()) {
      root.dataset.theme = theme
    } else if (theme === systemTheme()) {
      delete root.dataset.theme
    } else {
      root.dataset.theme = theme
    }
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: ResolvedTheme = prev === 'dark' ? 'light' : 'dark'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        /* private mode / storage disabled — session-only toggle still works */
      }
      return next
    })
  }, [])

  return { theme, toggle }
}

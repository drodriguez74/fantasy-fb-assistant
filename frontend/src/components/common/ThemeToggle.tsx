import { MoonIcon, SunIcon } from '@heroicons/react/24/outline'
import { useTheme } from '../../hooks/useTheme'

/**
 * Light/dark switch. Sits in the (always-dark) navbar, so its own colors are
 * fixed light-on-dark rather than themed.
 */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, toggle } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-sm text-ink-300 transition-colors hover:bg-ink-800 hover:text-volt focus:outline-none focus-visible:ring-2 focus-visible:ring-volt ${className}`}
    >
      {theme === 'dark' ? (
        <SunIcon className="h-[18px] w-[18px]" aria-hidden="true" />
      ) : (
        <MoonIcon className="h-[18px] w-[18px]" aria-hidden="true" />
      )}
    </button>
  )
}

// Player search for the Bets page's long lists (sportsbook props, the PrizePicks board).
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline'

export function PlayerSearch({
  value,
  onChange,
  placeholder = 'Search a player or team',
  count,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  // Matching lines, shown while searching.
  count?: number
}) {
  return (
    <div className="flex items-center gap-3">
      <label className="relative flex-1 min-w-0">
        <span className="sr-only">{placeholder}</span>
        <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-faint" />
        <input
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && onChange('')}
          placeholder={placeholder}
          autoComplete="off"
          className="w-full rounded-lg border border-hairline bg-surface pl-9 pr-9 py-2 text-sm text-body placeholder:text-faint focus:outline-none focus:border-line"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange('')}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-body"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        )}
      </label>
      {value.trim() && count != null && (
        <span className="stat-nums text-xs text-muted shrink-0">
          {count} {count === 1 ? 'line' : 'lines'}
        </span>
      )}
    </div>
  )
}

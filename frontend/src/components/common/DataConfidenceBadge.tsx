import { InformationCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'

export type DataConfidenceLevel = 'computed' | 'heuristic' | 'insufficient'

interface DataConfidenceBadgeProps {
  level: DataConfidenceLevel
  label?: string
  className?: string
}

const LEVEL_STYLES: Record<DataConfidenceLevel, string> = {
  computed: 'bg-ink-100 text-ink-600',
  heuristic: 'bg-warning-100 text-warning-800',
  insufficient: 'bg-ink-50 text-ink-400 border border-dashed border-ink-200',
}

const DEFAULT_LABEL: Record<DataConfidenceLevel, string> = {
  computed: 'Computed',
  heuristic: 'Heuristic',
  insufficient: 'Insufficient data',
}

/**
 * Small badge that tells the reader how much to trust a nearby number,
 * independent of how confident that number *looks*. A bar or a big stat
 * reads the same whether it's a real calculation or a placeholder -- this
 * makes the difference explicit instead of leaving every score looking
 * equally authoritative:
 *
 *  - `computed`: a direct, deterministic calculation from real data.
 *  - `heuristic`: a real calculation standing in for something more
 *    sophisticated (a weighted/composite score, a proxy metric, etc).
 *  - `insufficient`: an honest empty/no-data state, rather than a
 *    fabricated number.
 *
 * Deliberately generic -- no page-specific copy lives here. Pass `label`
 * to override the default noun when a page wants something more specific
 * (e.g. "Live ratio" instead of "Computed").
 */
export function DataConfidenceBadge({ level, label, className = '' }: DataConfidenceBadgeProps) {
  const Icon = level === 'heuristic' ? InformationCircleIcon : level === 'insufficient' ? ExclamationTriangleIcon : null

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${LEVEL_STYLES[level]} ${className}`}
    >
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {label ?? DEFAULT_LABEL[level]}
    </span>
  )
}

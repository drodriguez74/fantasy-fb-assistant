import type { Position } from '../../types'

// Shared display helpers for player position/risk/injury badges. Single
// source of truth for position-badge colors -- import from here rather than
// re-declaring a local color map, so every surface (PlayerCard, PlayersPage,
// DraftBoard, TeamRoster, RecommendationCard, WaiverWirePage,
// HistoricalPage, ...) renders the same player's position badge in the same
// color. Kept in a non-component file so react-refresh/only-export-components
// doesn't flag PlayerCard.tsx for exporting non-component values.

// Theme-aware position badge classes (see `.pos-badge*` in index.css). The
// old raw Tailwind palette classes (`bg-red-100 text-red-800`, ...) were
// fixed light values and rendered as pale chips with invisible text in dark
// mode.
export const positionColors: Record<Position, string> = {
  QB: 'pos-badge pos-badge-QB',
  RB: 'pos-badge pos-badge-RB',
  WR: 'pos-badge pos-badge-WR',
  TE: 'pos-badge pos-badge-TE',
  K: 'pos-badge pos-badge-K',
  DEF: 'pos-badge pos-badge-DEF',
}

const FALLBACK_POSITION_COLOR = 'pos-badge pos-badge-DEF'

// Same palette as `positionColors`, but tolerant of a loosely-typed `string`
// (rather than the `Position` union) and of unrecognized values -- for call
// sites whose player data isn't narrowed to `Position`.
export function getPositionColor(position: string): string {
  return positionColors[position as Position] || FALLBACK_POSITION_COLOR
}

export const riskColors = {
  LOW: 'text-success-700',
  MEDIUM: 'text-warning-700',
  HIGH: 'text-danger-700',
}

// Semantic injury-status scale, applied by matching keywords rather than an
// exact string so it holds up against the various casings/phrasings the
// backend sends ("Healthy", "HEALTHY", "Questionable", "Out", "IR", ...).
export function injuryStatusClasses(status: string): string {
  const s = status.toUpperCase()
  if (s.includes('OUT') || s === 'IR' || s.includes('INJURED RESERVE') || s.includes('DOUBTFUL') || s.includes('SUSPENDED') || s.includes('PUP')) {
    return 'bg-danger-100 text-danger-800'
  }
  if (s.includes('QUESTIONABLE')) {
    return 'bg-warning-100 text-warning-800'
  }
  return 'bg-success-100 text-success-800'
}

// Compact injury designation (ESPN-style: Q / D / O / IR / SUS / PUP / DTD)
// plus a theme-aware color. Returns null for healthy/active players.
export function injuryTag(status?: string | null): { label: string; className: string } | null {
  if (!status) return null
  const s = status.toUpperCase()
  if (['ACTIVE', 'NORMAL', 'HEALTHY', 'PROBABLE', ''].includes(s)) return null
  const danger = 'bg-danger-100 text-danger-800'
  const warn = 'bg-warning-100 text-warning-800'
  if (s.includes('IR') || s.includes('INJURY_RESERVE') || s.includes('INJURED RESERVE') || s.includes('INJURY RESERVE')) return { label: 'IR', className: danger }
  if (s.includes('OUT')) return { label: 'O', className: danger }
  if (s.includes('DOUBTFUL')) return { label: 'D', className: danger }
  if (s.includes('SUSPEN')) return { label: 'SUS', className: danger }
  if (s.includes('PUP')) return { label: 'PUP', className: danger }
  if (s.includes('QUESTIONABLE')) return { label: 'Q', className: warn }
  if (s.includes('DAY') || s.includes('DTD')) return { label: 'DTD', className: warn }
  return { label: s.slice(0, 3), className: warn }
}

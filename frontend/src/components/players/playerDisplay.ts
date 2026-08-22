import type { Position } from '../../types'

// Shared display helpers for player position/risk/injury badges. Single
// source of truth for position-badge colors -- import from here rather than
// re-declaring a local color map, so every surface (PlayerCard, PlayersPage,
// DraftBoard, TeamRoster, RecommendationCard, WaiverWirePage,
// HistoricalPage, ...) renders the same player's position badge in the same
// color. Kept in a non-component file so react-refresh/only-export-components
// doesn't flag PlayerCard.tsx for exporting non-component values.

export const positionColors: Record<Position, string> = {
  QB: 'bg-red-100 text-red-800',
  RB: 'bg-green-100 text-green-800',
  WR: 'bg-blue-100 text-blue-800',
  TE: 'bg-yellow-100 text-yellow-800',
  K: 'bg-purple-100 text-purple-800',
  DEF: 'bg-gray-100 text-gray-800',
}

const FALLBACK_POSITION_COLOR = 'bg-gray-100 text-gray-800'

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

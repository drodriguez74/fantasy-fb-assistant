// Badge colors and labels shared by the League Detail tabs.
import type { StartSitCall } from './types'

export const getGradeColor = (grade: string) => {
  switch (grade) {
    case 'A': return 'bg-success-100 text-success-800'
    case 'B': return 'bg-highlight text-accent-ink'
    case 'C': return 'bg-warning-100 text-warning-800'
    case 'D': return 'bg-warning-200 text-warning-900'
    case 'F': return 'bg-danger-100 text-danger-800'
    default: return 'bg-surface-2 text-body'
  }
}

// Standings points_for/points_against come from whichever platform is
// connected -- ESPN gives clean numbers, but Yahoo's raw JSON floats
// (e.g. summed weekly scores) can carry IEEE754 drift like
// 274.54999999999995. Round for display rather than showing that
// straight through; a plain string (Yahoo also sometimes sends
// points_for as "458.55") is parsed first.
export const formatPoints = (value?: number | string) => {
  if (value == null) return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}

// Real per-player status straight from the connected platform (ESPN's
// injuryStatus) -- "Out"/"Injury Reserve" etc. are genuine alerts worth
// surfacing; a merely active/normal player is not.
export const formatStatusLabel = (status?: string) =>
  (status || '').replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())

export const getStatusColor = (status?: string) => {
  const s = (status || '').toUpperCase()
  if (s === 'OUT' || s === 'INJURY_RESERVE' || s === 'IR' || s === 'SUSPENDED') return 'bg-danger-100 text-danger-800'
  if (s === 'DOUBTFUL') return 'bg-danger-50 text-danger-700'
  if (s === 'QUESTIONABLE') return 'bg-warning-100 text-warning-800'
  return 'bg-surface-2 text-body'
}

export const POSITION_COLORS: Record<string, string> = {
  QB: 'bg-ink-800 text-white',
  RB: 'bg-success-100 text-success-800',
  WR: 'bg-highlight text-accent-ink',
  TE: 'bg-warning-100 text-warning-800',
  K: 'bg-surface-2 text-body',
  // Was bg-ink-200 (a fixed light gray) + text-body (which flips to a
  // light color in dark mode) -- light bg + light text, invisible in
  // dark mode. bg-surface-2/text-body is the same theme-safe pairing K
  // already uses above.
  DEF: 'bg-surface-2 text-body',
  'D/ST': 'bg-surface-2 text-body',
}
export const getPositionColor = (position?: string) => POSITION_COLORS[position || ''] || 'bg-surface-2 text-body'

// Start/sit + swap confidence tiers -- both share a color language since
// they're the same two real signals (projection margin, live injury
// status) read at different points in the lineup. 'locked' (no bench
// alternative exists at that slot) is intentionally unstyled below --
// there's no real decision to flag confidence on.
export const CONFIDENCE_STYLE: Record<string, { label: string; cls: string }> = {
  comfortable: { label: 'Confident start', cls: 'bg-success-100 text-success-800' },
  strong: { label: 'Strong upgrade', cls: 'bg-success-100 text-success-800' },
  moderate: { label: 'Likely start', cls: 'bg-highlight text-accent-ink' },
  toss_up: { label: 'Toss-up', cls: 'bg-warning-100 text-warning-800' },
  lean: { label: 'Lean upgrade', cls: 'bg-warning-100 text-warning-800' },
  risky: { label: 'Injury risk', cls: 'bg-danger-100 text-danger-800' },
}
export const confidenceBadge = (tier?: string) => {
  if (!tier || tier === 'locked') return null
  const s = CONFIDENCE_STYLE[tier]
  if (!s) return null
  return (
    <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${s.cls}`}>{s.label}</span>
  )
}
// Row-level start/sit badge is deliberately quieter than the swap-card
// one above: 'comfortable' is the default state for most healthy
// starters with a real margin, so badging every single one is noise, not
// signal. Only surface the tiers that actually call for a look, and
// explain the real number behind the badge on hover rather than making
// the reader trust a label alone.
export const startSitBadge = (call?: StartSitCall) => {
  if (!call || call.tier === 'locked' || call.tier === 'comfortable') return null
  const s = CONFIDENCE_STYLE[call.tier]
  if (!s) return null
  const title =
    call.tier === 'risky'
      ? 'Live injury designation for a game not yet played -- the projection alone doesn’t capture that risk.'
      : call.margin != null
        ? `${call.margin > 0 ? '+' : ''}${call.margin.toFixed(1)} pt projected edge over ${call.best_bench_alternative ?? 'the best bench option'} at this slot.`
        : undefined
  return (
    <span title={title} className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${s.cls} cursor-help`}>
      {s.label}
    </span>
  )
}

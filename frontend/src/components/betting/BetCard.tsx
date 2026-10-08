// One priced line on the Bets page: a bet (units), a watch-list play, or a
// line we priced but wouldn't bet. Collapsed it's two lines -- the pick, then
// price, book and kickoff -- with the win chance as the one big number; a tap
// opens the evidence (edge, price floor, books vs projections) and the alert.
// Volt is reserved for real bets, so a bet never looks like a no-bet.
import { useState } from 'react'
import { ChevronDownIcon } from '@heroicons/react/24/outline'
import { type BoardRow, type WatchAlert, dollars, kickoffLabel, odds, pct, sideSpread, signedPct } from './betTypes'

const whole = (p: number) => `${Math.round(p * 100)}%`

function SizeChip({ row, bankroll }: { row: BoardRow; bankroll: number | null }) {
  const money = dollars(row.units, bankroll)
  if (row.units > 0) {
    // Real bet: solid volt. "Best available" fill: outlined -- on the card, but not a measured edge.
    const look = row.card_fill ? 'border border-volt text-body' : 'bg-volt text-volt-ink'
    return (
      <div className={`w-14 shrink-0 rounded-md px-1 py-1.5 text-center ${look}`}>
        <div className="stat-nums text-base font-bold leading-none">{row.units}u</div>
        <div className="stat-nums text-xs mt-1 leading-none">{money ?? (row.card_fill ? 'fill' : '')}</div>
      </div>
    )
  }
  return (
    <div className="w-14 shrink-0 rounded-md border border-hairline px-1 py-2 text-center text-muted">
      <div className="stat-nums text-xs uppercase tracking-wide">{row.watch ? 'Watch' : 'Pass'}</div>
    </div>
  )
}

function pickText(row: BoardRow): string {
  if (row.market === 'player_anytime_td') return 'Anytime TD'
  // A spread's line is already from the bet side's point of view.
  if (row.market === 'spread' && row.line != null) return `${row.side} ${row.line > 0 ? `+${row.line}` : row.line === 0 ? 'PK' : row.line}`
  return `${row.side} ${row.line ?? ''}`
}

// Where the number comes from: the books' fair chance and each projection.
function sources(row: BoardRow): string[] {
  if (row.type === 'player_prop') {
    const parts = [`Books ${pct(row.market_prob)}`]
    if (row.projection != null) parts.push(`Sleeper ${row.projection.toFixed(1)}`)
    if (row.espn_projection != null) parts.push(`ESPN ${row.espn_projection.toFixed(1)}`)
    if (row.market_line != null && row.market_line !== row.line) parts.push(`books' main line ${row.market_line}`)
    if (row.prizepicks_line != null) parts.push(`PrizePicks ${row.prizepicks_line}`)
    return parts
  }
  if (row.market === 'spread') {
    const parts = [`Books ${row.side} ${sideSpread(row, row.consensus_line)}`]
    if (row.model_line != null) parts.push(`our model ${row.side} ${sideSpread(row, row.model_line)}`)
    if (row.check_line != null) parts.push(`ESPN ${row.side} ${sideSpread(row, row.check_line)}`)
    if (row.p_push > 0.005) parts.push(`${pct(row.p_push)} push`)
    return parts
  }
  const parts = [`Books' total ${row.consensus_line}`]
  if (row.model_line != null) parts.push(`our model ${row.model_line}`)
  if (row.check_line != null) parts.push(`ESPN ${row.check_line}`)
  if (row.p_push > 0.005) parts.push(`${pct(row.p_push)} push`)
  return parts
}

export function BetCard({
  row,
  bankroll,
  alert,
  onToggleAlert,
}: {
  row: BoardRow
  bankroll: number | null
  // The user's alert on this pick, if any (watch-list lines only).
  alert?: WatchAlert
  onToggleAlert?: (row: BoardRow) => void
}) {
  const [open, setOpen] = useState(false)
  const isBet = row.units > 0
  const title = row.type === 'player_prop' ? row.player : row.game
  const what =
    row.type === 'player_prop'
      ? row.market === 'player_anytime_td'
        ? ''
        : row.market_label.toLowerCase()
      : row.market_label.toLowerCase()
  const when = kickoffLabel(row.kickoff)
  // The one warning that changes whether to act stays visible collapsed.
  const warning = row.projection_outlier
    ? "Don't play: the projection is far from the line, which usually means stale news, not a mistake by the books."
    : row.espn_agrees === false
      ? "ESPN doesn't back this side, so no units."
      : null
  const canAlert = (row.watch || row.card_fill) && onToggleAlert

  return (
    <div className={`rounded-lg bg-surface border border-hairline ${row.projection_outlier ? 'opacity-60' : ''}`}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 p-3 text-left"
      >
        <SizeChip row={row} bankroll={bankroll} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-body truncate">
            <span className="font-medium">{title}</span>{' '}
            <span className="font-semibold">{pickText(row)}</span> <span className="text-muted">{what}</span>
          </p>
          <p className="stat-nums text-xs text-muted truncate mt-0.5">
            {odds(row.price)} at {row.book}
            {row.type === 'player_prop' ? ` · ${row.game}` : ''}
            {when && ` · ${when}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className={`stat-nums text-xl font-bold leading-none ${isBet || row.watch ? 'text-body' : 'text-muted'}`}>
            {whole(row.p_win)}
          </div>
          <div className="text-xs text-faint mt-1">to win</div>
        </div>
        <ChevronDownIcon className={`h-4 w-4 shrink-0 text-faint transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      {warning && <p className="px-3 -mt-1 pb-2 text-xs text-warning-700">{warning}</p>}
      {open && (
        <div className="border-t border-hairline px-3 py-3 space-y-2 text-xs">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 stat-nums">
            <span className={row.ev > 0 ? 'text-success-700' : 'text-muted'} title="Expected profit per $1 bet">
              Edge {signedPct(row.ev)}
            </span>
            <span className="text-muted">Win chance {pct(row.p_win)}</span>
            {isBet && !row.card_fill && row.min_price != null && (
              <span className="text-muted">Good down to {odds(row.min_price)}</span>
            )}
            {(row.watch || row.card_fill) && row.bet_at != null && (
              <span className="text-muted">Bet if it reaches {odds(row.bet_at)}</span>
            )}
            {isBet && (
              <span className="text-muted">
                {row.units}u{dollars(row.units, bankroll) ? ` · ${dollars(row.units, bankroll)}` : ''}
                {row.card_fill ? ' · Best available, not a measured edge' : ''}
              </span>
            )}
          </div>
          <p className="stat-nums text-muted">{sources(row).join(' · ')}</p>
          {row.espn_confirms === false && row.espn_agrees && (
            <p className="text-muted">
              No units: ESPN leans this way too, but its projection doesn't show an edge on its own. A bet needs both.
            </p>
          )}
          {canAlert && (
            <button
              onClick={() => onToggleAlert(row)}
              className={`text-xs rounded-md px-2 py-1 border ${
                alert?.status === 'triggered' ? 'border-success-700 text-success-700' : alert ? 'border-volt text-body' : 'border-hairline text-body hover:border-volt'
              }`}
              aria-pressed={Boolean(alert)}
            >
              {alert?.status === 'triggered' ? 'Alert sent' : alert ? 'Alert on · cancel' : 'Alert me if it becomes a bet'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

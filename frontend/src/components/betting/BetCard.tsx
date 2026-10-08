// One priced line on the Bets page: a bet (units), a watch-list play, or a
// line we priced but wouldn't bet. Tiers are visually distinct so a bet
// never looks like a no-bet.
import { type BoardRow, type WatchAlert, SIZE_LABEL, dollars, kickoffLabel, odds, pct, sideSpread, signedPct } from './betTypes'

function SizeBadge({ row, bankroll }: { row: BoardRow; bankroll: number | null }) {
  if (row.card_fill) {
    // Best available: on the card, but not a measured edge -- outlined, not solid.
    return (
      <div className="w-[68px] shrink-0 rounded-md border border-volt text-body px-2 py-1.5 text-center">
        <div className="stat-nums text-lg font-bold leading-none">{row.units}u</div>
        <div className="stat-nums text-[9px] tracking-wider uppercase mt-1 text-muted">{SIZE_LABEL[row.confidence]}</div>
        {dollars(row.units, bankroll) && <div className="stat-nums text-[10px] mt-0.5">{dollars(row.units, bankroll)}</div>}
      </div>
    )
  }
  if (row.units > 0) {
    return (
      <div className="w-[68px] shrink-0 rounded-md bg-volt text-volt-ink px-2 py-1.5 text-center">
        <div className="stat-nums text-lg font-bold leading-none">{row.units}u</div>
        <div className="stat-nums text-[9px] tracking-wider uppercase mt-1">{SIZE_LABEL[row.confidence]}</div>
        {dollars(row.units, bankroll) && <div className="stat-nums text-[10px] mt-0.5">{dollars(row.units, bankroll)}</div>}
      </div>
    )
  }
  if (row.watch) {
    return (
      <div className="w-[68px] shrink-0 rounded-md border border-accent-ink text-accent-ink px-2 py-2 text-center">
        <div className="stat-nums text-[10px] tracking-wider uppercase">Watch</div>
      </div>
    )
  }
  return (
    <div className="w-[68px] shrink-0 rounded-md bg-surface-2 text-faint px-2 py-2 text-center">
      <div className="stat-nums text-[10px] tracking-wider uppercase">No bet</div>
    </div>
  )
}

function pickText(row: BoardRow): string {
  if (row.market === 'player_anytime_td') return 'Anytime TD'
  // A spread's line is already from the bet side's point of view.
  if (row.market === 'spread' && row.line != null) return `${row.side} ${row.line > 0 ? `+${row.line}` : row.line === 0 ? 'PK' : row.line}`
  return `${row.side} ${row.line ?? ''}`
}

function details(row: BoardRow): string {
  if (row.type === 'player_prop') {
    const parts = [`Books ${pct(row.market_prob)}`]
    if (row.projection != null) parts.push(`Sleeper projects ${row.projection.toFixed(1)}`)
    if (row.espn_projection != null) parts.push(`ESPN ${row.espn_projection.toFixed(1)}`)
    if (row.market_line != null && row.market_line !== row.line) parts.push(`books' main line ${row.market_line}`)
    if (row.prizepicks_line != null) parts.push(`PrizePicks ${row.prizepicks_line}`)
    return parts.join(' · ')
  }
  if (row.market === 'spread') {
    const parts = [`Books: ${row.side} ${sideSpread(row, row.consensus_line)}`]
    if (row.model_line != null) parts.push(`we project ${row.side} ${sideSpread(row, row.model_line)}`)
    if (row.check_line != null) parts.push(`ESPN ${row.side} ${sideSpread(row, row.check_line)}`)
    if (row.p_push > 0.005) parts.push(`${pct(row.p_push)} push`)
    return parts.join(' · ')
  }
  const parts = [`Books' total ${row.consensus_line}`]
  if (row.model_line != null) parts.push(`we project ${row.model_line}`)
  if (row.check_line != null) parts.push(`ESPN ${row.check_line}`)
  if (row.p_push > 0.005) parts.push(`${pct(row.p_push)} push`)
  return parts.join(' · ')
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
  const isBet = row.units > 0
  const title = row.type === 'player_prop' ? row.player : row.game
  const when = kickoffLabel(row.kickoff)
  return (
    <div
      className={`rounded-lg p-4 bg-surface border ${
        isBet ? 'border-volt' : 'border-hairline'
      } ${row.projection_outlier ? 'opacity-50' : !isBet && !row.watch ? 'opacity-80' : ''}`}
    >
      <div className="flex items-start gap-3">
        <SizeBadge row={row} bankroll={bankroll} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <h4 className="font-medium text-body">{title}</h4>
            <span className="stat-nums text-[11px] text-faint">
              {row.type === 'player_prop' ? `${row.game}${when ? ` · ${when}` : ''}` : `${row.market_label}${when ? ` · ${when}` : ''}`}
            </span>
          </div>
          <p className="text-sm text-body mt-0.5">
            {row.type === 'player_prop' && row.market !== 'player_anytime_td' && (
              <span className="text-muted">{row.market_label}: </span>
            )}
            <span className="font-semibold">{pickText(row)}</span>{' '}
            <span className="stat-nums">{odds(row.price)}</span>
            <span className="text-muted"> at {row.book}</span>
          </p>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="stat-nums text-sm text-body">
              <span className="font-semibold">{pct(row.p_win)}</span> <span className="text-muted text-xs">to win</span>
            </span>
            <span className={`stat-nums text-xs ${row.ev > 0 ? 'text-success-700' : 'text-muted'}`}>EV {signedPct(row.ev)}</span>
            {isBet && row.min_price != null && (
              <span className="stat-nums text-xs text-muted">Still a bet at {odds(row.min_price)} or better</span>
            )}
            {(row.watch || row.card_fill) && row.bet_at != null && (
              <span className="stat-nums text-xs text-muted">Becomes a bet at {odds(row.bet_at)} or better</span>
            )}
            {(row.watch || row.card_fill) && onToggleAlert && (
              <button
                onClick={() => onToggleAlert(row)}
                className={`ml-auto text-xs rounded-md px-2 py-0.5 border ${
                  alert?.status === 'triggered'
                    ? 'border-success-700 text-success-700'
                    : alert
                      ? 'border-volt text-body'
                      : 'border-hairline text-accent-ink hover:border-volt'
                }`}
                aria-pressed={Boolean(alert)}
              >
                {alert?.status === 'triggered' ? 'Alert sent' : alert ? 'Alert on · cancel' : 'Alert me'}
              </button>
            )}
          </div>
          <p className="stat-nums text-[11px] text-faint mt-1.5">{details(row)}</p>
          {row.espn_agrees === false && !row.projection_outlier && (
            <p className="text-[11px] text-warning-700 mt-1">
              ESPN's projection doesn't back this side, so no units. When the two sources split, the edge is usually noise.
            </p>
          )}
          {row.projection_outlier && (
            <p className="text-[11px] text-warning-700 mt-1">
              Don't play this one: the projection is far from the market line, which almost always means the projection is
              stale (role change, injury news), not that the books are wrong.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

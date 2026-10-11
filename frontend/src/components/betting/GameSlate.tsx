// Every game on the board, one card each: the projected score, the spread
// and the total, and a verdict (Bet / Watch / Pass) for the best price at the user's book. Built
// from GET /betting/board's game_props (one row per game per market: the
// best-priced side, see betting_service.evaluate_game).
//
// The projection is the books' consensus: NFL game lines are market-only
// (GAME_MODEL_WEIGHT = 0) and ESPN's college predictor added nothing to the
// line over 2025, so Sleeper's and ESPN's numbers are shown for reference
// only. A Bet means Hard Rock's price beats the market. The A-F tiers stay
// internal (sorting, filters); the founder prefers words over letters on screen.
//
// Volt is reserved for real bets (as on BetCard): only A/B chips and a game
// holding a bet use it. A pass still names the better side, but quietly, so
// it never reads as a pick.
import { useState } from 'react'
import { type BoardRow, type WatchAlert, kickoffLabel, odds, signedPct } from './betTypes'
import { MY_BOOK } from './BetCard'

type Grade = 'A' | 'B' | 'C' | 'D' | 'F'

// -110 on a true coin flip is -4.5% EV: anything worse is a bad price, not just no edge.
const BAD_PRICE_EV = -0.05

function gradeOf(row: BoardRow): Grade {
  if (row.units > 0 && !row.card_fill) return row.units >= 1.5 ? 'A' : 'B'
  if (row.watch || row.card_fill) return 'C'
  return row.ev >= BAD_PRICE_EV ? 'D' : 'F'
}

const GRADE_TEXT: Record<Grade, string> = { A: 'Bet', B: 'Bet', C: 'Watch', D: 'Pass', F: 'Pass' }

const GRADE_LONG: Record<Grade, string> = {
  A: 'bet, medium or max size',
  B: 'bet, small size',
  C: 'watch: a small edge, not enough for units',
  D: 'pass: a fair price, no edge',
  F: "pass: Hard Rock's price is poor",
}

const GRADE_LOOK: Record<Grade, string> = {
  A: 'bg-volt text-volt-ink',
  B: 'bg-volt text-volt-ink',
  C: 'border border-line text-body',
  D: 'border border-hairline text-muted',
  F: 'border border-hairline text-faint',
}

const RANK: Record<Grade, number> = { A: 0, B: 1, C: 2, D: 3, F: 4 }
const isAction = (g: Grade) => RANK[g] <= RANK.C

const signed = (v: number) => (v === 0 ? 'PK' : v > 0 ? `+${v}` : `${v}`)
const one = (v: number) => (Math.round(v * 10) / 10).toFixed(1)

function GradeChip({
  grade,
  fill,
  units,
  started,
}: {
  grade: Grade
  fill?: boolean
  units?: number
  started: boolean
}) {
  if (started) {
    return (
      <div
        className="w-14 shrink-0 rounded-md border border-hairline px-1 py-1.5 text-center text-faint"
        aria-label="Started: line closed"
      >
        <div className="text-sm font-bold leading-none">Closed</div>
      </div>
    )
  }
  return (
    <div
      className={`w-14 shrink-0 rounded-md px-1 py-1.5 text-center ${GRADE_LOOK[grade]}`}
      aria-label={fill ? 'Best available fill' : GRADE_LONG[grade]}
      title={GRADE_LONG[grade]}
    >
      <div className="text-sm font-bold leading-none">{fill ? 'Fill' : GRADE_TEXT[grade]}</div>
      {units != null && units > 0 && <div className="stat-nums text-xs mt-1 leading-none">{units}u</div>}
    </div>
  )
}

/** "SEA −3" from the home spread (negative = home favored). */
function favoriteText(home: string, away: string, homeSpread: number): string {
  if (homeSpread === 0) return 'PK'
  return homeSpread < 0 ? `${home} ${homeSpread}` : `${away} ${-homeSpread}`
}

function Market({
  row,
  started,
  alert,
  onToggleAlert,
}: {
  row: BoardRow
  started: boolean
  alert?: WatchAlert
  onToggleAlert?: (row: BoardRow) => void
}) {
  const grade = gradeOf(row)
  const home = row.home ?? ''
  const away = row.away ?? ''
  const isSpread = row.market === 'spread'
  const pick = isSpread && row.line != null ? `${row.side} ${signed(row.line)}` : `${row.side} ${row.line ?? ''}`
  const market =
    row.consensus_line == null ? '—' : isSpread ? favoriteText(home, away, row.consensus_line) : `${row.consensus_line}`
  const refs: string[] = []
  if (row.model_line != null)
    refs.push(`Sleeper ${isSpread ? favoriteText(home, away, row.model_line) : row.model_line}`)
  if (row.check_line != null) refs.push(`ESPN ${isSpread ? favoriteText(home, away, row.check_line) : row.check_line}`)
  const acting = !started && isAction(grade)
  const canAlert = !started && (row.watch || row.card_fill) && onToggleAlert

  return (
    <div className="flex items-start gap-3 py-2.5">
      <GradeChip grade={grade} fill={row.card_fill} units={row.units} started={started} />
      <div className="min-w-0 flex-1">
        <p className="text-sm break-words">
          <span className="text-muted">{row.market_label}</span>{' '}
          <span className="stat-nums font-medium text-body">{market}</span>
        </p>
        <p className="text-sm break-words mt-0.5">
          <span className="text-muted">{acting ? 'Take ' : 'Better side '}</span>
          <span className={acting ? 'font-semibold text-body' : 'text-muted'}>{pick}</span>{' '}
          <span className="stat-nums text-muted">
            {odds(row.price)}
            {row.book !== MY_BOOK && ` at ${row.book}`}
          </span>
        </p>
        <p className="stat-nums text-xs text-muted break-words mt-0.5">
          {Math.round(row.p_win * 100)}% to win · edge {signedPct(row.ev)}
          {!started && grade === 'F' && ` · poor price at ${MY_BOOK}`}
          {row.watch && row.bet_at != null && ` · bet at ${odds(row.bet_at)}`}
          {isSpread && row.p_push > 0.005 && ` · ${Math.round(row.p_push * 100)}% push`}
        </p>
        {refs.length > 0 && <p className="stat-nums text-xs text-faint break-words mt-0.5">{refs.join(' · ')}</p>}
        {canAlert && (
          <button
            onClick={() => onToggleAlert(row)}
            className={`mt-1.5 text-xs rounded-md px-2 py-1 border ${
              alert?.status === 'triggered'
                ? 'border-success-700 text-success-700'
                : alert
                  ? 'border-volt text-body'
                  : 'border-hairline text-body hover:border-volt'
            }`}
            aria-pressed={Boolean(alert)}
          >
            {alert?.status === 'triggered'
              ? 'Alert sent'
              : alert
                ? 'Alert on · cancel'
                : 'Alert me if it becomes a bet'}
          </button>
        )}
      </div>
    </div>
  )
}

interface Game {
  game: string
  kickoff?: string
  home: string
  away: string
  spread?: BoardRow
  total?: BoardRow
}

function groupGames(rows: BoardRow[]): Game[] {
  const games = new Map<string, Game>()
  for (const row of rows) {
    const g = games.get(row.game) ?? {
      game: row.game,
      kickoff: row.kickoff,
      home: row.home ?? '',
      away: row.away ?? '',
    }
    if (row.market === 'spread') g.spread = row
    else if (row.market === 'total') g.total = row
    games.set(row.game, g)
  }
  return [...games.values()]
}

const hasStarted = (g: Game, now: number) => g.kickoff != null && new Date(g.kickoff).getTime() <= now
const marketsOf = (g: Game) => [g.spread, g.total].filter((r): r is BoardRow => r != null)

/** The books' projected score: home = (total - home spread) / 2. Favorite first. */
function projectedScore(g: Game): [string, string, string, string] | null {
  const spread = g.spread?.consensus_line
  const total = g.total?.consensus_line
  if (spread == null || total == null) return null
  const home = (total - spread) / 2
  const away = (total + spread) / 2
  return home >= away ? [g.home, one(home), g.away, one(away)] : [g.away, one(away), g.home, one(home)]
}

export function GameSlate({
  rows,
  alertFor,
  onToggleAlert,
}: {
  rows: BoardRow[]
  alertFor?: (row: BoardRow) => WatchAlert | undefined
  onToggleAlert?: (row: BoardRow) => void
}) {
  const [onlyAction, setOnlyAction] = useState(false)
  const now = Date.now()
  // Upcoming games by kickoff; games already under way sink to the bottom (their lines are closed).
  const all = groupGames(rows).sort(
    (a, b) =>
      Number(hasStarted(a, now)) - Number(hasStarted(b, now)) ||
      (a.kickoff ?? '').localeCompare(b.kickoff ?? '') ||
      a.game.localeCompare(b.game),
  )
  if (all.length === 0) return null
  const upcoming = all.filter((g) => !hasStarted(g, now))
  const actionGames = upcoming.filter((g) => marketsOf(g).some((r) => isAction(gradeOf(r))))
  const bets = upcoming.flatMap(marketsOf).filter((r) => RANK[gradeOf(r)] <= RANK.B).length
  const games = onlyAction ? actionGames : all

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-body">
          <span className="stat-nums font-medium">{upcoming.length}</span> upcoming ·{' '}
          {bets === 0 ? (
            <span className="text-muted">no game line is a bet right now</span>
          ) : (
            <span className="font-medium">
              {bets} {bets === 1 ? 'bet' : 'bets'}
            </span>
          )}
        </p>
        <div className="flex rounded-lg border border-hairline p-0.5 text-xs" role="tablist" aria-label="Which games">
          {(
            [
              [false, `All (${all.length})`],
              [true, `Bets & watch (${actionGames.length})`],
            ] as const
          ).map(([v, text]) => (
            <button
              key={text}
              role="tab"
              aria-selected={onlyAction === v}
              onClick={() => setOnlyAction(v)}
              className={`px-2.5 py-1 rounded-md ${onlyAction === v ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
            >
              {text}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-muted leading-relaxed">
        Projected score is the books' consensus; Sleeper and ESPN are shown for reference (neither has beaten the
        market). Bet / Watch / Pass is for the better side at {MY_BOOK}.
      </p>
      {games.length === 0 && (
        <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
          No game line is a bet or on the watch list right now.
        </div>
      )}
      {games.map((g) => {
        const started = hasStarted(g, now)
        const score = projectedScore(g)
        const holdsBet = !started && marketsOf(g).some((r) => RANK[gradeOf(r)] <= RANK.B)
        return (
          <div
            key={g.game}
            className={`rounded-lg bg-surface border px-3 pt-3 pb-1 ${holdsBet ? 'border-volt' : 'border-hairline'} ${
              started ? 'opacity-60' : ''
            }`}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="font-medium text-body">{g.game}</span>
              <span className="stat-nums text-xs text-faint">{started ? 'Started' : kickoffLabel(g.kickoff)}</span>
            </div>
            {score && (
              <p className="stat-nums text-sm mt-1">
                <span className="text-xs text-muted">Projected </span>
                <span className="text-body font-semibold">
                  {score[0]} {score[1]}
                </span>
                <span className="text-muted">
                  {' '}
                  – {score[2]} {score[3]}
                </span>
              </p>
            )}
            <div className="divide-y divide-hairline">
              {marketsOf(g).map((row) => (
                <Market
                  key={row.market}
                  row={row}
                  started={started}
                  alert={alertFor?.(row)}
                  onToggleAlert={onToggleAlert}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

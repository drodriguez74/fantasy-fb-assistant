// Picks made on radio shows and podcasts, from GET /betting/analyst-picks
// (backend/app/services/analyst_picks.py). Tracked, never priced.
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import { type BoardRow, odds, pct } from './betTypes'

export interface ShowRecord {
  picks: number
  won: number
  lost: number
  push: number
  pending: number
  hit_rate: number | null
  units: number
  roi: number | null
}

export interface ShowPickSnapshot {
  board_line: string
  board_price: number | null
  board_game: string | null
  kickoff: string | null
  our_prob: number | null
  books_prob: number | null
  ev: number | null
  units: number
  // true: our model gives this side more than the books do; null: market-only line.
  agrees: boolean | null
  // The board's line minus the show's, in the show's favor (+ = the show's number is better).
  line_value: number | null
  far_line: boolean
}

export interface ShowPick {
  id: number
  source: string
  network: string | null
  sport: 'nfl' | 'cfb'
  analyst: string
  segment: string | null
  aired_on: string
  season: number
  week: number
  player: string
  team: string | null
  game: string | null
  kickoff: string | null
  market: string
  market_label: string
  side: 'More' | 'Less'
  line: number
  line_stated: boolean
  price: number | null
  conviction: 'bet' | 'lean'
  quote: string | null
  snapshot: ShowPickSnapshot | null
  status: 'pending' | 'won' | 'lost' | 'push' | 'void'
  actual: number | null
}

export interface Show {
  source: string
  network: string | null
  sports: ('nfl' | 'cfb')[]
  episodes: string[]
  record: ShowRecord
  leans: ShowRecord
  analysts: (ShowRecord & { analyst: string })[]
  vs_board: { agreed: ShowRecord; disagreed: ShowRecord }
  line_moves: { picks: number; toward: number; away: number; unchanged: number }
  picks: ShowPick[]
}

export function useShowPicks() {
  const [shows, setShows] = useState<Show[] | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try {
      const res = await betting.getAnalystPicks()
      setShows(res.data.shows)
      setError('')
    } catch (e) {
      setError(getErrorMessage(e, "Couldn't load the show picks."))
    }
  }, [])
  useEffect(() => {
    load()
  }, [load])
  return { shows, error, reload: load }
}

const overUnder = (p: ShowPick) => (p.side === 'More' ? 'Over' : 'Under')

/** The pick the way a bettor says it: "PIT -2.5", "LV +3.5", "Tyler Warren Under 51.5 receiving yards". */
export function showPickText(p: ShowPick): string {
  let text: string
  if (p.market === 'team_spread') {
    // More L on a team's margin = that team -L.
    const n = p.side === 'More' ? -p.line : p.line
    text = `${p.player} ${n === 0 ? 'PK' : n > 0 ? `+${n}` : n}`
  } else if (p.market === 'game_total') {
    text = `${p.player} ${overUnder(p)} ${p.line}`
  } else if (p.market === 'team_win') {
    text = `${p.player} ${p.side === 'More' ? 'to win' : 'to lose'}`
  } else if (p.market === 'player_anytime_td') {
    text = `${p.player} anytime TD`
  } else {
    text = `${p.player} ${overUnder(p)} ${p.line} ${p.market_label.toLowerCase()}`
  }
  return p.price != null ? `${text} (${odds(p.price)})` : text
}

const sameTime = (a?: string | null, b?: string | null) => Boolean(a && b) && new Date(a!).getTime() === new Date(b!).getTime()
const nameKey = (s?: string | null) => (s ?? '').toLowerCase().replace(/[^a-z]/g, '')

/** Show picks on the same game and line as a board row (for the "On air" note). */
export function onAirFor(row: BoardRow, shows: Show[] | null): ShowPick[] {
  if (!shows) return []
  return shows.flatMap((s) =>
    s.picks.filter((p) => {
      if (!sameTime(p.kickoff, row.kickoff)) return false
      if (row.type === 'player_prop') return p.market === row.market && nameKey(p.player) === nameKey(row.player)
      const teams = [row.home, row.away]
      if (row.market === 'spread') return p.market === 'team_spread' && teams.includes(p.player)
      return row.market === 'total' && p.market === 'game_total' && teams.includes(p.team ?? '')
    }),
  )
}


// ---- "Should I tail it?" -------------------------------------------------
// Each pending pick is checked against the live board (falling back to the
// snapshot taken at import) and phrased from the show's side of the bet.
// Order of the rules matters: the first that applies is the verdict.

export type VerdictKey = 'tail' | 'fade' | 'lean' | 'pass' | 'unknown' | 'started' | 'won' | 'lost' | 'push'

export interface Verdict {
  key: VerdictKey
  label: string
  reason: string
  // Our chance for the show's side (big number), when we can price it.
  ours: number | null
  // How today's line compares with the show's (stated lines only).
  lineNote: string | null
}

// Upcoming picks sort by what to do about them.
export const VERDICT_ORDER: VerdictKey[] = ['tail', 'fade', 'lean', 'pass', 'unknown', 'started', 'won', 'lost', 'push']

const NO_LEAN = 0.002 // our chance within this of the books' = the market's own price
const FAR_LINE = 0.15 // a prop line this far (share of the line) from ours isn't the same bet

function signed(n: number) {
  return n === 0 ? 'PK' : n > 0 ? `+${n}` : `${n}`
}

/** The board row for a show pick: same game (kickoff) and the same market. */
export function liveRowFor(p: ShowPick, rows: BoardRow[]): BoardRow | undefined {
  return rows.find((r) => {
    if (!sameTime(p.kickoff, r.kickoff)) return false
    if (p.market === 'team_spread') return r.market === 'spread' && [r.home, r.away].includes(p.player)
    if (p.market === 'game_total') return r.market === 'total' && [r.home, r.away].includes(p.team ?? '')
    return r.type === 'player_prop' && r.market === p.market && nameKey(r.player) === nameKey(p.player)
  })
}

/** The live row restated on the show's side: same side?, today's line in the show's terms, chances. */
function onShowSide(p: ShowPick, r: BoardRow) {
  const more = p.side === 'More'
  let same: boolean
  let line: number | null
  if (p.market === 'team_spread') {
    const mine = r.side === p.player
    same = mine === more
    // The board's "T +h" is More -h on T's margin.
    line = r.line == null ? null : mine ? -r.line : r.line
  } else {
    same = (r.side === 'Over' || r.side === 'Yes') === more
    line = r.line
  }
  const push = r.p_push ?? 0
  const ours = same ? r.p_win : Math.max(0, 1 - r.p_win - push)
  const books = r.market_prob == null ? null : same ? r.market_prob : Math.max(0, 1 - r.market_prob - push)
  let text: string
  if (p.market === 'team_spread') text = line == null ? p.player : `${p.player} ${signed(more ? -line : line)}`
  else if (p.market === 'player_anytime_td') text = `${p.player} anytime TD`
  else text = `${more ? 'Over' : 'Under'} ${line}`
  return { same, line, ours, books, text: same ? `${text} (${odds(r.price)})` : text }
}

export function verdictFor(p: ShowPick, rows: BoardRow[], now = Date.now()): Verdict {
  const base = { ours: null, lineNote: null }
  if (p.status === 'won') return { ...base, key: 'won', label: 'Won', reason: p.actual != null ? `Final: ${p.actual}` : 'Final' }
  if (p.status === 'lost') return { ...base, key: 'lost', label: 'Lost', reason: p.actual != null ? `Final: ${p.actual}` : 'Final' }
  if (p.status === 'push' || p.status === 'void')
    return { ...base, key: 'push', label: p.status === 'push' ? 'Push' : 'Void', reason: p.status === 'void' ? "Didn't play: no action." : 'Landed on the line.' }
  if (p.kickoff && new Date(p.kickoff).getTime() <= now)
    return { ...base, key: 'started', label: 'Started', reason: 'Game under way; it grades after the final.' }
  if (p.market === 'team_win')
    return { ...base, key: 'unknown', label: "Can't check", reason: 'No moneyline on our board, so this is their read only.' }

  const r = liveRowFor(p, rows)
  if (r) {
    const v = onShowSide(p, r)
    let lineNote: string | null = null
    if (p.line_stated && v.line != null && v.line !== p.line && p.market !== 'player_anytime_td') {
      const todayBetter = p.side === 'More' ? v.line < p.line : v.line > p.line
      const n = Math.abs(v.line - p.line)
      lineNote = todayBetter
        ? `Today's line is ${n} pt${n === 1 ? '' : 's'} better than theirs.`
        : `They had a better number; today's line is ${n} pt${n === 1 ? '' : 's'} worse.`
    }
    if (p.market.startsWith('player_') && v.line != null && Math.abs(v.line - p.line) > FAR_LINE * Math.max(Math.abs(p.line), 1))
      return { ...base, key: 'unknown', label: "Can't check", reason: `Our board only has ${v.text}, too far from their line to compare.` }
    if (v.same && r.units > 0)
      return {
        key: 'tail', label: `Tail · ${r.units}u`, ours: v.ours, lineNote,
        reason: `On our card: ${v.text} at ${r.book}.${r.min_price != null ? ` Good down to ${odds(r.min_price)}.` : ''}`,
      }
    if (!v.same && r.units > 0)
      return {
        key: 'fade', label: `Fade · ${r.units}u`, ours: v.ours, lineNote,
        reason: `We bet the other side: ${r.side} ${r.market === 'spread' && r.line != null ? signed(r.line) : r.line ?? ''} (${odds(r.price)}), ${r.units}u on our card.`,
      }
    if (v.books != null && v.ours - v.books >= NO_LEAN)
      return {
        key: 'lean', label: 'Lean', ours: v.ours, lineNote,
        reason: `Our model agrees (${pct(v.ours)} vs books ${pct(v.books)}) but the edge is under the bar.${
          v.same && r.bet_at != null ? ` It's a bet at ${odds(r.bet_at)} or better.` : ''
        }`,
      }
    if (v.books == null || Math.abs(v.ours - v.books) < NO_LEAN)
      return { key: 'pass', label: 'Pass', ours: v.ours, lineNote, reason: `Priced at the market (${v.text}): a coin flip minus the vig.` }
    return { key: 'pass', label: 'Pass', ours: v.ours, lineNote, reason: `Our model leans the other way: ${pct(v.ours)} for this side, books ${pct(v.books)}.` }
  }

  // No live line (board rebuilt without it): what we said when it was imported.
  const s = p.snapshot
  if (!s || s.far_line || s.our_prob == null)
    return { ...base, key: 'unknown', label: "Can't check", reason: 'Not on our board, so this is their read only.' }
  const reason = ' (as of import; the line is off our board now)'
  if (s.agrees === true) return { ...base, key: 'lean', label: 'Lean', ours: s.our_prob, reason: `Our model agreed${reason}.` }
  if (s.agrees === false)
    return { ...base, key: 'pass', label: 'Pass', ours: s.our_prob, reason: `Our model leaned the other way${reason}.` }
  return { ...base, key: 'pass', label: 'Pass', ours: s.our_prob, reason: `Priced at the market${reason}.` }
}

/** For graded picks: what our board said before kickoff, from the import snapshot. */
export function ourReadThen(p: ShowPick): string | null {
  const s = p.snapshot
  if (!s || s.far_line || s.agrees === undefined) return null
  if (s.agrees === true) return 'Our model agreed'
  if (s.agrees === false) return 'Our model disagreed'
  return p.market === 'team_win' ? null : 'Market-priced: no lean'
}

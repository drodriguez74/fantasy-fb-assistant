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

/** What our board said about the pick, in one sentence. */
export function boardView(p: ShowPick): string {
  const s = p.snapshot
  if (!s) return 'Not on our board.'
  if (p.market === 'team_win') return `No moneyline on our board (spread ${s.board_line}).`
  if (s.far_line) return `Our board priced ${s.board_line}; too far from this line to compare.`
  const lean = s.agrees === null ? 'market-only line, no lean' : s.agrees ? 'our model leans this way' : 'our model leans the other way'
  const price = s.board_price != null ? ` (${odds(s.board_price)})` : ''
  return `Our board: ${s.board_line}${price} · ${pct(s.our_prob)} for this side, books ${pct(s.books_prob)} · ${lean}`
}

/** How the show's number compares with our board's when imported (stated lines only). */
export function lineNote(p: ShowPick): string | null {
  const v = p.snapshot?.line_value
  if (!p.line_stated || v == null || v === 0 || p.snapshot?.far_line) return null
  const pts = `${Math.abs(v)} pt${Math.abs(v) === 1 ? '' : 's'}`
  return v > 0 ? `The show's number is ${pts} better than our board's` : `The show's number is ${pts} worse than our board's`
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

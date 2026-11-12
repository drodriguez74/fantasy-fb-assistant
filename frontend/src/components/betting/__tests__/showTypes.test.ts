import { describe, expect, it } from 'vitest'
import { type BoardRow } from '../betTypes'
import { liveRowFor, ourReadThen, showPickText, verdictFor, type ShowPick } from '../showTypes'

const KICKOFF = '2026-11-15T18:00:00Z'
const BEFORE = new Date('2026-11-13T12:00:00Z').getTime()

const pick = (over: Partial<ShowPick>): ShowPick => ({
  id: 1, source: 'Show', network: null, sport: 'nfl', analyst: 'A', segment: null, aired_on: '2026-11-12',
  season: 2026, week: 10, player: 'HOU', team: 'HOU', game: 'HOU @ CLE', kickoff: KICKOFF, market: 'team_spread',
  market_label: 'Spread', side: 'More', line: 4.5, line_stated: true, price: null, conviction: 'bet', quote: null,
  snapshot: null, status: 'pending', actual: null, ...over,
})

// The board's spread row: side = the team bet, line = that team's spread.
const spreadRow = (over: Partial<BoardRow>): BoardRow => ({
  type: 'game', market: 'spread', market_label: 'Spread', side: 'HOU', line: -4.5, book: 'hardrockbet', price: -110,
  model_prob: null, market_prob: 0.5, p_win: 0.5, p_push: 0, ev: 0, units: 0, confidence: 'none',
  game: 'HOU @ CLE', kickoff: KICKOFF, home: 'CLE', away: 'HOU', books_quoting: 7, ...over,
})

describe('showPickText', () => {
  it('says a pick the way a bettor does', () => {
    expect(showPickText(pick({}))).toBe('HOU -4.5')
    expect(showPickText(pick({ player: 'WSH', line: -2.5 }))).toBe('WSH +2.5')
    expect(showPickText(pick({ line: 0 }))).toBe('HOU PK')
    expect(showPickText(pick({ market: 'game_total', player: 'HOU @ CLE', side: 'Less', line: 40.5 }))).toBe('HOU @ CLE Under 40.5')
    expect(showPickText(pick({ market: 'team_win', price: 135 }))).toBe('HOU to win (+135)')
    expect(showPickText(pick({ market: 'player_rec_yds', market_label: 'Receiving yards', player: 'Tyler Warren', side: 'Less', line: 51.5 })))
      .toBe('Tyler Warren Under 51.5 receiving yards')
  })
})

describe('verdictFor', () => {
  it('reports graded picks and started games before anything else', () => {
    expect(verdictFor(pick({ status: 'won', actual: 7 }), [], BEFORE).key).toBe('won')
    expect(verdictFor(pick({ status: 'lost' }), [], BEFORE).key).toBe('lost')
    expect(verdictFor(pick({ status: 'void' }), [], BEFORE).label).toBe('Void')
    expect(verdictFor(pick({}), [], new Date(KICKOFF).getTime() + 1).key).toBe('started')
  })

  it("can't check a moneyline or a pick that's off the board", () => {
    expect(verdictFor(pick({ market: 'team_win' }), [spreadRow({})], BEFORE).key).toBe('unknown')
    expect(verdictFor(pick({}), [], BEFORE).key).toBe('unknown')
  })

  it('says Tail when our card bets the same side', () => {
    const v = verdictFor(pick({}), [spreadRow({ units: 1.5, p_win: 0.56 })], BEFORE)
    expect(v.key).toBe('tail')
    expect(v.label).toBe('Tail · 1.5u')
    expect(v.ours).toBeCloseTo(0.56)
  })

  it('says Fade only when our card bets the other side', () => {
    const other = spreadRow({ side: 'CLE', line: 4.5, units: 1, p_win: 0.57 })
    const v = verdictFor(pick({}), [other], BEFORE)
    expect(v.key).toBe('fade')
    expect(v.ours).toBeCloseTo(0.43)
  })

  it('is a Pass, never a Fade, when the model merely leans away', () => {
    const leansAway = spreadRow({ side: 'CLE', line: 4.5, units: 0, p_win: 0.55, market_prob: 0.5 })
    expect(verdictFor(pick({}), [leansAway], BEFORE).key).toBe('pass')
  })

  it('is a Lean when the model agrees under the bar, and a Pass at the market price', () => {
    expect(verdictFor(pick({}), [spreadRow({ p_win: 0.53, market_prob: 0.5 })], BEFORE).key).toBe('lean')
    expect(verdictFor(pick({}), [spreadRow({ p_win: 0.5, market_prob: 0.5 })], BEFORE).key).toBe('pass')
  })

  it("notes when today's line beats the show's number", () => {
    const v = verdictFor(pick({ line: 4.5 }), [spreadRow({ line: -3.5 })], BEFORE)
    expect(v.lineNote).toBe("Today's line is 1 pt better than theirs.")
    const worse = verdictFor(pick({ line: 4.5 }), [spreadRow({ line: -6.5 })], BEFORE)
    expect(worse.lineNote).toBe("They had a better number; today's line is 2 pts worse.")
  })

  it("won't compare a prop whose line is far from the show's", () => {
    const prop: BoardRow = {
      ...spreadRow({}), type: 'player_prop', market: 'player_rec_yds', market_label: 'Receiving yards',
      side: 'Over', line: 62.5, player: 'Tyler Warren',
    }
    const p = pick({ market: 'player_rec_yds', market_label: 'Receiving yards', player: 'Tyler Warren', line: 90.5 })
    expect(verdictFor(p, [prop], BEFORE).key).toBe('unknown')
    expect(liveRowFor(p, [prop])).toBe(prop)
  })

  it('falls back to the import snapshot when the line left the board', () => {
    const snap = { board_line: '', board_price: null, board_game: null, kickoff: KICKOFF, our_prob: 0.55, books_prob: 0.5, ev: 0.02, units: 0, agrees: true, line_value: 0, far_line: false }
    expect(verdictFor(pick({ snapshot: snap }), [], BEFORE).key).toBe('lean')
    expect(verdictFor(pick({ snapshot: { ...snap, agrees: false } }), [], BEFORE).key).toBe('pass')
    expect(verdictFor(pick({ snapshot: { ...snap, far_line: true } }), [], BEFORE).key).toBe('unknown')
  })
})

describe('ourReadThen', () => {
  it('summarizes what the board said at import', () => {
    const snap = { board_line: '', board_price: null, board_game: null, kickoff: null, our_prob: 0.5, books_prob: 0.5, ev: 0, units: 0, agrees: null, line_value: null, far_line: false }
    expect(ourReadThen(pick({ snapshot: null }))).toBeNull()
    expect(ourReadThen(pick({ snapshot: { ...snap, agrees: true } }))).toBe('Our model agreed')
    expect(ourReadThen(pick({ snapshot: { ...snap, agrees: false } }))).toBe('Our model disagreed')
    expect(ourReadThen(pick({ snapshot: snap }))).toBe('Market-priced: no lean')
  })
})

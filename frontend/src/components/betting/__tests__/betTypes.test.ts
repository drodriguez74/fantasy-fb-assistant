import { describe, expect, it } from 'vitest'
import { dollars, matchesQuery, sameWeek, sideSpread, watchKey, weeksOf, type BoardRow } from '../betTypes'
import { chance, money, odds, rate, signedNum, signedPct } from '../format'

const row = (over: Partial<BoardRow>): BoardRow => ({
  type: 'game', market: 'spread', market_label: 'Spread', side: 'BAL', line: -4, book: 'hardrockbet', price: -110,
  model_prob: null, market_prob: 0.5, p_win: 0.5, p_push: 0, ev: 0, units: 0, confidence: 'none',
  game: 'LAC @ BAL', home: 'BAL', away: 'LAC', books_quoting: 7, ...over,
})

describe('sideSpread', () => {
  it('shows the home spread for the home side and flips it for the away side', () => {
    expect(sideSpread(row({ side: 'BAL' }), -4)).toBe('-4')
    expect(sideSpread(row({ side: 'LAC' }), -4)).toBe('+4')
  })
  it('handles a pick-em and a missing line', () => {
    expect(sideSpread(row({}), 0)).toBe('PK')
    expect(sideSpread(row({}), null)).toBe('—')
  })
})

describe('dollars', () => {
  it('is 1% of bankroll per unit', () => {
    expect(dollars(1, 1000)).toBe('$10')
    expect(dollars(0.5, 250)).toBe('$1.25')
    expect(dollars(3, 5000)).toBe('$150')
  })
  it('is empty without a bankroll or a stake', () => {
    expect(dollars(1, null)).toBeNull()
    expect(dollars(0, 1000)).toBeNull()
  })
})

describe('matchesQuery', () => {
  it('ignores case, accents and punctuation', () => {
    expect(matchesQuery('jamarr', "Ja'Marr Chase")).toBe(true)
    expect(matchesQuery('CHASE cin', "Ja'Marr Chase", 'CIN')).toBe(true)
  })
  it('needs every word to appear somewhere', () => {
    expect(matchesQuery('chase dal', "Ja'Marr Chase", 'CIN')).toBe(false)
    expect(matchesQuery('   ', 'anything')).toBe(true)
    expect(matchesQuery('x', null, undefined)).toBe(false)
  })
})

describe('weeks', () => {
  it('lists weeks newest first, once each, always with the current week', () => {
    const rows = [{ season: 2026, week: 8 }, { season: 2026, week: 10 }, { season: 2026, week: 8 }, { season: 2025, week: 17 }]
    expect(weeksOf(rows, { season: 2026, week: 11 })).toEqual([
      { season: 2026, week: 11 }, { season: 2026, week: 10 }, { season: 2026, week: 8 }, { season: 2025, week: 17 },
    ])
    expect(weeksOf([], null)).toEqual([])
  })
  it('compares weeks by season and week', () => {
    expect(sameWeek({ season: 2026, week: 10 }, { season: 2026, week: 10 })).toBe(true)
    expect(sameWeek({ season: 2025, week: 10 }, { season: 2026, week: 10 })).toBe(false)
    expect(sameWeek(null, { season: 2026, week: 10 })).toBe(false)
  })
})

describe('formatting', () => {
  it('keeps one number format across the page', () => {
    expect(chance(0.724)).toBe('72%')
    expect(chance(0.034)).toBe('3.4%')
    expect(chance(null)).toBe('—')
    expect(rate(0.1234)).toBe('12.3%')
    expect(signedPct(0.032)).toBe('+3.2%')
    expect(signedPct(-0.01)).toBe('-1.0%')
    expect(signedNum(1.25)).toBe('+1.25')
    expect(odds(135)).toBe('+135')
    expect(odds(-110)).toBe('-110')
    expect(odds(null)).toBe('—')
    expect(money(-3)).toBe('-$3.00')
  })
  it('builds a stable watch key', () => {
    expect(watchKey('prop', 'Josh Allen', 'player_pass_yds', 'Over')).toBe('prop|Josh Allen|player_pass_yds|Over')
  })
})

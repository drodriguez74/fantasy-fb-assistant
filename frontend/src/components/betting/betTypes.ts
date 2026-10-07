// Shapes of GET /betting/board (backend/app/services/betting_service.py) and
// the formatting shared by the Bets page's cards.
import { useState } from 'react'
import type { PrizePicksBoard } from './PrizePicksPairs'
import type { GameComboSet } from './GameCombos'

export type Confidence = 'high' | 'strong' | 'lean' | 'none'

export interface BoardRow {
  type: 'player_prop' | 'game'
  market: string
  market_label: string
  side: string
  line: number | null
  book: string
  price: number
  model_prob: number | null
  market_prob: number | null
  p_win: number
  p_push: number
  ev: number
  units: number
  confidence: Confidence
  // Worst price (American) still worth taking if the line moves; bets only.
  min_price?: number | null
  game: string
  kickoff?: string
  home?: string
  away?: string
  books_quoting: number
  // player props
  player?: string
  projection?: number
  market_line?: number | null
  prizepicks_line?: number | null
  projection_outlier?: boolean
  espn_projection?: number | null
  espn_agrees?: boolean
  // Positive EV every source agrees with, too small to size.
  watch?: boolean
  // game lines (home spread or total; negative spread = home favored)
  consensus_line?: number
  model_line?: number | null
  check_line?: number | null
}

export interface Board {
  available: boolean
  detail?: string
  week?: number
  games_modeled?: number
  generated_at?: string
  player_props?: BoardRow[]
  game_props?: BoardRow[]
  prizepicks?: PrizePicksBoard
  game_combos?: GameComboSet[]
  watch_count?: number
  recommended_count?: number
  evaluated?: { player_props: number; games: number; props_without_projection: number }
  games_without_props?: string[]
  credits_remaining?: number | null
  sources?: { odds: string; projections: string }
  method?: string
  disclaimer: string
}

export const pct = (p: number | null | undefined) => (p == null ? '—' : `${(p * 100).toFixed(1)}%`)
export const odds = (p: number) => (p > 0 ? `+${p}` : `${p}`)
export const signedPct = (x: number) => `${x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`

// Plain-language bet sizes (backend confidence tiers: 0.5-1u, 1.5-2u, 2.5-3u).
export const SIZE_LABEL: Record<Confidence, string> = { lean: 'Small', strong: 'Medium', high: 'Max', none: '' }

export function kickoffLabel(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}

/** A spread from the bet side's point of view ("BAL +3"), given the home spread. */
export function sideSpread(row: BoardRow, homeSpread: number | null | undefined): string {
  if (homeSpread == null) return '—'
  const v = row.side === row.home ? homeSpread : -homeSpread
  return v === 0 ? 'PK' : v > 0 ? `+${v}` : `${v}`
}

// Bankroll for showing units in dollars (1u = 1% of bankroll). Per-browser
// convenience only, so localStorage is fine; everything works without it.
const BANKROLL_KEY = 'bets-bankroll'

export function useBankroll(): [number | null, (value: number | null) => void] {
  const [bankroll, setBankroll] = useState<number | null>(() => {
    try {
      const v = Number(localStorage.getItem(BANKROLL_KEY))
      return v > 0 ? v : null
    } catch {
      return null
    }
  })
  const update = (value: number | null) => {
    setBankroll(value)
    try {
      if (value && value > 0) localStorage.setItem(BANKROLL_KEY, String(value))
      else localStorage.removeItem(BANKROLL_KEY)
    } catch {
      // storage unavailable: the value still applies this session
    }
  }
  return [bankroll, update]
}

export function dollars(units: number, bankroll: number | null): string | null {
  if (!bankroll || units <= 0) return null
  const amount = (units * bankroll) / 100
  return amount >= 100 ? `$${Math.round(amount)}` : `$${amount.toFixed(amount % 1 ? 2 : 0)}`
}

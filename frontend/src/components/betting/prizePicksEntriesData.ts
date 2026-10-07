// Loader and ranking for PrizePicks entries (POST /betting/prizepicks-entries,
// backend betting_service.prizepicks_entries). A hook so the Bets page's
// "This week's card" and the PrizePicks tab share one request.
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import type { PrizePicksLeg } from './PrizePicksPairs'

export interface Entry {
  size: number
  type: 'power' | 'flex'
  ev: number
  p_all: number
  p_paid: number
  payouts: Record<string, number>
  legs: PrizePicksLeg[]
}

export type Power = Record<string, number>
export type Flex = Record<string, Record<string, number>>

const STORAGE_KEY = 'prizepicks-payouts'

function loadSaved(): { power?: Power; flex?: Flex } {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

export interface EntriesState {
  entries: Entry[]
  power: Power | null
  flex: Flex | null
  loading: boolean
  error: string
  setPayouts: (p: Power, f: Flex) => void
  save: () => void
  reset: () => void
}

export function usePrizePicksEntries(): EntriesState {
  const [entries, setEntries] = useState<Entry[]>([])
  const [power, setPower] = useState<Power | null>(null)
  const [flex, setFlex] = useState<Flex | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async (p?: Power, f?: Flex) => {
    setLoading(true)
    setError('')
    try {
      const saved = loadSaved()
      const response = await betting.getPrizePicksEntries({ power: p ?? saved.power, flex: f ?? saved.flex })
      setEntries(response.data.entries)
      setPower((cur) => cur ?? saved.power ?? response.data.default_power)
      setFlex((cur) => cur ?? saved.flex ?? response.data.default_flex)
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't build PrizePicks entries."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return {
    entries,
    power,
    flex,
    loading,
    error,
    setPayouts: (p, f) => {
      setPower(p)
      setFlex(f)
    },
    save: () => {
      if (!power || !flex) return
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ power, flex }))
      } catch {
        // storage unavailable: payouts still apply to this request
      }
      load(power, flex)
    },
    reset: () => {
      try {
        localStorage.removeItem(STORAGE_KEY)
      } catch {
        // nothing saved
      }
      setPower(null)
      setFlex(null)
      load(undefined, undefined)
    },
  }
}

/** Entries ranked best-first, each tagged with how many of its picks a better entry already uses. */
export function rankEntries(entries: Entry[]): (Entry & { overlap: number })[] {
  const ranked = [...entries].sort((a, b) => b.ev - a.ev)
  const seen = new Set<string>()
  return ranked.map((e) => {
    const keys = e.legs.map((l) => `${l.player}|${l.market}`)
    const overlap = keys.filter((k) => seen.has(k)).length
    keys.forEach((k) => seen.add(k))
    return { ...e, overlap }
  })
}


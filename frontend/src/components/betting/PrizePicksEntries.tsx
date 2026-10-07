// Best 3-6 pick PrizePicks Power and Flex entries from POST
// /betting/prizepicks-entries (backend betting_service.prizepicks_entries).
// Payouts default to PrizePicks' standard published multipliers; they vary
// by state, so the user can edit them (kept in this browser only).
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import type { PrizePicksLeg } from './PrizePicksPairs'

interface Entry {
  size: number
  type: 'power' | 'flex'
  ev: number
  p_all: number
  p_paid: number
  payouts: Record<string, number>
  legs: PrizePicksLeg[]
}

type Power = Record<string, number>
type Flex = Record<string, Record<string, number>>

const STORAGE_KEY = 'prizepicks-payouts'

function loadSaved(): { power?: Power; flex?: Flex } {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

const pct = (p: number) => `${(p * 100).toFixed(1)}%`

function PayoutEditor({ power, flex, onChange }: { power: Power; flex: Flex; onChange: (p: Power, f: Flex) => void }) {
  const num = (v: string) => (v === '' ? 0 : Number(v))
  return (
    <div className="grid gap-4 sm:grid-cols-2 text-xs">
      <div>
        <p className="text-body font-medium mb-1">Power Play (all must hit)</p>
        {Object.keys(power).map((size) => (
          <label key={size} className="flex items-center gap-2 mb-1">
            <span className="w-14 text-muted">{size}-pick</span>
            <input
              type="number"
              step="0.1"
              min="0"
              value={power[size]}
              onChange={(e) => onChange({ ...power, [size]: num(e.target.value) }, flex)}
              className="w-20 rounded border-line bg-surface-2 px-2 py-1 text-body"
            />
            <span className="text-faint">x</span>
          </label>
        ))}
      </div>
      <div>
        <p className="text-body font-medium mb-1">Flex Play (pays on misses too)</p>
        {Object.keys(flex).map((size) => (
          <div key={size} className="flex flex-wrap items-center gap-2 mb-1">
            <span className="w-14 text-muted">{size}-pick</span>
            {Object.keys(flex[size])
              .sort((a, b) => Number(b) - Number(a))
              .map((hits) => (
                <label key={hits} className="flex items-center gap-1">
                  <span className="text-faint">{hits}/{size}</span>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    value={flex[size][hits]}
                    onChange={(e) => onChange(power, { ...flex, [size]: { ...flex[size], [hits]: num(e.target.value) } })}
                    className="w-16 rounded border-line bg-surface-2 px-2 py-1 text-body"
                  />
                </label>
              ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function PrizePicksEntries() {
  const [entries, setEntries] = useState<Entry[]>([])
  const [power, setPower] = useState<Power | null>(null)
  const [flex, setFlex] = useState<Flex | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)

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

  const save = () => {
    if (!power || !flex) return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ power, flex }))
    } catch {
      // storage unavailable: payouts still apply to this request
    }
    load(power, flex)
  }

  const reset = () => {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // nothing saved
    }
    setPower(null)
    setFlex(null)
    load(undefined, undefined)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-body">2–6 pick entries</h3>
        <button onClick={() => setEditing((v) => !v)} className="text-xs text-accent-ink underline">
          {editing ? 'Hide payouts' : 'Edit payouts'}
        </button>
      </div>
      <p className="text-xs text-muted leading-relaxed">
        Built from the most likely picks, one per player, from at least two teams. Payouts are PrizePicks' standard
        multipliers for all-standard lineups; they vary by state, so check yours by building a lineup (don't submit it) and
        reading "$1 to pay $X". Flex pays even if one or two picks miss.
      </p>
      {editing && power && flex && (
        <div className="rounded-lg border border-hairline bg-surface p-4 space-y-3">
          <PayoutEditor
            power={power}
            flex={flex}
            onChange={(p, f) => {
              setPower(p)
              setFlex(f)
            }}
          />
          <div className="flex gap-3">
            <button onClick={save} className="bg-volt text-volt-ink px-3 py-1.5 rounded-lg text-sm hover:bg-volt-dark">
              Save and reprice
            </button>
            <button onClick={reset} className="text-xs text-muted underline">
              Reset to standard
            </button>
          </div>
        </div>
      )}
      {loading ? (
        <p className="text-xs text-muted">Building entries...</p>
      ) : error ? (
        <p className="text-xs text-warning-700">{error}</p>
      ) : entries.length === 0 ? (
        <p className="text-xs text-muted">Not enough picks to build entries this week.</p>
      ) : (
        <div className="space-y-3">
          {entries.map((e) => (
            <div
              key={`${e.type}-${e.legs.map((l) => `${l.player}${l.market}`).join('|')}`}
              className="rounded-lg border border-hairline bg-surface p-4"
            >
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 stat-nums text-xs">
                <span className="text-sm font-semibold text-body">
                  {e.size}-pick {e.type === 'power' ? 'Power' : 'Flex'}
                </span>
                <span>
                  <span className="text-faint">EV </span>
                  <span className={e.ev > 0 ? 'text-success-700' : 'text-muted'}>
                    {e.ev > 0 ? '+' : ''}
                    {(e.ev * 100).toFixed(1)}%
                  </span>
                </span>
                <span><span className="text-faint">All hit </span><span className="text-body">{pct(e.p_all)}</span></span>
                {e.type === 'flex' && (
                  <span><span className="text-faint">Pays something </span><span className="text-body">{pct(e.p_paid)}</span></span>
                )}
                <span className="text-faint">
                  Pays{' '}
                  {Object.entries(e.payouts)
                    .sort((a, b) => Number(b[0]) - Number(a[0]))
                    .map(([hits, m]) => `${m}x${e.type === 'flex' ? ` (${hits}/${e.size})` : ''}`)
                    .join(' · ')}
                </span>
              </div>
              <ul className="mt-2 grid gap-1 sm:grid-cols-2 text-sm">
                {e.legs.map((l) => (
                  <li key={`${l.player}-${l.market}`} className="text-body">
                    {l.player} <span className="text-faint text-xs">{l.team}</span>{' '}
                    <span className={l.side === 'More' ? 'text-success-700' : 'text-accent-ink'}>{l.side}</span>{' '}
                    <span className="stat-nums">{l.line}</span> <span className="text-muted">{l.market_label}</span>{' '}
                    <span className="stat-nums text-[11px] text-faint">{pct(l.p_win)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

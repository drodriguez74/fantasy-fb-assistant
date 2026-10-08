// The entry-builder tray (PrizePicks tab): picks added from Safest picks,
// stacks, entries, goblins and demons collect here. The server checks
// PrizePicks' rules and prices the chance every pick hits with same-game
// correlation (POST /betting/prizepicks-ticket). The user types the payout
// PrizePicks shows -- goblins and demons change it -- and sees the edge and
// the break-even payout, then logs the ticket to My entries in one tap.
import { useEffect, useState } from 'react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { betting, getErrorMessage } from '../../services/api'
import type { Flex, Power } from './prizePicksEntriesData'
import { legKey, type TicketLeg } from './ticketTypes'

interface Priced {
  p_all: number
  p_independent: number
  hits: number[]
  breakeven_power: number | null
}

const pct = (p: number) => `${(p * 100).toFixed(1)}%`

export function TicketTray({
  legs,
  onRemove,
  onClear,
  power,
  flex,
}: {
  legs: TicketLeg[]
  onRemove: (l: TicketLeg) => void
  onClear: () => void
  power: Power | null
  flex: Flex | null
}) {
  const [type, setType] = useState<'power' | 'flex'>('power')
  const [payout, setPayout] = useState('')
  const [stake, setStake] = useState('')
  const [priced, setPriced] = useState<Priced | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState('')
  const [open, setOpen] = useState(true)
  const size = legs.length
  const specials = legs.some((l) => l.odds_type && l.odds_type !== 'standard')

  // Standard payout as the starting point; goblins/demons change it, so the user types what PrizePicks shows.
  useEffect(() => {
    const std = type === 'power' ? power?.[String(size)] : flex?.[String(size)]?.[String(size)]
    setPayout(std && !specials ? String(std) : '')
  }, [size, type, power, flex, specials])

  useEffect(() => {
    setSaved('')
    if (size < 2) {
      setPriced(null)
      setError('')
      return
    }
    let live = true
    betting
      .priceTicket(legs.map(({ player, team, game, market, side, line, p_win }) => ({ player, team, game, market, side, line, p_win })))
      .then((r) => live && (setPriced(r.data), setError('')))
      .catch((err) => live && (setPriced(null), setError(getErrorMessage(err, "Couldn't price this ticket."))))
    return () => {
      live = false
    }
  }, [legs, size])

  if (size === 0) return null
  const x = Number(payout)
  const edge = (() => {
    if (!priced || !(x > 0)) return null
    if (type === 'power') return priced.p_all * x - 1
    const table = { ...(flex?.[String(size)] ?? {}), [String(size)]: x }
    return priced.hits.reduce((sum, p, k) => sum + p * (table[String(k)] ?? 0), 0) - 1
  })()

  const log = async () => {
    setSaving(true)
    setError('')
    try {
      await betting.logEntry({
        entry_type: type,
        stake: Number(stake),
        to_win: Number(stake) * x,
        legs: legs.map((l) => ({ player: l.player, market: l.market, side: l.side, line: l.line, ...(l.team ? { team: l.team } : {}) })),
      })
      setSaved('Logged to My entries.')
      onClear()
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't log this entry."))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 px-2 pb-2 sm:px-4">
      <div className="max-w-5xl mx-auto rounded-xl border border-line bg-surface shadow-lg">
        <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-3 px-4 py-2.5 text-left" aria-expanded={open}>
          <span className="text-sm font-medium text-body">Your ticket · {size} pick{size === 1 ? '' : 's'}</span>
          {priced && (
            <span className="stat-nums text-xs text-muted">
              {pct(priced.p_all)} all hit{edge != null && ` · edge ${edge > 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`}
            </span>
          )}
          <span className="ml-auto text-xs text-muted">{open ? 'Hide' : 'Show'}</span>
        </button>
        {open && (
          <div className="px-4 pb-4 space-y-3 max-h-[60vh] overflow-y-auto">
            <ul className="divide-y divide-hairline">
              {legs.map((l) => (
                <li key={legKey(l)} className="py-1.5 flex items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate text-body">
                    {l.player} <span className="text-faint text-xs">{l.team}</span> <span className="font-medium">{l.side}</span>{' '}
                    <span className="stat-nums">{l.line}</span>{' '}
                    <span className="text-muted">{(l.market_label ?? l.market).toString().toLowerCase()}</span>
                    {l.odds_type && l.odds_type !== 'standard' && (
                      <span className="ml-1 text-xs text-muted border border-hairline rounded px-1 capitalize">{l.odds_type}</span>
                    )}
                  </span>
                  <span className="stat-nums text-xs text-faint shrink-0">{Math.round(l.p_win * 100)}%</span>
                  <button onClick={() => onRemove(l)} aria-label={`Remove ${l.player}`} className="text-faint hover:text-body">
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
            {size < 2 ? (
              <p className="text-xs text-muted">Add at least one more pick (players from two teams).</p>
            ) : error ? (
              <p className="text-xs text-warning-700">{error}</p>
            ) : priced ? (
              <>
                <div className="flex flex-wrap items-end gap-3 text-xs">
                  <div className="flex rounded-lg border border-hairline p-0.5" role="tablist" aria-label="Entry type">
                    {(['power', 'flex'] as const).map((t) => (
                      <button
                        key={t}
                        role="tab"
                        aria-selected={type === t}
                        onClick={() => setType(t)}
                        className={`px-3 py-1 rounded-md ${type === t ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
                      >
                        {t === 'power' ? 'Power' : 'Flex'}
                      </button>
                    ))}
                  </div>
                  <label className="flex flex-col gap-1 text-muted">
                    {type === 'power' ? 'Pays (x) if all hit' : `Pays (x) for ${size}/${size}`}
                    <input
                      type="number"
                      min="0"
                      step="0.05"
                      inputMode="decimal"
                      value={payout}
                      placeholder="from PrizePicks"
                      onChange={(e) => setPayout(e.target.value)}
                      className="w-28 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums"
                    />
                  </label>
                  <p className="stat-nums text-muted pb-1">
                    {pct(priced.p_all)} all hit (vs {pct(priced.p_independent)} if independent)
                    {priced.breakeven_power && type === 'power' && ` · needs ${priced.breakeven_power}x`}
                  </p>
                </div>
                {edge != null ? (
                  <p className={`text-sm stat-nums ${edge > 0 ? 'text-success-700' : 'text-danger-700'}`}>
                    Edge {edge > 0 ? '+' : ''}
                    {(edge * 100).toFixed(1)}% at {x}x{edge <= 0 && ' -- PrizePicks pays less than the chance needs'}
                  </p>
                ) : (
                  <p className="text-xs text-muted">
                    Type the payout PrizePicks shows ("$1 to pay $X"){specials ? ': goblins and demons change it.' : '.'}
                  </p>
                )}
                <div className="flex flex-wrap items-end gap-3 text-xs">
                  <label className="flex flex-col gap-1 text-muted">
                    Entry fee ($)
                    <input
                      type="number"
                      min="0"
                      inputMode="decimal"
                      value={stake}
                      onChange={(e) => setStake(e.target.value)}
                      className="w-24 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums"
                    />
                  </label>
                  <button
                    onClick={log}
                    disabled={saving || !(Number(stake) > 0) || !(x > 1)}
                    className="bg-volt text-volt-ink px-3 py-1.5 rounded-lg text-sm hover:bg-volt-dark disabled:opacity-50"
                  >
                    {saving ? 'Logging...' : 'Log this entry'}
                  </button>
                  <button onClick={onClear} className="text-xs text-muted underline pb-1.5">
                    Clear
                  </button>
                </div>
              </>
            ) : (
              <p className="text-xs text-muted">Pricing...</p>
            )}
            {saved && <p className="text-xs text-success-700">{saved}</p>}
          </div>
        )}
      </div>
    </div>
  )
}

/** A small "+ Add" button for any pick row. */
export function AddButton({ active, onClick, label = 'Add' }: { active: boolean; onClick: () => void; label?: string }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 text-xs rounded-md border px-2 py-0.5 ${active ? 'border-line bg-surface-2 text-body' : 'border-hairline text-muted hover:text-body'}`}
      aria-pressed={active}
    >
      {active ? 'Added' : `+ ${label}`}
    </button>
  )
}

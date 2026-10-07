// Best PrizePicks Power and Flex entries, ranked by EV with overlap warnings.
// Data comes from usePrizePicksEntries (prizePicksEntriesData.ts). Payouts
// default to PrizePicks' standard multipliers; they vary by state, so the
// user can edit them (kept in this browser only).
import { useState } from 'react'
import { type EntriesState, type Entry, type Flex, type Power, rankEntries } from './prizePicksEntriesData'

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

const entryName = (e: Entry) => `${e.size}-pick ${e.type === 'power' ? 'Power' : 'Flex'}`

export function PrizePicksEntries({ state }: { state: EntriesState }) {
  const [editing, setEditing] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const { entries, power, flex, loading, error } = state
  const ranked = rankEntries(entries)
  // By default, skip entries that mostly repeat a better shown one (half or
  // more of their picks already used above): the same bet with one swap.
  const distinct: typeof ranked = []
  const used = new Set<string>()
  for (const e of ranked) {
    if (e.ev <= 0 || distinct.length >= 6) continue
    const keys = e.legs.map((l) => `${l.player}|${l.market}`)
    const overlap = keys.filter((k) => used.has(k)).length
    if (overlap >= e.size / 2) continue
    keys.forEach((k) => used.add(k))
    distinct.push({ ...e, overlap })
  }
  const shown = showAll ? ranked : distinct

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-body">Best entries</h3>
        <button onClick={() => setEditing((v) => !v)} className="text-xs text-accent-ink underline">
          {editing ? 'Hide payouts' : 'Edit payouts'}
        </button>
      </div>
      <p className="text-xs text-muted leading-relaxed">
        Ranked by expected value; near-duplicates of a better entry are hidden. One pick per player, players from at
        least two teams. Payouts are PrizePicks' standard
        multipliers; check yours on a built (unsubmitted) lineup's "$1 to pay $X" line and edit them here if they differ.
      </p>
      {editing && power && flex && (
        <div className="rounded-lg border border-hairline bg-surface p-4 space-y-3">
          <PayoutEditor power={power} flex={flex} onChange={state.setPayouts} />
          <div className="flex gap-3">
            <button onClick={state.save} className="bg-volt text-volt-ink px-3 py-1.5 rounded-lg text-sm hover:bg-volt-dark">
              Save and reprice
            </button>
            <button onClick={state.reset} className="text-xs text-muted underline">
              Reset to standard
            </button>
          </div>
        </div>
      )}
      {loading ? (
        <p className="text-xs text-muted">Building entries...</p>
      ) : error ? (
        <p className="text-xs text-warning-700">{error}</p>
      ) : shown.length === 0 ? (
        <div className="rounded-lg border border-hairline bg-surface p-4 text-sm text-muted">
          No entry has positive expected value at these payouts this week.
          {ranked.length > 0 && (
            <button onClick={() => setShowAll(true)} className="block mt-1 text-xs text-accent-ink underline">
              Show all {ranked.length} entries anyway
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {shown.map((e, i) => (
            <div
              key={`${e.type}-${e.legs.map((l) => `${l.player}${l.market}`).join('|')}`}
              className={`rounded-lg bg-surface p-4 border ${i === 0 && e.ev > 0 ? 'border-volt' : 'border-hairline'} ${
                e.ev <= 0 ? 'opacity-70' : ''
              }`}
            >
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 stat-nums text-xs">
                <span className="text-sm font-semibold text-body">{entryName(e)}</span>
                <span className={e.ev > 0 ? 'text-success-700' : 'text-muted'}>
                  EV {e.ev > 0 ? '+' : ''}
                  {(e.ev * 100).toFixed(1)}%
                </span>
                <span><span className="text-body">{pct(e.p_all)}</span> <span className="text-faint">all hit</span></span>
                {e.type === 'flex' && (
                  <span><span className="text-body">{pct(e.p_paid)}</span> <span className="text-faint">pays something</span></span>
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
              {e.overlap > 0 && (
                <p className="text-[11px] text-warning-700 mt-2">
                  Shares {e.overlap} pick{e.overlap === 1 ? '' : 's'} with a better entry above. Playing both doubles up on
                  the same outcomes, so pick one.
                </p>
              )}
            </div>
          ))}
          {!showAll && ranked.length > shown.length && (
            <button onClick={() => setShowAll(true)} className="text-xs text-accent-ink underline">
              Show all {ranked.length} entries, including near-duplicates and ones that lose money
            </button>
          )}
          {showAll && (
            <button onClick={() => setShowAll(false)} className="text-xs text-accent-ink underline">
              Show distinct profitable entries only
            </button>
          )}
        </div>
      )}
    </div>
  )
}

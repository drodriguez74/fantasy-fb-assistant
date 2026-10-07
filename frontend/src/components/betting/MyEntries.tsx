// "My entries": PrizePicks entries the user actually placed, logged here and
// graded automatically from real stats (backend app/services/user_entries.py).
// Each pick keeps a snapshot of what the books and our model said when it was
// logged, so the record shows over time whose read was right.
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'

interface Snapshot {
  books_prob: number
  model_prob: number
  sleeper_projection?: number
  espn_projection?: number | null
  books_line?: number | null
  projections_disagree?: boolean
}

interface EntryLeg {
  player: string
  team?: string | null
  market: string
  side: 'More' | 'Less'
  line: number
  snapshot?: Snapshot | null
  status: 'pending' | 'won' | 'lost' | 'push' | 'void'
  actual: number | null
}

interface MyEntry {
  id: number
  entry_type: 'power' | 'flex'
  stake: number
  to_win: number
  week: number
  legs: EntryLeg[]
  est_hit_prob: number | null
  status: 'pending' | 'won' | 'lost' | 'partial' | 'refunded'
  payout: number | null
  profit: number | null
}

interface Check {
  picks: number
  hit_rate: number
  books_said: number | null
  model_said: number | null
}

interface EntriesData {
  entries: MyEntry[]
  record: { entries: number; settled: number; pending: number; won: number; lost: number; staked: number; returned: number; profit: number; roi: number | null }
  pick_check: { all: Check | null; projections_disagreed_with_books: Check | null }
  markets: Record<string, string>
}

interface DraftLeg {
  player: string
  team?: string | null
  market: string
  side: 'More' | 'Less'
  line: string
}

// What /betting/entries/read-screenshot returns: the form, prefilled.
interface ScreenshotRead {
  entry_type: 'power' | 'flex' | null
  stake: number | null
  to_win: number | null
  picks: { player: string; team: string | null; market: string; side: 'More' | 'Less'; line: number }[]
  warnings: string[]
}

const blankLeg = (): DraftLeg => ({ player: '', market: 'player_reception_yds', side: 'More', line: '' })
const pct = (p: number | null | undefined) => (p == null ? '—' : `${(p * 100).toFixed(0)}%`)
const money = (x: number) => `${x < 0 ? '-' : ''}$${Math.abs(x).toFixed(2)}`

const STATUS_STYLE: Record<string, string> = {
  won: 'bg-success-100 text-success-800',
  partial: 'bg-highlight text-accent-ink',
  refunded: 'bg-surface-2 text-muted',
  lost: 'bg-danger-100 text-danger-700',
  pending: 'bg-surface-2 text-muted',
  push: 'bg-surface-2 text-muted',
  void: 'bg-surface-2 text-muted',
}

function EntryForm({ markets, players, onSaved }: { markets: Record<string, string>; players: string[]; onSaved: () => void }) {
  const [entryType, setEntryType] = useState<'power' | 'flex'>('power')
  const [stake, setStake] = useState('')
  const [toWin, setToWin] = useState('')
  const [legs, setLegs] = useState<DraftLeg[]>([blankLeg(), blankLeg()])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [reading, setReading] = useState(false)
  const [warnings, setWarnings] = useState<string[]>([])

  // Prefills the form from a screenshot; the user checks it and saves.
  const importScreenshot = async (file: File | null | undefined) => {
    if (!file) return
    setReading(true)
    setError('')
    setWarnings([])
    try {
      const r: ScreenshotRead = (await betting.readEntryScreenshot(file)).data
      if (r.entry_type) setEntryType(r.entry_type)
      setStake(r.stake != null ? String(r.stake) : '')
      setToWin(r.to_win != null ? String(r.to_win) : '')
      const read = r.picks.slice(0, 6).map((p) => ({
        player: p.player,
        team: p.team,
        market: p.market in markets ? p.market : blankLeg().market,
        side: p.side,
        line: String(p.line),
      }))
      setLegs(read.length >= 2 ? read : [...read, ...Array.from({ length: 2 - read.length }, blankLeg)])
      setWarnings(['Read from your screenshot: check every pick before saving.', ...r.warnings])
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't read that screenshot."))
    } finally {
      setReading(false)
    }
  }

  const update = (i: number, patch: Partial<DraftLeg>) => setLegs((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))

  const submit = async () => {
    setSaving(true)
    setError('')
    try {
      await betting.logEntry({
        entry_type: entryType,
        stake: Number(stake),
        to_win: Number(toWin),
        legs: legs.map((l) => ({ player: l.player, market: l.market, side: l.side, line: Number(l.line), ...(l.team ? { team: l.team } : {}) })),
      })
      setStake('')
      setToWin('')
      setLegs([blankLeg(), blankLeg()])
      setWarnings([])
      onSaved()
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't save that entry."))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="rounded-lg border border-hairline bg-surface p-4 space-y-3"
      onPaste={(e) => {
        const file = Array.from(e.clipboardData.files).find((f) => f.type.startsWith('image/'))
        if (file) {
          e.preventDefault()
          importScreenshot(file)
        }
      }}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-medium text-body">Log an entry you placed</h3>
        <label className={`text-xs text-accent-ink underline cursor-pointer ${reading ? 'opacity-50 pointer-events-none' : ''}`}>
          {reading ? 'Reading screenshot...' : 'Import from screenshot'}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="sr-only"
            disabled={reading}
            onChange={(e) => {
              importScreenshot(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </label>
        <span className="text-[11px] text-faint">or paste one here</span>
      </div>
      {warnings.length > 0 && (
        <ul className="text-xs text-warning-700 space-y-0.5">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <div className="flex rounded-lg border border-hairline p-0.5" role="tablist" aria-label="Entry type">
          {(['power', 'flex'] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={entryType === t}
              onClick={() => setEntryType(t)}
              className={`px-3 py-1 rounded-md ${entryType === t ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
            >
              {t === 'power' ? 'Power' : 'Flex'}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-muted">
          Entry fee ($)
          <input type="number" min="0" inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} className="w-24 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums" />
        </label>
        <label className="flex flex-col gap-1 text-muted">
          Pays if all hit ($)
          <input type="number" min="0" inputMode="decimal" value={toWin} onChange={(e) => setToWin(e.target.value)} className="w-28 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums" />
        </label>
        <span className="text-faint pb-1">From PrizePicks' "$10 to pay $30" line.</span>
      </div>
      <datalist id="entry-players">
        {players.map((p) => (
          <option key={p} value={p} />
        ))}
      </datalist>
      <div className="space-y-2">
        {legs.map((l, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
            <input
              list="entry-players"
              placeholder="Player"
              value={l.player}
              onChange={(e) => update(i, { player: e.target.value, team: null })}
              className="w-44 rounded border-line bg-surface-2 px-2 py-1 text-body"
              aria-label={`Pick ${i + 1} player`}
            />
            <select value={l.market} onChange={(e) => update(i, { market: e.target.value })} className="rounded border-line bg-surface-2 px-2 py-1 text-body" aria-label={`Pick ${i + 1} stat`}>
              {Object.entries(markets).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
            <div className="flex rounded border border-hairline">
              {(['More', 'Less'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => update(i, { side: s })}
                  className={`px-2 py-1 text-xs ${l.side === s ? (s === 'More' ? 'bg-success-100 text-success-800' : 'bg-highlight text-accent-ink') : 'text-muted'}`}
                >
                  {s}
                </button>
              ))}
            </div>
            <input
              type="number"
              step="0.5"
              placeholder="Line"
              value={l.line}
              onChange={(e) => update(i, { line: e.target.value })}
              className="w-20 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums"
              aria-label={`Pick ${i + 1} line`}
            />
            {legs.length > 2 && (
              <button onClick={() => setLegs((ls) => ls.filter((_, j) => j !== i))} className="text-xs text-faint underline">
                Remove
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {legs.length < 6 && (
          <button onClick={() => setLegs((ls) => [...ls, blankLeg()])} className="text-xs text-accent-ink underline">
            Add a pick
          </button>
        )}
        <button onClick={submit} disabled={saving} className="ml-auto bg-volt text-volt-ink px-3 py-1.5 rounded-lg text-sm hover:bg-volt-dark disabled:opacity-50">
          {saving ? 'Saving...' : 'Save entry'}
        </button>
      </div>
      {error && <p className="text-xs text-warning-700">{error}</p>}
    </div>
  )
}

function CheckRow({ label, c }: { label: string; c: Check | null }) {
  if (!c) return null
  return (
    <tr className="border-t border-hairline">
      <td className="py-1.5 text-body">{label}</td>
      <td className="text-right text-faint">{c.picks}</td>
      <td className="text-right text-muted">{pct(c.books_said)}</td>
      <td className="text-right text-muted">{pct(c.model_said)}</td>
      <td className="text-right text-body">{pct(c.hit_rate)}</td>
    </tr>
  )
}

export function MyEntries({ players }: { players: string[] }) {
  const [data, setData] = useState<EntriesData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await betting.getEntries()
      setData(response.data)
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't load your entries."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const remove = async (id: number) => {
    try {
      await betting.deleteEntry(id)
      load()
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't delete that entry."))
    }
  }

  if (loading && !data) return <p className="text-sm text-muted">Loading your entries...</p>
  if (error && !data) return <p className="text-sm text-warning-700">{error}</p>
  if (!data) return null
  const r = data.record
  const check = data.pick_check

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted leading-relaxed">
        Entries you placed on PrizePicks, graded automatically from real stats once each game is final. A player who
        doesn't play, or a pick exactly on the line, drops out and the entry pays as a smaller one (standard payouts).
        Each pick saves what the books and our model said when you logged it.
      </p>

      <EntryForm markets={data.markets} players={players} onSaved={load} />

      {r.entries > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            ['Record', r.settled ? `${r.won}-${r.lost}` : '—'],
            ['Profit', r.settled ? money(r.profit) : '—'],
            ['ROI', r.roi == null ? '—' : `${r.roi > 0 ? '+' : ''}${(r.roi * 100).toFixed(1)}%`],
            ['Pending', String(r.pending)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-hairline bg-surface p-3">
              <div className="stat-nums text-[10px] uppercase tracking-wider text-faint">{label}</div>
              <div className="stat-nums text-lg font-semibold text-body mt-1">{value}</div>
            </div>
          ))}
        </div>
      )}

      {check.all && (
        <div className="rounded-lg border border-hairline bg-surface p-4">
          <h3 className="text-sm font-medium text-body mb-1">Whose read was right?</h3>
          <p className="text-xs text-muted mb-2">
            For your graded picks: what the books said, what our model said, and how often they actually hit. The second
            row is picks where the projections disagreed with the books, like a player projected far over his line.
          </p>
          <table className="w-full stat-nums text-xs">
            <thead>
              <tr className="text-faint text-left">
                <th className="font-normal py-1">Picks</th>
                <th className="font-normal text-right">Count</th>
                <th className="font-normal text-right">Books said</th>
                <th className="font-normal text-right">Model said</th>
                <th className="font-normal text-right">Hit</th>
              </tr>
            </thead>
            <tbody>
              <CheckRow label="All graded picks" c={check.all} />
              <CheckRow label="Projections disagreed" c={check.projections_disagreed_with_books} />
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-3">
        {data.entries.map((e) => (
          <div key={e.id} className="rounded-lg border border-hairline bg-surface p-4">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 stat-nums text-xs">
              <span className="text-sm font-semibold text-body">
                {e.legs.length}-pick {e.entry_type === 'power' ? 'Power' : 'Flex'}
              </span>
              <span className="text-muted">
                {money(e.stake)} to pay {money(e.to_win)} · week {e.week}
              </span>
              {e.est_hit_prob != null && <span className="text-faint">books: {pct(e.est_hit_prob)} to hit all</span>}
              <span className={`ml-auto uppercase text-[10px] px-1.5 py-0.5 rounded ${STATUS_STYLE[e.status]}`}>{e.status}</span>
              {e.profit != null && (
                <span className={e.profit > 0 ? 'text-success-700' : e.profit < 0 ? 'text-danger-700' : 'text-muted'}>{money(e.profit)}</span>
              )}
            </div>
            <ul className="mt-2 space-y-1">
              {e.legs.map((l, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className={`stat-nums uppercase text-[9px] px-1 py-0.5 rounded ${STATUS_STYLE[l.status]}`}>{l.status}</span>
                  <span className="text-body">{l.player}</span>
                  {l.team && <span className="text-faint text-xs">{l.team}</span>}
                  <span className={l.side === 'More' ? 'text-success-700' : 'text-accent-ink'}>{l.side}</span>
                  <span className="stat-nums">{l.line}</span>
                  <span className="text-muted">{data.markets[l.market] ?? l.market}</span>
                  {l.actual != null && <span className="stat-nums text-xs text-faint">actual {l.actual}</span>}
                  {l.snapshot && (
                    <span className="stat-nums text-[11px] text-faint">
                      · books {pct(l.snapshot.books_prob)} · model {pct(l.snapshot.model_prob)}
                      {l.snapshot.projections_disagree ? ' · projections disagreed' : ''}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {e.status === 'pending' && (
              <button onClick={() => remove(e.id)} className="mt-2 text-[11px] text-faint underline">
                Delete
              </button>
            )}
          </div>
        ))}
      </div>
      {error && <p className="text-xs text-warning-700">{error}</p>}
    </div>
  )
}

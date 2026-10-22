// "My entries": PrizePicks entries the user actually placed, logged here and
// graded automatically from real stats (backend app/services/user_entries.py).
// Each pick keeps a snapshot of what the books and our model said when it was
// logged, so the record shows over time whose read was right.
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import { type BetWeek, sameWeek, weeksOf } from './betTypes'
import { WeekPicker } from './WeekPicker'
import { chance, money } from './format'
import { Explainer, Segmented, StatusBadge } from './ui'

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
  entry_type: 'power' | 'flex' | 'straight' | 'parlay'
  // PrizePicks, or a sportsbook bet (e.g. Hard Rock Bet) logged in the same table.
  platform?: 'prizepicks' | 'sportsbook'
  book?: string | null
  stake: number
  to_win: number
  season: number
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
  // Hard Rock bets only: American odds, and (college) the kickoff as a local datetime.
  price?: string
  kickoff?: string
}

type Platform = 'prizepicks' | 'sportsbook'
type Sport = 'nfl' | 'cfb'
const GAME_MARKETS = ['team_spread', 'game_total', 'team_win']
const MAX_LEGS: Record<Platform, number> = { prizepicks: 6, sportsbook: 12 }

/** A form row -> the API's leg. A sportsbook spread is typed as the book shows
 * it ("+7.5"); the API's spread is "wins by more than", so +7.5 is More -7.5. */
function toApiLeg(l: DraftLeg, platform: Platform, sport: Sport) {
  const book = platform === 'sportsbook'
  let side = l.side
  let line = Number(l.line)
  if (book && l.market === 'team_spread') [side, line] = ['More', -line]
  if (l.market === 'team_win') [side, line] = ['More', 0.5]
  return {
    player: l.player,
    market: l.market,
    side,
    line,
    ...(l.team ? { team: l.team } : sport === 'cfb' ? { team: l.player } : {}),
    ...(book ? { price: Number(l.price) } : {}),
    ...(sport === 'cfb' && l.kickoff ? { kickoff: new Date(l.kickoff).toISOString() } : {}),
  }
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

/** Profit, stake and record for a set of entries (settled ones; pending counted apart). */
function tally(entries: MyEntry[]) {
  const settled = entries.filter((e) => e.status !== 'pending')
  const staked = settled.reduce((t, e) => t + e.stake, 0)
  const profit = settled.reduce((t, e) => t + (e.payout ?? 0) - e.stake, 0)
  return {
    settled: settled.length,
    won: settled.filter((e) => e.status === 'won').length,
    lost: settled.filter((e) => e.status === 'lost').length,
    pending: entries.length - settled.length,
    staked,
    profit,
    roi: staked ? profit / staked : null,
  }
}

// Game picks (team wins, spread, total) read the way PrizePicks shows them.
const GAME_PICK: Record<string, (l: EntryLeg) => string> = {
  team_win: (l) => `${l.player} to win`,
  team_spread: (l) => `${l.player} ${l.line > 0 ? `-${l.line}` : `+${-l.line}`} spread`,
  game_total: (l) => `${l.player} ${l.side === 'More' ? 'Over' : 'Under'} ${l.line} total points`,
}

// One dot per pick: won / lost / pending (push and void are grey).
const LEG_DOT: Record<string, string> = {
  won: 'bg-success-700',
  lost: 'bg-danger-700',
  pending: 'bg-faint',
}

function EntryForm({ markets, players, onSaved }: { markets: Record<string, string>; players: string[]; onSaved: () => void }) {
  const [platform, setPlatform] = useState<Platform>('prizepicks')
  const [sport, setSport] = useState<Sport>('nfl')
  const [entryType, setEntryType] = useState<'power' | 'flex'>('power')
  const book = platform === 'sportsbook'
  // College is game lines only (no player stats graded for college).
  const legMarkets = Object.entries(markets).filter(([k]) => !(book && sport === 'cfb') || GAME_MARKETS.includes(k))
  const blank = (): DraftLeg => (book && sport === 'cfb' ? { ...blankLeg(), market: 'team_spread' } : blankLeg())
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
      // A 1-pick Power Play is a real entry; anything else starts with 2 rows.
      const min = r.entry_type === 'power' && read.length === 1 ? 1 : 2
      setLegs(read.length >= min ? read : [...read, ...Array.from({ length: min - read.length }, blankLeg)])
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
        platform,
        ...(book ? { sport, book: 'Hard Rock Bet' } : {}),
        entry_type: book ? (legs.length === 1 ? 'straight' : 'parlay') : entryType,
        stake: Number(stake),
        to_win: Number(toWin),
        legs: legs.map((l) => toApiLeg(l, platform, sport)),
      })
      setStake('')
      setToWin('')
      setLegs(book ? [blank()] : [blankLeg(), blankLeg()])
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
        {!book && (<>
        <label className={`text-xs text-body underline cursor-pointer ${reading ? 'opacity-50 pointer-events-none' : ''}`}>
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
        <span className="text-xs text-faint">or paste one here</span>
        </>)}
      </div>
      {warnings.length > 0 && (
        <ul className="text-xs text-warning-700 space-y-0.5">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-3 text-xs">
        <Segmented
          label="Where"
          value={platform}
          options={[
            ['prizepicks', 'PrizePicks'],
            ['sportsbook', 'Hard Rock Bet'],
          ]}
          onChange={(v) => {
            setPlatform(v)
            setLegs(v === 'sportsbook' ? [sport === 'cfb' ? { ...blankLeg(), market: 'team_spread' } : blankLeg()] : [blankLeg(), blankLeg()])
          }}
        />
        {book ? (
          <Segmented
            label="League"
            value={sport}
            options={[
              ['nfl', 'NFL'],
              ['cfb', 'College'],
            ]}
            onChange={(v) => {
              setSport(v)
              setLegs([v === 'cfb' ? { ...blankLeg(), market: 'team_spread' } : blankLeg()])
            }}
          />
        ) : (
          <Segmented
            label="Entry type"
            value={entryType}
            options={[
              ['power', 'Power'],
              ['flex', 'Flex'],
            ]}
            onChange={setEntryType}
          />
        )}
        <label className="flex flex-col gap-1 text-muted">
          {book ? 'Wager ($)' : 'Entry fee ($)'}
          <input type="number" min="0" inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} className="w-24 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums" />
        </label>
        <label className="flex flex-col gap-1 text-muted">
          {book ? 'Payout ($)' : 'Pays if all hit ($)'}
          <input type="number" min="0" inputMode="decimal" value={toWin} onChange={(e) => setToWin(e.target.value)} className="w-28 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums" />
        </label>
        <span className="text-faint pb-1">
          {book
            ? `The full payout the bet slip shows (wager included). ${legs.length === 1 ? 'Straight bet' : `${legs.length}-leg parlay`}.`
            : `From PrizePicks' "$10 to pay $30" line.`}
        </span>
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
              list={book && sport === 'cfb' ? undefined : 'entry-players'}
              placeholder={book && sport === 'cfb' ? 'Team (e.g. Toledo Rockets)' : GAME_MARKETS.includes(l.market) ? 'Team' : 'Player'}
              value={l.player}
              onChange={(e) => update(i, { player: e.target.value, team: null })}
              className="w-44 rounded border-line bg-surface-2 px-2 py-1 text-body"
              aria-label={`Pick ${i + 1} player`}
            />
            <select value={l.market} onChange={(e) => update(i, { market: e.target.value })} className="rounded border-line bg-surface-2 px-2 py-1 text-body" aria-label={`Pick ${i + 1} stat`}>
              {legMarkets.map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
            {!(book && l.market === 'team_spread') && l.market !== 'team_win' && (
            <div className="flex rounded border border-hairline">
              {(['More', 'Less'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => update(i, { side: s })}
                  className={`px-2 py-1 text-xs ${l.side === s ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
                >
                  {l.market === 'game_total' ? (s === 'More' ? 'Over' : 'Under') : s}
                </button>
              ))}
            </div>
            )}
            {l.market !== 'team_win' && (
            <input
              type="number"
              step="0.5"
              placeholder={book && l.market === 'team_spread' ? 'Spread (+7.5)' : 'Line'}
              value={l.line}
              onChange={(e) => update(i, { line: e.target.value })}
              className="w-20 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums"
              aria-label={`Pick ${i + 1} line`}
            />
            )}
            {book && (
              <input
                type="number"
                placeholder="Odds (-110)"
                value={l.price ?? ''}
                onChange={(e) => update(i, { price: e.target.value })}
                className="w-24 rounded border-line bg-surface-2 px-2 py-1 text-body stat-nums"
                aria-label={`Pick ${i + 1} odds`}
              />
            )}
            {book && sport === 'cfb' && (
              <input
                type="datetime-local"
                value={l.kickoff ?? ''}
                onChange={(e) => update(i, { kickoff: e.target.value })}
                className="rounded border-line bg-surface-2 px-2 py-1 text-body"
                aria-label={`Pick ${i + 1} kickoff`}
              />
            )}
            {legs.length > (book || entryType === 'power' ? 1 : 2) && (
              <button onClick={() => setLegs((ls) => ls.filter((_, j) => j !== i))} className="text-xs text-faint underline">
                Remove
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {legs.length < MAX_LEGS[platform] && (
          <button onClick={() => setLegs((ls) => [...ls, blank()])} className="text-xs text-body underline">
            {book ? 'Add a parlay leg' : 'Add a pick'}
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
      <td className="text-right text-muted">{chance(c.books_said)}</td>
      <td className="text-right text-muted">{chance(c.model_said)}</td>
      <td className="text-right text-body">{chance(c.hit_rate)}</td>
    </tr>
  )
}

export function MyEntries({
  players,
  current,
  picked,
  onPick,
}: {
  players: string[]
  current: BetWeek | null
  // The page's chosen week (shared with Shows and the Audit); null = this week.
  picked: BetWeek | null
  onPick: (w: BetWeek) => void
}) {
  const [data, setData] = useState<EntriesData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)

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
  const weeks = weeksOf(data.entries, current)
  // The list shows one week: the one picked, else this week.
  const shownWeek = picked ?? current ?? weeks[0] ?? null
  const weekEntries = data.entries.filter((e) => sameWeek(e, shownWeek))
  const thisWeek = tally(data.entries.filter((e) => sameWeek(e, current)))

  return (
    <div className="space-y-5">
      {data.entries.length > 0 && !formOpen ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted">
            Your PrizePicks entries, graded from real stats as each game ends. Each pick keeps what the books and our model
            said when you logged it.
          </p>
          <button
            onClick={() => setFormOpen(true)}
            className="bg-volt text-volt-ink px-3 py-1.5 rounded-lg text-sm hover:bg-volt-dark"
          >
            Log an entry
          </button>
        </div>
      ) : (
        <>
          <Explainer>
            <p>
            Entries you placed on PrizePicks, graded automatically from real stats once each game is final. A player who
            doesn't play, or a pick exactly on the line, drops out and the entry pays as a smaller one.
          </p>
          </Explainer>
          <EntryForm
            markets={data.markets}
            players={players}
            onSaved={() => {
              setFormOpen(false)
              load()
            }}
          />
        </>
      )}

      {data.entries.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface p-4 overflow-x-auto">
          <table className="w-full stat-nums text-xs sm:text-sm [&_th+th]:pl-3 [&_td+td]:pl-3">
            <thead>
              <tr className="text-xs text-faint text-left">
                <th className="font-normal pb-1"></th>
                <th className="font-normal pb-1 text-right">Profit</th>
                <th className="font-normal pb-1 text-right">Staked</th>
                <th className="font-normal pb-1 text-right">Record</th>
                <th className="font-normal pb-1 text-right">Open</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  [current ? `Week ${current.week}` : 'This week', thisWeek],
                  ['Season', { ...r, staked: r.staked, profit: r.profit }],
                ] as const
              ).map(([label, t]) => (
                <tr key={label} className="border-t border-hairline">
                  <td className="py-1.5 text-body font-medium whitespace-nowrap">{label}</td>
                  <td className={`text-right ${t.profit > 0 ? 'text-success-700' : t.profit < 0 ? 'text-danger-700' : 'text-body'}`}>
                    {t.settled ? money(t.profit) : '—'}
                  </td>
                  <td className="text-right text-muted">{t.settled ? money(t.staked) : '—'}</td>
                  <td className="text-right text-body">{t.settled ? `${t.won}-${t.lost}` : '—'}</td>
                  <td className="text-right text-muted">{t.pending}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.settled > 0 && r.settled < 20 && <p className="text-xs text-faint mt-2">Too few settled entries to judge yet.</p>}
        </div>
      )}

      {weeks.length > 1 && <WeekPicker weeks={weeks} value={shownWeek} current={current} onChange={onPick} />}
      {data.entries.length > 0 && weekEntries.length === 0 && (
        <p className="text-sm text-muted">No entries logged for week {shownWeek?.week}.</p>
      )}

      <div className="space-y-3">
        {weekEntries.map((e) => (
          <div key={e.id} className="rounded-lg border border-hairline bg-surface p-4">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 stat-nums text-xs">
              <span className="text-sm font-semibold text-body">
                {e.platform === 'sportsbook'
                  ? `${e.book ?? 'Sportsbook'} · ${e.entry_type === 'straight' ? 'Straight' : `${e.legs.length}-leg parlay`}`
                  : `${e.legs.length}-pick ${e.entry_type === 'power' ? 'Power' : 'Flex'}`}
              </span>
              <span className="text-muted">
                {money(e.stake)} to pay {money(e.to_win)}
              </span>
              {e.est_hit_prob != null && <span className="text-faint">books: {chance(e.est_hit_prob)} to hit all</span>}
              <span className="ml-auto"><StatusBadge status={e.status} /></span>
              {e.profit != null && (
                <span className={e.profit > 0 ? 'text-success-700' : e.profit < 0 ? 'text-danger-700' : 'text-muted'}>{money(e.profit)}</span>
              )}
            </div>
            <ul className="mt-2 space-y-1">
              {e.legs.map((l, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span
                    className={`inline-block h-2 w-2 rounded-full shrink-0 ${LEG_DOT[l.status] ?? 'bg-line'}`}
                    title={l.status}
                    aria-label={l.status}
                  />
                  {GAME_PICK[l.market] ? (
                    <span className="text-body">{GAME_PICK[l.market](l)}</span>
                  ) : (
                    <>
                      <span className="text-body">{l.player}</span>
                      {l.team && <span className="text-faint text-xs">{l.team}</span>}
                      <span className="text-body font-medium">{l.side}</span>
                      <span className="stat-nums">{l.line}</span>
                      <span className="text-muted">{data.markets[l.market] ?? l.market}</span>
                    </>
                  )}
                  {l.actual != null && <span className="stat-nums text-xs text-faint">actual {l.actual}</span>}
                  {l.snapshot && (
                    <span className="stat-nums text-xs text-faint">
                      · books {chance(l.snapshot.books_prob)} · model {chance(l.snapshot.model_prob)}
                      {l.snapshot.projections_disagree ? ' · projections disagreed' : ''}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {e.status === 'pending' && (
              <button onClick={() => remove(e.id)} className="mt-2 text-xs text-faint underline">
                Delete
              </button>
            )}
          </div>
        ))}
      </div>
      {check.all && (
        <details className="rounded-lg border border-hairline bg-surface p-4">
          <summary className="cursor-pointer text-sm font-medium text-body">
            Whose read was right?{' '}
            <span className="text-xs font-normal text-muted">
              {check.all.picks} graded pick{check.all.picks === 1 ? '' : 's'}
              {check.all.picks < 100 ? ', too few to judge' : ''}
            </span>
          </summary>
          <div className="mt-2">
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
        </details>
      )}

      {error && <p className="text-xs text-warning-700">{error}</p>}
    </div>
  )
}

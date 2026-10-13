// Weekly audit (GET /betting/audit -- backend/app/services/betting_audit.py):
// every recommendation the app made in a week -- bets, Best available fills,
// Most likely to win picks, suggested PrizePicks tickets -- plus the user's
// own entries, with what we said, the engine version and whether it hit.
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import { ShowMore } from './ShowMore'
import { WeekPicker } from './WeekPicker'
import { type BetWeek } from './betTypes'
import { chance } from './format'
import { Explainer, StatusBadge } from './ui'

interface AuditRow {
  section: string
  pick: string
  market: string
  side: string | null
  line: number | null
  book: string | null
  price: number | null
  p_win: number | null
  books_prob: number | null
  engine_prob: number | null
  units: number | null
  engine_version: string
  kickoff?: string | null
  close_line?: number | null
  close_books_prob?: number | null
  beat_close?: boolean | null
  status: string
  actual: number | string | null
  profit: number | null
  profit_unit: string | null
}

interface SectionSummary {
  picks: number
  decided: number
  pending: number
  hits: number
  hit_rate: number | null
  predicted: number | null
}

interface Audit {
  season: number | null
  week: number | null
  weeks: { season: number; week: number }[]
  engine_version: string
  summary: Record<string, SectionSummary>
  rows: AuditRow[]
}


// Before kickoff the "close" is just the latest line so far, so say so.
function closeText(r: AuditRow): string {
  const moved = r.close_line != null && r.close_line !== r.line ? ` (${r.close_line})` : ''
  const future = r.kickoff != null && new Date(r.kickoff).getTime() > Date.now()
  if (future) return ` · line ${r.beat_close ? 'moving our way' : 'moving against us'} so far${moved}`
  return ` · ${r.beat_close ? 'beat' : 'lost to'} the close${moved}`
}

// Display names for the audit sections (backend names stay stable for the CSV).
const SECTION_NAME: Record<string, string> = { 'Most likely to win': 'Safest picks' }

const ROW_TONE: Record<string, string> = {
  won: 'border-l-success-600',
  lost: 'border-l-danger-600',
  partial: 'border-l-accent-ink',
}
/** One week's recommendations, for one sport ('all' = both, plus the PrizePicks tickets and your entries). */
export function BettingAudit({
  sport = 'all',
  current = null,
  picked = null,
  onPick,
}: {
  sport?: 'nfl' | 'cfb' | 'all'
  current?: BetWeek | null
  // The page's chosen week; null = the latest mostly-settled week (backend default).
  picked?: BetWeek | null
  onPick?: (w: BetWeek) => void
}) {
  const [data, setData] = useState<Audit | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  const load = useCallback((season?: number, week?: number) => {
    setLoading(true)
    setError('')
    betting
      .getAudit(season, week, sport)
      .then((r) => setData(r.data))
      .catch((err) => setError(getErrorMessage(err, "Couldn't load the audit.")))
      .finally(() => setLoading(false))
  }, [sport])

  useEffect(() => {
    load(picked?.season, picked?.week)
  }, [load, picked?.season, picked?.week])

  const download = async () => {
    if (!data?.season || !data.week) return
    setDownloading(true)
    try {
      const r = await betting.downloadAudit(data.season, data.week, sport)
      const url = URL.createObjectURL(r.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `bets-audit-${data.season}-week${data.week}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't download the CSV."))
    } finally {
      setDownloading(false)
    }
  }

  const isLatest = !!data && data.weeks.length > 0 && data.weeks[0].season === data.season && data.weeks[0].week === data.week

  return (
    <div className="bg-surface rounded-lg border border-hairline p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-body">Audit: every recommendation, hit or miss</h3>
        <div className="flex items-center gap-2">
          {data && data.weeks.length > 0 && data.season != null && data.week != null && (
            <WeekPicker
              weeks={data.weeks}
              value={{ season: data.season, week: data.week }}
              current={current}
              onChange={(w) => (onPick ? onPick(w) : load(w.season, w.week))}
            />
          )}
          <button
            onClick={download}
            disabled={downloading || !data?.rows.length}
            className="text-xs rounded-lg border border-hairline px-2.5 py-1 text-body hover:border-volt disabled:opacity-50"
          >
            {downloading ? 'Downloading...' : 'Download CSV'}
          </button>
        </div>
      </div>
      <div className="mt-1">
        <Explainer>
        <p>
        What we said when each pick was shown (frozen, never edited), the model version that made it, and the graded
        result. Picks grade a few hours after their game ends.
      </p>
      </Explainer>
      </div>

      {loading && <p className="text-xs text-faint mt-3">Loading...</p>}
      {error && (
        <p className="text-xs text-warning-700 mt-3">
          {error}{' '}
          <button onClick={() => load(data?.season ?? undefined, data?.week ?? undefined)} className="text-body underline">
            Try again
          </button>
        </p>
      )}
      {!loading && data && data.rows.length === 0 && <p className="text-xs text-faint mt-3">Nothing tracked yet.</p>}

      {!loading && data && data.rows.length > 0 && (
        <div className="mt-3 divide-y divide-hairline border-t border-hairline">
          {Object.entries(data.summary)
            // The current week's entries are the Entries tab's list; the CSV keeps them.
            .filter(([section]) => !(section === 'My entries' && isLatest))
            .map(([section, s]) => (
              <AuditSection
                key={`${data.season}-${data.week}-${section}`}
                name={SECTION_NAME[section] ?? section}
                summary={s}
                rows={data.rows.filter((r) => r.section === section)}
              />
            ))}
        </div>
      )}
    </div>
  )
}

const SETTLED = ['won', 'lost', 'partial', 'push', 'refunded', 'void']

function auditRow(r: AuditRow, key: string) {
  return (
    <li key={key} className={`py-1.5 pl-2 border-l-2 ${ROW_TONE[r.status] ?? 'border-l-hairline'}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-body min-w-0 break-words">
          {r.pick}
          {r.side && (
            <span className="text-muted">
              {' '}
              {r.market} {r.side} {r.line ?? ''}
            </span>
          )}
        </p>
        <StatusBadge status={r.status} />
      </div>
      <p className="stat-nums text-xs text-faint">
        We said {chance(r.p_win)}
        {r.books_prob != null && r.section !== 'My entries' && ` · books ${chance(r.books_prob)}`}
        {r.engine_prob != null && ` · model ${chance(r.engine_prob)}`}
        {r.units ? ` · ${r.units}u` : ''}
        {r.book && ` · ${r.book}`}
        {r.actual != null && ` · actual ${r.actual}`}
        {r.beat_close != null && closeText(r)}
        {r.profit != null && r.status !== 'pending' &&
          ` · ${r.profit > 0 ? '+' : ''}${r.profit_unit === '$' ? `$${r.profit}` : `${r.profit}${r.profit_unit === 'u' ? 'u' : 'x'}`}`}
        {` · ${r.engine_version === 'pre-versioning' ? 'v0 (before tracking)' : `model ${r.engine_version}`}`}
      </p>
    </li>
  )
}

/** One audit section: its summary line, opened on tap. Settled picks first
 * (10 at a time), pending and pre-tracking picks folded. */
function AuditSection({ name, summary: s, rows }: { name: string; summary: SectionSummary; rows: AuditRow[] }) {
  const [open, setOpen] = useState(false)
  const [showPending, setShowPending] = useState(false)
  const tracked = rows.filter((r) => r.engine_version !== 'pre-versioning')
  const settled = tracked.filter((r) => SETTLED.includes(r.status))
  const pending = tracked.filter((r) => !SETTLED.includes(r.status))
  const old = rows.filter((r) => r.engine_version === 'pre-versioning')
  return (
    <div className="py-2">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full flex flex-wrap items-baseline justify-between gap-x-2 text-left">
        <span className="text-xs font-semibold uppercase tracking-wider text-body">
          <span className="text-faint mr-1">{open ? '▾' : '▸'}</span>
          {name}
        </span>
        <span className="stat-nums text-xs text-muted">
          {s.decided > 0 ? `${s.hits}/${s.decided} hit (${chance(s.hit_rate)}) vs ${chance(s.predicted)} predicted` : `${s.picks} picks`}
          {s.pending > 0 && ` · ${s.pending} pending`}
        </span>
      </button>
      {open && (
        <div className="mt-1">
          {settled.length > 0 && (
            <ShowMore items={settled} limit={10} render={(r, i) => auditRow(r, `s${i}`)} className="divide-y divide-hairline" />
          )}
          {pending.length > 0 && (
            <>
              <button onClick={() => setShowPending(!showPending)} className="block mt-1 text-xs text-muted underline hover:text-body">
                {showPending ? 'Hide pending' : `${pending.length} pending`}
              </button>
              {showPending && (
                <ShowMore items={pending} limit={10} render={(r, i) => auditRow(r, `p${i}`)} className="divide-y divide-hairline" />
              )}
            </>
          )}
          {old.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-muted py-1">
                Before tracking began ({old.length}): recorded by the earlier model, kept for the record
              </summary>
              <ShowMore items={old} limit={10} render={(r, i) => auditRow(r, `o${i}`)} className="divide-y divide-hairline" />
            </details>
          )}
        </div>
      )}
    </div>
  )
}

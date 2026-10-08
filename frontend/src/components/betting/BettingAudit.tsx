// Weekly audit (GET /betting/audit -- backend/app/services/betting_audit.py):
// every recommendation the app made in a week -- bets, Best available fills,
// Most likely to win picks, suggested PrizePicks tickets -- plus the user's
// own entries, with what we said, the engine version and whether it hit.
import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'

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

const pct = (p: number | null | undefined) => (p == null ? '—' : `${Math.round(p * 100)}%`)

// Display names for the audit sections (backend names stay stable for the CSV).
const SECTION_NAME: Record<string, string> = { 'Most likely to win': 'Safest picks' }

const ROW_TONE: Record<string, string> = {
  won: 'border-l-success-600',
  lost: 'border-l-danger-600',
  partial: 'border-l-accent-ink',
}
const BADGE: Record<string, string> = {
  won: 'bg-success-100 text-success-800',
  lost: 'bg-danger-100 text-danger-800',
  partial: 'bg-highlight text-accent-ink',
}

export function BettingAudit() {
  const [data, setData] = useState<Audit | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  const load = useCallback((season?: number, week?: number) => {
    setLoading(true)
    setError('')
    betting
      .getAudit(season, week)
      .then((r) => setData(r.data))
      .catch((err) => setError(getErrorMessage(err, "Couldn't load the audit.")))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const download = async () => {
    if (!data?.season || !data.week) return
    setDownloading(true)
    try {
      const r = await betting.downloadAudit(data.season, data.week)
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

  return (
    <div className="bg-surface rounded-lg border border-hairline p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-body">Audit: every recommendation, hit or miss</h3>
        <div className="flex items-center gap-2">
          {data && data.weeks.length > 0 && (
            <select
              aria-label="Week"
              value={`${data.season}-${data.week}`}
              onChange={(e) => {
                const [s, w] = e.target.value.split('-').map(Number)
                load(s, w)
              }}
              className="rounded border-line bg-surface-2 px-2 py-1 text-xs text-body"
            >
              {data.weeks.map((w) => (
                <option key={`${w.season}-${w.week}`} value={`${w.season}-${w.week}`}>
                  {w.season} week {w.week}
                </option>
              ))}
            </select>
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
      <p className="text-xs text-muted mt-1">
        What we said when each pick was shown (frozen, never edited), the model version that made it, and the graded
        result. Picks grade a few hours after their game ends.
      </p>

      {loading && <p className="text-xs text-faint mt-3">Loading...</p>}
      {error && <p className="text-xs text-warning-700 mt-3">{error}</p>}
      {!loading && data && data.rows.length === 0 && <p className="text-xs text-faint mt-3">Nothing tracked yet.</p>}

      {!loading && data && data.rows.length > 0 && (
        <div className="mt-3 space-y-4">
          {Object.entries(data.summary).map(([section, s]) => (
            <div key={section}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-body">{SECTION_NAME[section] ?? section}</h4>
                <span className="stat-nums text-xs text-muted">
                  {s.picks} picks
                  {s.decided > 0 && ` · hit ${s.hits}/${s.decided} (${pct(s.hit_rate)}) vs ${pct(s.predicted)} predicted`}
                  {s.pending > 0 && ` · ${s.pending} pending`}
                </span>
              </div>
              <ul className="mt-1 divide-y divide-hairline">
                {data.rows
                  .filter((r) => r.section === section)
                  .map((r, i) => (
                    <li key={i} className={`py-1.5 pl-2 border-l-2 ${ROW_TONE[r.status] ?? 'border-l-hairline'}`}>
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
                        <span
                          className={`stat-nums shrink-0 text-xs px-1.5 py-0.5 rounded ${
                            BADGE[r.status] ?? 'bg-surface-2 text-muted'
                          }`}
                        >
                          {r.status}
                        </span>
                      </div>
                      <p className="stat-nums text-xs text-faint">
                        We said {pct(r.p_win)}
                        {r.books_prob != null && r.section !== 'My entries' && ` · books ${pct(r.books_prob)}`}
                        {r.engine_prob != null && ` · model ${pct(r.engine_prob)}`}
                        {r.units ? ` · ${r.units}u` : ''}
                        {r.book && ` · ${r.book}`}
                        {r.actual != null && ` · actual ${r.actual}`}
                        {r.profit != null && r.status !== 'pending' &&
                          ` · ${r.profit > 0 ? '+' : ''}${r.profit_unit === '$' ? `$${r.profit}` : `${r.profit}${r.profit_unit === 'u' ? 'u' : 'x'}`}`}
                        {` · ${r.engine_version === 'pre-versioning' ? 'v0 (before tracking)' : `model ${r.engine_version}`}`}
                      </p>
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

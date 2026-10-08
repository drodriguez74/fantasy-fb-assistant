import { useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import { ClockIcon } from '@heroicons/react/24/outline'
import { BettingAudit } from './BettingAudit'

// GET /betting/results -- backend/app/services/betting_tracking.py.
interface RecordSummary {
  bets: number
  won: number
  lost: number
  push: number
  void: number
  pending: number
  win_rate: number | null
  units_staked: number
  units_profit: number
  roi: number | null
}

interface TrackedPick {
  id: number
  week: number
  kind: 'player_prop' | 'game' | 'cfb_game'
  subject: string
  game: string
  market: string
  side: string
  line: number | null
  book: string
  price: number
  units: number
  confidence: string
  p_win: number
  status: 'pending' | 'won' | 'lost' | 'push' | 'void'
  actual: number | null
  profit_units: number | null
}

interface Results {
  overall: RecordSummary
  by_sport?: Record<string, RecordSummary>
  by_confidence: Record<string, RecordSummary>
  by_market: Record<string, RecordSummary>
  by_week: (RecordSummary & { season: number; week: number })[]
  calibration: {
    lines: number
    buckets: { range: string; n: number; predicted: number; actual: number }[]
    brier: { blend: number | null; model: number | null; market: number | null }
  }
  lines_tracked: number
  picks: TrackedPick[]
  // Which engine version made each pick ("pre-versioning" before 2026-10-07).
  by_engine_version?: Record<string, RecordSummary>
  engine_version?: string
  // "Most likely to win" PrizePicks picks: predicted vs actual hit rate.
  most_likely?: {
    picks: number
    decided: number
    pending: number
    predicted: number | null
    actual: number | null
    calibration: { range: string; n: number; predicted: number; actual: number }[]
  }
}

const MARKET_LABELS: Record<string, string> = {
  player_pass_yds: 'Passing yards',
  player_rush_yds: 'Rushing yards',
  player_reception_yds: 'Receiving yards',
  player_receptions: 'Receptions',
  player_anytime_td: 'Anytime TD',
  spread: 'Spread',
  total: 'Total',
}
const STATUS_STYLE: Record<TrackedPick['status'], string> = {
  won: 'bg-success-100 text-success-800',
  lost: 'bg-danger-100 text-danger-800',
  push: 'bg-surface-2 text-muted',
  void: 'bg-surface-2 text-muted',
  pending: 'bg-highlight text-accent-ink',
}

const signed = (n: number, digits = 2) => `${n > 0 ? '+' : ''}${n.toFixed(digits)}`
const pct = (n: number | null) => (n == null ? '—' : `${(n * 100).toFixed(1)}%`)

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="bg-surface rounded-lg border border-hairline p-3">
      <div className="stat-nums text-[10px] tracking-wider text-muted uppercase">{label}</div>
      <div className={`stat-nums text-xl font-semibold mt-1 ${tone === 'good' ? 'text-success-700' : tone === 'bad' ? 'text-danger-700' : 'text-body'}`}>
        {value}
      </div>
    </div>
  )
}

function recordText(r: RecordSummary) {
  return `${r.won}-${r.lost}${r.push ? `-${r.push}` : ''}`
}

function SplitTable({ title, rows }: { title: string; rows: [string, RecordSummary][] }) {
  if (rows.length === 0) return null
  return (
    <div className="bg-surface rounded-lg border border-hairline p-4">
      <h3 className="text-sm font-medium text-body mb-2">{title}</h3>
      <table className="w-full stat-nums text-xs">
        <thead>
          <tr className="text-faint text-left">
            <th className="font-normal py-1">Group</th>
            <th className="font-normal">Record</th>
            <th className="font-normal text-right">Units</th>
            <th className="font-normal text-right">ROI</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, r]) => (
            <tr key={name} className="border-t border-hairline">
              <td className="py-1.5 text-body">{name}</td>
              <td className="text-body">{recordText(r)}{r.pending ? <span className="text-faint"> ({r.pending} pending)</span> : null}</td>
              <td className={`text-right ${r.units_profit > 0 ? 'text-success-700' : r.units_profit < 0 ? 'text-danger-700' : 'text-muted'}`}>
                {signed(r.units_profit)}u
              </td>
              <td className="text-right text-muted">{pct(r.roi)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const SPORT_NAME = { nfl: 'NFL', cfb: 'College' } as const

/** Track record for the current sport (each model is judged on its own), with an "All sports" view. */
export function BettingResults({ sport }: { sport: 'nfl' | 'cfb' }) {
  const [scope, setScope] = useState<'sport' | 'all'>('sport')
  const [currentOnly, setCurrentOnly] = useState(false)
  const [data, setData] = useState<Results | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError('')
    betting.getResults(scope === 'all' ? 'all' : sport, currentOnly ? 'current' : 'all')
      .then((r) => setData(r.data))
      .catch((err) => setError(getErrorMessage(err, "Couldn't load the track record.")))
      .finally(() => setLoading(false))
  }, [sport, scope, currentOnly])

  const scopeToggle = (
    <div className="flex flex-wrap items-center gap-3">
    <div className="flex rounded-lg border border-hairline p-0.5 w-fit" role="tablist" aria-label="Results scope">
      {(['sport', 'all'] as const).map((s) => (
        <button
          key={s}
          role="tab"
          aria-selected={scope === s}
          onClick={() => setScope(s)}
          className={`px-3 py-1 rounded-md text-xs ${scope === s ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
        >
          {s === 'sport' ? `${SPORT_NAME[sport]} only` : 'All sports'}
        </button>
      ))}
    </div>
    <label className="flex items-center gap-1.5 text-xs text-muted">
      <input type="checkbox" checked={currentOnly} onChange={(e) => setCurrentOnly(e.target.checked)} />
      Current engine only
    </label>
    </div>
  )

  if (loading) {
    return (
      <div className="space-y-4">
        {scopeToggle}
        <div className="bg-surface rounded-lg shadow p-6 text-center">
          <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
          <p className="text-sm text-muted">Grading finished games...</p>
        </div>
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="space-y-4">
        {scopeToggle}
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center text-sm text-muted">{error}</div>
      </div>
    )
  }

  const o = data.overall
  const settled = o.won + o.lost + o.push
  const brier = data.calibration.brier
  return (
    <div className="space-y-4">
      {scopeToggle}
      <p className="text-xs text-muted">
        {scope === 'all' ? 'NFL and college combined. ' : `${SPORT_NAME[sport]} only: each sport's model is judged on its own record and calibration. `}
        Every recommendation is saved at the price shown and graded automatically once its game is final (Sleeper stats
        for props, ESPN scores for games). Voids are players who didn't play. {data.lines_tracked} lines tracked
        {scope === 'all' ? ' in total' : ''}, including no-bet lines used to check calibration.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Tile label="Record" value={settled ? recordText(o) : '—'} />
        <Tile label="Units" value={settled ? `${signed(o.units_profit)}u` : '—'} tone={o.units_profit > 0 ? 'good' : o.units_profit < 0 ? 'bad' : undefined} />
        <Tile label="ROI" value={pct(o.roi)} tone={(o.roi ?? 0) > 0 ? 'good' : (o.roi ?? 0) < 0 ? 'bad' : undefined} />
        <Tile label="Pending" value={String(o.pending)} />
      </div>

      {settled === 0 && (
        <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
          No graded picks yet -- results appear here after this week's games finish. One week is noise; judge the model
          on a few hundred bets, and on calibration below, not on any single week.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {scope === 'all' && data.by_sport && Object.keys(data.by_sport).length > 1 && (
          <SplitTable title="By sport" rows={Object.entries(data.by_sport).map(([k, v]) => [k, v])} />
        )}
        <SplitTable
          title="By confidence"
          rows={(['high', 'strong', 'lean', 'fill'] as const)
            .filter((k) => data.by_confidence[k])
            .map((k) => [k === 'fill' ? 'Best available' : k[0].toUpperCase() + k.slice(1), data.by_confidence[k]])}
        />
        <SplitTable
          title="By market"
          rows={Object.entries(data.by_market).map(([k, v]) => [MARKET_LABELS[k] ?? k, v])}
        />
        <SplitTable title="By week" rows={data.by_week.map((w) => [`Week ${w.week}`, w])} />
        {data.by_engine_version && Object.keys(data.by_engine_version).length > 0 && (
          <SplitTable
            title="By engine version"
            rows={Object.entries(data.by_engine_version).map(([k, v]) => [
              k === data.engine_version ? `${k} (current)` : k,
              v,
            ])}
          />
        )}

        {data.most_likely && data.most_likely.picks > 0 && (
          <div className="bg-surface rounded-lg border border-hairline p-4">
            <h3 className="text-sm font-medium text-body mb-1">Most likely to win</h3>
            <p className="text-xs text-muted">
              {data.most_likely.decided === 0
                ? `${data.most_likely.picks} picks tracked, none graded yet.`
                : `${data.most_likely.decided} graded: we said ${Math.round((data.most_likely.predicted ?? 0) * 100)}% on average, they hit ${Math.round((data.most_likely.actual ?? 0) * 100)}%.`}
              {data.most_likely.pending ? ` ${data.most_likely.pending} pending.` : ''}
            </p>
          </div>
        )}

        <div className="bg-surface rounded-lg border border-hairline p-4">
          <h3 className="text-sm font-medium text-body mb-1">Calibration</h3>
          <p className="text-xs text-muted mb-2">
            When we said a side wins X% of the time, how often did it? Every graded line counts, including no-bet lines.
          </p>
          {data.calibration.lines === 0 ? (
            <p className="text-xs text-faint">Nothing graded yet.</p>
          ) : (
            <>
              <table className="w-full stat-nums text-xs">
                <thead>
                  <tr className="text-faint text-left">
                    <th className="font-normal py-1">Predicted</th>
                    <th className="font-normal text-right">Avg</th>
                    <th className="font-normal text-right">Actual</th>
                    <th className="font-normal text-right">Lines</th>
                  </tr>
                </thead>
                <tbody>
                  {data.calibration.buckets.map((b) => (
                    <tr key={b.range} className="border-t border-hairline">
                      <td className="py-1.5 text-body">{b.range}</td>
                      <td className="text-right text-muted">{pct(b.predicted)}</td>
                      <td className="text-right text-body">{pct(b.actual)}</td>
                      <td className="text-right text-faint">{b.n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="stat-nums text-[11px] text-faint mt-2">
                Brier score (lower is better): blend {brier.blend ?? '—'} · model {brier.model ?? '—'} · market {brier.market ?? '—'}
              </p>
            </>
          )}
        </div>
      </div>

      {data.picks.length > 0 && (
        <div className="bg-surface rounded-lg border border-hairline p-4">
          <h3 className="text-sm font-medium text-body mb-2">Recommendations</h3>
          <div className="divide-y divide-hairline">
            {data.picks.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm text-body truncate">
                    <span className="stat-nums text-xs text-faint mr-2">
                      {p.kind === 'cfb_game' ? 'CFB · ' : ''}W{p.week} · {p.units}u
                    </span>
                    {p.subject}
                  </div>
                  <div className="text-xs text-muted">
                    {MARKET_LABELS[p.market] ?? p.market}: {p.market === 'player_anytime_td' ? 'Anytime TD' : `${p.side} ${p.line ?? ''}`}{' '}
                    <span className="stat-nums">{p.price > 0 ? `+${p.price}` : p.price}</span> at {p.book}
                    {p.actual != null && <span className="text-faint"> · actual {p.actual}</span>}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <span className={`stat-nums text-[10px] uppercase px-1.5 py-0.5 rounded ${STATUS_STYLE[p.status]}`}>{p.status}</span>
                  {p.profit_units != null && p.status !== 'pending' && (
                    <div className={`stat-nums text-xs mt-0.5 ${p.profit_units > 0 ? 'text-success-700' : p.profit_units < 0 ? 'text-danger-700' : 'text-muted'}`}>
                      {signed(p.profit_units)}u
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <BettingAudit />
    </div>
  )
}

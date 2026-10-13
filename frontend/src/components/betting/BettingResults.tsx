import { useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import { ClockIcon } from '@heroicons/react/24/outline'
import { BettingAudit } from './BettingAudit'
import type { BetWeek } from './betTypes'
import { chance, rate, signedNum } from './format'
import { Explainer, Segmented } from './ui'

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
  // Closing-line value: did the market move toward our picks by kickoff?
  clv?: { picks: number; moved: number; beat: number; beat_rate: number | null; avg_prob_move: number | null }
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
const SIZE_NAME = { high: 'Max', strong: 'Medium', lean: 'Small' } as const


const tone = (n: number | null) => ((n ?? 0) > 0 ? 'text-success-700' : (n ?? 0) < 0 ? 'text-danger-700' : 'text-body')

/** This week next to the season: record, units, ROI, pending. */
function PeriodTable({ rows }: { rows: [string, RecordSummary | undefined][] }) {
  return (
    <div className="bg-surface rounded-lg border border-hairline p-4 overflow-x-auto">
      <table className="w-full stat-nums text-xs sm:text-sm [&_th+th]:pl-3 [&_td+td]:pl-3">
        <thead>
          <tr className="text-xs text-faint text-left">
            <th className="font-normal pb-1"></th>
            <th className="font-normal pb-1 text-right">Record</th>
            <th className="font-normal pb-1 text-right">Units</th>
            <th className="font-normal pb-1 text-right">ROI</th>
            <th className="font-normal pb-1 text-right">Open</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, r]) => (
            <tr key={label} className="border-t border-hairline">
              <td className="py-1.5 text-body font-medium whitespace-nowrap">{label}</td>
              {r ? (
                <>
                  <td className="text-right text-body">{r.won + r.lost + r.push ? recordText(r) : '—'}</td>
                  <td className={`text-right ${tone(r.units_profit)}`}>{r.won + r.lost ? `${signedNum(r.units_profit)}u` : '—'}</td>
                  <td className={`text-right ${tone(r.roi)}`}>{rate(r.roi)}</td>
                  <td className="text-right text-muted">{r.pending}</td>
                </>
              ) : (
                <td colSpan={4} className="text-right text-faint">no bets</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function recordText(r: RecordSummary) {
  return `${r.won}-${r.lost}${r.push ? `-${r.push}` : ''}`
}

function SplitTable({ title, rows }: { title: string; rows: [string, RecordSummary][] }) {
  if (rows.length === 0) return null
  return (
    <div>
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
                {signedNum(r.units_profit)}u
              </td>
              <td className="text-right text-muted">{rate(r.roi)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const SPORT_NAME = { nfl: 'NFL', cfb: 'College' } as const

/** Track record for the sport picked at the top of the page (each model is judged on its own). */
export function BettingResults({
  sport,
  current,
  picked,
  onPick,
}: {
  sport: 'nfl' | 'cfb'
  current: BetWeek | null
  picked: BetWeek | null
  onPick: (w: BetWeek) => void
}) {
  const [currentOnly, setCurrentOnly] = useState(false)
  const [data, setData] = useState<Results | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setError('')
    betting.getResults(sport, currentOnly ? 'current' : 'all')
      .then((r) => setData(r.data))
      .catch((err) => setError(getErrorMessage(err, "Couldn't load the track record.")))
      .finally(() => setLoading(false))
  }, [sport, currentOnly])

  const scopeToggle = (
    <Segmented
      label="Model version"
      value={currentOnly}
      options={[
        [false, 'All picks'],
        [true, 'Current model'],
      ]}
      onChange={setCurrentOnly}
    />
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
  const graded = settled > 0 || data.calibration.lines > 0
  const versionName = (k: string) =>
    k === 'pre-versioning' ? 'v0 (before tracking)' : k === data.engine_version ? `${k} (current)` : k
  return (
    <div className="space-y-4">
      {scopeToggle}

      {settled === 0 ? (
        <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
          {o.pending ? `${o.pending} picks pending. ` : ''}Results appear a few hours after each game ends. One week is
          noise: judge the model on a few hundred bets and on calibration, not on any single week.
        </div>
      ) : (
        <PeriodTable
          rows={[
            [
              current ? `Week ${current.week}` : 'This week',
              current ? data.by_week.find((w) => w.season === current.season && w.week === current.week) : undefined,
            ],
            ['Season', o],
          ]}
        />
      )}

      {data.clv && data.clv.moved > 0 && (
        <div className="bg-surface rounded-lg border border-hairline p-4 text-sm">
          <p className="text-body">
            <span className="font-medium">Beat the closing line</span>{' '}
            <span className="text-muted">(games already started):</span>{' '}
            <span className="stat-nums">
              {data.clv.beat} of {data.clv.moved} ({chance(data.clv.beat_rate)})
            </span>
            {data.clv.avg_prob_move != null && (
              <span className={`stat-nums ${data.clv.avg_prob_move > 0 ? 'text-success-700' : 'text-danger-700'}`}>
                {' '}
                · books moved {data.clv.avg_prob_move > 0 ? '+' : ''}
                {(data.clv.avg_prob_move * 100).toFixed(1)} pts toward us on average
              </span>
            )}
          </p>
          <div className="mt-1">
            <Explainer>
            <p>
            The early sign of a real edge: if the market keeps moving toward our picks before kickoff, we're ahead of it,
            long before wins and losses can show it. Above 50% consistently is good.
          </p>
          </Explainer>
          </div>
        </div>
      )}

      <BettingAudit sport={sport} current={current} picked={picked} onPick={onPick} />

      {graded && (
        <details className="bg-surface rounded-lg border border-hairline p-4 group">
          <summary className="cursor-pointer text-sm font-medium text-body list-none flex items-center justify-between">
            Model performance
            <span className="text-xs text-muted group-open:hidden">Show</span>
            <span className="text-xs text-muted hidden group-open:inline">Hide</span>
          </summary>
          <div className="mt-2">
            <Explainer>
            <p>
            {`${SPORT_NAME[sport]} only (switch sport at the top). `}
            Every pick is saved at the price shown and graded from real stats; {data.lines_tracked} lines tracked, including
            lines we passed on, which is what the calibration check uses.
          </p>
          </Explainer>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-5 mt-4">
            <SplitTable
              title="By bet size"
              rows={(['high', 'strong', 'lean', 'fill'] as const)
                .filter((k) => data.by_confidence[k])
                .map((k) => [k === 'fill' ? 'Best available' : SIZE_NAME[k], data.by_confidence[k]])}
            />
            <SplitTable title="By market" rows={Object.entries(data.by_market).map(([k, v]) => [MARKET_LABELS[k] ?? k, v])} />
            <SplitTable title="By week" rows={data.by_week.map((w) => [`Week ${w.week}`, w])} />
            {data.by_engine_version && Object.keys(data.by_engine_version).length > 0 && (
              <SplitTable
                title="By model version"
                rows={Object.entries(data.by_engine_version).map(([k, v]) => [versionName(k), v])}
              />
            )}
            {data.most_likely && data.most_likely.decided > 0 && (
              <div>
                <h3 className="text-sm font-medium text-body mb-1">Safest picks</h3>
                <p className="text-xs text-muted">
                  {data.most_likely.decided} graded: we said {chance(data.most_likely.predicted)} on
                  average, they hit {chance(data.most_likely.actual)}.
                </p>
              </div>
            )}
            {data.calibration.lines > 0 && (
              <div>
                <h3 className="text-sm font-medium text-body mb-1">Calibration</h3>
                <p className="text-xs text-muted mb-2">When we said a side wins X% of the time, how often did it?</p>
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
                        <td className="text-right text-muted">{rate(b.predicted)}</td>
                        <td className="text-right text-body">{rate(b.actual)}</td>
                        <td className="text-right text-faint">{b.n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="stat-nums text-xs text-faint mt-2">
                  Brier score (lower is better): ours {brier.blend ?? '—'} · model alone {brier.model ?? '—'} · books{' '}
                  {brier.market ?? '—'}
                </p>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  )
}

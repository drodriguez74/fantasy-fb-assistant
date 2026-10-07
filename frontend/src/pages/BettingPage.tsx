import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../services/api'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { BettingResults } from '../components/betting/BettingResults'
import { PrizePicksPairs, type PrizePicksBoard } from '../components/betting/PrizePicksPairs'
import { PrizePicksEntries } from '../components/betting/PrizePicksEntries'
import { GameCombos, type GameComboSet } from '../components/betting/GameCombos'
import { ClockIcon, ExclamationTriangleIcon, InformationCircleIcon } from '@heroicons/react/24/outline'

// GET /betting/board -- see backend/app/services/betting_service.py and
// betting_model.py for the method (Monte Carlo + de-vigged market,
// quarter-Kelly units).
interface BoardRow {
  type: 'player_prop' | 'game'
  market: string
  market_label: string
  side: string
  line: number | null
  book: string
  price: number
  model_prob: number
  market_prob: number | null
  p_win: number
  p_push: number
  ev: number
  units: number
  confidence: 'high' | 'strong' | 'lean' | 'none'
  game: string
  kickoff?: string
  books_quoting: number
  // player props
  player?: string
  projection?: number
  market_line?: number | null
  prizepicks_line?: number | null
  projection_outlier?: boolean
  espn_projection?: number | null
  espn_agrees?: boolean
  // Positive EV every source agrees with, too small to size.
  watch?: boolean
  // game lines
  consensus_line?: number
  model_line?: number | null
  check_line?: number | null
}

interface Board {
  available: boolean
  detail?: string
  week?: number
  games_modeled?: number
  generated_at?: string
  player_props?: BoardRow[]
  game_props?: BoardRow[]
  prizepicks?: PrizePicksBoard
  game_combos?: GameComboSet[]
  watch_count?: number
  recommended_count?: number
  evaluated?: { player_props: number; games: number; props_without_projection: number }
  games_without_props?: string[]
  credits_remaining?: number | null
  sources?: { odds: string; projections: string }
  method?: string
  disclaimer: string
}

const CONFIDENCE_STYLE: Record<BoardRow['confidence'], string> = {
  high: 'bg-success-600 text-white',
  strong: 'bg-success-100 text-success-800',
  lean: 'bg-highlight text-accent-ink',
  none: 'bg-surface-2 text-muted',
}

const pct = (p: number | null | undefined) => (p == null ? '—' : `${(p * 100).toFixed(1)}%`)
const price = (p: number) => (p > 0 ? `+${p}` : `${p}`)

function UnitsBadge({ units, confidence, watch }: { units: number; confidence: BoardRow['confidence']; watch?: boolean }) {
  const isWatch = units === 0 && watch
  return (
    <div
      className={`shrink-0 rounded-md px-2.5 py-1.5 text-center ${
        isWatch ? 'border border-accent-ink text-accent-ink' : CONFIDENCE_STYLE[confidence]
      }`}
    >
      <div className="stat-nums text-base font-semibold leading-none">{units > 0 ? `${units}u` : '—'}</div>
      <div className="stat-nums text-[9px] tracking-wider uppercase mt-0.5">
        {isWatch ? 'watch' : confidence === 'none' ? 'no bet' : confidence}
      </div>
    </div>
  )
}

function RowCard({ row }: { row: BoardRow }) {
  const title = row.type === 'player_prop' ? row.player : row.game
  const pick =
    row.market === 'player_anytime_td'
      ? 'Anytime TD'
      : `${row.side} ${row.line != null ? (row.market === 'spread' && row.line > 0 ? `+${row.line}` : row.line) : ''}`
  return (
    <div className={`border border-hairline rounded-lg p-4 bg-surface ${row.projection_outlier ? 'opacity-60' : ''}`}>
      <div className="flex items-start gap-3">
        <UnitsBadge units={row.units} confidence={row.confidence} watch={row.watch} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h4 className="font-medium text-body">{title}</h4>
            <span className="stat-nums text-xs text-faint">{row.type === 'player_prop' ? row.game : row.market_label}</span>
          </div>
          <p className="text-sm text-body mt-0.5">
            {row.type === 'player_prop' && <span className="text-muted">{row.market_label}: </span>}
            <span className="font-semibold">{pick}</span>{' '}
            <span className="stat-nums">{price(row.price)}</span>
            <span className="text-muted"> at {row.book}</span>
          </p>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 stat-nums text-xs">
            <div><span className="text-faint">Win prob </span><span className="text-body">{pct(row.p_win)}</span></div>
            <div><span className="text-faint">Market </span><span className="text-body">{pct(row.market_prob)}</span></div>
            <div><span className="text-faint">Model </span><span className="text-body">{pct(row.model_prob)}</span></div>
            <div>
              <span className="text-faint">EV </span>
              <span className={row.ev > 0 ? 'text-success-700' : 'text-muted'}>{row.ev > 0 ? '+' : ''}{(row.ev * 100).toFixed(1)}%</span>
            </div>
          </div>
          {row.type === 'player_prop' && (
            <p className="stat-nums text-[11px] text-faint mt-1.5">
              Projection {row.projection?.toFixed(1)}
              {row.espn_projection != null && ` · ESPN ${row.espn_projection.toFixed(1)}`}
              {row.market_line != null && ` · market line ${row.market_line}`}
              {row.prizepicks_line != null && ` · PrizePicks ${row.prizepicks_line}`}
              {` · ${row.books_quoting} book${row.books_quoting === 1 ? '' : 's'}`}
            </p>
          )}
          {row.type === 'game' && (
            <p className="stat-nums text-[11px] text-faint mt-1.5">
              Consensus {row.market === 'spread' ? 'home spread' : 'total'} {row.consensus_line}
              {row.model_line != null && ` · model ${row.model_line}`}
              {row.check_line != null && ` · ESPN ${row.check_line}`}
              {row.p_push > 0 && ` · push ${pct(row.p_push)}`} · {row.books_quoting} books
            </p>
          )}
          {row.espn_agrees === false && !row.projection_outlier && (
            <p className="text-[11px] text-warning-700 mt-1">
              ESPN's projection doesn't back this side, so no units. When the two sources split, the edge is usually noise.
            </p>
          )}
          {row.projection_outlier && (
            <p className="text-[11px] text-warning-700 mt-1">
              Don't play this one: the projection is far from the market line, which almost always means the projection is
              stale (role change, injury news), not that the books are wrong. The EV shown is the stale projection talking.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export function BettingPage() {
  const [board, setBoard] = useState<Board | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sport, setSport] = useState<'nfl' | 'cfb'>('nfl')
  const [tab, setTab] = useState<'props' | 'games' | 'college' | 'prizepicks' | 'results'>('props')
  // College board (GET /betting/board?sport=cfb), loaded the first time College is picked.
  const [college, setCollege] = useState<Board | null>(null)
  const [collegeLoading, setCollegeLoading] = useState(false)
  const [collegeError, setCollegeError] = useState('')
  const [recommendedOnly, setRecommendedOnly] = useState(true)
  const [showMethod, setShowMethod] = useState(false)

  const load = useCallback(async (refresh = false) => {
    setLoading(true)
    setError('')
    try {
      const response = await betting.getBoard(refresh)
      setBoard(response.data)
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't load this week's betting board."))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadCollege = useCallback(async (refresh = false) => {
    setCollegeLoading(true)
    setCollegeError('')
    try {
      const response = await betting.getBoard(refresh, 'cfb')
      setCollege(response.data)
    } catch (err) {
      setCollegeError(getErrorMessage(err, "Couldn't load college game lines."))
    } finally {
      setCollegeLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (sport === 'cfb' && !college && !collegeLoading && !collegeError) loadCollege()
  }, [sport, college, collegeLoading, collegeError, loadCollege])

  // College: game lines only (college player props are shelved, and grading is NFL-only).
  const tabs =
    sport === 'cfb' ? (['college'] as const) : (['props', 'games', 'prizepicks', 'results'] as const)
  const TAB_LABELS: Record<'props' | 'games' | 'college' | 'prizepicks' | 'results', string> = {
    props: 'Player props',
    games: 'Game lines',
    college: 'CFB Game Lines',
    prizepicks: 'PrizePicks',
    results: 'Results',
  }
  const switchSport = (next: 'nfl' | 'cfb') => {
    setSport(next)
    setTab(next === 'cfb' ? 'college' : 'props')
  }
  const view = sport === 'cfb' ? college : board
  const viewLoading = sport === 'cfb' ? collegeLoading || (!college && !collegeError) : loading
  const viewError = sport === 'cfb' ? collegeError : error

  const rows = (tab === 'props' ? board?.player_props : tab === 'college' ? college?.game_props : board?.game_props) ?? []
  const shown = recommendedOnly ? rows.filter((r) => r.units > 0 || r.watch) : rows.slice(0, 60)

  return (
    <div className="max-w-5xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-6">
        <div>
          <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Bets</h1>
          <p className="text-muted mt-2">
            Player props and game lines priced by simulation against the market. More units = more confidence.
          </p>
        </div>
        <div className="self-start flex items-center gap-3">
          <div className="flex rounded-lg border border-hairline p-0.5" role="tablist" aria-label="Sport">
            {(['nfl', 'cfb'] as const).map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={sport === s}
                onClick={() => switchSport(s)}
                className={`px-3 py-1.5 rounded-md text-sm ${sport === s ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
              >
                {s === 'nfl' ? 'NFL' : 'College'}
              </button>
            ))}
          </div>
          <button
            onClick={() => (sport === 'cfb' ? loadCollege(true) : load(true))}
            disabled={viewLoading}
            className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="yard-divider mb-6" aria-hidden="true" />

      {view?.disclaimer && (
        <div className="flex gap-3 rounded-lg border border-warning-200 bg-warning-50 px-4 py-3 mb-6">
          <ExclamationTriangleIcon className="h-5 w-5 text-warning-700 shrink-0" />
          <p className="text-xs text-warning-800 leading-relaxed">{view.disclaimer}</p>
        </div>
      )}

      {viewLoading ? (
        <div className="bg-surface rounded-lg shadow p-6 text-center">
          <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
          <p className="text-sm text-muted">{sport === 'cfb' ? 'Pricing college games...' : "Simulating this week's props..."}</p>
        </div>
      ) : viewError || !view?.available ? (
        <div className="bg-surface rounded-lg shadow p-6 text-center">
          <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">{viewError || view?.detail}</p>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 stat-nums text-xs text-muted">
            <span>{sport === 'cfb' ? 'COLLEGE' : `WEEK ${view.week}`}</span>
            <span><span className="text-body font-semibold">{view.recommended_count}</span> recommended</span>
            {view.watch_count != null && <span>{view.watch_count} on watch</span>}
            <span>
              {sport === 'cfb'
                ? `${view.evaluated?.games} games priced · ${view.games_modeled ?? 0} with ESPN's predictor`
                : `${view.evaluated?.player_props} props · ${view.evaluated?.games} games priced`}
            </span>
            {view.credits_remaining != null && <span>{view.credits_remaining} odds credits left</span>}
            <DataConfidenceBadge level="computed" label="Simulated" />
          </div>

          <div className="bg-surface rounded-lg border border-hairline">
            <button
              onClick={() => setShowMethod((v) => !v)}
              className="w-full flex items-center gap-2 px-4 py-3 text-left text-sm text-body"
            >
              <InformationCircleIcon className="h-4 w-4 text-accent-ink" />
              How the units are calculated
              <span className="ml-auto text-xs text-faint">{showMethod ? 'Hide' : 'Show'}</span>
            </button>
            {showMethod && (
              <div className="px-4 pb-4 text-xs text-muted leading-relaxed space-y-2">
                <p>{view.method}</p>
                <p>
                  Win prob is the blended estimate; Market is the de-vigged consensus; Model is the simulation alone.
                  EV is expected profit per unit at the listed price. Lean = 0.5–1u, Strong = 1.5–2u, High = 2.5–3u. Watch = positive EV that every source agrees with, but under the 3% bar, so no units.
                </p>
                <p>Sources: {view.sources?.odds}; {view.sources?.projections}.</p>
                {view.evaluated && view.evaluated.props_without_projection > 0 && (
                  <p>{view.evaluated.props_without_projection} props skipped -- no matching projection (never guessed).</p>
                )}
                {view.games_without_props && view.games_without_props.length > 0 && (
                  <p>Props not loaded for: {view.games_without_props.join(', ')} (odds credit reserve).</p>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline">
            <nav className="-mb-px flex gap-6">
              {tabs.map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`py-2 px-1 border-b-2 text-sm font-medium ${
                    tab === t ? 'border-accent-ink text-accent-ink' : 'border-transparent text-muted hover:text-body'
                  }`}
                >
                  {TAB_LABELS[t]}
                </button>
              ))}
            </nav>
            {(tab === 'props' || tab === 'games' || tab === 'college') && (
            <label className="flex items-center gap-2 text-xs text-muted pb-2">
              <input
                type="checkbox"
                checked={recommendedOnly}
                onChange={(e) => setRecommendedOnly(e.target.checked)}
                className="rounded border-line text-accent-ink focus:ring-volt"
              />
              Bets + watch list
            </label>
            )}
          </div>

          {tab === 'results' ? (
            <BettingResults />
          ) : tab === 'prizepicks' ? (
            <div className="space-y-8">
              <PrizePicksPairs data={view.prizepicks} onUploaded={() => load(true)} />
              <PrizePicksEntries />
            </div>

          ) : shown.length === 0 ? (
            <div className="bg-surface rounded-lg border border-hairline p-6 text-center text-sm text-muted">
              {tab === 'games' || tab === 'college'
                ? 'No game line clears the bar or makes the watch list right now.'
                : 'No player prop clears the bar or makes the watch list right now.'}
              {recommendedOnly && rows.length > 0 && (
                <button onClick={() => setRecommendedOnly(false)} className="block mx-auto mt-2 text-accent-ink underline">
                  Show everything we priced
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {tab === 'college' && (
                <p className="text-xs text-muted leading-relaxed">
                  Spreads use ESPN's predictor at half the NFL weight with a 1u cap until results are graded; totals only
                  flag a sportsbook that's off the others, since nothing projects college totals. College picks aren't
                  tracked in Results yet.
                </p>
              )}
              {shown.map((row, i) => (
                <RowCard key={`${row.game}-${row.player ?? ''}-${row.market}-${i}`} row={row} />
              ))}
            </div>
          )}
          {tab === 'games' && <GameCombos games={view.game_combos} />}
          {tab === 'college' && <GameCombos games={view.game_combos} />}
        </div>
      )}
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../services/api'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { BettingResults } from '../components/betting/BettingResults'
import { PrizePicksPairs } from '../components/betting/PrizePicksPairs'
import { usePrizePicksEntries } from '../components/betting/prizePicksEntriesData'
import { GameCombos } from '../components/betting/GameCombos'
import { BetCard } from '../components/betting/BetCard'
import { ThisWeekCard } from '../components/betting/ThisWeekCard'
import { MyEntries } from '../components/betting/MyEntries'
import { type Board, type BoardRow, type WatchAlert, useBankroll, watchKey } from '../components/betting/betTypes'
import { ClockIcon, ExclamationTriangleIcon, InformationCircleIcon } from '@heroicons/react/24/outline'

// GET /betting/board -- see backend/app/services/betting_service.py and
// betting_model.py for the method (Monte Carlo + de-vigged market,
// quarter-Kelly units). Layout: this week's card (the bets) first, then the
// evidence per tab.

type Tab = 'props' | 'games' | 'college' | 'prizepicks' | 'entries' | 'results'

const TAB_LABELS: Record<Tab, string> = {
  props: 'Player props',
  games: 'Game lines',
  college: 'CFB Game Lines',
  prizepicks: 'PrizePicks',
  entries: 'My entries',
  results: 'Results',
}

// Render's free tier sleeps when idle; the first request can take ~30s.
const SLOW_LOAD_MS = 8000

function Disclaimer({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex gap-2 items-start rounded-lg border border-warning-200 bg-warning-50 px-3 py-2 text-xs text-warning-800">
      <ExclamationTriangleIcon className="h-4 w-4 text-warning-700 shrink-0 mt-px" />
      <p className="leading-relaxed">
        21+ only · model estimates, not guarantees · gambling problem? Call 1-800-GAMBLER.{' '}
        {open ? <span>{text} </span> : null}
        <button onClick={() => setOpen((v) => !v)} className="underline">
          {open ? 'Less' : 'More'}
        </button>
      </p>
    </div>
  )
}

export function BettingPage() {
  const [board, setBoard] = useState<Board | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sport, setSport] = useState<'nfl' | 'cfb'>('nfl')
  const [tab, setTab] = useState<Tab>('props')
  // College board (GET /betting/board?sport=cfb), loaded the first time College is picked.
  const [college, setCollege] = useState<Board | null>(null)
  const [collegeLoading, setCollegeLoading] = useState(false)
  const [collegeError, setCollegeError] = useState('')
  const [recommendedOnly, setRecommendedOnly] = useState(true)
  const [showMethod, setShowMethod] = useState(false)
  const [slow, setSlow] = useState(false)
  const [bankroll, setBankroll] = useBankroll()
  const [alerts, setAlerts] = useState<WatchAlert[]>([])
  const [alertError, setAlertError] = useState('')
  const entries = usePrizePicksEntries()

  const load = useCallback(async (refresh = false) => {
    setLoading(true)
    setError('')
    try {
      const response = await betting.getBoard(refresh)
      setBoard(response.data)
      // A saved board came back while the server rebuilds: swap in the fresh one shortly.
      if (response.data.refreshing) setTimeout(() => load(), 40000)
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
      if (response.data.refreshing) setTimeout(() => loadCollege(), 40000)
    } catch (err) {
      setCollegeError(getErrorMessage(err, "Couldn't load college game lines."))
    } finally {
      setCollegeLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const loadAlerts = useCallback(async () => {
    try {
      setAlerts((await betting.getWatchAlerts()).data.alerts)
    } catch {
      // alerts are a convenience; the board still works without them
    }
  }, [])

  useEffect(() => {
    loadAlerts()
  }, [loadAlerts])

  const alertFor = (row: BoardRow) =>
    alerts.find(
      (a) =>
        watchKey(a.kind, a.subject, a.market, a.side) ===
        watchKey(sport === 'cfb' ? 'cfb_game' : row.type, row.type === 'player_prop' ? row.player ?? '' : row.game, row.market, row.side),
    )

  const toggleAlert = async (row: BoardRow) => {
    setAlertError('')
    const existing = alertFor(row)
    try {
      if (existing) await betting.deleteWatchAlert(existing.id)
      else
        await betting.addWatchAlert({
          sport,
          type: row.type,
          subject: row.type === 'player_prop' ? row.player ?? '' : row.game,
          market: row.market,
          side: row.side,
        })
      await loadAlerts()
    } catch (err) {
      setAlertError(getErrorMessage(err, "Couldn't update that alert."))
    }
  }

  useEffect(() => {
    if (sport === 'cfb' && !college && !collegeLoading && !collegeError) loadCollege()
  }, [sport, college, collegeLoading, collegeError, loadCollege])

  // College: game lines + the shared Results (college player props are shelved).
  const tabs: readonly Tab[] = sport === 'cfb' ? ['college', 'results'] : ['props', 'games', 'prizepicks', 'entries', 'results']
  const switchSport = (next: 'nfl' | 'cfb') => {
    setSport(next)
    setTab(next === 'cfb' ? 'college' : 'props')
  }
  const view = sport === 'cfb' ? college : board
  const viewLoading = sport === 'cfb' ? collegeLoading || (!college && !collegeError) : loading
  const viewError = sport === 'cfb' ? collegeError : error

  // After a few seconds of a first load, say why it's slow instead of spinning silently.
  useEffect(() => {
    if (!viewLoading) {
      setSlow(false)
      return
    }
    const timer = setTimeout(() => setSlow(true), SLOW_LOAD_MS)
    return () => clearTimeout(timer)
  }, [viewLoading])

  const rows = (tab === 'props' ? board?.player_props : tab === 'college' ? college?.game_props : board?.game_props) ?? []
  const shown = recommendedOnly ? rows.filter((r) => r.units > 0 || r.watch) : rows.slice(0, 60)

  return (
    <div className="max-w-5xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Bets</h1>
          <p className="text-muted text-sm mt-1">Priced by simulation against the market. More units = more confidence.</p>
        </div>
        <div className="flex items-center gap-3">
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
            {viewLoading && view ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {view?.disclaimer && (
        <div className="mb-5">
          <Disclaimer text={view.disclaimer} />
        </div>
      )}

      {viewLoading && !view ? (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
          <p className="text-sm text-muted">{sport === 'cfb' ? 'Pricing college games...' : "Pricing this week's bets..."}</p>
          {slow && (
            <p className="text-xs text-faint mt-2">
              Waking up the odds server. The first load after a quiet spell can take about 30 seconds.
            </p>
          )}
        </div>
      ) : viewError && !view ? (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">{viewError}</p>
        </div>
      ) : !view?.available ? (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">{view?.detail}</p>
        </div>
      ) : (
        <div className="space-y-5">
          <ThisWeekCard
            board={view}
            entries={sport === 'nfl' ? entries : undefined}
            bankroll={bankroll}
            setBankroll={setBankroll}
            onOpen={(t) => {
              setTab(t)
              // The tabs sit below the card: bring them into view.
              requestAnimationFrame(() => document.getElementById('bets-tabs')?.scrollIntoView({ behavior: 'smooth' }))
            }}
          />

          <div id="bets-tabs" className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline scroll-mt-4">
            <nav className="-mb-px flex gap-5 overflow-x-auto">
              {tabs.map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`py-2 px-1 border-b-2 text-sm font-medium whitespace-nowrap ${
                    tab === t ? 'border-accent-ink text-accent-ink' : 'border-transparent text-muted hover:text-body'
                  }`}
                >
                  {TAB_LABELS[t]}
                </button>
              ))}
            </nav>
            {(tab === 'props' || tab === 'games' || tab === 'college') && (
              <div className="flex rounded-lg border border-hairline p-0.5 mb-2 text-xs" role="tablist" aria-label="Which lines">
                {([true, false] as const).map((v) => (
                  <button
                    key={String(v)}
                    role="tab"
                    aria-selected={recommendedOnly === v}
                    onClick={() => setRecommendedOnly(v)}
                    className={`px-2.5 py-1 rounded-md ${recommendedOnly === v ? 'bg-surface-2 text-body font-medium' : 'text-muted'}`}
                  >
                    {v ? 'Recommended' : 'All lines'}
                  </button>
                ))}
              </div>
            )}
          </div>

          {tab === 'results' ? (
            <BettingResults sport={sport} />
          ) : tab === 'entries' ? (
            <MyEntries
              players={[
                ...new Set([
                  ...(board?.player_props ?? []).map((r) => r.player ?? ''),
                  ...(board?.prizepicks?.legs ?? []).map((l) => l.player),
                  ...(board?.prizepicks?.goblins ?? []).map((l) => l.player),
                  ...(board?.prizepicks?.demons ?? []).map((l) => l.player),
                ]),
              ]
                .filter(Boolean)
                .sort()}
            />
          ) : tab === 'prizepicks' ? (
            <PrizePicksPairs data={view.prizepicks} onUploaded={() => load(true)} entries={entries} />
          ) : shown.length === 0 ? (
            <div className="bg-surface rounded-lg border border-hairline p-6 text-center text-sm text-muted">
              {tab === 'props' ? 'No player prop clears the bar or makes the watch list right now.' : 'No game line clears the bar or makes the watch list right now.'}
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
                  flag a sportsbook that's off the others, since nothing projects college totals.
                </p>
              )}
              {alertError && <p className="text-xs text-warning-700">{alertError}</p>}
              {shown.map((row, i) => (
                <BetCard
                  key={`${row.game}-${row.player ?? ''}-${row.market}-${i}`}
                  row={row}
                  bankroll={bankroll}
                  alert={alertFor(row)}
                  onToggleAlert={toggleAlert}
                />
              ))}
            </div>
          )}
          {(tab === 'games' || tab === 'college') && <GameCombos games={view.game_combos} />}

          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 stat-nums text-xs text-faint pt-2">
            <span>{sport === 'cfb' ? 'College' : `Week ${view.week}`}</span>
            {view.refreshing && <span>Updated {view.saved_age_minutes} min ago · refreshing</span>}
            <span>
              {sport === 'cfb'
                ? `${view.evaluated?.games} games · ${view.games_modeled ?? 0} with ESPN's predictor`
                : `${view.evaluated?.player_props} props · ${view.evaluated?.games} games priced`}
            </span>
            {view.credits_remaining != null && <span>{view.credits_remaining} odds credits left</span>}
            {/* Free-tier credits: odds_service.PROP_REFRESH_WEEKDAYS */}
            {view.evaluated?.player_props ? <span>Props refresh Wed &amp; Sun</span> : null}
            <DataConfidenceBadge level="computed" label="Simulated" />
          </div>

          <div className="bg-surface rounded-lg border border-hairline">
            <button
              onClick={() => setShowMethod((v) => !v)}
              className="w-full flex items-center gap-2 px-4 py-3 text-left text-sm text-body"
              aria-expanded={showMethod}
            >
              <InformationCircleIcon className="h-4 w-4 text-accent-ink" />
              How the picks and units work
              <span className="ml-auto text-xs text-faint">{showMethod ? 'Hide' : 'Show'}</span>
            </button>
            {showMethod && (
              <div className="px-4 pb-4 text-xs text-muted leading-relaxed space-y-2">
                <p>{view.method}</p>
                <p>
                  "To win" is our blended chance; "Books" is the sportsbooks' chance with their cut removed. EV is expected
                  profit per dollar at the listed price. Sizes: Small = 0.5–1u, Medium = 1.5–2u, Max = 2.5–3u (1u = 1% of
                  your bankroll). Watch = a small edge every source agrees on, but under the 3% bar, so no units. "Still a
                  bet at" is the worst price that keeps the bet above the bar if the line moves.
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
        </div>
      )}
    </div>
  )
}

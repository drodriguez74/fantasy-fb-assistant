import { useCallback, useEffect, useState } from 'react'
import { betting, getErrorMessage } from '../services/api'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { BettingResults } from '../components/betting/BettingResults'
import { PrizePicksPairs } from '../components/betting/PrizePicksPairs'
import { usePrizePicksEntries } from '../components/betting/prizePicksEntriesData'
import { GameCombos } from '../components/betting/GameCombos'
import { GameSlate } from '../components/betting/GameSlate'
import { BetCard } from '../components/betting/BetCard'
import { BankrollInput, ThisWeekCard } from '../components/betting/ThisWeekCard'
import { ShowMore } from '../components/betting/ShowMore'
import { MyEntries } from '../components/betting/MyEntries'
import { PlayerSearch } from '../components/betting/PlayerSearch'
import { ShowPicks } from '../components/betting/ShowPicks'
import { onAirFor, useShowPicks } from '../components/betting/showTypes'
import { type BetWeek, type Board, type BoardRow, type WatchAlert, matchesQuery, useBankroll, watchKey } from '../components/betting/betTypes'
import { ClockIcon, ExclamationTriangleIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
import { Explainer, Segmented } from '../components/betting/ui'

// GET /betting/board -- see backend/app/services/betting_service.py and
// betting_model.py for the method (Monte Carlo + de-vigged market,
// quarter-Kelly units). Layout: this week's card (the bets) first, then the
// evidence per tab.

// Tabs follow the weekly loop (2026-10-09 review): act first (PrizePicks, the
// shows' picks), then monitor (the watch list), then review (your entries,
// the model's record). The bets themselves live in This week's best bets.
type Tab = 'prizepicks' | 'shows' | 'watch' | 'entries' | 'track'

const TAB_LABELS: Record<Tab, [string, string]> = {
  // [full label, phone label]: all five fit at 390px without scrolling.
  prizepicks: ['PrizePicks', 'PrizePicks'],
  shows: ['Shows', 'Shows'],
  // Every game graded (spread + total), then the player-prop watch list.
  watch: ['Lines', 'Lines'],
  entries: ['My entries', 'Entries'],
  track: ['Track record', 'Record'],
}

// Render's free tier sleeps when idle; the first request can take ~30s.
const SLOW_LOAD_MS = 8000

// One muted line (2026-10-12 review): the routine notice, not a warning box.
function Disclaimer({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <p className="text-xs text-faint leading-relaxed">
      21+ only · model estimates, not guarantees · gambling problem? Call 1-800-GAMBLER.{' '}
      {open ? <span>{text} </span> : null}
      <button onClick={() => setOpen((v) => !v)} className="underline hover:text-muted">
        {open ? 'Less' : 'More'}
      </button>
    </p>
  )
}

export function BettingPage() {
  const [board, setBoard] = useState<Board | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sport, setSport] = useState<'nfl' | 'cfb'>('nfl')
  const [tab, setTab] = useState<Tab>('prizepicks')
  // Lines tab: every game graded, or sportsbook player props (college has games only).
  const [lines, setLines] = useState<'props' | 'games'>('games')
  const [showInfo, setShowInfo] = useState(false)
  // College board (GET /betting/board?sport=cfb), loaded the first time College is picked.
  const [college, setCollege] = useState<Board | null>(null)
  const [collegeLoading, setCollegeLoading] = useState(false)
  const [collegeError, setCollegeError] = useState('')
  // Play lists what isn't a bet (the bets live in This week's best bets): the watch list, or every other line.
  const [playView, setPlayView] = useState<'watch' | 'all'>('watch')
  const [query, setQuery] = useState('')
  // Radio/podcast picks: the Shows tab and the "On air" note on board cards.
  const showPicks = useShowPicks()
  // The NFL betting week (Thu-Mon) everything is filed under, college included.
  const currentWeek: BetWeek | null = board?.season && board?.week ? { season: board.season, week: board.week } : null
  // One week for Shows, My entries and the Audit: picking it on one tab keeps it on the others (null = each tab's default).
  const [pickedWeek, setPickedWeek] = useState<BetWeek | null>(null)
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
  const switchSport = (next: 'nfl' | 'cfb') => {
    setSport(next)
    setTab(next === 'cfb' ? 'shows' : 'prizepicks')
  }
  const view = sport === 'cfb' ? college : board
  const viewLoading = sport === 'cfb' ? collegeLoading || (!college && !collegeError) : loading
  const viewError = sport === 'cfb' ? collegeError : error
  // Without lines (Monday night until Wednesday's props, or no key) the record, shows and
  // entries still show: only PrizePicks and Lines need a priced board.
  const linesUp = !!view?.available
  const allTabs: readonly Tab[] = sport === 'cfb' ? ['shows', 'watch', 'track'] : ['prizepicks', 'shows', 'watch', 'entries', 'track']
  const tabs = linesUp ? allTabs : allTabs.filter((t) => t !== 'prizepicks' && t !== 'watch')
  const activeTab: Tab = tabs.includes(tab) ? tab : tabs[0]

  // After a few seconds of a first load, say why it's slow instead of spinning silently.
  useEffect(() => {
    if (!viewLoading) {
      setSlow(false)
      return
    }
    const timer = setTimeout(() => setSlow(true), SLOW_LOAD_MS)
    return () => clearTimeout(timer)
  }, [viewLoading])

  const showingGames = sport === 'cfb' || lines === 'games'
  const rows = (sport === 'cfb' ? college?.game_props : lines === 'props' ? board?.player_props : board?.game_props) ?? []
  const betRows = rows.filter((r) => r.units > 0)
  const watchRows = rows.filter((r) => r.units === 0 && r.watch)
  // A search looks through every priced line, bets included, not just the first 60.
  const searching = query.trim() !== ''
  const shown = searching
    ? rows.filter((r) => matchesQuery(query, r.player, r.game, r.home, r.away))
    : playView === 'watch'
      ? watchRows
      : rows.filter((r) => r.units === 0)
  const kind = showingGames ? 'game line' : 'player prop'
  const card = (row: BoardRow, i: number) => (
    <BetCard
      key={`${row.game}-${row.player ?? ''}-${row.market}-${i}`}
      row={row}
      bankroll={bankroll}
      alert={alertFor(row)}
      onToggleAlert={toggleAlert}
      onAir={onAirFor(row, showPicks.shows)}
    />
  )

  return (
    <div className="max-w-5xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Bets</h1>
        </div>
        <div className="flex items-center gap-3">
          <Segmented
            label="Sport"
            size="md"
            value={sport}
            options={[
              ['nfl', 'NFL'],
              ['cfb', 'College'],
            ]}
            onChange={switchSport}
          />
          <button
            onClick={() => setShowInfo((v) => !v)}
            aria-expanded={showInfo}
            aria-label="About this board"
            className={`p-2 rounded-lg border ${showInfo ? 'border-line text-body' : 'border-hairline text-muted hover:text-body'}`}
          >
            <InformationCircleIcon className="h-5 w-5" />
          </button>
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
        <div className="mb-3">
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
      ) : !view ? null : (
        <div className="space-y-5">
          {!view.available && (
            <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
              <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
              <p className="text-sm text-muted">{view.detail}</p>
            </div>
          )}
          {view.available && showInfo && (
            <div className="rounded-lg border border-hairline bg-surface p-4 text-xs text-muted leading-relaxed space-y-2">
              <p className="stat-nums flex flex-wrap gap-x-4 gap-y-1">
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
              </p>
              <BankrollInput bankroll={bankroll} onChange={setBankroll} />
              <p>{view.method}</p>
              <p>
                "To win" is our blended chance; "Books" is the sportsbooks' chance with their cut removed. Edge is expected
                profit per $1 at the listed price. 1u = 1% of your bankroll. Watch = a small edge every source leans toward,
                not enough for units. "Good down to" is the worst price that still clears the bar if the line moves.
              </p>
              <p>Sources: {view.sources?.odds}; {view.sources?.projections}.</p>
              {view.evaluated && view.evaluated.props_without_projection > 0 && (
                <p>{view.evaluated.props_without_projection} props skipped: no matching projection (never guessed).</p>
              )}
              {view.games_without_props && view.games_without_props.length > 0 && (
                <p>Props not loaded for: {view.games_without_props.join(', ')} (odds credit reserve).</p>
              )}
            </div>
          )}

          {view.available && (
            <ThisWeekCard
              board={view}
              renderBet={card}
              entries={sport === 'nfl' ? entries : undefined}
              bankroll={bankroll}
              hideLinks={activeTab === 'prizepicks'}
              onOpen={(t) => {
                setTab(t)
                // The tabs sit below the card: bring them into view.
                requestAnimationFrame(() => document.getElementById('bets-tabs')?.scrollIntoView({ behavior: 'smooth' }))
              }}
            />
          )}

          <nav
            id="bets-tabs"
            className={`-mb-px grid sm:flex sm:gap-5 border-b border-hairline scroll-mt-4 ${({ 2: 'grid-cols-2', 3: 'grid-cols-3', 5: 'grid-cols-5' } as Record<number, string>)[tabs.length] ?? 'grid-cols-3'}`}
            aria-label="Bets sections"
          >
            {tabs.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                aria-current={activeTab === t ? 'page' : undefined}
                className={`py-2 px-1 border-b-2 text-xs sm:text-sm font-medium whitespace-nowrap text-center ${
                  activeTab === t ? 'border-accent-ink text-accent-ink' : 'border-transparent text-muted hover:text-body'
                }`}
              >
                <span className="sm:hidden">{TAB_LABELS[t][1]}</span>
                <span className="hidden sm:inline">{TAB_LABELS[t][0]}</span>
              </button>
            ))}
          </nav>

          {activeTab === 'track' ? (
            <BettingResults sport={sport} current={currentWeek} picked={pickedWeek} onPick={setPickedWeek} />
          ) : activeTab === 'shows' ? (
            <ShowPicks
              shows={showPicks.shows}
              error={showPicks.error}
              onRetry={showPicks.reload}
              current={currentWeek}
              picked={pickedWeek}
              onPick={setPickedWeek}
              sport={sport}
              rows={sport === 'cfb' ? college?.game_props ?? [] : [...(board?.player_props ?? []), ...(board?.game_props ?? [])]}
            />
          ) : activeTab === 'entries' ? (
            <MyEntries
              current={currentWeek}
              picked={pickedWeek}
              onPick={setPickedWeek}
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
          ) : activeTab === 'prizepicks' ? (
            <PrizePicksPairs
              data={view.prizepicks}
              onUploaded={() => load(true)}
              entries={entries}
              mostLikely={view.most_likely}
            />
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                {sport === 'nfl' ? (
                  <Segmented
                    label="Bet type"
                    value={lines}
                    options={[
                      ['games', 'Games'],
                      ['props', 'Player props'],
                    ]}
                    onChange={setLines}
                  />
                ) : (
                  <p className="text-sm text-body font-medium">College games</p>
                )}
                <Segmented
                  label="Which lines"
                  value={playView}
                  options={[
                    ['watch', 'Bets & watch'],
                    ['all', 'All'],
                  ]}
                  onChange={setPlayView}
                />
              </div>
              <PlayerSearch
                value={query}
                onChange={setQuery}
                placeholder={showingGames ? 'Search a team' : 'Search a player or team'}
                count={searching ? shown.length : undefined}
              />
              {sport === 'cfb' && (
                <Explainer>
                  <p>
                  College lines are market-only: a bet shows only when Hard Rock's price beats the other books' consensus.
                  ESPN's predictor is shown for reference; over the 2025 season it added nothing to the line.
                </p>
                </Explainer>
              )}
              {alertError && <p className="text-xs text-warning-700">{alertError}</p>}
              {/* Games: one graded card per game replaces the per-side cards. */}
              {showingGames ? (
                <GameSlate
                  rows={rows.filter((r) => matchesQuery(query, r.game, r.home, r.away))}
                  onlyAction={playView === 'watch' && !searching}
                  alertFor={alertFor}
                  onToggleAlert={toggleAlert}
                />
              ) : !searching && (
                <p className="text-xs text-muted">
                  {playView === 'watch'
                    ? 'Not bets yet. Tap one to get an alert if its price gets good enough.'
                    : 'Every other line we priced, best first.'}
                  {betRows.length === 0 && ` No ${kind} clears the bar right now.`}
                </p>
              )}
              {showingGames ? null : shown.length === 0 ? (
                <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
                  {searching
                    ? `No ${kind} matches "${query.trim()}" on this board.`
                    : playView === 'watch'
                      ? `Nothing on the ${kind} watch list right now.`
                      : `No other ${kind}s priced right now.`}
                </div>
              ) : (
                <ShowMore items={shown} limit={20} render={card} as="div" className="space-y-3" noun="more lines" />
              )}
              {showingGames && <GameCombos games={view.game_combos} />}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

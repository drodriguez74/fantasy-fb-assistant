import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { api, getErrorMessage } from '../services/api'
import { LeagueScoringSettings } from '../components/leagues/LeagueScoringSettings'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { LineupWaiverCard, TeamNeedsStrip } from '../components/waivers/LineupWaivers'
import { ThisWeekTab } from '../components/leagues/detail/ThisWeekTab'
import { RosterTab } from '../components/leagues/detail/RosterTab'
import { MatchupsTab } from '../components/leagues/detail/MatchupsTab'
import { TradesTab } from '../components/leagues/detail/TradesTab'
import { StandingsTab } from '../components/leagues/detail/StandingsTab'
import { getGradeColor } from '../components/leagues/detail/display'
import {
  STALE_RETRY_DELAYS_MS,
  type ByeWeekRadarData,
  type LeagueInfo,
  type LeagueTab,
  type MatchupHistoryData,
  type RosterAnalysis,
  type StandingsData,
  type StandingsTeam,
  type ThisWeekData,
  type TradeRecommendation,
  type WaiverRecommendation,
} from '../components/leagues/detail/types'
import {
  UserGroupIcon,
  TrophyIcon,
  ArrowsRightLeftIcon,
  ArrowLeftIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  FireIcon,
  StarIcon,
  AdjustmentsHorizontalIcon,
  CalendarDaysIcon
} from '@heroicons/react/24/outline'

export function LeagueDetailPage() {
  const { leagueId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [searchParams] = useSearchParams()

  const TABS: LeagueTab[] = ['this-week', 'roster', 'matchups', 'standings', 'waiver', 'trades', 'scoring']
  const tabParam = searchParams.get('tab')
  const [activeTab, setActiveTab] = useState<LeagueTab>(
    TABS.includes(tabParam as LeagueTab) ? (tabParam as LeagueTab) : 'this-week'
  )
  const [leagueInfo, setLeagueInfo] = useState<LeagueInfo | null>(null)
  const [rosterAnalysis, setRosterAnalysis] = useState<RosterAnalysis | null>(null)
  const [waiverRecs, setWaiverRecs] = useState<WaiverRecommendation | null>(null)
  const [tradeRecs, setTradeRecs] = useState<TradeRecommendation | null>(null)
  const [standingsData, setStandingsData] = useState<StandingsData | null>(null)
  const [thisWeek, setThisWeek] = useState<ThisWeekData | null>(null)
  const [thisWeekLoading, setThisWeekLoading] = useState(false)
  const [thisWeekError, setThisWeekError] = useState('')
  const [matchupHistory, setMatchupHistory] = useState<MatchupHistoryData | null>(null)
  const [matchupHistoryLoading, setMatchupHistoryLoading] = useState(false)
  const [matchupHistoryError, setMatchupHistoryError] = useState('')
  const [byeWeekRadar, setByeWeekRadar] = useState<ByeWeekRadarData | null>(null)
  const [byeWeekRadarLoading, setByeWeekRadarLoading] = useState(false)
  const [byeWeekRadarError, setByeWeekRadarError] = useState('')
  const [showOptimal, setShowOptimal] = useState(false)
  const [lineupView, setLineupView] = useState<'mine' | 'matchup'>('mine')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [waiverLoading, setWaiverLoading] = useState(true)
  const [tradeLoading, setTradeLoading] = useState(true)
  const [waiverError, setWaiverError] = useState('')
  const [tradeError, setTradeError] = useState('')
  // Bumped on every (re)load so a stale in-flight request from a previous
  // leagueId / React StrictMode double-invoke can't write into state.
  const reqIdRef = useRef(0)

  const loadLeagueData = useCallback(async (force = false) => {
    const reqId = ++reqIdRef.current
    const isCurrent = () => reqIdRef.current === reqId
    const rq = force ? '&refresh=1' : ''

    setLoading(true)
    setError('')
    setWaiverError('')
    setTradeError('')
    setWaiverLoading(true)
    setTradeLoading(true)

    // The page renders progressively: roster / standings are the "core"
    // bundle the header + most tabs need, so only those block the
    // page-level spinner. Waiver + trade recommendations (which internally
    // make slow live ESPN/Yahoo calls, and honestly 400 for Sleeper) fill
    // in their own sections afterwards without holding up the rest.
    // (The old /insights fetch was dropped along with the Overview tab --
    // it only ever fed that tab's "Weekly Insights" card, and the endpoint
    // itself is an honest not-yet-computed stub with no real content.)
    void (async () => {
      const [rosterResult, standingsResult] = await Promise.allSettled([
        api.get(`/leagues/${leagueId}/roster-analysis?_=1${rq}`),
        api.get(`/leagues/${leagueId}/standings?season=2025${rq}`),
      ])
      if (!isCurrent()) return

      const firstRejection = [rosterResult, standingsResult].find((r) => r.status === 'rejected')
      if (firstRejection && firstRejection.status === 'rejected') {
        setError(getErrorMessage(firstRejection.reason, 'Failed to load league data'))
        setLoading(false)
        return
      }

      const rosterResponse = (rosterResult as PromiseFulfilledResult<{ data: { league_info: LeagueInfo; roster_analysis: RosterAnalysis } }>).value
      const standingsResponse = (standingsResult as PromiseFulfilledResult<{ data: { teams: StandingsTeam[] } }>).value

      setLeagueInfo(rosterResponse.data.league_info)
      setRosterAnalysis(rosterResponse.data.roster_analysis)

      // Identify "your" team by the real team name this league's roster
      // analysis was computed for, rather than a hardcoded name.
      const userTeamName: string | undefined = rosterResponse.data.roster_analysis?.team_name

      const teams: StandingsTeam[] = standingsResponse.data.teams
      setStandingsData({
        teams,
        user_team_rank: teams.find((team) => team.team_name === userTeamName)?.rank ?? 0,
        total_teams: teams.length,
        playoff_teams: 6,
        updated_at: new Date().toISOString()
      })

      setLoading(false)
    })()

    // Independent, non-blocking: waiver recommendations.
    api.get(`/leagues/${leagueId}/waiver-recommendations`)
      .then((waiverResponse) => {
        if (!isCurrent()) return
        setWaiverRecs({
          recommendations: waiverResponse.data.waiver_recommendations?.recommendations ?? [],
          position_needs: waiverResponse.data.waiver_recommendations?.position_needs ?? {},
          team_needs: waiverResponse.data.waiver_recommendations?.team_needs,
          watch_only: waiverResponse.data.waiver_recommendations?.watch_only,
          basis: waiverResponse.data.waiver_recommendations?.basis,
          total_available: waiverResponse.data.waiver_recommendations?.total_available ?? 0,
          updated_at: waiverResponse.data.waiver_recommendations?.updated_at ?? new Date().toISOString()
        })
      })
      .catch((err) => {
        if (!isCurrent()) return
        setWaiverError(getErrorMessage(err, 'Waiver recommendations are unavailable for this league right now.'))
      })
      .finally(() => {
        if (isCurrent()) setWaiverLoading(false)
      })

    // Independent, non-blocking: trade suggestions.
    api.get(`/leagues/${leagueId}/trade-suggestions`)
      .then((tradeResponse) => {
        if (!isCurrent()) return
        setTradeRecs({
          suggestions: tradeResponse.data.trade_recommendations?.suggestions ?? [],
          trade_deadline: tradeResponse.data.trade_recommendations?.trade_deadline ?? "Week 13",
          updated_at: tradeResponse.data.trade_recommendations?.updated_at ?? new Date().toISOString(),
          basis: tradeResponse.data.trade_recommendations?.basis,
          team_needs: tradeResponse.data.trade_recommendations?.team_needs
        })
      })
      .catch((err) => {
        if (!isCurrent()) return
        setTradeError(getErrorMessage(err, 'Trade suggestions are unavailable for this league right now.'))
      })
      .finally(() => {
        if (isCurrent()) setTradeLoading(false)
      })
  }, [leagueId])

  useEffect(() => {
    if (user && leagueId) {
      loadLeagueData()
    }
  }, [user, leagueId, loadLeagueData])

  // The This Week payload pulls a live ESPN weekly box score. The backend
  // now serves a stored snapshot instantly (stale-while-revalidate) and
  // refreshes in the background, so the first open is fast; when it hands
  // back a stale copy (`_cache.stale`) we silently re-poll to pick up the
  // freshly-synced version, with backoff (7s/15s/30s) rather than a single
  // fixed retry -- a cold Render instance (free tier sleeps after ~15min
  // idle) can take longer than a few seconds to wake up AND finish the
  // live ESPN fetch, and one missed retry previously meant the stale copy
  // (e.g. last night's pre-game 0-0) just sat there until the user
  // manually reloaded or hit Refresh.
  const staleRetryCountRef = useRef(0)
  const loadThisWeek = useCallback(async (force = false, silent = false) => {
    if (!silent) {
      setThisWeekLoading(true)
      setThisWeekError('')
    }
    try {
      const res = await api.get(`/leagues/${leagueId}/this-week${force ? '?refresh=1' : ''}`)
      setThisWeek(res.data)
      if (res.data?._cache?.stale && staleRetryCountRef.current < STALE_RETRY_DELAYS_MS.length) {
        const delay = STALE_RETRY_DELAYS_MS[staleRetryCountRef.current]
        staleRetryCountRef.current += 1
        setTimeout(() => { void loadThisWeek(false, true) }, delay)
      } else if (!res.data?._cache?.stale) {
        staleRetryCountRef.current = 0
      }
    } catch (err) {
      if (!silent) {
        setThisWeekError(getErrorMessage(err, 'This Week is unavailable for this league right now.'))
      }
    } finally {
      if (!silent) setThisWeekLoading(false)
    }
  }, [leagueId])

  useEffect(() => {
    if (user && leagueId && activeTab === 'this-week' && !thisWeek && !thisWeekLoading && !thisWeekError) {
      loadThisWeek()
    }
  }, [user, leagueId, activeTab, thisWeek, thisWeekLoading, thisWeekError, loadThisWeek])

  // Season schedule/history -- fetched lazily the first time the Matchups
  // tab is opened, same pattern as This Week (a live ESPN call per week
  // played, cached server-side via the same snapshot mechanism).
  const loadMatchupHistory = useCallback(async (force = false) => {
    setMatchupHistoryLoading(true)
    setMatchupHistoryError('')
    try {
      const res = await api.get(`/leagues/${leagueId}/matchup-history${force ? '?refresh=1' : ''}`)
      setMatchupHistory(res.data)
    } catch (err) {
      setMatchupHistoryError(getErrorMessage(err, 'Matchup history is unavailable for this league right now.'))
    } finally {
      setMatchupHistoryLoading(false)
    }
  }, [leagueId])

  useEffect(() => {
    if (user && leagueId && activeTab === 'matchups' && !matchupHistory && !matchupHistoryLoading && !matchupHistoryError) {
      loadMatchupHistory()
    }
  }, [user, leagueId, activeTab, matchupHistory, matchupHistoryLoading, matchupHistoryError, loadMatchupHistory])

  // Real upcoming byes, fetched lazily the first time the Roster tab is
  // opened -- same snapshot-backed pattern as Matchups. See
  // espn_service_enhanced.get_bye_week_radar's docstring for why this
  // couldn't ship earlier (a real espn_api bug made every future-week bye
  // lookup wrong; fixed 2026-09-15 by not depending on box_scores at all).
  const loadByeWeekRadar = useCallback(async (force = false) => {
    setByeWeekRadarLoading(true)
    setByeWeekRadarError('')
    try {
      const res = await api.get(`/leagues/${leagueId}/bye-week-radar${force ? '?refresh=1' : ''}`)
      setByeWeekRadar(res.data)
    } catch (err) {
      setByeWeekRadarError(getErrorMessage(err, 'Bye week radar is unavailable for this league right now.'))
    } finally {
      setByeWeekRadarLoading(false)
    }
  }, [leagueId])

  useEffect(() => {
    if (user && leagueId && activeTab === 'roster' && !byeWeekRadar && !byeWeekRadarLoading && !byeWeekRadarError) {
      loadByeWeekRadar()
    }
  }, [user, leagueId, activeTab, byeWeekRadar, byeWeekRadarLoading, byeWeekRadarError, loadByeWeekRadar])

  const refreshData = async () => {
    staleRetryCountRef.current = 0
    setThisWeekError('')
    await Promise.all([
      loadLeagueData(true),
      activeTab === 'this-week' ? loadThisWeek(true) : Promise.resolve(),
      activeTab === 'matchups' ? loadMatchupHistory(true) : Promise.resolve(),
      activeTab === 'roster' ? loadByeWeekRadar(true) : Promise.resolve(),
    ])
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-faint" />
          <h3 className="mt-2 text-sm font-medium text-body">Authentication Required</h3>
          <p className="mt-1 text-sm text-muted">Please sign in to view league details.</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-ink mr-4"></div>
          <div>
            <h3 className="text-lg font-medium text-body">Loading league analysis</h3>
            <p className="text-sm text-muted">Pulling your roster, standings, and matchups.</p>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="bg-danger-50 border border-danger-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-danger-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-danger-800">Error Loading League</h3>
              <div className="mt-2 text-sm text-danger-700">{error}</div>
              <div className="mt-4">
                <button
                  onClick={() => navigate('/leagues')}
                  className="bg-danger-100 text-danger-800 px-4 py-2 rounded-md text-sm hover:bg-danger-200 transition-colors"
                >
                  Back to Leagues
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const tabs = [
    { id: 'this-week', name: 'This Week', icon: CalendarDaysIcon },
    { id: 'roster', name: 'Roster Analysis', icon: UserGroupIcon },
    { id: 'matchups', name: 'Matchups', icon: TrophyIcon },
    { id: 'standings', name: 'Standings', icon: StarIcon },
    { id: 'waiver', name: 'Waiver Wire', icon: FireIcon },
    { id: 'trades', name: 'Trade Center', icon: ArrowsRightLeftIcon },
    { id: 'scoring', name: 'Scoring', icon: AdjustmentsHorizontalIcon },
  ]


  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center space-x-3 min-w-0">
            <button
              onClick={() => navigate('/leagues')}
              className="p-2 -ml-2 shrink-0 text-faint hover:text-muted"
            >
              <ArrowLeftIcon className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <h1 className="font-display font-bold uppercase tracking-tight text-2xl sm:text-3xl text-body break-words">{leagueInfo?.name}</h1>
              <p className="text-muted">
                {leagueInfo?.platform} • {leagueInfo?.season} • {leagueInfo?.league_size} Teams • {leagueInfo?.scoring_format}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {rosterAnalysis && (
              <span className="inline-flex items-center gap-2">
                <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getGradeColor(rosterAnalysis.overall_grade?.grade || 'N/A')}`}>
                  Team Grade: {rosterAnalysis.overall_grade?.grade || 'N/A'}
                </span>
                <DataConfidenceBadge level={rosterAnalysis.overall_grade?.grade && rosterAnalysis.overall_grade.grade !== 'N/A' ? 'computed' : 'insufficient'} />
              </span>
            )}
            <button
              onClick={refreshData}
              className="bg-volt text-volt-ink px-4 py-2 rounded-md hover:bg-volt-dark transition-colors flex items-center space-x-2 focus:outline-none focus:ring-2 focus:ring-volt"
            >
              <ClockIcon className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-hairline mb-6">
        <nav className="-mb-px flex gap-6 overflow-x-auto no-scrollbar">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as LeagueTab)}
                className={`shrink-0 whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'border-accent-ink text-accent-ink'
                    : 'border-transparent text-muted hover:text-body hover:border-line'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.name}</span>
              </button>
            )
          })}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'this-week' && thisWeekLoading && (
        <div className="bg-surface rounded-lg border border-hairline p-10 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-ink mx-auto mb-3" />
          <p className="text-sm text-muted">Pulling this week&apos;s matchup and projections from ESPN.</p>
        </div>
      )}

      {activeTab === 'this-week' && !thisWeekLoading && thisWeekError && (
        <div className="bg-surface rounded-lg border border-hairline p-8 text-center">
          <CalendarDaysIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">{thisWeekError}</p>
        </div>
      )}

      {activeTab === 'this-week' && !thisWeekLoading && !thisWeekError && thisWeek && !thisWeek.platform_supported && (
        <div className="bg-surface rounded-lg border border-hairline p-8 text-center">
          <CalendarDaysIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">{thisWeek.detail || 'This Week is only available for ESPN leagues today.'}</p>
        </div>
      )}

      {activeTab === 'this-week' && !thisWeekLoading && !thisWeekError && thisWeek && thisWeek.platform_supported && !thisWeek.matchup && (
        <div className="bg-surface rounded-lg border border-hairline p-8 text-center">
          <CalendarDaysIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">{thisWeek.detail || 'This week’s matchup isn’t available yet.'}</p>
        </div>
      )}

      {activeTab === 'this-week' && !thisWeekLoading && !thisWeekError && thisWeek?.platform_supported && thisWeek.matchup && (
        <ThisWeekTab setActiveTab={setActiveTab} waiverRecs={waiverRecs} thisWeek={thisWeek} showOptimal={showOptimal} setShowOptimal={setShowOptimal} lineupView={lineupView} setLineupView={setLineupView} />
      )}

      {activeTab === 'roster' && rosterAnalysis && (
        <RosterTab rosterAnalysis={rosterAnalysis} byeWeekRadar={byeWeekRadar} byeWeekRadarLoading={byeWeekRadarLoading} byeWeekRadarError={byeWeekRadarError} />
      )}

      {activeTab === 'matchups' && (
        <MatchupsTab matchupHistory={matchupHistory} matchupHistoryLoading={matchupHistoryLoading} matchupHistoryError={matchupHistoryError} />
      )}

      {activeTab === 'waiver' && !waiverRecs && (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <FireIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">
            {waiverError || (waiverLoading ? 'Loading waiver recommendations…' : 'No waiver recommendations for this league right now.')}
          </p>
        </div>
      )}

      {activeTab === 'waiver' && waiverRecs && (
        <div className="space-y-6">
          {waiverRecs.team_needs && waiverRecs.team_needs.length > 0 && <TeamNeedsStrip needs={waiverRecs.team_needs} />}
          <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="text-lg font-medium text-body">Waiver Wire Recommendations</h3>
              <DataConfidenceBadge level="computed" label="Lineup impact" />
            </div>
            <p className="text-sm text-muted mb-6">
              {waiverRecs.watch_only
                ? 'No free agent is a clear upgrade on your roster right now. Best available at your weakest spots:'
                : waiverRecs.basis || 'Based on your roster needs and available players.'}
            </p>

            <div className="space-y-4">
              {waiverRecs.recommendations.slice(0, 10).map((rec, index: number) => (
                <LineupWaiverCard key={`waiver-${rec.player.name}-${index}`} rec={rec} />
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'trades' && !tradeRecs && (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <ArrowsRightLeftIcon className="mx-auto h-8 w-8 text-faint mb-2" />
          <p className="text-sm text-muted">
            {tradeError || (tradeLoading ? 'Loading trade suggestions…' : 'No trade suggestions for this league right now.')}
          </p>
        </div>
      )}

      {activeTab === 'trades' && tradeRecs && (
        <TradesTab tradeRecs={tradeRecs} />
      )}

      {activeTab === 'standings' && standingsData && (
        <StandingsTab rosterAnalysis={rosterAnalysis} standingsData={standingsData} />
      )}

      {activeTab === 'scoring' && leagueId && (
        <div className="space-y-6">
          {/* leagueId (the route param, not leagueInfo.id) is this app's own
              UserLeague row id -- what every other call on this page
              (standings/insights/roster-analysis above) already scopes
              itself by. leagueInfo.id isn't reliably the same value: for a
              connected ESPN league, GET /leagues/{id}/roster-analysis
              overwrites its own league_info.id with ESPN's platform league
              id instead (see leagues.py), which is not what POST
              /league-scoring/configure expects for user_league_id. */}
          <LeagueScoringSettings leagueId={Number(leagueId)} />
        </div>
      )}
    </div>
  )
}
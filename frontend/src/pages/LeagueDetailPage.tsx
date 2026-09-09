import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { api, getErrorMessage } from '../services/api'
import { LeagueScoringSettings } from '../components/leagues/LeagueScoringSettings'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import {
  ChartBarIcon,
  UserGroupIcon,
  TrophyIcon,
  ArrowsRightLeftIcon,
  ArrowLeftIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ClockIcon,
  FireIcon,
  StarIcon,
  AdjustmentsHorizontalIcon,
  BoltIcon,
  CalendarDaysIcon
} from '@heroicons/react/24/outline'

interface LeagueInfo {
  id: number
  name: string
  platform: string
  season: number
  scoring_format: string
  league_size: number
}

interface RosterPlayer {
  name: string
  position?: string
  team?: string
  total_points?: number
  projected_points?: number
  injury_status?: string
}

interface PositionAnalysisEntry {
  grade: string
  summary?: string
  recommendations?: string[]
}

interface RosterAnalysis {
  team_name?: string
  owner?: string
  roster_size?: number
  total_players: number
  position_analysis?: Record<string, PositionAnalysisEntry>
  composition?: {
    starting_lineup: RosterPlayer[]
    bench_players: RosterPlayer[]
    composition_score: number
  }
  overall_grade: {
    grade: string
    score: number
    description: string
    player_count?: number
    avg_player_value?: number
  }
  strengths_weaknesses?: {
    strengths: string[]
    weaknesses: string[]
  }
  strengths?: string[]
  weaknesses?: string[]
  players?: RosterPlayer[]
  injury_concerns?: { player: string; position?: string; team?: string; status?: string }[]
  last_updated?: string
}

interface WaiverRecommendationItem {
  player: {
    name: string
    position?: { value?: string }
    projected_points?: number
  }
  reason?: string
  priority?: number
}

interface WaiverRecommendation {
  recommendations: WaiverRecommendationItem[]
  position_needs: Record<string, number>
  total_available: number
  updated_at: string
}

interface TradeSuggestion {
  target?: { name?: string }
  target_player?: string
  offer_players: string[]
  likelihood?: string
  reasoning?: string
}

interface TradeRecommendation {
  suggestions: TradeSuggestion[]
  trade_deadline: string
  updated_at: string
}

interface MatchupTeam {
  name?: string
  points?: number
}

interface MatchupData {
  week: number
  user_team: MatchupTeam
  opponent_team: MatchupTeam
  ai_analysis: string
  updated_at: string
}

interface StandingsTeam {
  rank: number
  name?: string
  team_name?: string
  wins?: number
  losses?: number
  points_for?: number
  points_against?: number
}

interface StandingsData {
  teams: StandingsTeam[]
  user_team_rank: number
  total_teams: number
  playoff_teams: number
  updated_at: string
}

interface LeagueInsights {
  weekly_outlook?: { key_points?: string[] }
  pickup_targets?: Array<{ player: string; position?: string }>
}

interface ThisWeekPlayer {
  name: string
  position?: string
  slot_position?: string
  team?: string
  pro_opponent?: string
  injury_status?: string
  projected_points?: number
  points?: number
  game_played?: number
  on_bye?: boolean
}

interface ThisWeekSwap {
  slot?: string
  bench_out: { name: string; position?: string; projected_points?: number }
  start_in: { name: string; position?: string; team?: string; projected_points?: number }
  delta: number
}

interface ThisWeekMatchupSide {
  team_name?: string
  live_score?: number
  projected_score?: number
  wins?: number
  losses?: number
  ties?: number
  rank?: number
}

interface ThisWeekData {
  league_info?: LeagueInfo
  platform_supported: boolean
  detail?: string
  week?: number
  matchup?: {
    my_team: ThisWeekMatchupSide
    opponent: ThisWeekMatchupSide
    projected_margin: number
    favored: 'my_team' | 'opponent' | 'even'
  }
  lineup?: ThisWeekPlayer[]
  optimization?: {
    current_projected: number
    optimized_projected: number
    points_gained: number
    swaps: ThisWeekSwap[]
  }
  starter_injuries?: { name: string; position?: string; status?: string }[]
}

export function LeagueDetailPage() {
  const { leagueId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [searchParams] = useSearchParams()

  type LeagueTab = 'this-week' | 'overview' | 'roster' | 'matchups' | 'standings' | 'waiver' | 'trades' | 'scoring'
  const TABS: LeagueTab[] = ['this-week', 'overview', 'roster', 'matchups', 'standings', 'waiver', 'trades', 'scoring']
  const tabParam = searchParams.get('tab')
  const [activeTab, setActiveTab] = useState<LeagueTab>(
    TABS.includes(tabParam as LeagueTab) ? (tabParam as LeagueTab) : 'this-week'
  )
  const [leagueInfo, setLeagueInfo] = useState<LeagueInfo | null>(null)
  const [rosterAnalysis, setRosterAnalysis] = useState<RosterAnalysis | null>(null)
  const [waiverRecs, setWaiverRecs] = useState<WaiverRecommendation | null>(null)
  const [tradeRecs, setTradeRecs] = useState<TradeRecommendation | null>(null)
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null)
  const [standingsData, setStandingsData] = useState<StandingsData | null>(null)
  const [insights, setInsights] = useState<LeagueInsights | null>(null)
  const [thisWeek, setThisWeek] = useState<ThisWeekData | null>(null)
  const [thisWeekLoading, setThisWeekLoading] = useState(false)
  const [thisWeekError, setThisWeekError] = useState('')
  const [showOptimal, setShowOptimal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [waiverLoading, setWaiverLoading] = useState(true)
  const [tradeLoading, setTradeLoading] = useState(true)
  const [waiverError, setWaiverError] = useState('')
  const [tradeError, setTradeError] = useState('')
  // Bumped on every (re)load so a stale in-flight request from a previous
  // leagueId / React StrictMode double-invoke can't write into state.
  const reqIdRef = useRef(0)

  const loadLeagueData = useCallback(async () => {
    const reqId = ++reqIdRef.current
    const isCurrent = () => reqIdRef.current === reqId

    setLoading(true)
    setError('')
    setWaiverError('')
    setTradeError('')
    setWaiverLoading(true)
    setTradeLoading(true)

    // The page renders progressively: roster / standings / insights are the
    // "core" bundle the header + most tabs need, so only those block the
    // page-level spinner. Waiver + trade recommendations (which internally
    // make slow live ESPN/Yahoo calls, and honestly 400 for Sleeper) fill
    // in their own sections afterwards without holding up the rest.
    void (async () => {
      const [rosterResult, standingsResult, insightsResult] = await Promise.allSettled([
        api.get(`/leagues/${leagueId}/roster-analysis`),
        api.get(`/leagues/${leagueId}/standings?season=2025`),
        api.get(`/leagues/${leagueId}/insights`)
      ])
      if (!isCurrent()) return

      const firstRejection = [rosterResult, standingsResult, insightsResult].find((r) => r.status === 'rejected')
      if (firstRejection && firstRejection.status === 'rejected') {
        setError(getErrorMessage(firstRejection.reason, 'Failed to load league data'))
        setLoading(false)
        return
      }

      const rosterResponse = (rosterResult as PromiseFulfilledResult<{ data: { league_info: LeagueInfo; roster_analysis: RosterAnalysis } }>).value
      const standingsResponse = (standingsResult as PromiseFulfilledResult<{ data: { teams: StandingsTeam[] } }>).value
      const insightsResponse = (insightsResult as PromiseFulfilledResult<{ data: { insights: LeagueInsights } }>).value

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

      setInsights(insightsResponse.data.insights)
      setMatchupData(null)
      setLoading(false)
    })()

    // Independent, non-blocking: waiver recommendations.
    api.get(`/leagues/${leagueId}/waiver-recommendations`)
      .then((waiverResponse) => {
        if (!isCurrent()) return
        setWaiverRecs({
          recommendations: waiverResponse.data.waiver_recommendations?.recommendations ?? [],
          position_needs: waiverResponse.data.waiver_recommendations?.position_needs ?? {},
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
          updated_at: tradeResponse.data.trade_recommendations?.updated_at ?? new Date().toISOString()
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

  // The This Week payload pulls a live ESPN weekly box score (slower than
  // the other calls), so it's fetched lazily the first time that tab is
  // opened rather than blocking the initial page load.
  const loadThisWeek = useCallback(async () => {
    setThisWeekLoading(true)
    setThisWeekError('')
    try {
      const res = await api.get(`/leagues/${leagueId}/this-week`)
      setThisWeek(res.data)
    } catch (err) {
      setThisWeekError(getErrorMessage(err, 'This Week is unavailable for this league right now.'))
    } finally {
      setThisWeekLoading(false)
    }
  }, [leagueId])

  useEffect(() => {
    if (user && leagueId && activeTab === 'this-week' && !thisWeek && !thisWeekLoading && !thisWeekError) {
      loadThisWeek()
    }
  }, [user, leagueId, activeTab, thisWeek, thisWeekLoading, thisWeekError, loadThisWeek])

  const refreshData = async () => {
    setThisWeek(null)
    setThisWeekError('')
    await loadLeagueData()
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
    { id: 'overview', name: 'Overview', icon: ChartBarIcon },
    { id: 'roster', name: 'Roster Analysis', icon: UserGroupIcon },
    { id: 'matchups', name: 'Matchups', icon: TrophyIcon },
    { id: 'standings', name: 'Standings', icon: StarIcon },
    { id: 'waiver', name: 'Waiver Wire', icon: FireIcon },
    { id: 'trades', name: 'Trade Center', icon: ArrowsRightLeftIcon },
    { id: 'scoring', name: 'Scoring', icon: AdjustmentsHorizontalIcon },
  ]

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A': return 'bg-success-100 text-success-800'
      case 'B': return 'bg-highlight text-accent-ink'
      case 'C': return 'bg-warning-100 text-warning-800'
      case 'D': return 'bg-warning-200 text-warning-900'
      case 'F': return 'bg-danger-100 text-danger-800'
      default: return 'bg-surface-2 text-body'
    }
  }

  // Real per-player status straight from the connected platform (ESPN's
  // injuryStatus) -- "Out"/"Injury Reserve" etc. are genuine alerts worth
  // surfacing; a merely active/normal player is not.
  const formatStatusLabel = (status?: string) =>
    (status || '').replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())

  const getStatusColor = (status?: string) => {
    const s = (status || '').toUpperCase()
    if (s === 'OUT' || s === 'INJURY_RESERVE' || s === 'IR' || s === 'SUSPENDED') return 'bg-danger-100 text-danger-800'
    if (s === 'DOUBTFUL') return 'bg-danger-50 text-danger-700'
    if (s === 'QUESTIONABLE') return 'bg-warning-100 text-warning-800'
    return 'bg-surface-2 text-body'
  }

  const POSITION_COLORS: Record<string, string> = {
    QB: 'bg-ink-800 text-white',
    RB: 'bg-success-100 text-success-800',
    WR: 'bg-highlight text-accent-ink',
    TE: 'bg-warning-100 text-warning-800',
    K: 'bg-surface-2 text-body',
    DEF: 'bg-ink-200 text-body',
    'D/ST': 'bg-ink-200 text-body',
  }
  const getPositionColor = (position?: string) => POSITION_COLORS[position || ''] || 'bg-surface-2 text-body'

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

      {activeTab === 'this-week' && !thisWeekLoading && !thisWeekError && thisWeek?.platform_supported && thisWeek.matchup && (() => {
        const m = thisWeek.matchup!
        const opt = thisWeek.optimization
        const lineup = thisWeek.lineup ?? []
        const BENCH = new Set(['BE', 'IR', 'BENCH', ''])
        const starters = lineup.filter((p) => !BENCH.has((p.slot_position || '').toUpperCase()))
        const bench = lineup.filter((p) => BENCH.has((p.slot_position || '').toUpperCase()))
        const swapOutNames = new Set((opt?.swaps ?? []).map((s) => s.bench_out.name))
        const swapInNames = new Set((opt?.swaps ?? []).map((s) => s.start_in.name))
        const rec = (side: ThisWeekMatchupSide) =>
          side.wins != null ? `${side.wins}–${side.losses}${side.ties ? `–${side.ties}` : ''}` : null
        const fmtRank = (n?: number) => (n ? `#${n}` : null)
        // Field-position marker: 0 = dead even, clamp the projected margin to
        // a +/-30 pt visual range so a blowout projection doesn't peg the
        // marker off the bar.
        const margin = m.projected_margin || 0
        const markerPct = 50 + Math.max(-30, Math.min(30, margin)) / 30 * 42

        const renderRow = (p: ThisWeekPlayer, isBench: boolean) => {
          const flaggedOut = swapOutNames.has(p.name)
          const flaggedIn = swapInNames.has(p.name)
          const highlight = showOptimal && (flaggedOut || flaggedIn)
          const injured = !['ACTIVE', 'NORMAL', 'HEALTHY', ''].includes((p.injury_status || '').toUpperCase())
          return (
            <div
              key={`tw-${isBench ? 'bn' : 'st'}-${p.name}`}
              className={`grid grid-cols-[3rem_1fr_auto] sm:grid-cols-[3.5rem_1fr_7rem_4rem] items-center gap-2 px-3 py-2.5 border-b border-hairline text-sm ${
                highlight ? 'bg-highlight border-l-2 border-l-volt' : ''
              }`}
            >
              <span className="stat-nums text-xs text-muted">{(p.slot_position || '').toUpperCase()}</span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`shrink-0 inline-flex items-center justify-center w-9 h-6 rounded text-[11px] font-semibold ${getPositionColor(p.position)}`}>
                    {p.position || '—'}
                  </span>
                  <span className="font-medium text-body truncate">{p.name}</span>
                  {injured && (
                    <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${getStatusColor(p.injury_status)}`}>
                      {formatStatusLabel(p.injury_status)}
                    </span>
                  )}
                </div>
                {showOptimal && flaggedOut && (
                  <p className="stat-nums text-[11px] text-accent-ink mt-1">
                    &#9662; bench &mdash; swap in {(opt?.swaps ?? []).find((s) => s.bench_out.name === p.name)?.start_in.name}
                  </p>
                )}
                {showOptimal && flaggedIn && (
                  <p className="stat-nums text-[11px] text-accent-ink mt-1">&#9656; start at {(opt?.swaps ?? []).find((s) => s.start_in.name === p.name)?.slot}</p>
                )}
              </div>
              <span className="hidden sm:block stat-nums text-xs text-muted">
                {p.pro_opponent || (p.on_bye ? 'BYE' : '—')}
              </span>
              <span className="stat-nums text-sm text-body text-right tabular-nums">
                {p.projected_points != null ? p.projected_points.toFixed(1) : '—'}
              </span>
            </div>
          )
        }

        return (
          <div className="space-y-6">
            {/* MATCHUP SCOREBOARD */}
            <div className="bg-surface rounded-lg border border-hairline overflow-hidden">
              <div className="p-6">
                <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-4 sm:gap-8">
                  <div>
                    <div className="stat-nums text-xs text-muted">
                      MY TEAM{rec(m.my_team) ? ` · ${rec(m.my_team)}` : ''}{fmtRank(m.my_team.rank) ? ` · ${fmtRank(m.my_team.rank)}` : ''}
                    </div>
                    <div className="font-display font-bold uppercase tracking-tight text-2xl sm:text-3xl text-body mt-1">
                      {m.my_team.team_name || 'My Team'}
                    </div>
                  </div>
                  <div className="font-display font-semibold tracking-[0.16em] text-sm text-faint pb-1">
                    WK {thisWeek.week}
                  </div>
                  <div className="text-right">
                    <div className="stat-nums text-xs text-muted">
                      {rec(m.opponent) || ''}{fmtRank(m.opponent.rank) ? ` · ${fmtRank(m.opponent.rank)}` : ''} {m.opponent.team_name ? `· ${m.opponent.team_name}` : ''}
                    </div>
                    <div className="font-display font-bold uppercase tracking-tight text-2xl sm:text-3xl text-muted mt-1">
                      {m.opponent.team_name || 'Opponent'}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 sm:gap-8 mt-4">
                  <div className="font-display font-bold text-4xl sm:text-5xl leading-none text-body">
                    {(m.my_team.projected_score ?? 0).toFixed(1)}
                  </div>
                  <div className="text-center">
                    <div className="font-display font-semibold tracking-[0.14em] text-xs text-muted">PROJECTED</div>
                    <div className="font-display font-bold text-2xl sm:text-3xl leading-none text-accent-ink mt-1">
                      {margin > 0 ? '+' : ''}{margin.toFixed(1)}
                    </div>
                  </div>
                  <div className="font-display font-bold text-4xl sm:text-5xl leading-none text-muted text-right">
                    {(m.opponent.projected_score ?? 0).toFixed(1)}
                  </div>
                </div>

                {/* FIELD-POSITION BAR */}
                <div className="mt-4">
                  <div
                    className="relative h-8 rounded-sm border border-hairline overflow-hidden"
                    style={{ background: 'var(--field)' }}
                  >
                    <div className="absolute inset-y-0 left-0 w-[10%]" style={{ background: 'var(--field-endzone)' }} />
                    <div className="absolute inset-y-0 right-0 w-[10%]" style={{ background: 'var(--field-endzone-alt)' }} />
                    {[20, 30, 40, 50, 60, 70, 80].map((x) => (
                      <div key={x} className="absolute inset-y-0 w-px" style={{ left: `${x}%`, background: 'var(--field-line)' }} />
                    ))}
                    <div className="absolute inset-y-0 w-px" style={{ left: '50%', background: 'var(--line)' }} />
                    <div
                      className="absolute inset-y-0 w-0.5"
                      style={{ left: `${markerPct}%`, background: 'var(--color-volt)' }}
                    />
                  </div>
                  <div className="flex justify-between mt-1.5">
                    <span className="stat-nums text-[10px] text-accent-ink">
                      {m.favored === 'my_team' ? `◄ ${m.my_team.team_name || 'MY TEAM'} FAVORED BY ${Math.abs(margin).toFixed(1)}` : ''}
                    </span>
                    <span className="stat-nums text-[10px] text-faint">
                      {m.favored === 'opponent' ? `${m.opponent.team_name || 'OPPONENT'} FAVORED BY ${Math.abs(margin).toFixed(1)} ►` : ''}
                      {m.favored === 'even' ? 'EVEN MATCHUP' : ''}
                    </span>
                  </div>
                </div>
              </div>

              {/* OPTIMIZE ACTION */}
              <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between px-6 py-4 border-t border-hairline bg-surface-2">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowOptimal((v) => !v)}
                    className="bg-volt text-volt-ink px-4 py-2 rounded-md hover:bg-volt-dark transition-colors flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-volt text-sm font-medium"
                  >
                    <BoltIcon className="h-4 w-4" />
                    <span>{showOptimal ? 'Hide optimal lineup' : 'Optimize lineup'}</span>
                  </button>
                  <span className="stat-nums text-xs text-muted">
                    {opt && opt.swaps.length > 0 ? (
                      <>Found <span className="text-accent-ink">{opt.swaps.length} upgrade{opt.swaps.length > 1 ? 's' : ''}</span> &mdash; projected <span className="text-accent-ink">+{opt.points_gained.toFixed(1)} pts</span> ({opt.current_projected.toFixed(1)} &rarr; {opt.optimized_projected.toFixed(1)})</>
                    ) : (
                      <>Your lineup is already the highest-projecting legal set ({opt?.current_projected.toFixed(1)} pts).</>
                    )}
                  </span>
                </div>
                <DataConfidenceBadge level="computed" label="ESPN weekly proj" />
              </div>
            </div>

            {/* BODY: lineup + rail */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-6">
              <div className="bg-surface rounded-lg border border-hairline overflow-hidden">
                <div className="grid grid-cols-[3rem_1fr_auto] sm:grid-cols-[3.5rem_1fr_7rem_4rem] gap-2 px-3 py-2 border-b border-hairline stat-nums text-[10px] tracking-wider text-faint">
                  <span>SLOT</span><span>PLAYER</span><span className="hidden sm:block">MATCHUP</span><span className="text-right">PROJ</span>
                </div>
                {starters.map((p) => renderRow(p, false))}
                {bench.length > 0 && (
                  <>
                    <div className="stat-nums text-[10px] text-faint px-3 pt-3 pb-1 tracking-wider">BENCH</div>
                    {bench.map((p) => renderRow(p, true))}
                  </>
                )}
              </div>

              {/* CALL RAIL */}
              <div className="space-y-3">
                <div className="font-display font-bold tracking-[0.1em] text-accent-ink">LINEUP CALL</div>
                <div className="yard-divider" />

                {opt && opt.swaps.length > 0 ? (
                  opt.swaps.map((s, i) => (
                    <div key={`swap-${i}`} className="border border-hairline bg-surface rounded-lg">
                      <div className="px-4 py-2.5 border-b border-hairline flex items-center justify-between">
                        <span className="stat-nums text-[10px] tracking-wider text-muted">LINEUP UPGRADE</span>
                        <span className="stat-nums text-[10px] text-accent-ink">+{s.delta.toFixed(1)} PTS</span>
                      </div>
                      <div className="p-4">
                        <div className="text-sm font-medium text-body leading-snug">
                          Start <span className="text-accent-ink">{s.start_in.name}</span> over {s.bench_out.name}{s.slot ? ` at ${s.slot}` : ''}.
                        </div>
                        <div className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">
                          {s.start_in.name} projects {s.start_in.projected_points?.toFixed(1)} this week vs {s.bench_out.name}&apos;s {s.bench_out.projected_points?.toFixed(1)} &mdash; a {s.delta.toFixed(1)}-point swing on ESPN&apos;s own weekly projection.
                        </div>
                        <button
                          onClick={() => setShowOptimal(true)}
                          className="mt-3 stat-nums text-[11px] text-accent-ink hover:underline"
                        >
                          Show in lineup &#9656;
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="border border-hairline bg-surface rounded-lg p-4">
                    <div className="flex items-center gap-2">
                      <CheckCircleIcon className="h-4 w-4 text-success-500" />
                      <span className="text-sm font-medium text-body">Lineup is optimal</span>
                    </div>
                    <p className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">
                      No bench player out-projects a current starter at a slot they&apos;re eligible for.
                    </p>
                  </div>
                )}

                {thisWeek.starter_injuries && thisWeek.starter_injuries.length > 0 && (
                  <div className="border border-hairline bg-surface rounded-lg">
                    <div className="px-4 py-2.5 border-b border-hairline">
                      <span className="stat-nums text-[10px] tracking-wider text-warning-700">STARTER STATUS</span>
                    </div>
                    <div className="p-4 space-y-2">
                      {thisWeek.starter_injuries.map((inj, i) => (
                        <div key={`inj-${i}`} className="flex items-center justify-between">
                          <span className="text-sm text-body">{inj.name} <span className="text-xs text-muted">{inj.position}</span></span>
                          <span className={`stat-nums text-[10px] px-1.5 py-0.5 rounded font-medium ${getStatusColor(inj.status)}`}>
                            {formatStatusLabel(inj.status)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {waiverRecs && waiverRecs.recommendations.length > 0 && (
                  <div className="border border-hairline bg-surface rounded-lg">
                    <div className="px-4 py-2.5 border-b border-hairline flex items-center justify-between">
                      <span className="stat-nums text-[10px] tracking-wider text-muted">TOP WAIVER TARGET</span>
                      <button onClick={() => setActiveTab('waiver')} className="stat-nums text-[10px] text-accent-ink hover:underline">All &#9656;</button>
                    </div>
                    <div className="p-4">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center justify-center w-9 h-6 rounded text-[11px] font-semibold ${getPositionColor(waiverRecs.recommendations[0].player.position?.value)}`}>
                          {waiverRecs.recommendations[0].player.position?.value || '—'}
                        </span>
                        <span className="text-sm font-medium text-body">{waiverRecs.recommendations[0].player.name}</span>
                      </div>
                      {waiverRecs.recommendations[0].reason && (
                        <p className="stat-nums text-[11px] text-muted mt-2 leading-relaxed">{waiverRecs.recommendations[0].reason}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })()}

      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center">
                <TrophyIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Team Rank</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {standingsData?.user_team_rank || 'N/A'}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center">
                <UserGroupIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Roster Grade</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {rosterAnalysis?.overall_grade?.grade || 'N/A'}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center">
                <ExclamationTriangleIcon className="h-8 w-8 text-danger-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Injuries</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {rosterAnalysis?.injury_concerns?.length || 0}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center">
                <FireIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Waiver Targets</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {waiverRecs?.recommendations?.length || 0}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Player Alerts -- real injury/availability status pulled directly
              from the connected platform for every rostered player. This app
              has no real per-player news source (a prior attempt at one
              turned out to fabricate canned text, so it was deliberately
              disabled) -- this is the honest substitute: real status
              changes, not invented headlines. */}
          {rosterAnalysis?.injury_concerns && rosterAnalysis.injury_concerns.length > 0 && (
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <h3 className="text-lg font-medium text-body mb-1 flex items-center gap-2">
                <ExclamationTriangleIcon className="h-5 w-5 text-danger-500" />
                Player Alerts
              </h3>
              <p className="text-sm text-muted mb-4">
                Real status changes for your rostered players, from {leagueInfo?.platform || 'your platform'}.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {rosterAnalysis.injury_concerns.map((concern, index) => (
                  <div
                    key={`alert-${concern.player}-${index}`}
                    className="flex items-center justify-between p-3 border border-danger-100 bg-danger-50/40 rounded-lg"
                  >
                    <div>
                      <p className="text-sm font-medium text-body">{concern.player}</p>
                      <p className="text-xs text-muted">{concern.position} • {concern.team}</p>
                    </div>
                    <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${getStatusColor(concern.status)}`}>
                      {formatStatusLabel(concern.status)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Your Roster -- condensed starting lineup, so the Overview tab
              actually shows who's on the team instead of only aggregate
              numbers. Full roster + bench detail still lives on the Roster
              Analysis tab. */}
          {rosterAnalysis?.composition?.starting_lineup && rosterAnalysis.composition.starting_lineup.length > 0 && (
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium text-body">Your Roster</h3>
                <span className="text-sm text-muted">{rosterAnalysis.team_name}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {rosterAnalysis.composition.starting_lineup.map((player, index) => {
                  const alert = rosterAnalysis.injury_concerns?.find((c) => c.player === player.name)
                  return (
                    <div
                      key={`overview-starter-${player.name}-${index}`}
                      className="flex items-center gap-3 p-3 bg-surface-2 rounded-lg"
                    >
                      <span className={`shrink-0 inline-flex items-center justify-center w-10 h-8 rounded text-xs font-semibold ${getPositionColor(player.position)}`}>
                        {player.position || '—'}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-body truncate">{player.name}</p>
                        <p className="text-xs text-muted">{player.team || 'FA'}</p>
                      </div>
                      {alert && (
                        <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${getStatusColor(alert.status)}`}>
                          {formatStatusLabel(alert.status)}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Weekly Insights */}
          {insights && (
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <h3 className="text-lg font-medium text-body mb-4">Weekly Insights</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h4 className="font-medium text-body mb-2">Weekly Outlook</h4>
                  <div className="space-y-2">
                    {insights.weekly_outlook?.key_points?.map((point: string, index: number) => (
                      <div key={`weekly-point-${index}-${point.slice(0, 20)}`} className="flex items-start space-x-2">
                        <CheckCircleIcon className="h-4 w-4 text-success-500 mt-0.5" />
                        <span className="text-sm text-muted">{point}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <h4 className="font-medium text-body mb-2">Top Pickup Targets</h4>
                  <div className="space-y-2">
                    {insights.pickup_targets?.slice(0, 3).map((target, index: number) => (
                      <div key={`pickup-${target.player}-${index}`} className="flex items-center justify-between">
                        <span className="text-sm font-medium text-body">{target.player}</span>
                        <span className="text-xs text-muted">{target.position}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Current Matchup Preview */}
          {matchupData && (
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <h3 className="text-lg font-medium text-body mb-4">Week {matchupData.week} Matchup</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="text-center">
                  <h4 className="font-medium text-accent-ink">Your Team</h4>
                  <p className="text-lg font-bold">{matchupData.user_team?.name || 'Your Team'}</p>
                  <p className="text-sm text-muted">{matchupData.user_team?.points || 0} points</p>
                </div>
                <div className="text-center">
                  <h4 className="font-medium text-danger-600">Opponent</h4>
                  <p className="text-lg font-bold">{matchupData.opponent_team?.name || 'Opponent'}</p>
                  <p className="text-sm text-muted">{matchupData.opponent_team?.points || 0} points</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'roster' && rosterAnalysis && (
        <div className="space-y-6">
          {/* Roster Summary */}
          <div className="bg-surface rounded-lg border border-hairline p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-medium text-body">Roster Analysis</h3>
                <p className="text-sm text-muted">
                  {rosterAnalysis.team_name} • {rosterAnalysis.total_players} players
                </p>
              </div>
              <span className="inline-flex items-center gap-2">
                <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getGradeColor(rosterAnalysis.overall_grade?.grade || 'N/A')}`}>
                  Grade: {rosterAnalysis.overall_grade?.grade || 'N/A'}
                </span>
                <DataConfidenceBadge level={rosterAnalysis.overall_grade?.grade && rosterAnalysis.overall_grade.grade !== 'N/A' ? 'computed' : 'insufficient'} />
              </span>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-medium text-success-700 mb-2">Strengths</h4>
                <ul className="space-y-1">
                  {(rosterAnalysis.strengths_weaknesses?.strengths || rosterAnalysis.strengths || []).map((strength: string, index: number) => (
                    <li key={`strength-${index}-${strength.slice(0, 20)}`} className="text-sm text-muted flex items-start space-x-2">
                      <CheckCircleIcon className="h-4 w-4 text-success-500 mt-0.5" />
                      <span>{strength}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="font-medium text-danger-700 mb-2">Weaknesses</h4>
                <ul className="space-y-1">
                  {(rosterAnalysis.strengths_weaknesses?.weaknesses || rosterAnalysis.weaknesses || []).map((weakness: string, index: number) => (
                    <li key={`weakness-${index}-${weakness.slice(0, 20)}`} className="text-sm text-muted flex items-start space-x-2">
                      <ExclamationTriangleIcon className="h-4 w-4 text-danger-500 mt-0.5" />
                      <span>{weakness}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Current Roster */}
          <div className="bg-surface rounded-lg border border-hairline p-6">
            <h3 className="text-lg font-medium text-body mb-4">Current Roster</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-medium text-accent-ink mb-2">Starting Lineup</h4>
                <div className="space-y-2">
                  {(rosterAnalysis.composition?.starting_lineup || []).map((player, index: number) => (
                    <div key={`starter-${player.name}-${index}`} className="flex items-center justify-between p-2 bg-highlight rounded">
                      <div>
                        <p className="text-sm font-medium text-body">{player.name}</p>
                        <p className="text-xs text-muted">{player.position} • {player.team}</p>
                      </div>
                      <span className="text-xs text-accent-ink">{player.total_points || 0} pts</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="font-medium text-body mb-2">Bench Players</h4>
                <div className="space-y-2">
                  {(rosterAnalysis.composition?.bench_players || rosterAnalysis.players || []).slice(0, 6).map((player, index: number) => (
                    <div key={`bench-${player.name}-${index}`} className="flex items-center justify-between p-2 bg-surface-2 rounded">
                      <div>
                        <p className="text-sm font-medium text-body">{player.name}</p>
                        <p className="text-xs text-muted">{player.position} • {player.team}</p>
                      </div>
                      <span className="text-xs text-muted">{player.total_points || 0} pts</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Position Analysis (if available) */}
          {rosterAnalysis.position_analysis && Object.keys(rosterAnalysis.position_analysis).length > 0 && (
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <h3 className="text-lg font-medium text-body mb-4">Position-by-Position Analysis</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(rosterAnalysis.position_analysis).map(([position, analysis]) => (
                  <div key={position} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-medium text-body">{position}</h4>
                      <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${getGradeColor(analysis.grade)}`}>
                        {analysis.grade}
                      </span>
                    </div>
                    <p className="text-sm text-muted mb-2">{analysis.summary}</p>
                    {analysis.recommendations && (
                      <div className="text-xs text-accent-ink">
                        {analysis.recommendations.slice(0, 2).join(', ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
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
          <div className="bg-surface rounded-lg border border-hairline p-6">
            <h3 className="text-lg font-medium text-body mb-4">Waiver Wire Recommendations</h3>
            <p className="text-sm text-muted mb-6">
              Based on your roster needs and available players. {waiverRecs.total_available} targets identified.
            </p>
            
            <div className="space-y-4">
              {waiverRecs.recommendations.slice(0, 10).map((rec, index: number) => (
                <div key={`waiver-${rec.player.name}-${index}`} className="border rounded-lg p-4 hover:bg-surface-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium text-body">{rec.player.name}</h4>
                      <p className="text-sm text-muted">{rec.player.position?.value || 'UNKNOWN'}</p>
                      <p className="text-sm text-accent-ink">{rec.reason}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-medium text-body">
                        Priority: {rec.priority}/3
                      </div>
                      {rec.player.projected_points && (
                        <div className="text-xs text-muted">
                          {rec.player.projected_points.toFixed(1)} proj pts
                        </div>
                      )}
                    </div>
                  </div>
                </div>
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
        <div className="space-y-6">
          <div className="bg-surface rounded-lg border border-hairline p-6">
            <h3 className="text-lg font-medium text-body mb-4">Trade Suggestions</h3>
            <p className="text-sm text-muted mb-6">
              Trade recommendations based on roster analysis. Trade deadline: {tradeRecs.trade_deadline}
            </p>
            
            <div className="space-y-4">
              {tradeRecs.suggestions.map((suggestion, index: number) => (
                <div key={`trade-suggestion-${index}-${suggestion.target?.name || index}`} className="border rounded-lg p-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <h4 className="font-medium text-success-700">Target</h4>
                      <p className="text-body">{suggestion.target_player}</p>
                    </div>
                    <div>
                      <h4 className="font-medium text-accent-ink">Offer</h4>
                      <p className="text-body">{suggestion.offer_players.join(', ')}</p>
                    </div>
                    <div>
                      <h4 className="font-medium text-body">Likelihood</h4>
                      <p className="text-body">{suggestion.likelihood}</p>
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t">
                    <p className="text-sm text-muted">{suggestion.reasoning}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'standings' && standingsData && (
        <div className="space-y-6">
          <div className="bg-surface rounded-lg border border-hairline p-6">
            <h3 className="text-lg font-medium text-body mb-4">League Standings</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-hairline">
                <thead className="bg-surface-2">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Rank
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Team
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Record
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Points For
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Points Against
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-surface divide-y divide-hairline">
                  {standingsData.teams.map((team) => (
                    <tr key={`team-${team.name || team.team_name}-${team.rank}`} className={team.rank <= standingsData.playoff_teams ? 'bg-success-50' : ''}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-body">
                        {team.rank}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                        {team.team_name || team.name}
                        {team.team_name === rosterAnalysis?.team_name && (
                          <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink">
                            You
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                        {team.wins}-{team.losses}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                        {team.points_for}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                        {team.points_against}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'matchups' && matchupData && (
        <div className="space-y-6">
          <div className="bg-surface rounded-lg border border-hairline p-6">
            <h3 className="text-lg font-medium text-body mb-4">Week {matchupData.week} Matchup Analysis</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div className="text-center p-4 border-2 border-highlight-line rounded-lg">
                <h4 className="font-medium text-accent-ink mb-2">Your Team</h4>
                <p className="text-xl font-bold text-body">{matchupData.user_team?.name || 'Your Team'}</p>
                <p className="text-lg text-muted">{matchupData.user_team?.points || 0} points</p>
              </div>
              
              <div className="text-center p-4 border-2 border-danger-200 rounded-lg">
                <h4 className="font-medium text-danger-600 mb-2">Opponent</h4>
                <p className="text-xl font-bold text-body">{matchupData.opponent_team?.name || 'Opponent'}</p>
                <p className="text-lg text-muted">{matchupData.opponent_team?.points || 0} points</p>
              </div>
            </div>
            
            <div className="bg-surface-2 rounded-lg p-4">
              <h4 className="font-medium text-body mb-2">AI Matchup Analysis</h4>
              <p className="text-sm text-body whitespace-pre-wrap">{matchupData.ai_analysis}</p>
            </div>
          </div>
        </div>
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
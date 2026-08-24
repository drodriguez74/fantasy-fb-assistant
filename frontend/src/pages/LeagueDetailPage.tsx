import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
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
  AdjustmentsHorizontalIcon
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
  injury_concerns?: unknown[]
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

export function LeagueDetailPage() {
  const { leagueId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  
  const [activeTab, setActiveTab] = useState<'overview' | 'roster' | 'matchups' | 'standings' | 'waiver' | 'trades' | 'scoring'>('overview')
  const [leagueInfo, setLeagueInfo] = useState<LeagueInfo | null>(null)
  const [rosterAnalysis, setRosterAnalysis] = useState<RosterAnalysis | null>(null)
  const [waiverRecs, setWaiverRecs] = useState<WaiverRecommendation | null>(null)
  const [tradeRecs, setTradeRecs] = useState<TradeRecommendation | null>(null)
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null)
  const [standingsData, setStandingsData] = useState<StandingsData | null>(null)
  const [insights, setInsights] = useState<LeagueInsights | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [waiverError, setWaiverError] = useState('')
  const [tradeError, setTradeError] = useState('')

  const loadLeagueData = useCallback(async () => {
    setLoading(true)
    setError('')
    setWaiverError('')
    setTradeError('')

    // Fetched independently (not one Promise.all) because waiver/trade
    // recommendations are, today, only really implemented for Yahoo leagues
    // (league_management_service.py honestly 400s for ESPN/Sleeper instead
    // of faking data) -- that known, documented gap must not take down
    // roster/standings/insights, which work for every connected platform.
    const [rosterResult, standingsResult, insightsResult, waiverResult, tradeResult] = await Promise.allSettled([
      api.get(`/leagues/${leagueId}/roster-analysis`),
      api.get(`/leagues/${leagueId}/standings?season=2025`),
      api.get(`/leagues/${leagueId}/insights`),
      api.get(`/leagues/${leagueId}/waiver-recommendations`),
      api.get(`/leagues/${leagueId}/trade-suggestions`)
    ])

    if (rosterResult.status === 'rejected') {
      setError(getErrorMessage(rosterResult.reason, 'Failed to load league data'))
      setLoading(false)
      return
    }
    if (standingsResult.status === 'rejected') {
      setError(getErrorMessage(standingsResult.reason, 'Failed to load league data'))
      setLoading(false)
      return
    }
    if (insightsResult.status === 'rejected') {
      setError(getErrorMessage(insightsResult.reason, 'Failed to load league data'))
      setLoading(false)
      return
    }

    const rosterResponse = rosterResult.value
    const standingsResponse = standingsResult.value
    const insightsResponse = insightsResult.value

    // Set league info from roster analysis
    setLeagueInfo(rosterResponse.data.league_info)
    setRosterAnalysis(rosterResponse.data.roster_analysis)

    // Identify "your" team by the real team name this league's roster
    // analysis was computed for, rather than a hardcoded name -- that
    // hardcoded name only ever matched one specific test league.
    const userTeamName: string | undefined = rosterResponse.data.roster_analysis?.team_name

    // Set standings data
    const teams: StandingsTeam[] = standingsResponse.data.teams
    setStandingsData({
      teams,
      user_team_rank: teams.find((team) => team.team_name === userTeamName)?.rank ?? 0,
      total_teams: teams.length,
      playoff_teams: 6,
      updated_at: new Date().toISOString()
    })

    // Set insights
    setInsights(insightsResponse.data.insights)
    setMatchupData(null) // No matchup data for now

    if (waiverResult.status === 'fulfilled') {
      const waiverResponse = waiverResult.value
      setWaiverRecs({
        recommendations: waiverResponse.data.waiver_recommendations?.recommendations ?? [],
        position_needs: waiverResponse.data.waiver_recommendations?.position_needs ?? {},
        total_available: waiverResponse.data.waiver_recommendations?.total_available ?? 0,
        updated_at: waiverResponse.data.waiver_recommendations?.updated_at ?? new Date().toISOString()
      })
    } else {
      setWaiverError(getErrorMessage(waiverResult.reason, 'Waiver recommendations are unavailable for this league right now.'))
    }

    if (tradeResult.status === 'fulfilled') {
      const tradeResponse = tradeResult.value
      setTradeRecs({
        suggestions: tradeResponse.data.trade_recommendations?.suggestions ?? [],
        trade_deadline: tradeResponse.data.trade_recommendations?.trade_deadline ?? "Week 13",
        updated_at: tradeResponse.data.trade_recommendations?.updated_at ?? new Date().toISOString()
      })
    } else {
      setTradeError(getErrorMessage(tradeResult.reason, 'Trade suggestions are unavailable for this league right now.'))
    }

    setLoading(false)
  }, [leagueId])

  useEffect(() => {
    if (user && leagueId) {
      loadLeagueData()
    }
  }, [user, leagueId, loadLeagueData])

  const refreshData = async () => {
    await loadLeagueData()
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-ink-400" />
          <h3 className="mt-2 text-sm font-medium text-ink-900">Authentication Required</h3>
          <p className="mt-1 text-sm text-ink-500">Please sign in to view league details.</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mr-4"></div>
          <div>
            <h3 className="text-lg font-medium text-ink-900">Loading league analysis</h3>
            <p className="text-sm text-ink-500">Pulling your roster, standings, and matchups.</p>
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
      case 'B': return 'bg-accent-100 text-accent-800'
      case 'C': return 'bg-warning-100 text-warning-800'
      case 'D': return 'bg-warning-200 text-warning-900'
      case 'F': return 'bg-danger-100 text-danger-800'
      default: return 'bg-ink-100 text-ink-800'
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/leagues')}
              className="p-2 text-ink-400 hover:text-ink-600"
            >
              <ArrowLeftIcon className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-3xl font-bold text-ink-900">{leagueInfo?.name}</h1>
              <p className="text-ink-600">
                {leagueInfo?.platform} • {leagueInfo?.season} • {leagueInfo?.league_size} Teams • {leagueInfo?.scoring_format}
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-3">
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
              className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors flex items-center space-x-2 focus:outline-none focus:ring-2 focus:ring-accent-500"
            >
              <ClockIcon className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-ink-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as 'overview' | 'roster' | 'matchups' | 'standings' | 'waiver' | 'trades' | 'scoring')}
                className={`py-2 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'border-accent-500 text-accent-600'
                    : 'border-transparent text-ink-500 hover:text-ink-700 hover:border-ink-300'
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
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <div className="flex items-center">
                <TrophyIcon className="h-8 w-8 text-accent-500" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-ink-500">Team Rank</p>
                  <p className="text-2xl font-bold text-ink-900">
                    {standingsData?.user_team_rank || 'N/A'}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <div className="flex items-center">
                <UserGroupIcon className="h-8 w-8 text-accent-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-ink-500">Roster Grade</p>
                  <p className="text-2xl font-bold text-ink-900">
                    {rosterAnalysis?.overall_grade?.grade || 'N/A'}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <div className="flex items-center">
                <ExclamationTriangleIcon className="h-8 w-8 text-danger-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-ink-500">Injuries</p>
                  <p className="text-2xl font-bold text-ink-900">
                    {rosterAnalysis?.injury_concerns?.length || 0}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <div className="flex items-center">
                <FireIcon className="h-8 w-8 text-accent-500" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-ink-500">Waiver Targets</p>
                  <p className="text-2xl font-bold text-ink-900">
                    {waiverRecs?.recommendations?.length || 0}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Weekly Insights */}
          {insights && (
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <h3 className="text-lg font-medium text-ink-900 mb-4">Weekly Insights</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h4 className="font-medium text-ink-700 mb-2">Weekly Outlook</h4>
                  <div className="space-y-2">
                    {insights.weekly_outlook?.key_points?.map((point: string, index: number) => (
                      <div key={`weekly-point-${index}-${point.slice(0, 20)}`} className="flex items-start space-x-2">
                        <CheckCircleIcon className="h-4 w-4 text-success-500 mt-0.5" />
                        <span className="text-sm text-ink-600">{point}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <h4 className="font-medium text-ink-700 mb-2">Top Pickup Targets</h4>
                  <div className="space-y-2">
                    {insights.pickup_targets?.slice(0, 3).map((target, index: number) => (
                      <div key={`pickup-${target.player}-${index}`} className="flex items-center justify-between">
                        <span className="text-sm font-medium text-ink-900">{target.player}</span>
                        <span className="text-xs text-ink-500">{target.position}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Current Matchup Preview */}
          {matchupData && (
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <h3 className="text-lg font-medium text-ink-900 mb-4">Week {matchupData.week} Matchup</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="text-center">
                  <h4 className="font-medium text-accent-600">Your Team</h4>
                  <p className="text-lg font-bold">{matchupData.user_team?.name || 'Your Team'}</p>
                  <p className="text-sm text-ink-500">{matchupData.user_team?.points || 0} points</p>
                </div>
                <div className="text-center">
                  <h4 className="font-medium text-danger-600">Opponent</h4>
                  <p className="text-lg font-bold">{matchupData.opponent_team?.name || 'Opponent'}</p>
                  <p className="text-sm text-ink-500">{matchupData.opponent_team?.points || 0} points</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'roster' && rosterAnalysis && (
        <div className="space-y-6">
          {/* Roster Summary */}
          <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-medium text-ink-900">Roster Analysis</h3>
                <p className="text-sm text-ink-600">
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
                    <li key={`strength-${index}-${strength.slice(0, 20)}`} className="text-sm text-ink-600 flex items-start space-x-2">
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
                    <li key={`weakness-${index}-${weakness.slice(0, 20)}`} className="text-sm text-ink-600 flex items-start space-x-2">
                      <ExclamationTriangleIcon className="h-4 w-4 text-danger-500 mt-0.5" />
                      <span>{weakness}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Current Roster */}
          <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Current Roster</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-medium text-accent-700 mb-2">Starting Lineup</h4>
                <div className="space-y-2">
                  {(rosterAnalysis.composition?.starting_lineup || []).map((player, index: number) => (
                    <div key={`starter-${player.name}-${index}`} className="flex items-center justify-between p-2 bg-accent-50 rounded">
                      <div>
                        <p className="text-sm font-medium text-ink-900">{player.name}</p>
                        <p className="text-xs text-ink-500">{player.position} • {player.team}</p>
                      </div>
                      <span className="text-xs text-accent-600">{player.total_points || 0} pts</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="font-medium text-ink-700 mb-2">Bench Players</h4>
                <div className="space-y-2">
                  {(rosterAnalysis.composition?.bench_players || rosterAnalysis.players || []).slice(0, 6).map((player, index: number) => (
                    <div key={`bench-${player.name}-${index}`} className="flex items-center justify-between p-2 bg-ink-50 rounded">
                      <div>
                        <p className="text-sm font-medium text-ink-900">{player.name}</p>
                        <p className="text-xs text-ink-500">{player.position} • {player.team}</p>
                      </div>
                      <span className="text-xs text-ink-600">{player.total_points || 0} pts</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Position Analysis (if available) */}
          {rosterAnalysis.position_analysis && Object.keys(rosterAnalysis.position_analysis).length > 0 && (
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
              <h3 className="text-lg font-medium text-ink-900 mb-4">Position-by-Position Analysis</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(rosterAnalysis.position_analysis).map(([position, analysis]) => (
                  <div key={position} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-medium text-ink-900">{position}</h4>
                      <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${getGradeColor(analysis.grade)}`}>
                        {analysis.grade}
                      </span>
                    </div>
                    <p className="text-sm text-ink-600 mb-2">{analysis.summary}</p>
                    {analysis.recommendations && (
                      <div className="text-xs text-accent-600">
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
        <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 text-center">
          <FireIcon className="mx-auto h-8 w-8 text-ink-300 mb-2" />
          <p className="text-sm text-ink-600">
            {waiverError || 'Loading waiver recommendations…'}
          </p>
        </div>
      )}

      {activeTab === 'waiver' && waiverRecs && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Waiver Wire Recommendations</h3>
            <p className="text-sm text-ink-600 mb-6">
              Based on your roster needs and available players. {waiverRecs.total_available} targets identified.
            </p>
            
            <div className="space-y-4">
              {waiverRecs.recommendations.slice(0, 10).map((rec, index: number) => (
                <div key={`waiver-${rec.player.name}-${index}`} className="border rounded-lg p-4 hover:bg-ink-50">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium text-ink-900">{rec.player.name}</h4>
                      <p className="text-sm text-ink-500">{rec.player.position?.value || 'UNKNOWN'}</p>
                      <p className="text-sm text-accent-600">{rec.reason}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-medium text-ink-900">
                        Priority: {rec.priority}/3
                      </div>
                      {rec.player.projected_points && (
                        <div className="text-xs text-ink-500">
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
        <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 text-center">
          <ArrowsRightLeftIcon className="mx-auto h-8 w-8 text-ink-300 mb-2" />
          <p className="text-sm text-ink-600">
            {tradeError || 'Loading trade suggestions…'}
          </p>
        </div>
      )}

      {activeTab === 'trades' && tradeRecs && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Trade Suggestions</h3>
            <p className="text-sm text-ink-600 mb-6">
              Trade recommendations based on roster analysis. Trade deadline: {tradeRecs.trade_deadline}
            </p>
            
            <div className="space-y-4">
              {tradeRecs.suggestions.map((suggestion, index: number) => (
                <div key={`trade-suggestion-${index}-${suggestion.target?.name || index}`} className="border rounded-lg p-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <h4 className="font-medium text-success-700">Target</h4>
                      <p className="text-ink-900">{suggestion.target_player}</p>
                    </div>
                    <div>
                      <h4 className="font-medium text-accent-700">Offer</h4>
                      <p className="text-ink-900">{suggestion.offer_players.join(', ')}</p>
                    </div>
                    <div>
                      <h4 className="font-medium text-ink-700">Likelihood</h4>
                      <p className="text-ink-900">{suggestion.likelihood}</p>
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t">
                    <p className="text-sm text-ink-600">{suggestion.reasoning}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'standings' && standingsData && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">League Standings</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-ink-200">
                <thead className="bg-ink-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Rank
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Team
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Record
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Points For
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Points Against
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-ink-200">
                  {standingsData.teams.map((team) => (
                    <tr key={`team-${team.name || team.team_name}-${team.rank}`} className={team.rank <= standingsData.playoff_teams ? 'bg-success-50' : ''}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink-900">
                        {team.rank}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-900">
                        {team.team_name || team.name}
                        {team.team_name === rosterAnalysis?.team_name && (
                          <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-accent-100 text-accent-800">
                            You
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-900">
                        {team.wins}-{team.losses}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-900">
                        {team.points_for}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-900">
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
          <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Week {matchupData.week} Matchup Analysis</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div className="text-center p-4 border-2 border-accent-200 rounded-lg">
                <h4 className="font-medium text-accent-600 mb-2">Your Team</h4>
                <p className="text-xl font-bold text-ink-900">{matchupData.user_team?.name || 'Your Team'}</p>
                <p className="text-lg text-ink-600">{matchupData.user_team?.points || 0} points</p>
              </div>
              
              <div className="text-center p-4 border-2 border-danger-200 rounded-lg">
                <h4 className="font-medium text-danger-600 mb-2">Opponent</h4>
                <p className="text-xl font-bold text-ink-900">{matchupData.opponent_team?.name || 'Opponent'}</p>
                <p className="text-lg text-ink-600">{matchupData.opponent_team?.points || 0} points</p>
              </div>
            </div>
            
            <div className="bg-ink-50 rounded-lg p-4">
              <h4 className="font-medium text-ink-900 mb-2">AI Matchup Analysis</h4>
              <p className="text-sm text-ink-700 whitespace-pre-wrap">{matchupData.ai_analysis}</p>
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
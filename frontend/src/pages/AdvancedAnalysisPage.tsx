import { useState, useEffect, useCallback } from 'react'
import { api, getErrorMessage } from '../services/api'
import {
  MagnifyingGlassIcon,
  ChartBarIcon,
  CalendarIcon,
  ArrowTrendingUpIcon as TrendingUpIcon,
  ExclamationTriangleIcon,
  UserGroupIcon,
  PlayIcon,
  PlusIcon,
  XMarkIcon,
  EyeIcon,
  EyeSlashIcon
} from '@heroicons/react/24/outline'
import { useAuth } from '../hooks/useAuth'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { getPositionColor } from '../components/players/playerDisplay'
import {
  PlayerComparisonChart,
  PlayerComparisonBarChart,
  ScheduleDifficultyChart,
  ScheduleDifficultyHeatmap,
  BreakoutCandidateChart,
  BreakoutCandidateBubbleChart,
  SituationalAnalysisChart,
  WeatherImpactChart,
  GameScriptChart,
  PlayerComparisonData,
  ScheduleDifficultyData,
  BreakoutCandidateData,
  SituationalData
} from '../components/charts'

interface Player {
  id: number
  name: string
  position: string
  team: string
  projected_points: number
  ownership_percentage: number
}

interface ComparisonPlayer {
  id: number
  name: string
  position: string
  team: string
  current_metrics: {
    projected_points?: number
    consistency_rating?: number
    ceiling_score?: number
    floor_score?: number
    target_share?: number
    snap_count_percentage?: number
  }
  risk_assessment: {
    risk_score?: number
    risk_level: string
    risk_factors: string[]
  }
  advanced_metrics: {
    value_score: number
    upside_rating?: number
    opportunity_share?: number
  }
}

interface PlayerComparison {
  players: ComparisonPlayer[]
  insights: string[]
  head_to_head: {
    categories?: Record<string, { winner: string }>
    overall_winner?: string
    score?: number | string
  }
  recommendation: string
}

interface ScheduleMatchup {
  week: number
  opponent: string
  difficulty_score: number | null
  difficulty_rating: 'EASY' | 'MODERATE' | 'DIFFICULT' | 'INSUFFICIENT_DATA'
}

interface ScheduleAnalysisEntry {
  player: { id: number; name: string }
  upcoming_matchups: ScheduleMatchup[]
  schedule_difficulty: {
    rank: number | null
    rating: 'EASY' | 'MODERATE' | 'DIFFICULT' | 'INSUFFICIENT_DATA'
    data_confidence?: 'computed' | 'heuristic' | 'insufficient'
  }
  recommendation: string
}

interface ScheduleAnalysis {
  schedule_analysis: ScheduleAnalysisEntry[]
  summary: {
    easiest_schedule: string | null
    hardest_schedule: string | null
    average_difficulty: number | null
  }
}

interface BreakoutCandidate {
  player: { id: number; name: string; position: string; team: string; age?: number; ownership_percentage?: number }
  breakout_analysis: { probability: number }
  supporting_factors: string[]
  risk_factors: string[]
  recommendation: string
}

interface BreakoutCandidates {
  breakout_candidates: BreakoutCandidate[]
  summary: {
    total_candidates: number
    high_probability: number
    medium_probability: number
    average_probability: number
  }
}

// Game Situations tab: wired to game_situations.py's /game-situations/enhanced-analysis,
// backed by EnhancedGameSituationService -- the real, most rigorously-labeled
// analysis in the app (Computed/Heuristic/Insufficient-data throughout), replacing
// the thinner AdvancedAnalysisService.analyze_game_situations that used to back this
// tab. Several sub-sections carry an explicit `data_confidence`; for the sections
// that don't (they're real per-player DB queries, just not individually labeled by
// the service), the badge below is derived from whether both sides of the split
// have a nonzero sample.
type DataConfidence = 'computed' | 'heuristic' | 'insufficient'

interface SituationalStats {
  avg_points: number
  games: number
  consistency: number
  ceiling: number
  floor: number
}

interface HomeAwayAnalysis {
  home_performance: SituationalStats
  away_performance: SituationalStats
  advantage: 'HOME' | 'AWAY'
  home_away_differential: number
  venue_specific_performance: Record<string, { avg_points: number; games: number }>
  travel_impact: { travel_fatigue_factor: string; note?: string; data_confidence: DataConfidence }
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'VERY_LOW'
  recommendations: string[]
}

type DomeVsOutdoor =
  | { dome_performance: SituationalStats; outdoor_performance: SituationalStats; dome_advantage: number }
  | { insufficient_data: true }

interface WeatherAnalysis {
  weather_condition_performance: Record<string, { avg_points: number; games: number }>
  dome_vs_outdoor: DomeVsOutdoor
  weather_sensitivity: string
  upcoming_weather_impact: { note?: string; data_confidence: DataConfidence }
  recommendations: string[]
}

interface OpponentAnalysis {
  defense_strength_performance: Record<string, { avg_points: number; games: number; ceiling: number; floor: number }>
  matchup_dependency: string
  division_rival_performance: { division_avg: number | null; non_division_avg: number | null; rivalry_factor: number | null; note?: string; data_confidence: DataConfidence }
  upcoming_opponents: Array<{ week: number; opponent: string; def_rank: number | null; difficulty: string }>
  optimal_matchups: string[]
  avoid_matchups: string[]
  recommendations: string[]
}

interface GameScriptAnalysis {
  game_script_performance: Record<string, { avg_points: number; games: number; avg_targets: number; avg_carries: number }>
  pace_of_play_impact: Record<string, { avg_points: number; games: number }>
  garbage_time_performance: { garbage_time_boost: boolean | null; avg_boost: number | null; note?: string; data_confidence: DataConfidence }
  red_zone_analysis: { red_zone_targets_per_game: number | null; goal_line_carries_per_game: number | null; touchdown_dependency: string; note?: string; data_confidence: DataConfidence }
  script_dependency: string
  optimal_game_scripts: string[]
  recommendations: string[]
}

interface VenueAnalysis {
  venue_type_performance: Record<string, { avg_points: number; games: number }>
  altitude_impact: { high_altitude_games: number; sea_level_avg: number | null; high_altitude_avg: number | null; altitude_impact: number | null; note?: string; data_confidence: DataConfidence }
  surface_impact: { grass_avg: number | null; turf_avg: number | null; surface_preference: string; note?: string; data_confidence: DataConfidence }
  venue_recommendations: string[]
}

interface PrimeTimeAnalysis {
  prime_time_performance: SituationalStats
  regular_time_performance: SituationalStats
  prime_time_advantage: number
  sample_sizes: { prime_time: number; regular: number }
  recommendations: string[]
}

interface RivalryAnalysis {
  rivalry_performance: SituationalStats
  non_rivalry_performance: SituationalStats
  rivalry_impact: number
  emotional_factor: string
  recommendations: string[]
}

interface UpcomingForecast {
  next_4_weeks: Array<{ week: number; opponent: string; location: string; def_rank: number | null; matchup_rating: number | null }>
  optimal_weeks: number[]
  caution_weeks: number[]
  overall_outlook: string
  note?: string
  data_confidence: DataConfidence
}

interface EnhancedPlayerSituationAnalysis {
  player: { id: number; name: string; position: string; team: string }
  home_away_analysis?: HomeAwayAnalysis
  weather_analysis?: WeatherAnalysis
  opponent_analysis?: OpponentAnalysis
  game_script_analysis?: GameScriptAnalysis
  venue_analysis?: VenueAnalysis
  prime_time_analysis?: PrimeTimeAnalysis
  rivalry_analysis?: RivalryAnalysis
  situational_insights: string[]
  upcoming_situation_forecast: UpcomingForecast
}

interface GameSituations {
  player_analyses: EnhancedPlayerSituationAnalysis[]
  comparison_insights: string[]
  recommendations: string[]
}

interface WeatherDataItem {
  player: string
  outdoor: number
  dome: number
  weatherSensitivity: string
}

interface GameScriptDataItem {
  player: string
  leading: number
  trailing: number
  close: number
}

export function AdvancedAnalysisPage() {
  const { user } = useAuth()
  const [selectedPlayers, setSelectedPlayers] = useState<Player[]>([])
  const [playerSearch, setPlayerSearch] = useState('')
  const [playerSuggestions, setPlayerSuggestions] = useState<Player[]>([])
  const [activeTab, setActiveTab] = useState<'comparison' | 'schedule' | 'breakout' | 'situations'>('comparison')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  
  // Analysis results
  const [comparisonResult, setComparisonResult] = useState<PlayerComparison | null>(null)
  const [scheduleResult, setScheduleResult] = useState<ScheduleAnalysis | null>(null)
  const [breakoutResult, setBreakoutResult] = useState<BreakoutCandidates | null>(null)
  const [situationResult, setSituationResult] = useState<GameSituations | null>(null)
  
  // Form state
  const [weeksAhead, setWeeksAhead] = useState(4)
  const [breakoutPosition, setBreakoutPosition] = useState('ALL')
  const [maxOwnership, setMaxOwnership] = useState(50)
  
  // Chart visibility state
  const [showCharts, setShowCharts] = useState(true)
  const [chartType, setChartType] = useState<'radar' | 'bar' | 'both'>('both')

  const searchPlayers = useCallback(async () => {
    try {
      const response = await api.get(`/advanced-analysis/player-suggestions?query=${encodeURIComponent(playerSearch)}&limit=8`)
      setPlayerSuggestions(response.data.suggestions || [])
    } catch (err) {
      console.error('Failed to search players:', err)
    }
  }, [playerSearch])

  useEffect(() => {
    if (playerSearch.length >= 2) {
      searchPlayers()
    } else {
      setPlayerSuggestions([])
    }
  }, [playerSearch, searchPlayers])

  const addPlayer = (player: Player) => {
    if (selectedPlayers.find(p => p.id === player.id)) return
    if (selectedPlayers.length >= 5) {
      setError('Maximum 5 players allowed for comparison')
      return
    }
    
    setSelectedPlayers([...selectedPlayers, player])
    setPlayerSearch('')
    setPlayerSuggestions([])
    setError('')
  }

  const removePlayer = (playerId: number) => {
    setSelectedPlayers(selectedPlayers.filter(p => p.id !== playerId))
  }

  const runPlayerComparison = async () => {
    if (selectedPlayers.length < 2) {
      setError('At least 2 players required for comparison')
      return
    }

    try {
      setLoading(true)
      setError('')
      
      const response = await api.post('/advanced-analysis/compare-players', {
        player_ids: selectedPlayers.map(p => p.id)
      })
      
      setComparisonResult(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to compare players'))
    } finally {
      setLoading(false)
    }
  }

  const runScheduleAnalysis = async () => {
    if (selectedPlayers.length === 0) {
      setError('At least 1 player required for schedule analysis')
      return
    }

    try {
      setLoading(true)
      setError('')
      
      const response = await api.post('/advanced-analysis/strength-of-schedule', {
        player_ids: selectedPlayers.map(p => p.id),
        weeks_ahead: weeksAhead
      })
      
      setScheduleResult(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to analyze schedule'))
    } finally {
      setLoading(false)
    }
  }

  const runBreakoutAnalysis = async () => {
    try {
      setLoading(true)
      setError('')
      
      const response = await api.post('/advanced-analysis/breakout-candidates', {
        position: breakoutPosition === 'ALL' ? null : breakoutPosition,
        min_ownership: 0,
        max_ownership: maxOwnership
      })
      
      setBreakoutResult(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to detect breakout candidates'))
    } finally {
      setLoading(false)
    }
  }

  const runSituationAnalysis = async () => {
    if (selectedPlayers.length === 0) {
      setError('At least 1 player required for situation analysis')
      return
    }

    try {
      setLoading(true)
      setError('')

      // Canonical path: EnhancedGameSituationService via game_situations.py.
      // This replaces the thinner AdvancedAnalysisService.analyze_game_situations
      // that used to back this tab -- same real, per-player data, but with the
      // full home/away, weather, opponent, game-script, venue, prime-time, and
      // rivalry breakdowns and honest Computed/Heuristic/Insufficient-data labeling.
      const response = await api.post('/game-situations/enhanced-analysis', {
        player_ids: selectedPlayers.map(p => p.id),
        analysis_type: 'all'
      })

      setSituationResult({
        player_analyses: response.data.player_analyses || [],
        comparison_insights: response.data.comparison_insights || [],
        recommendations: response.data.recommendations || []
      })
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to analyze game situations'))
    } finally {
      setLoading(false)
    }
  }

  // Transform data for charts
  const transformPlayerComparisonData = (players: ComparisonPlayer[]): PlayerComparisonData[] => {
    return players.map(player => ({
      player: player.name,
      projectedPoints: player.current_metrics?.projected_points || 0,
      consistency: player.current_metrics?.consistency_rating || 0,
      ceiling: player.current_metrics?.ceiling_score || 0,
      floor: player.current_metrics?.floor_score || 0,
      targetShare: player.current_metrics?.target_share || 0,
      snapCount: player.current_metrics?.snap_count_percentage || 0,
      riskScore: player.risk_assessment?.risk_score || 0,
      valueScore: player.advanced_metrics?.value_score || 0,
      upsideRating: player.advanced_metrics?.upside_rating || 0,
      opportunityShare: player.advanced_metrics?.opportunity_share || 0
    }))
  }

  const renderComparisonResults = () => {
    if (!comparisonResult) return null

    const chartData = transformPlayerComparisonData(comparisonResult.players)

    return (
      <div className="space-y-6">
        {/* Chart Controls */}
        <div className="flex items-center justify-between bg-ink-50 p-4 rounded-lg">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setShowCharts(!showCharts)}
              className="flex items-center space-x-2 text-sm text-ink-700 hover:text-ink-900"
            >
              {showCharts ? <EyeSlashIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
              <span>{showCharts ? 'Hide Charts' : 'Show Charts'}</span>
            </button>
            
            {showCharts && (
              <div className="flex items-center space-x-2">
                <label className="text-sm text-ink-700">Chart Type:</label>
                <select
                  value={chartType}
                  onChange={(e) => setChartType(e.target.value as 'radar' | 'bar' | 'both')}
                  className="text-sm border border-ink-300 rounded px-2 py-1"
                >
                  <option value="radar">Radar Chart</option>
                  <option value="bar">Bar Chart</option>
                  <option value="both">Both</option>
                </select>
              </div>
            )}
          </div>
          <div className="text-xs text-ink-500">
            Comparing {comparisonResult.players.length} players
          </div>
        </div>

        {/* Interactive Charts */}
        {showCharts && chartData.length > 0 && (
          <div className="space-y-6">
            {(chartType === 'radar' || chartType === 'both') && (
              <div className="bg-white rounded-lg border border-ink-200 p-6">
                <h3 className="text-lg font-semibold text-ink-900 mb-4">Player Comparison Radar Chart</h3>
                <PlayerComparisonChart data={chartData} height={450} />
              </div>
            )}
            
            {(chartType === 'bar' || chartType === 'both') && (
              <div className="bg-white rounded-lg border border-ink-200 p-6">
                <h3 className="text-lg font-semibold text-ink-900 mb-4">Detailed Metrics Comparison</h3>
                <PlayerComparisonBarChart data={chartData} height={400} />
              </div>
            )}
          </div>
        )}

        {/* Key Insights */}
        <div className="bg-accent-50 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-accent-900 mb-3">Key Insights</h3>
          <ul className="space-y-2">
            {comparisonResult.insights.map((insight, index) => (
              <li key={`comparison-insight-${index}-${insight.slice(0, 20)}`} className="text-accent-800">• {insight}</li>
            ))}
          </ul>
        </div>

        {/* Head-to-Head (for 2 players) */}
        {comparisonResult.head_to_head && Object.keys(comparisonResult.head_to_head).length > 0 && (
          <div className="bg-white rounded-lg border border-ink-200 p-6">
            <h3 className="text-lg font-semibold text-ink-900 mb-4">Head-to-Head Comparison</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(comparisonResult.head_to_head.categories || {}).map(([category, data]) => (
                <div key={category} className="flex items-center justify-between p-3 bg-ink-50 rounded-lg">
                  <span className="font-medium">{category}</span>
                  <span className="text-success-600 font-semibold">{data.winner}</span>
                </div>
              ))}
            </div>
            {comparisonResult.head_to_head.overall_winner && (
              <div className="mt-4 p-3 bg-success-50 rounded-lg text-center">
                <span className="text-success-800 font-semibold">
                  Overall Winner: {comparisonResult.head_to_head.overall_winner} 
                  ({comparisonResult.head_to_head.score})
                </span>
              </div>
            )}
          </div>
        )}

        {/* Player Details */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {comparisonResult.players.map((player) => (
            <div key={player.id} className="bg-white rounded-lg border border-ink-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-ink-900">{player.name}</h3>
                <span className={`px-2 py-1 text-sm rounded-full ${getPositionColor(player.position)}`}>
                  {player.position} - {player.team}
                </span>
              </div>
              
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-ink-600">Projected Points:</span>
                    <span className="ml-2 font-semibold">{player.current_metrics.projected_points || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-ink-600">Consistency:</span>
                    <span className="ml-2 font-semibold">{player.current_metrics.consistency_rating || 'N/A'}/10</span>
                  </div>
                  <div>
                    <span className="text-ink-600">Risk Level:</span>
                    <span className={`ml-2 font-semibold ${
                      player.risk_assessment.risk_level === 'LOW' ? 'text-success-600' :
                      player.risk_assessment.risk_level === 'MEDIUM' ? 'text-warning-600' : 'text-danger-600'
                    }`}>
                      {player.risk_assessment.risk_level}
                    </span>
                  </div>
                  <div>
                    <span className="text-ink-600">Value Score:</span>
                    <span className="ml-2 font-semibold">{player.advanced_metrics.value_score}/100</span>
                  </div>
                </div>

                {player.risk_assessment.risk_factors.length > 0 && (
                  <div className="mt-3">
                    <span className="text-sm font-medium text-ink-700">Risk Factors:</span>
                    <ul className="mt-1 text-sm text-ink-600">
                      {player.risk_assessment.risk_factors.map((factor, idx: number) => (
                        <li key={idx}>• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Recommendation */}
        <div className="bg-accent-50 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-accent-900 mb-2">Recommendation</h3>
          <p className="text-accent-800">{comparisonResult.recommendation}</p>
        </div>
      </div>
    )
  }

  // Transform schedule data for charts. Matchups with no synced defensive
  // ranking (difficulty_score/rating null/'INSUFFICIENT_DATA') are excluded
  // here rather than charted as 0 -- a 0 bar would look like a real "easy"
  // matchup instead of "we don't know yet."
  const transformScheduleData = (scheduleAnalysis: ScheduleAnalysisEntry[]): ScheduleDifficultyData[] => {
    const data: ScheduleDifficultyData[] = []
    scheduleAnalysis.forEach(analysis => {
      analysis.upcoming_matchups.forEach((matchup) => {
        if (matchup.difficulty_score === null || matchup.difficulty_rating === 'INSUFFICIENT_DATA') return
        data.push({
          week: matchup.week,
          opponent: matchup.opponent,
          difficulty: matchup.difficulty_score,
          rating: matchup.difficulty_rating,
          player: analysis.player.name
        })
      })
    })
    return data
  }

  const renderScheduleResults = () => {
    if (!scheduleResult) return null

    const chartData = transformScheduleData(scheduleResult.schedule_analysis)

    return (
      <div className="space-y-6">
        {/* Summary */}
        <div className="bg-white rounded-lg border border-ink-200 p-6">
          <h3 className="text-lg font-semibold text-ink-900 mb-4">Schedule Summary (Next {weeksAhead} Weeks)</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{scheduleResult.summary.easiest_schedule ?? '—'}</div>
              <div className="text-xs uppercase text-ink-500">Easiest Schedule</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{scheduleResult.summary.hardest_schedule ?? '—'}</div>
              <div className="text-xs uppercase text-ink-500">Hardest Schedule</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{scheduleResult.summary.average_difficulty ?? '—'}</div>
              <div className="text-xs uppercase text-ink-500">Average Difficulty</div>
            </div>
          </div>
          {scheduleResult.summary.average_difficulty === null && (
            <div className="mt-3">
              <DataConfidenceBadge level="insufficient" label="No synced schedule/defensive-ranking data yet" />
            </div>
          )}
        </div>

        {/* Schedule Difficulty Charts */}
        {showCharts && chartData.length > 0 && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-ink-200 p-6">
              <h3 className="text-lg font-semibold text-ink-900 mb-4">Schedule Difficulty Chart</h3>
              <ScheduleDifficultyChart data={chartData} height={350} />
            </div>
            
            <div className="bg-white rounded-lg border border-ink-200 p-6">
              <h3 className="text-lg font-semibold text-ink-900 mb-4">Schedule Difficulty Heatmap</h3>
              <ScheduleDifficultyHeatmap data={chartData} height={250} />
            </div>
          </div>
        )}

        {/* Player Schedule Analysis */}
        <div className="space-y-4">
          {scheduleResult.schedule_analysis.map((analysis) => (
            <div key={analysis.player.id} className="bg-white rounded-lg border border-ink-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-ink-900">{analysis.player.name}</h3>
                <div className="flex items-center space-x-4">
                  {analysis.schedule_difficulty.rank !== null && (
                    <span className="px-2 py-1 bg-ink-100 text-ink-600 text-sm rounded-full">
                      Rank #{analysis.schedule_difficulty.rank}
                    </span>
                  )}
                  {analysis.schedule_difficulty.rating === 'INSUFFICIENT_DATA' ? (
                    <DataConfidenceBadge level="insufficient" />
                  ) : (
                    <span className={`px-2 py-1 text-sm rounded-full ${
                      analysis.schedule_difficulty.rating === 'EASY' ? 'bg-success-100 text-success-800' :
                      analysis.schedule_difficulty.rating === 'MODERATE' ? 'bg-warning-100 text-warning-800' :
                      'bg-danger-100 text-danger-800'
                    }`}>
                      {analysis.schedule_difficulty.rating}
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                {analysis.upcoming_matchups.map((matchup, idx: number) => (
                  <div key={idx} className="text-center p-3 bg-ink-50 rounded-lg">
                    <div className="font-semibold">Week {matchup.week}</div>
                    <div className="text-sm text-ink-600">{matchup.opponent}</div>
                    {matchup.difficulty_score === null ? (
                      <DataConfidenceBadge level="insufficient" className="mt-1" />
                    ) : (
                      <div className={`text-sm font-medium ${
                        matchup.difficulty_rating === 'EASY' ? 'text-success-600' :
                        matchup.difficulty_rating === 'MODERATE' ? 'text-warning-600' :
                        'text-danger-600'
                      }`}>
                        {matchup.difficulty_score}/10
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="bg-accent-50 p-3 rounded-lg">
                <span className="text-sm font-medium text-accent-900">Recommendation: </span>
                <span className="text-sm text-accent-800">{analysis.recommendation}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Transform breakout data for charts
  const transformBreakoutData = (candidates: BreakoutCandidate[]): BreakoutCandidateData[] => {
    return candidates.map(candidate => ({
      player: candidate.player.name,
      probability: candidate.breakout_analysis.probability,
      age: candidate.player.age || 25,
      ownership: candidate.player.ownership_percentage || 0,
      targetShare: Number(candidate.supporting_factors.find((f: string) => f.includes('target'))?.match(/\d+/)?.[0]) || 15,
      snapCount: Number(candidate.supporting_factors.find((f: string) => f.includes('snap'))?.match(/\d+/)?.[0]) || 60,
      efficiency: candidate.breakout_analysis.probability * 100 // Simplified efficiency metric
    }))
  }

  const renderBreakoutResults = () => {
    if (!breakoutResult) return null

    const chartData = transformBreakoutData(breakoutResult.breakout_candidates.slice(0, 15))

    return (
      <div className="space-y-6">
        {/* Summary */}
        <div className="bg-white rounded-lg border border-ink-200 p-6">
          <h3 className="text-lg font-semibold text-ink-900 mb-4">Breakout Analysis Summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{breakoutResult.summary.total_candidates}</div>
              <div className="text-xs uppercase text-ink-500">Total Candidates</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{breakoutResult.summary.high_probability}</div>
              <div className="text-xs uppercase text-ink-500">High Probability</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{breakoutResult.summary.medium_probability}</div>
              <div className="text-xs uppercase text-ink-500">Medium Probability</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-semibold text-ink-900">{(breakoutResult.summary.average_probability * 100).toFixed(1)}%</div>
              <div className="text-xs uppercase text-ink-500">Avg Probability</div>
            </div>
          </div>
        </div>

        {/* Breakout Candidate Charts */}
        {showCharts && chartData.length > 0 && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-ink-200 p-6">
              <h3 className="text-lg font-semibold text-ink-900 mb-4">Breakout Probability Analysis</h3>
              <BreakoutCandidateBubbleChart data={chartData} height={400} />
            </div>
            
            <div className="bg-white rounded-lg border border-ink-200 p-6">
              <h3 className="text-lg font-semibold text-ink-900 mb-4">Age vs Probability Scatter Plot</h3>
              <BreakoutCandidateChart 
                data={chartData} 
                height={350} 
                xAxis="age" 
                yAxis="probability"
              />
            </div>
          </div>
        )}

        {/* Breakout Candidates */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {breakoutResult.breakout_candidates.slice(0, 10).map((candidate) => (
            <div key={candidate.player.id} className="bg-white rounded-lg border border-ink-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-ink-900">{candidate.player.name}</h3>
                <div className="flex items-center space-x-2">
                  <span className={`px-2 py-1 text-sm rounded-full ${getPositionColor(candidate.player.position)}`}>
                    {candidate.player.position} - {candidate.player.team}
                  </span>
                  <span className={`px-2 py-1 text-sm font-semibold rounded-full ${
                    candidate.breakout_analysis.probability > 0.7 ? 'bg-success-100 text-success-800' :
                    candidate.breakout_analysis.probability > 0.5 ? 'bg-warning-100 text-warning-800' :
                    'bg-danger-100 text-danger-800'
                  }`}>
                    {(candidate.breakout_analysis.probability * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-ink-600">Age:</span>
                    <span className="ml-2 font-semibold">{candidate.player.age || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-ink-600">Ownership:</span>
                    <span className="ml-2 font-semibold">{candidate.player.ownership_percentage?.toFixed(1) || '0'}%</span>
                  </div>
                </div>

                {candidate.supporting_factors.length > 0 && (
                  <div>
                    <span className="text-sm font-medium text-success-700">Supporting Factors:</span>
                    <ul className="mt-1 text-sm text-success-600">
                      {candidate.supporting_factors.map((factor: string, idx: number) => (
                        <li key={idx}>• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {candidate.risk_factors.length > 0 && (
                  <div>
                    <span className="text-sm font-medium text-danger-700">Risk Factors:</span>
                    <ul className="mt-1 text-sm text-danger-600">
                      {candidate.risk_factors.map((factor: string, idx: number) => (
                        <li key={idx}>• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="bg-accent-50 p-3 rounded-lg">
                  <span className="text-sm font-medium text-accent-900">Recommendation: </span>
                  <span className="text-sm text-accent-800">{candidate.recommendation}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Transform situation data for charts. Players whose section came back
  // "insufficient data" (zero games on one side of the split) are excluded
  // from that chart rather than charted as 0 -- a 0 bar would look like a
  // real, unfavorable number instead of "we don't know yet."
  const transformSituationData = (playerAnalyses: EnhancedPlayerSituationAnalysis[]): {
    homeAwayData: SituationalData[],
    weatherData: WeatherDataItem[],
    gameScriptData: GameScriptDataItem[]
  } => {
    const homeAwayData: SituationalData[] = playerAnalyses
      .filter(a => a.home_away_analysis && a.home_away_analysis.home_performance.games > 0 && a.home_away_analysis.away_performance.games > 0)
      .map(a => ({
        situation: 'Home vs Away',
        home: a.home_away_analysis!.home_performance.avg_points,
        away: a.home_away_analysis!.away_performance.avg_points,
        player: a.player.name
      }))

    const weatherData: WeatherDataItem[] = playerAnalyses
      .filter(a => {
        const dvo = a.weather_analysis?.dome_vs_outdoor
        return dvo && 'dome_performance' in dvo && dvo.dome_performance.games > 0 && dvo.outdoor_performance.games > 0
      })
      .map(a => {
        const dvo = a.weather_analysis!.dome_vs_outdoor as Extract<DomeVsOutdoor, { dome_performance: SituationalStats }>
        return {
          player: a.player.name,
          outdoor: dvo.outdoor_performance.avg_points,
          dome: dvo.dome_performance.avg_points,
          weatherSensitivity: a.weather_analysis!.weather_sensitivity
        }
      })

    const gameScriptData: GameScriptDataItem[] = playerAnalyses
      .filter(a => {
        const perf = a.game_script_analysis?.game_script_performance
        return perf && perf.LEADING && perf.TRAILING
      })
      .map(a => {
        const perf = a.game_script_analysis!.game_script_performance
        const leading = perf.LEADING.avg_points
        const trailing = perf.TRAILING.avg_points
        return {
          player: a.player.name,
          leading,
          trailing,
          close: perf.CLOSE?.avg_points ?? (leading + trailing) / 2
        }
      })

    return { homeAwayData, weatherData, gameScriptData }
  }

  const renderSituationResults = () => {
    if (!situationResult) return null

    const { homeAwayData, weatherData, gameScriptData } = transformSituationData(situationResult.player_analyses)

    return (
      <div className="space-y-6">
        {/* Cross-Player Insights */}
        {situationResult.comparison_insights.length > 0 && (
          <div className="bg-accent-50 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-accent-900 mb-3">Key Insights</h3>
            <ul className="space-y-2">
              {situationResult.comparison_insights.map((insight, index) => (
                <li key={`situation-insight-${index}-${insight.slice(0, 20)}`} className="text-accent-800">• {insight}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Situational Analysis Charts */}
        {showCharts && homeAwayData.length > 0 && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-ink-200 p-6">
              <h3 className="text-lg font-semibold text-ink-900 mb-4">Home vs Away Performance</h3>
              <SituationalAnalysisChart
                data={homeAwayData}
                height={300}
                chartType="comparison"
              />
            </div>

            {weatherData.length > 0 && (
              <div className="bg-white rounded-lg border border-ink-200 p-6">
                <h3 className="text-lg font-semibold text-ink-900 mb-4">Weather Impact Analysis</h3>
                <WeatherImpactChart data={weatherData} height={250} />
              </div>
            )}

            {gameScriptData.length > 0 && gameScriptData[0] && (
              <div className="bg-white rounded-lg border border-ink-200 p-6">
                <h3 className="text-lg font-semibold text-ink-900 mb-4">Game Script Performance</h3>
                <GameScriptChart data={gameScriptData} height={250} />
              </div>
            )}
          </div>
        )}

        {/* Player Situation Analysis */}
        <div className="space-y-6">
          {situationResult.player_analyses.map((analysis) => {
            const ha = analysis.home_away_analysis
            const wa = analysis.weather_analysis
            const oa = analysis.opponent_analysis
            const ga = analysis.game_script_analysis
            const va = analysis.venue_analysis
            const pt = analysis.prime_time_analysis
            const rv = analysis.rivalry_analysis
            const domeVsOutdoor = wa?.dome_vs_outdoor && 'dome_performance' in wa.dome_vs_outdoor ? wa.dome_vs_outdoor : null

            return (
              <div key={analysis.player.id} className="bg-white rounded-lg border border-ink-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-ink-900">{analysis.player.name}</h3>
                  <span className={`px-2 py-1 text-sm rounded-full ${getPositionColor(analysis.player.position)}`}>
                    {analysis.player.position} - {analysis.player.team}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {/* Home vs Away */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Home vs Away</h4>
                      <DataConfidenceBadge level={ha && ha.home_performance.games > 0 && ha.away_performance.games > 0 ? 'computed' : 'insufficient'} />
                    </div>
                    {ha && ha.home_performance.games > 0 && ha.away_performance.games > 0 ? (
                      <div className="space-y-1 text-sm">
                        <div>Home: {ha.home_performance.avg_points} pts ({ha.home_performance.games} games)</div>
                        <div>Away: {ha.away_performance.avg_points} pts ({ha.away_performance.games} games)</div>
                        <div className="font-medium text-accent-600">Prefers: {ha.advantage}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">Not enough logged home/away games for this player yet.</div>
                    )}
                  </div>

                  {/* Weather Impact */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Weather Impact</h4>
                      <DataConfidenceBadge level={domeVsOutdoor && domeVsOutdoor.dome_performance.games > 0 && domeVsOutdoor.outdoor_performance.games > 0 ? 'computed' : 'insufficient'} />
                    </div>
                    {domeVsOutdoor && domeVsOutdoor.dome_performance.games > 0 && domeVsOutdoor.outdoor_performance.games > 0 ? (
                      <div className="space-y-1 text-sm">
                        <div>Outdoor: {domeVsOutdoor.outdoor_performance.avg_points} pts</div>
                        <div>Dome: {domeVsOutdoor.dome_performance.avg_points} pts</div>
                        <div className="font-medium text-accent-600">Sensitivity: {wa?.weather_sensitivity}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">No logged weather/venue data for this player yet.</div>
                    )}
                  </div>

                  {/* Opponent Strength */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Opponent Strength</h4>
                      <DataConfidenceBadge level={oa && Object.keys(oa.defense_strength_performance).length > 0 ? 'computed' : 'insufficient'} />
                    </div>
                    {oa && Object.keys(oa.defense_strength_performance).length > 0 ? (
                      <div className="space-y-1 text-sm">
                        {Object.entries(oa.defense_strength_performance).map(([tier, stats]) => (
                          <div key={tier}>{tier.replace('_', ' ')}: {stats.avg_points} pts ({stats.games}g)</div>
                        ))}
                        <div className="font-medium text-accent-600">Dependency: {oa.matchup_dependency}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">Not enough logged opponent-strength data yet.</div>
                    )}
                  </div>

                  {/* Game Script */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Game Script</h4>
                      <DataConfidenceBadge level={ga && Object.keys(ga.game_script_performance).length > 0 ? 'computed' : 'insufficient'} />
                    </div>
                    {ga && Object.keys(ga.game_script_performance).length > 0 ? (
                      <div className="space-y-1 text-sm">
                        {Object.entries(ga.game_script_performance).map(([script, stats]) => (
                          <div key={script}>{script}: {stats.avg_points} pts ({stats.games}g)</div>
                        ))}
                        <div className="font-medium text-accent-600">Dependency: {ga.script_dependency}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">No logged game-script data for this player yet.</div>
                    )}
                  </div>

                  {/* Red Zone Usage */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Red Zone Usage</h4>
                      <DataConfidenceBadge level={ga?.red_zone_analysis.data_confidence ?? 'insufficient'} />
                    </div>
                    {ga && ga.red_zone_analysis.data_confidence === 'computed' ? (
                      <div className="space-y-1 text-sm">
                        <div>RZ targets/gm: {ga.red_zone_analysis.red_zone_targets_per_game}</div>
                        <div>Goal-line carries/gm: {ga.red_zone_analysis.goal_line_carries_per_game}</div>
                        <div className="font-medium text-accent-600">TD dependency: {ga.red_zone_analysis.touchdown_dependency}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">{ga?.red_zone_analysis.note ?? 'No logged red-zone usage data yet.'}</div>
                    )}
                  </div>

                  {/* Prime Time */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Prime Time</h4>
                      <DataConfidenceBadge level={pt && pt.sample_sizes.prime_time > 0 && pt.sample_sizes.regular > 0 ? 'computed' : 'insufficient'} />
                    </div>
                    {pt && pt.sample_sizes.prime_time > 0 && pt.sample_sizes.regular > 0 ? (
                      <div className="space-y-1 text-sm">
                        <div>Prime time: {pt.prime_time_performance.avg_points} pts ({pt.sample_sizes.prime_time}g)</div>
                        <div>Regular: {pt.regular_time_performance.avg_points} pts ({pt.sample_sizes.regular}g)</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">Not enough logged prime-time games yet.</div>
                    )}
                  </div>

                  {/* Rivalry */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Division Rivalry</h4>
                      <DataConfidenceBadge level={rv && rv.rivalry_performance.games > 0 && rv.non_rivalry_performance.games > 0 ? 'computed' : 'insufficient'} />
                    </div>
                    {rv && rv.rivalry_performance.games > 0 && rv.non_rivalry_performance.games > 0 ? (
                      <div className="space-y-1 text-sm">
                        <div>Rivalry: {rv.rivalry_performance.avg_points} pts</div>
                        <div>Non-rivalry: {rv.non_rivalry_performance.avg_points} pts</div>
                        <div className="font-medium text-accent-600">Factor: {rv.emotional_factor}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">Not enough logged rivalry-game data yet.</div>
                    )}
                  </div>

                  {/* Venue Altitude */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Altitude Impact</h4>
                      <DataConfidenceBadge level={va?.altitude_impact.data_confidence ?? 'insufficient'} />
                    </div>
                    {va && va.altitude_impact.altitude_impact !== null ? (
                      <div className="space-y-1 text-sm">
                        <div>Sea level: {va.altitude_impact.sea_level_avg} pts</div>
                        <div>High altitude: {va.altitude_impact.high_altitude_avg} pts</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">{va?.altitude_impact.note ?? 'No logged high-altitude venue data yet.'}</div>
                    )}
                  </div>

                  {/* Upcoming Forecast */}
                  <div className="bg-ink-50 p-4 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-ink-900">Upcoming Weeks</h4>
                      <DataConfidenceBadge level={analysis.upcoming_situation_forecast.data_confidence} />
                    </div>
                    {analysis.upcoming_situation_forecast.next_4_weeks.length > 0 ? (
                      <div className="space-y-1 text-sm">
                        {analysis.upcoming_situation_forecast.next_4_weeks.map((wk) => (
                          <div key={wk.week}>Wk {wk.week} vs {wk.opponent} ({wk.location}){wk.matchup_rating !== null ? ` — rating ${wk.matchup_rating}` : ''}</div>
                        ))}
                        <div className="font-medium text-accent-600">Outlook: {analysis.upcoming_situation_forecast.overall_outlook}</div>
                      </div>
                    ) : (
                      <div className="text-sm text-ink-500">{analysis.upcoming_situation_forecast.note ?? 'No synced schedule data yet.'}</div>
                    )}
                  </div>
                </div>

                {/* Upcoming Opponents */}
                {oa && oa.upcoming_opponents.length > 0 && (
                  <div className="mt-4 bg-ink-50 p-3 rounded-lg">
                    <span className="text-sm font-medium text-ink-900">Upcoming Opponents: </span>
                    <span className="text-sm text-ink-700">
                      {oa.upcoming_opponents.map(o => `Wk ${o.week} ${o.opponent} (${o.difficulty})`).join(', ')}
                    </span>
                  </div>
                )}

                {/* Situational Insights */}
                {analysis.situational_insights.length > 0 && (
                  <div className="mt-4 bg-accent-50 p-3 rounded-lg">
                    <span className="text-sm font-medium text-accent-900">Situational Insights: </span>
                    <ul className="mt-1 text-sm text-accent-800">
                      {analysis.situational_insights.map((insight: string, idx: number) => (
                        <li key={idx}>• {insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Overall Recommendations */}
        {situationResult.recommendations.length > 0 && (
          <div className="bg-accent-50 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-accent-900 mb-2">Recommendations</h3>
            <ul className="space-y-1">
              {situationResult.recommendations.map((rec, index) => (
                <li key={`situation-rec-${index}-${rec.slice(0, 20)}`} className="text-accent-800">• {rec}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-ink-400" />
        <h3 className="mt-2 text-sm font-medium text-ink-900">Authentication Required</h3>
        <p className="mt-1 text-sm text-ink-500">Please log in to access Advanced Analysis features.</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display font-black uppercase tracking-tight text-3xl text-ink-900">Advanced Analysis</h1>
          <p className="text-ink-600 mt-2">
            Compare players head-to-head, check strength of schedule, and spot breakouts before the waiver wire catches on
          </p>
        </div>
        <ChartBarIcon className="h-8 w-8 text-accent-500" />
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-danger-50 border border-danger-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-danger-500" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-danger-800">Error</h3>
              <div className="mt-2 text-sm text-danger-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Player Selection */}
      <div className="bg-white rounded-lg border border-ink-200 p-6">
        <h2 className="text-lg font-semibold text-ink-900 mb-4">Player Selection</h2>
        
        {/* Search */}
        <div className="relative mb-4">
          <MagnifyingGlassIcon className="absolute left-3 top-3 h-4 w-4 text-ink-400" />
          <input
            type="text"
            placeholder="Search players..."
            value={playerSearch}
            onChange={(e) => setPlayerSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-ink-300 rounded-md shadow-sm focus:border-accent-500 focus:ring-accent-500"
          />
          
          {/* Suggestions Dropdown */}
          {playerSuggestions.length > 0 && (
            <div className="absolute z-10 w-full mt-1 bg-white border border-ink-300 rounded-md shadow-lg max-h-60 overflow-y-auto">
              {playerSuggestions.map((player) => (
                <button
                  key={player.id}
                  onClick={() => addPlayer(player)}
                  className="w-full text-left px-4 py-2 hover:bg-ink-50 flex items-center justify-between"
                >
                  <div>
                    <div className="font-medium">{player.name}</div>
                    <div className="text-sm text-ink-600">{player.position} - {player.team}</div>
                  </div>
                  <PlusIcon className="h-4 w-4 text-accent-500" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected Players */}
        {selectedPlayers.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-ink-700 mb-2">Selected Players ({selectedPlayers.length}/5)</h3>
            <div className="flex flex-wrap gap-2">
              {selectedPlayers.map((player) => (
                <div key={player.id} className={`flex items-center px-3 py-1 rounded-full text-sm ${getPositionColor(player.position)}`}>
                  <span>{player.name} ({player.position})</span>
                  <button
                    onClick={() => removePlayer(player.id)}
                    className="ml-2 hover:opacity-75"
                  >
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Analysis Tabs */}
      <div className="bg-white rounded-lg border border-ink-200">
        {/* Tab Navigation */}
        <div className="border-b border-ink-200">
          <nav className="-mb-px flex space-x-8 px-6">
            {[
              { key: 'comparison', label: 'Player Comparison', icon: UserGroupIcon },
              { key: 'schedule', label: 'Schedule Analysis', icon: CalendarIcon },
              { key: 'breakout', label: 'Breakout Candidates', icon: TrendingUpIcon },
              { key: 'situations', label: 'Game Situations', icon: PlayIcon }
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key as 'comparison' | 'schedule' | 'breakout' | 'situations')}
                className={`flex items-center py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === key
                    ? 'border-accent-500 text-accent-600'
                    : 'border-transparent text-ink-500 hover:text-ink-700 hover:border-ink-300'
                }`}
              >
                <Icon className="h-4 w-4 mr-2" />
                {label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          {activeTab === 'comparison' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-ink-900">Player Comparison</h3>
                  <p className="text-ink-600">Compare up to 5 players across multiple metrics</p>
                </div>
                <button
                  onClick={runPlayerComparison}
                  disabled={loading || selectedPlayers.length < 2}
                  className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-ink-200 disabled:text-ink-400 disabled:cursor-not-allowed flex items-center"
                >
                  {loading ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  ) : (
                    <ChartBarIcon className="h-4 w-4 mr-2" />
                  )}
                  Compare Players
                </button>
              </div>
              {renderComparisonResults()}
            </div>
          )}

          {activeTab === 'schedule' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-ink-900">Strength of Schedule</h3>
                  <p className="text-ink-600">Analyze upcoming matchup difficulty</p>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <label className="text-sm font-medium text-ink-700">Weeks Ahead:</label>
                    <select
                      value={weeksAhead}
                      onChange={(e) => setWeeksAhead(parseInt(e.target.value))}
                      className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                    >
                      {[1, 2, 3, 4, 5, 6, 7, 8].map(weeks => (
                        <option key={weeks} value={weeks}>{weeks}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={runScheduleAnalysis}
                    disabled={loading || selectedPlayers.length === 0}
                    className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-ink-200 disabled:text-ink-400 disabled:cursor-not-allowed flex items-center"
                  >
                    {loading ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    ) : (
                      <CalendarIcon className="h-4 w-4 mr-2" />
                    )}
                    Analyze Schedule
                  </button>
                </div>
              </div>
              {renderScheduleResults()}
            </div>
          )}

          {activeTab === 'breakout' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-ink-900">Breakout Candidates</h3>
                  <p className="text-ink-600">Low-owned players trending up based on age, usage, and recent performance</p>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <label className="text-sm font-medium text-ink-700">Position:</label>
                    <select
                      value={breakoutPosition}
                      onChange={(e) => setBreakoutPosition(e.target.value)}
                      className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                    >
                      <option value="ALL">All Positions</option>
                      <option value="QB">QB</option>
                      <option value="RB">RB</option>
                      <option value="WR">WR</option>
                      <option value="TE">TE</option>
                    </select>
                  </div>
                  <div className="flex items-center space-x-2">
                    <label className="text-sm font-medium text-ink-700">Max Ownership:</label>
                    <select
                      value={maxOwnership}
                      onChange={(e) => setMaxOwnership(parseInt(e.target.value))}
                      className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                    >
                      <option value={25}>25%</option>
                      <option value={50}>50%</option>
                      <option value={75}>75%</option>
                      <option value={100}>100%</option>
                    </select>
                  </div>
                  <button
                    onClick={runBreakoutAnalysis}
                    disabled={loading}
                    className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-ink-200 disabled:text-ink-400 disabled:cursor-not-allowed flex items-center"
                  >
                    {loading ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    ) : (
                      <TrendingUpIcon className="h-4 w-4 mr-2" />
                    )}
                    Find Breakouts
                  </button>
                </div>
              </div>
              {renderBreakoutResults()}
            </div>
          )}

          {activeTab === 'situations' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-ink-900">Game Situation Analysis</h3>
                  <p className="text-ink-600">Performance across different game contexts</p>
                </div>
                <button
                  onClick={runSituationAnalysis}
                  disabled={loading || selectedPlayers.length === 0}
                  className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 disabled:bg-ink-200 disabled:text-ink-400 disabled:cursor-not-allowed flex items-center"
                >
                  {loading ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  ) : (
                    <PlayIcon className="h-4 w-4 mr-2" />
                  )}
                  Analyze Situations
                </button>
              </div>
              {renderSituationResults()}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
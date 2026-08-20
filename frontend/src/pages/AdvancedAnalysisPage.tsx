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
  difficulty_score: number
  difficulty_rating: 'EASY' | 'MODERATE' | 'DIFFICULT'
}

interface ScheduleAnalysisEntry {
  player: { id: number; name: string }
  upcoming_matchups: ScheduleMatchup[]
  schedule_difficulty: { rank: number; rating: 'EASY' | 'MODERATE' | 'DIFFICULT' }
  recommendation: string
}

interface ScheduleAnalysis {
  schedule_analysis: ScheduleAnalysisEntry[]
  summary: {
    easiest_schedule: string
    hardest_schedule: string
    average_difficulty: number
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

interface SituationAnalysisEntry {
  player: { id: number; name: string }
  situation_analysis: {
    home_vs_away: { home_average: number; away_average: number; preference: string }
    weather_impact: { outdoor_performance: number; dome_performance: number; weather_sensitivity: string }
    game_script: { leading_games: number; trailing_games: number; close_games?: number; script_preference: string }
  }
  key_insights: string[]
  upcoming_context: { outlook: string }
}

interface GameSituations {
  situation_analysis: SituationAnalysisEntry[]
  cross_player_insights: string[]
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
      
      const response = await api.post('/advanced-analysis/game-situations', {
        player_ids: selectedPlayers.map(p => p.id)
      })
      
      setSituationResult(response.data)
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
        <div className="flex items-center justify-between bg-gray-50 p-4 rounded-lg">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setShowCharts(!showCharts)}
              className="flex items-center space-x-2 text-sm text-gray-700 hover:text-gray-900"
            >
              {showCharts ? <EyeSlashIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
              <span>{showCharts ? 'Hide Charts' : 'Show Charts'}</span>
            </button>
            
            {showCharts && (
              <div className="flex items-center space-x-2">
                <label className="text-sm text-gray-700">Chart Type:</label>
                <select
                  value={chartType}
                  onChange={(e) => setChartType(e.target.value as 'radar' | 'bar' | 'both')}
                  className="text-sm border border-gray-300 rounded px-2 py-1"
                >
                  <option value="radar">Radar Chart</option>
                  <option value="bar">Bar Chart</option>
                  <option value="both">Both</option>
                </select>
              </div>
            )}
          </div>
          <div className="text-xs text-gray-500">
            Comparing {comparisonResult.players.length} players
          </div>
        </div>

        {/* Interactive Charts */}
        {showCharts && chartData.length > 0 && (
          <div className="space-y-6">
            {(chartType === 'radar' || chartType === 'both') && (
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Player Comparison Radar Chart</h3>
                <PlayerComparisonChart data={chartData} height={450} />
              </div>
            )}
            
            {(chartType === 'bar' || chartType === 'both') && (
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Detailed Metrics Comparison</h3>
                <PlayerComparisonBarChart data={chartData} height={400} />
              </div>
            )}
          </div>
        )}

        {/* Key Insights */}
        <div className="bg-blue-50 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-blue-900 mb-3">Key Insights</h3>
          <ul className="space-y-2">
            {comparisonResult.insights.map((insight, index) => (
              <li key={`comparison-insight-${index}-${insight.slice(0, 20)}`} className="text-blue-800">• {insight}</li>
            ))}
          </ul>
        </div>

        {/* Head-to-Head (for 2 players) */}
        {comparisonResult.head_to_head && Object.keys(comparisonResult.head_to_head).length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Head-to-Head Comparison</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(comparisonResult.head_to_head.categories || {}).map(([category, data]) => (
                <div key={category} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <span className="font-medium">{category}</span>
                  <span className="text-green-600 font-semibold">{data.winner}</span>
                </div>
              ))}
            </div>
            {comparisonResult.head_to_head.overall_winner && (
              <div className="mt-4 p-3 bg-green-50 rounded-lg text-center">
                <span className="text-green-800 font-semibold">
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
            <div key={player.id} className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">{player.name}</h3>
                <span className="px-2 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">
                  {player.position} - {player.team}
                </span>
              </div>
              
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Projected Points:</span>
                    <span className="ml-2 font-semibold">{player.current_metrics.projected_points || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Consistency:</span>
                    <span className="ml-2 font-semibold">{player.current_metrics.consistency_rating || 'N/A'}/10</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Risk Level:</span>
                    <span className={`ml-2 font-semibold ${
                      player.risk_assessment.risk_level === 'LOW' ? 'text-green-600' :
                      player.risk_assessment.risk_level === 'MEDIUM' ? 'text-yellow-600' : 'text-red-600'
                    }`}>
                      {player.risk_assessment.risk_level}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">Value Score:</span>
                    <span className="ml-2 font-semibold">{player.advanced_metrics.value_score}/100</span>
                  </div>
                </div>

                {player.risk_assessment.risk_factors.length > 0 && (
                  <div className="mt-3">
                    <span className="text-sm font-medium text-gray-700">Risk Factors:</span>
                    <ul className="mt-1 text-sm text-gray-600">
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
        <div className="bg-green-50 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-green-900 mb-2">Recommendation</h3>
          <p className="text-green-800">{comparisonResult.recommendation}</p>
        </div>
      </div>
    )
  }

  // Transform schedule data for charts
  const transformScheduleData = (scheduleAnalysis: ScheduleAnalysisEntry[]): ScheduleDifficultyData[] => {
    const data: ScheduleDifficultyData[] = []
    scheduleAnalysis.forEach(analysis => {
      analysis.upcoming_matchups.forEach((matchup) => {
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
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Schedule Summary (Next {weeksAhead} Weeks)</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{scheduleResult.summary.easiest_schedule}</div>
              <div className="text-sm text-gray-600">Easiest Schedule</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{scheduleResult.summary.hardest_schedule}</div>
              <div className="text-sm text-gray-600">Hardest Schedule</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">{scheduleResult.summary.average_difficulty}</div>
              <div className="text-sm text-gray-600">Average Difficulty</div>
            </div>
          </div>
        </div>

        {/* Schedule Difficulty Charts */}
        {showCharts && chartData.length > 0 && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Schedule Difficulty Chart</h3>
              <ScheduleDifficultyChart data={chartData} height={350} />
            </div>
            
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Schedule Difficulty Heatmap</h3>
              <ScheduleDifficultyHeatmap data={chartData} height={250} />
            </div>
          </div>
        )}

        {/* Player Schedule Analysis */}
        <div className="space-y-4">
          {scheduleResult.schedule_analysis.map((analysis) => (
            <div key={analysis.player.id} className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">{analysis.player.name}</h3>
                <div className="flex items-center space-x-4">
                  <span className="px-2 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">
                    Rank #{analysis.schedule_difficulty.rank}
                  </span>
                  <span className={`px-2 py-1 text-sm rounded-full ${
                    analysis.schedule_difficulty.rating === 'EASY' ? 'bg-green-100 text-green-800' :
                    analysis.schedule_difficulty.rating === 'MODERATE' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {analysis.schedule_difficulty.rating}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                {analysis.upcoming_matchups.map((matchup, idx: number) => (
                  <div key={idx} className="text-center p-3 bg-gray-50 rounded-lg">
                    <div className="font-semibold">Week {matchup.week}</div>
                    <div className="text-sm text-gray-600">{matchup.opponent}</div>
                    <div className={`text-sm font-medium ${
                      matchup.difficulty_rating === 'EASY' ? 'text-green-600' :
                      matchup.difficulty_rating === 'MODERATE' ? 'text-yellow-600' :
                      'text-red-600'
                    }`}>
                      {matchup.difficulty_score}/10
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-blue-50 p-3 rounded-lg">
                <span className="text-sm font-medium text-blue-900">Recommendation: </span>
                <span className="text-sm text-blue-800">{analysis.recommendation}</span>
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
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Breakout Analysis Summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">{breakoutResult.summary.total_candidates}</div>
              <div className="text-sm text-gray-600">Total Candidates</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{breakoutResult.summary.high_probability}</div>
              <div className="text-sm text-gray-600">High Probability</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-yellow-600">{breakoutResult.summary.medium_probability}</div>
              <div className="text-sm text-gray-600">Medium Probability</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">{(breakoutResult.summary.average_probability * 100).toFixed(1)}%</div>
              <div className="text-sm text-gray-600">Avg Probability</div>
            </div>
          </div>
        </div>

        {/* Breakout Candidate Charts */}
        {showCharts && chartData.length > 0 && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Breakout Probability Analysis</h3>
              <BreakoutCandidateBubbleChart data={chartData} height={400} />
            </div>
            
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Age vs Probability Scatter Plot</h3>
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
            <div key={candidate.player.id} className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">{candidate.player.name}</h3>
                <div className="flex items-center space-x-2">
                  <span className="px-2 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">
                    {candidate.player.position} - {candidate.player.team}
                  </span>
                  <span className={`px-2 py-1 text-sm font-semibold rounded-full ${
                    candidate.breakout_analysis.probability > 0.7 ? 'bg-green-100 text-green-800' :
                    candidate.breakout_analysis.probability > 0.5 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {(candidate.breakout_analysis.probability * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Age:</span>
                    <span className="ml-2 font-semibold">{candidate.player.age || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Ownership:</span>
                    <span className="ml-2 font-semibold">{candidate.player.ownership_percentage?.toFixed(1) || '0'}%</span>
                  </div>
                </div>

                {candidate.supporting_factors.length > 0 && (
                  <div>
                    <span className="text-sm font-medium text-green-700">Supporting Factors:</span>
                    <ul className="mt-1 text-sm text-green-600">
                      {candidate.supporting_factors.map((factor: string, idx: number) => (
                        <li key={idx}>• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {candidate.risk_factors.length > 0 && (
                  <div>
                    <span className="text-sm font-medium text-red-700">Risk Factors:</span>
                    <ul className="mt-1 text-sm text-red-600">
                      {candidate.risk_factors.map((factor: string, idx: number) => (
                        <li key={idx}>• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="bg-gray-50 p-3 rounded-lg">
                  <span className="text-sm font-medium text-gray-900">Recommendation: </span>
                  <span className="text-sm text-gray-800">{candidate.recommendation}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Transform situation data for charts
  const transformSituationData = (situationAnalysis: SituationAnalysisEntry[]): {
    homeAwayData: SituationalData[],
    weatherData: WeatherDataItem[],
    gameScriptData: GameScriptDataItem[]
  } => {
    const homeAwayData: SituationalData[] = situationAnalysis.map(analysis => ({
      situation: 'Home vs Away',
      home: analysis.situation_analysis.home_vs_away.home_average,
      away: analysis.situation_analysis.home_vs_away.away_average,
      player: analysis.player.name
    }))

    const weatherData = situationAnalysis.map(analysis => ({
      player: analysis.player.name,
      outdoor: analysis.situation_analysis.weather_impact.outdoor_performance,
      dome: analysis.situation_analysis.weather_impact.dome_performance,
      weatherSensitivity: analysis.situation_analysis.weather_impact.weather_sensitivity
    }))

    const gameScriptData = situationAnalysis.map(analysis => ({
      player: analysis.player.name,
      leading: analysis.situation_analysis.game_script.leading_games,
      trailing: analysis.situation_analysis.game_script.trailing_games,
      close: analysis.situation_analysis.game_script.close_games || 
             (analysis.situation_analysis.game_script.leading_games + analysis.situation_analysis.game_script.trailing_games) / 2
    }))

    return { homeAwayData, weatherData, gameScriptData }
  }

  const renderSituationResults = () => {
    if (!situationResult) return null

    const { homeAwayData, weatherData, gameScriptData } = transformSituationData(situationResult.situation_analysis)

    return (
      <div className="space-y-6">
        {/* Cross-Player Insights */}
        {situationResult.cross_player_insights.length > 0 && (
          <div className="bg-blue-50 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-blue-900 mb-3">Key Insights</h3>
            <ul className="space-y-2">
              {situationResult.cross_player_insights.map((insight, index) => (
                <li key={`situation-insight-${index}-${insight.slice(0, 20)}`} className="text-blue-800">• {insight}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Situational Analysis Charts */}
        {showCharts && homeAwayData.length > 0 && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Home vs Away Performance</h3>
              <SituationalAnalysisChart 
                data={homeAwayData} 
                height={300}
                chartType="comparison"
              />
            </div>
            
            {weatherData.length > 0 && (
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Weather Impact Analysis</h3>
                <WeatherImpactChart data={weatherData} height={250} />
              </div>
            )}
            
            {gameScriptData.length > 0 && gameScriptData[0] && (
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Game Script Performance</h3>
                <GameScriptChart data={gameScriptData} height={250} />
              </div>
            )}
          </div>
        )}

        {/* Player Situation Analysis */}
        <div className="space-y-6">
          {situationResult.situation_analysis.map((analysis) => (
            <div key={analysis.player.id} className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">{analysis.player.name}</h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Home vs Away */}
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="font-semibold text-gray-900 mb-2">Home vs Away</h4>
                  <div className="space-y-1 text-sm">
                    <div>Home: {analysis.situation_analysis.home_vs_away.home_average} pts</div>
                    <div>Away: {analysis.situation_analysis.home_vs_away.away_average} pts</div>
                    <div className="font-medium text-blue-600">
                      Prefers: {analysis.situation_analysis.home_vs_away.preference}
                    </div>
                  </div>
                </div>

                {/* Weather Impact */}
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="font-semibold text-gray-900 mb-2">Weather Impact</h4>
                  <div className="space-y-1 text-sm">
                    <div>Outdoor: {analysis.situation_analysis.weather_impact.outdoor_performance} pts</div>
                    <div>Dome: {analysis.situation_analysis.weather_impact.dome_performance} pts</div>
                    <div className="font-medium text-blue-600">
                      Sensitivity: {analysis.situation_analysis.weather_impact.weather_sensitivity}
                    </div>
                  </div>
                </div>

                {/* Game Script */}
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="font-semibold text-gray-900 mb-2">Game Script</h4>
                  <div className="space-y-1 text-sm">
                    <div>Leading: {analysis.situation_analysis.game_script.leading_games} pts</div>
                    <div>Trailing: {analysis.situation_analysis.game_script.trailing_games} pts</div>
                    <div className="font-medium text-blue-600">
                      Best: {analysis.situation_analysis.game_script.script_preference}
                    </div>
                  </div>
                </div>
              </div>

              {/* Key Insights */}
              {analysis.key_insights.length > 0 && (
                <div className="mt-4 bg-green-50 p-3 rounded-lg">
                  <span className="text-sm font-medium text-green-900">Key Insights: </span>
                  <ul className="mt-1 text-sm text-green-800">
                    {analysis.key_insights.map((insight: string, idx: number) => (
                      <li key={idx}>• {insight}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Upcoming Context */}
              <div className="mt-4 bg-blue-50 p-3 rounded-lg">
                <span className="text-sm font-medium text-blue-900">Next Game: </span>
                <span className="text-sm text-blue-800">{analysis.upcoming_context.outlook}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-sm font-medium text-gray-900">Authentication Required</h3>
        <p className="mt-1 text-sm text-gray-500">Please log in to access Advanced Analysis features.</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Advanced Analysis</h1>
          <p className="text-gray-600 mt-2">
            Deep player insights, comparisons, and predictive analytics
          </p>
        </div>
        <ChartBarIcon className="h-8 w-8 text-blue-600" />
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <div className="mt-2 text-sm text-red-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Player Selection */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Player Selection</h2>
        
        {/* Search */}
        <div className="relative mb-4">
          <MagnifyingGlassIcon className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search players..."
            value={playerSearch}
            onChange={(e) => setPlayerSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500"
          />
          
          {/* Suggestions Dropdown */}
          {playerSuggestions.length > 0 && (
            <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-y-auto">
              {playerSuggestions.map((player) => (
                <button
                  key={player.id}
                  onClick={() => addPlayer(player)}
                  className="w-full text-left px-4 py-2 hover:bg-gray-50 flex items-center justify-between"
                >
                  <div>
                    <div className="font-medium">{player.name}</div>
                    <div className="text-sm text-gray-600">{player.position} - {player.team}</div>
                  </div>
                  <PlusIcon className="h-4 w-4 text-blue-600" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected Players */}
        {selectedPlayers.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Selected Players ({selectedPlayers.length}/5)</h3>
            <div className="flex flex-wrap gap-2">
              {selectedPlayers.map((player) => (
                <div key={player.id} className="flex items-center bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
                  <span>{player.name} ({player.position})</span>
                  <button
                    onClick={() => removePlayer(player.id)}
                    className="ml-2 text-blue-600 hover:text-blue-800"
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
      <div className="bg-white rounded-lg border border-gray-200">
        {/* Tab Navigation */}
        <div className="border-b border-gray-200">
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
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
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
                  <h3 className="text-lg font-semibold text-gray-900">Player Comparison</h3>
                  <p className="text-gray-600">Compare up to 5 players across multiple metrics</p>
                </div>
                <button
                  onClick={runPlayerComparison}
                  disabled={loading || selectedPlayers.length < 2}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
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
                  <h3 className="text-lg font-semibold text-gray-900">Strength of Schedule</h3>
                  <p className="text-gray-600">Analyze upcoming matchup difficulty</p>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <label className="text-sm font-medium text-gray-700">Weeks Ahead:</label>
                    <select
                      value={weeksAhead}
                      onChange={(e) => setWeeksAhead(parseInt(e.target.value))}
                      className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                    >
                      {[1, 2, 3, 4, 5, 6, 7, 8].map(weeks => (
                        <option key={weeks} value={weeks}>{weeks}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={runScheduleAnalysis}
                    disabled={loading || selectedPlayers.length === 0}
                    className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
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
                  <h3 className="text-lg font-semibold text-gray-900">Breakout Candidates</h3>
                  <p className="text-gray-600">ML-powered breakout player detection</p>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <label className="text-sm font-medium text-gray-700">Position:</label>
                    <select
                      value={breakoutPosition}
                      onChange={(e) => setBreakoutPosition(e.target.value)}
                      className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                    >
                      <option value="ALL">All Positions</option>
                      <option value="QB">QB</option>
                      <option value="RB">RB</option>
                      <option value="WR">WR</option>
                      <option value="TE">TE</option>
                    </select>
                  </div>
                  <div className="flex items-center space-x-2">
                    <label className="text-sm font-medium text-gray-700">Max Ownership:</label>
                    <select
                      value={maxOwnership}
                      onChange={(e) => setMaxOwnership(parseInt(e.target.value))}
                      className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
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
                    className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
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
                  <h3 className="text-lg font-semibold text-gray-900">Game Situation Analysis</h3>
                  <p className="text-gray-600">Performance across different game contexts</p>
                </div>
                <button
                  onClick={runSituationAnalysis}
                  disabled={loading || selectedPlayers.length === 0}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
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
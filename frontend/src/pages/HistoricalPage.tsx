import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../hooks/useAuth'
import { historical, players, getErrorMessage } from '../services/api'
import { getPositionColor } from '../components/players/playerDisplay'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import {
  ChartBarIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  CalendarIcon,
  UserIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  FireIcon,
  CheckCircleIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline'

interface HistoricalSummary {
  player_id: number
  player_name: string
  position: string
  seasons_analyzed: number
  historical_average: number
  historical_consistency: number
  season_summaries: SeasonSummary[]
  career_trend: CareerTrend
  recent_trend: RecentTrend
}

interface SeasonSummary {
  season: number
  games_played: number
  avg_points: number
  total_points: number
  consistency_score: number
  ceiling: number
  floor: number
  boom_weeks: number
  bust_weeks: number
  trend_direction: string
  position_finish: number
}

interface CareerTrend {
  direction: string
  strength: number
  performance_change: number
}

interface RecentTrend {
  direction: string
  strength: number
  performance_change: number
}

interface DataOverview {
  data_coverage: {
    total_performance_records: number
    season_summaries: number
    trend_analyses: number
    matchup_records: number
    players_with_data: number
    seasons_covered: number[]
    latest_update: string
  }
  recommendations: {
    sync_needed: boolean
    data_freshness: string
  }
}

interface PlayerSearchResult {
  id?: number
  sleeper_id?: string
  full_name?: string
  name?: string
  position?: string
  team?: string
}

interface TrendingPlayer {
  player_id: number
  player_name: string
  position: string
  team: string
  trend_direction: string
  trend_strength: number
  performance_change: number
  confidence_level: number
  sample_size: number
  last_updated: string
}

function TrendsTab() {
  const [trendingPlayers, setTrendingPlayers] = useState<TrendingPlayer[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedPosition, setSelectedPosition] = useState<string>('all')
  const [trendType, setTrendType] = useState<string>('career')

  const loadTrendingPlayers = useCallback(async () => {
    try {
      setLoading(true)
      setError('')

      const params: { trend_type: string; limit: number; position?: string } = {
        trend_type: trendType,
        limit: 50
      }

      if (selectedPosition !== 'all') {
        params.position = selectedPosition
      }

      const response = await historical.getLeagueTrends(params)
      setTrendingPlayers(response.data.trending_players || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load trending players'))
    } finally {
      setLoading(false)
    }
  }, [selectedPosition, trendType])

  useEffect(() => {
    loadTrendingPlayers()
  }, [loadTrendingPlayers])

  const getTrendIcon = (direction: string) => {
    switch (direction) {
      case 'up':
        return <ArrowTrendingUpIcon className="h-5 w-5 text-success-600" />
      case 'down':
        return <ArrowTrendingDownIcon className="h-5 w-5 text-danger-600" />
      default:
        return <div className="h-5 w-5 bg-faint rounded-full" />
    }
  }

  const formatPerformanceChange = (change: number) => {
    const prefix = change > 0 ? '+' : ''
    return `${prefix}${change.toFixed(1)}%`
  }

  const positions = ['all', 'QB', 'RB', 'WR', 'TE']
  const trendTypes = [
    { value: 'career', label: 'Career Trends' },
    { value: 'season', label: 'Season Trends' },
    { value: '8_week', label: 'Recent (8 weeks)' }
  ]

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
        <h3 className="text-lg font-medium text-body mb-4">Performance Trends Analysis</h3>
        <div className="flex flex-col sm:flex-row space-y-4 sm:space-y-0 sm:space-x-4">
          <div>
            <label className="block text-sm font-medium text-body mb-1">Trend Type</label>
            <select
              value={trendType}
              onChange={(e) => setTrendType(e.target.value)}
              className="rounded-md border-line focus:outline-none focus:ring-2 focus:ring-volt"
            >
              {trendTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-body mb-1">Position</label>
            <select
              value={selectedPosition}
              onChange={(e) => setSelectedPosition(e.target.value)}
              className="rounded-md border-line focus:outline-none focus:ring-2 focus:ring-volt"
            >
              {positions.map(position => (
                <option key={position} value={position}>
                  {position === 'all' ? 'All Positions' : position}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-danger-50 border border-danger-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-danger-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-danger-800">Error</h3>
              <div className="mt-2 text-sm text-danger-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Trending Players */}
      {loading ? (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
          <p className="text-sm text-muted">Loading trending players...</p>
        </div>
      ) : trendingPlayers.length === 0 ? (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
          <ChartBarIcon className="mx-auto h-12 w-12 text-faint" />
          <h3 className="mt-2 text-sm font-medium text-body">No trending players found</h3>
          <p className="mt-1 text-sm text-muted">
            Try adjusting your filters or check back after more data is synced.
          </p>
        </div>
      ) : (
        <div className="bg-surface rounded-lg border border-hairline">
          <div className="px-6 py-4 border-b border-hairline">
            <h4 className="text-lg font-medium text-body">
              Trending Players ({trendingPlayers.length} found)
            </h4>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-hairline">
              <thead className="bg-surface-2">
                <tr>
                  <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Player
                  </th>
                  <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Trend
                  </th>
                  <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Performance Change
                  </th>
                  <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    <span className="flex items-center gap-1.5">
                      Confidence
                      <DataConfidenceBadge level="heuristic" />
                    </span>
                  </th>
                  <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Sample Size
                  </th>
                </tr>
              </thead>
              <tbody className="bg-surface divide-y divide-hairline">
                {trendingPlayers.map((player) => (
                  <tr key={player.player_id} className="hover:bg-surface-2">
                    <td className="px-3 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                            {player.position}
                          </span>
                        </div>
                        <div className="ml-4">
                          <div className="text-sm font-medium text-body">{player.player_name}</div>
                          <div className="text-sm text-muted">{player.team || 'FA'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center space-x-2">
                        {getTrendIcon(player.trend_direction)}
                        <span className="text-sm font-medium">
                          {player.trend_direction.charAt(0).toUpperCase() + player.trend_direction.slice(1)}
                        </span>
                        <span className="text-xs text-muted">
                          ({(player.trend_strength * 100).toFixed(0)}% strength)
                        </span>
                      </div>
                    </td>
                    <td className="px-3 sm:px-6 py-4 whitespace-nowrap">
                      <span className={`text-sm font-medium ${
                        player.performance_change > 0 ? 'text-success-600' : 
                        player.performance_change < 0 ? 'text-danger-600' : 'text-muted'
                      }`}>
                        {formatPerformanceChange(player.performance_change)}
                      </span>
                    </td>
                    <td className="px-3 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="w-16 bg-surface-2 rounded-full h-2">
                          <div
                            className="bg-accent-500 h-2 rounded-full"
                            style={{ width: `${player.confidence_level * 100}%` }}
                          ></div>
                        </div>
                        <span className="ml-2 text-xs text-muted">
                          {(player.confidence_level * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm text-body">
                      {player.sample_size} games
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export function HistoricalPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'overview' | 'players' | 'trends' | 'analysis'>('overview')
  const [dataOverview, setDataOverview] = useState<DataOverview | null>(null)
  const [playerSummary, setPlayerSummary] = useState<HistoricalSummary | null>(null)
  const [playerSearchResults, setPlayerSearchResults] = useState<PlayerSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    if (user) {
      loadDataOverview()
    }
  }, [user])

  const loadDataOverview = async () => {
    try {
      setLoading(true)
      const response = await historical.getOverview()
      setDataOverview(response.data)
    } catch (err) {
      console.error('Error loading historical data overview:', err)
      setError(getErrorMessage(err, "Historical performance data isn't available right now"))
    } finally {
      setLoading(false)
    }
  }

  const searchPlayers = async (query: string) => {
    if (query.length < 2) {
      setPlayerSearchResults([])
      return
    }

    try {
      const response = await players.search(query)
      const matches = response.data.matches || []
      setPlayerSearchResults(matches)
    } catch (err) {
      console.error('Error searching players:', err)
      setPlayerSearchResults([])
    }
  }

  const loadPlayerSummary = async (playerId: number) => {
    try {
      setLoading(true)
      setError('')
      const response = await historical.getPlayerSummary(playerId, 3)
      setPlayerSummary(response.data)
    } catch (err) {
      console.error('Error loading player summary:', err)
      setError(getErrorMessage(err, 'Failed to load player summary'))
      setPlayerSummary(null)
    } finally {
      setLoading(false)
    }
  }

  const syncHistoricalData = async () => {
    try {
      setSyncing(true)
      setError('')
      await historical.sync({ seasons: undefined, force_refresh: false })
      
      // Show success message and reload overview
      setTimeout(() => {
        loadDataOverview()
        setSyncing(false)
      }, 3000)
      
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to start historical sync'))
      setSyncing(false)
    }
  }

  const getTrendIcon = (direction: string) => {
    switch (direction) {
      case 'up':
        return <ArrowTrendingUpIcon className="h-5 w-5 text-success-600" />
      case 'down':
        return <ArrowTrendingDownIcon className="h-5 w-5 text-danger-600" />
      default:
        return <div className="h-5 w-5 bg-faint rounded-full" />
    }
  }

  // Only 3 status colors exist in this app's real token system
  // (success/warning/danger) -- collapsing 5 letter grades onto them
  // rather than inventing a 5-step color ramp the design system doesn't
  // have (see STYLE_GUIDE.md section 1: these tokens carry fixed
  // categorical meaning, not an arbitrary decorative scale).
  const getConsistencyGrade = (score: number) => {
    if (score >= 0.6) return { grade: score >= 0.8 ? 'A' : 'B', color: 'text-success-600' }
    if (score >= 0.4) return { grade: 'C', color: 'text-warning-600' }
    return { grade: score >= 0.2 ? 'D' : 'F', color: 'text-danger-600' }
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-faint" />
          <h3 className="mt-2 text-sm font-medium text-body">Authentication Required</h3>
          <p className="mt-1 text-sm text-muted">Please sign in to access historical performance data.</p>
        </div>
      </div>
    )
  }

  const tabs = [
    { id: 'overview', name: 'Data Overview', icon: ChartBarIcon },
    { id: 'players', name: 'Player History', icon: UserIcon },
    { id: 'trends', name: 'Performance Trends', icon: ArrowTrendingUpIcon },
    { id: 'analysis', name: 'Advanced Analysis', icon: FireIcon },
  ]

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Historical Performance</h1>
            <p className="text-muted mt-2">
              Week-by-week production, boom/bust rates, and multi-season trends for any player.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {dataOverview?.recommendations.sync_needed && (
              <div className="text-sm text-warning-800 bg-warning-100 px-3 py-1 rounded-full">
                Sync Needed
              </div>
            )}
            <button
              onClick={syncHistoricalData}
              disabled={syncing}
              className="bg-volt text-volt-ink px-4 py-2 rounded-md hover:bg-volt-dark transition-colors disabled:bg-surface-2 disabled:text-faint disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-volt flex items-center space-x-2"
            >
              <ArrowPathIcon className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              <span>{syncing ? 'Syncing...' : 'Sync Data'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mb-6 bg-danger-50 border border-danger-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-danger-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-danger-800">Error</h3>
              <div className="mt-2 text-sm text-danger-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="border-b border-hairline mb-6">
        <nav className="-mb-px flex gap-6 overflow-x-auto no-scrollbar">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as 'overview' | 'players' | 'trends' | 'analysis')}
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
      {activeTab === 'overview' && dataOverview && (
        <div className="space-y-6">
          {/* Data Coverage Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
              <div className="flex items-center">
                <ChartBarIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Performance Records</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {dataOverview.data_coverage.total_performance_records.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
              <div className="flex items-center">
                <UserIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Players Tracked</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {dataOverview.data_coverage.players_with_data}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
              <div className="flex items-center">
                <CalendarIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Seasons Covered</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {dataOverview.data_coverage.seasons_covered.length}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
              <div className="flex items-center">
                <ArrowTrendingUpIcon className="h-8 w-8 text-accent-ink" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-muted">Trend Analyses</p>
                  <p className="text-2xl font-stat tabular-nums font-semibold text-body">
                    {dataOverview.data_coverage.trend_analyses}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Data Status */}
          <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
            <h3 className="text-lg font-medium text-body mb-4">Data Status</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-medium text-body mb-2">Coverage</h4>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted">Seasons</span>
                    <span className="text-sm font-medium">
                      {dataOverview.data_coverage.seasons_covered.join(', ')}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted">Last Update</span>
                    <span className="text-sm font-medium">
                      {dataOverview.data_coverage.latest_update 
                        ? new Date(dataOverview.data_coverage.latest_update).toLocaleDateString()
                        : 'Never'
                      }
                    </span>
                  </div>
                </div>
              </div>
              <div>
                <h4 className="font-medium text-body mb-2">Data Quality</h4>
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    {dataOverview.recommendations.data_freshness === 'current' ? (
                      <CheckCircleIcon className="h-4 w-4 text-success-600" />
                    ) : (
                      <ExclamationTriangleIcon className="h-4 w-4 text-warning-600" />
                    )}
                    <span className="text-sm text-muted">
                      Data {dataOverview.recommendations.data_freshness}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    {!dataOverview.recommendations.sync_needed ? (
                      <CheckCircleIcon className="h-4 w-4 text-success-600" />
                    ) : (
                      <ClockIcon className="h-4 w-4 text-warning-600" />
                    )}
                    <span className="text-sm text-muted">
                      {dataOverview.recommendations.sync_needed ? 'Sync recommended' : 'Up to date'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'players' && (
        <div className="space-y-6">
          {/* Player Search */}
          <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
            <h3 className="text-lg font-medium text-body mb-4">Player Historical Analysis</h3>
            <div className="mb-4">
              <p className="text-sm text-muted mb-2">
                Try searching for: Josh Allen, Christian McCaffrey, Tyreek Hill, or Travis Kelce
              </p>
            </div>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  searchPlayers(e.target.value)
                }}
                className="block w-full rounded-md border-line focus:outline-none focus:ring-2 focus:ring-volt sm:text-sm"
                placeholder="Search for a player..."
              />
              
              {/* Search Results */}
              {playerSearchResults.length > 0 && (
                <div className="absolute z-10 mt-1 w-full bg-surface rounded-md border border-hairline max-h-60 overflow-auto">
                  {playerSearchResults.map((player) => (
                    <button
                      key={player.id || player.sleeper_id}
                      onClick={async () => {
                        setSearchQuery(player.full_name || player.name || '')
                        setPlayerSearchResults([])
                        
                        if (player.id) {
                          // Player is already in our database, load their summary
                          loadPlayerSummary(player.id)
                        } else if (player.sleeper_id) {
                          // Player is not in our database but has Sleeper ID, add them first
                          try {
                            setLoading(true)
                            setError('')
                            const response = await players.addFromSleeper(player.sleeper_id)
                            
                            if (response.data.player_id) {
                              // Player was added successfully, now load their summary
                              loadPlayerSummary(response.data.player_id)
                            } else {
                              setError('Player was added but summary could not be loaded')
                            }
                          } catch (err) {
                            setError(getErrorMessage(err, 'Failed to add player to database'))
                            setLoading(false)
                          }
                        }
                      }}
                      className={`w-full px-4 py-2 text-left hover:bg-surface-2 flex items-center justify-between ${
                        !player.id ? 'opacity-60' : ''
                      }`}
                    >
                      <div>
                        <span className="font-medium">{player.full_name || player.name}</span>
                        <span className="text-sm text-muted ml-2">
                          {player.position} - {player.team || 'FA'}
                          {!player.id && player.sleeper_id && ' (Will add to database)'}
                          {!player.id && !player.sleeper_id && ' (No data available)'}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Player Summary */}
          {loading && (
            <div className="bg-surface rounded-lg border border-hairline p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
              <p className="text-sm text-muted">Loading historical data...</p>
            </div>
          )}

          {playerSummary && (
            <div className="space-y-6">
              {/* Player Header */}
              <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xl font-bold text-body">{playerSummary.player_name}</h3>
                    <p className="text-muted">{playerSummary.position} • {playerSummary.seasons_analyzed} seasons analyzed</p>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-stat tabular-nums font-semibold text-accent-ink">
                      {playerSummary.historical_average.toFixed(1)}
                    </div>
                    <div className="text-sm text-muted">Avg PPR Points</div>
                  </div>
                </div>
              </div>

              {/* Career Trends */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
                  <h4 className="font-medium text-body mb-4">Career Trend</h4>
                  {playerSummary.career_trend ? (
                    <div className="space-y-3">
                      <div className="flex items-center space-x-2">
                        {getTrendIcon(playerSummary.career_trend.direction)}
                        <span className="font-medium">
                          {playerSummary.career_trend.direction.charAt(0).toUpperCase() + 
                           playerSummary.career_trend.direction.slice(1)} Trend
                        </span>
                      </div>
                      <div className="text-sm text-muted">
                        <p>Strength: {(playerSummary.career_trend.strength * 100).toFixed(1)}%</p>
                        <p>Performance Change: {playerSummary.career_trend.performance_change > 0 ? '+' : ''}
                           {playerSummary.career_trend.performance_change.toFixed(1)}%</p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted">No career trend data available</p>
                  )}
                </div>

                <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
                  <h4 className="font-medium text-body mb-4">Recent Form</h4>
                  {playerSummary.recent_trend ? (
                    <div className="space-y-3">
                      <div className="flex items-center space-x-2">
                        {getTrendIcon(playerSummary.recent_trend.direction)}
                        <span className="font-medium">
                          {playerSummary.recent_trend.direction.charAt(0).toUpperCase() + 
                           playerSummary.recent_trend.direction.slice(1)} (Recent)
                        </span>
                      </div>
                      <div className="text-sm text-muted">
                        <p>Strength: {(playerSummary.recent_trend.strength * 100).toFixed(1)}%</p>
                        <p>Performance Change: {playerSummary.recent_trend.performance_change > 0 ? '+' : ''}
                           {playerSummary.recent_trend.performance_change.toFixed(1)}%</p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted">No recent trend data available</p>
                  )}
                </div>
              </div>

              {/* Season Summaries */}
              <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
                <h4 className="font-medium text-body mb-4">Season-by-Season Performance</h4>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-hairline">
                    <thead className="bg-surface-2">
                      <tr>
                        <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                          Season
                        </th>
                        <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                          Games
                        </th>
                        <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                          Avg Points
                        </th>
                        <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                          Consistency
                        </th>
                        <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                          Ceiling/Floor
                        </th>
                        <th className="px-3 sm:px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                          Trend
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-surface divide-y divide-hairline">
                      {playerSummary.season_summaries.map((season) => {
                        const consistency = getConsistencyGrade(season.consistency_score)
                        return (
                          <tr key={season.season}>
                            <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm font-medium text-body">
                              {season.season}
                            </td>
                            <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm text-body">
                              {season.games_played}
                            </td>
                            <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm text-body">
                              {season.avg_points.toFixed(1)}
                            </td>
                            <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm">
                              <span className={`font-medium ${consistency.color}`}>
                                {consistency.grade}
                              </span>
                            </td>
                            <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm text-body">
                              {season.ceiling.toFixed(1)} / {season.floor.toFixed(1)}
                            </td>
                            <td className="px-3 sm:px-6 py-4 whitespace-nowrap text-sm">
                              <div className="flex items-center space-x-1">
                                {getTrendIcon(season.trend_direction)}
                                <span className="text-xs">{season.trend_direction}</span>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'trends' && (
        <TrendsTab />
      )}

      {activeTab === 'analysis' && (
        <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-4">Advanced Analysis</h3>
          <p className="text-muted">Advanced statistical analysis and predictive modeling coming soon...</p>
        </div>
      )}
    </div>
  )
}
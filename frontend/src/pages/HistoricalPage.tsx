import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../hooks/useAuth'
import { historical, players, getErrorMessage } from '../services/api'
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
        return <ArrowTrendingUpIcon className="h-5 w-5 text-green-500" />
      case 'down':
        return <ArrowTrendingDownIcon className="h-5 w-5 text-red-500" />
      default:
        return <div className="h-5 w-5 bg-gray-300 rounded-full" />
    }
  }

  const getPositionColor = (position: string) => {
    const colors: Record<string, string> = {
      QB: 'bg-red-100 text-red-800',
      RB: 'bg-green-100 text-green-800', 
      WR: 'bg-blue-100 text-blue-800',
      TE: 'bg-purple-100 text-purple-800',
      K: 'bg-yellow-100 text-yellow-800',
      DEF: 'bg-gray-100 text-gray-800'
    }
    return colors[position] || 'bg-gray-100 text-gray-800'
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
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Performance Trends Analysis</h3>
        <div className="flex flex-col sm:flex-row space-y-4 sm:space-y-0 sm:space-x-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Trend Type</label>
            <select
              value={trendType}
              onChange={(e) => setTrendType(e.target.value)}
              className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            >
              {trendTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Position</label>
            <select
              value={selectedPosition}
              onChange={(e) => setSelectedPosition(e.target.value)}
              className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
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

      {/* Trending Players */}
      {loading ? (
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <ClockIcon className="animate-spin h-8 w-8 text-blue-600 mx-auto mb-2" />
          <p className="text-sm text-gray-500">Loading trending players...</p>
        </div>
      ) : trendingPlayers.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <ChartBarIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No trending players found</h3>
          <p className="mt-1 text-sm text-gray-500">
            Try adjusting your filters or check back after more data is synced.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h4 className="text-lg font-medium text-gray-900">
              Trending Players ({trendingPlayers.length} found)
            </h4>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Player
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Trend
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Performance Change
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Confidence
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Sample Size
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {trendingPlayers.map((player) => (
                  <tr key={player.player_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                            {player.position}
                          </span>
                        </div>
                        <div className="ml-4">
                          <div className="text-sm font-medium text-gray-900">{player.player_name}</div>
                          <div className="text-sm text-gray-500">{player.team || 'FA'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center space-x-2">
                        {getTrendIcon(player.trend_direction)}
                        <span className="text-sm font-medium">
                          {player.trend_direction.charAt(0).toUpperCase() + player.trend_direction.slice(1)}
                        </span>
                        <span className="text-xs text-gray-500">
                          ({(player.trend_strength * 100).toFixed(0)}% strength)
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`text-sm font-medium ${
                        player.performance_change > 0 ? 'text-green-600' : 
                        player.performance_change < 0 ? 'text-red-600' : 'text-gray-600'
                      }`}>
                        {formatPerformanceChange(player.performance_change)}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="w-16 bg-gray-200 rounded-full h-2">
                          <div 
                            className="bg-blue-600 h-2 rounded-full" 
                            style={{ width: `${player.confidence_level * 100}%` }}
                          ></div>
                        </div>
                        <span className="ml-2 text-xs text-gray-500">
                          {(player.confidence_level * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
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
      console.log('Searching for:', query)
      const response = await players.search(query)
      const matches = response.data.matches || []
      console.log('Search results:', matches)
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
      console.log('Loading player summary for ID:', playerId)
      const response = await historical.getPlayerSummary(playerId, 3)
      console.log('Player summary response:', response.data)
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
        return <ArrowTrendingUpIcon className="h-5 w-5 text-green-500" />
      case 'down':
        return <ArrowTrendingDownIcon className="h-5 w-5 text-red-500" />
      default:
        return <div className="h-5 w-5 bg-gray-300 rounded-full" />
    }
  }

  const getConsistencyGrade = (score: number) => {
    if (score >= 0.8) return { grade: 'A', color: 'text-green-600' }
    if (score >= 0.6) return { grade: 'B', color: 'text-blue-600' }
    if (score >= 0.4) return { grade: 'C', color: 'text-yellow-600' }
    if (score >= 0.2) return { grade: 'D', color: 'text-orange-600' }
    return { grade: 'F', color: 'text-red-600' }
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">Authentication Required</h3>
          <p className="mt-1 text-sm text-gray-500">Please sign in to access historical performance data.</p>
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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Historical Performance</h1>
            <p className="text-gray-600 mt-2">
              Analyze player performance trends, consistency patterns, and historical data
            </p>
          </div>
          <div className="flex items-center space-x-3">
            {dataOverview?.recommendations.sync_needed && (
              <div className="text-sm text-orange-600 bg-orange-50 px-3 py-1 rounded-full">
                Sync Needed
              </div>
            )}
            <button
              onClick={syncHistoricalData}
              disabled={syncing}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center space-x-2"
            >
              <ArrowPathIcon className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              <span>{syncing ? 'Syncing...' : 'Sync Data'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <div className="mt-2 text-sm text-red-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as 'overview' | 'players' | 'trends' | 'analysis')}
                className={`py-2 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
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
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <ChartBarIcon className="h-8 w-8 text-blue-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Performance Records</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {dataOverview.data_coverage.total_performance_records.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <UserIcon className="h-8 w-8 text-green-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Players Tracked</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {dataOverview.data_coverage.players_with_data}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <CalendarIcon className="h-8 w-8 text-purple-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Seasons Covered</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {dataOverview.data_coverage.seasons_covered.length}
                  </p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <ArrowTrendingUpIcon className="h-8 w-8 text-orange-600" />
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Trend Analyses</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {dataOverview.data_coverage.trend_analyses}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Data Status */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Data Status</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-medium text-gray-700 mb-2">Coverage</h4>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Seasons</span>
                    <span className="text-sm font-medium">
                      {dataOverview.data_coverage.seasons_covered.join(', ')}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Last Update</span>
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
                <h4 className="font-medium text-gray-700 mb-2">Data Quality</h4>
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    {dataOverview.recommendations.data_freshness === 'current' ? (
                      <CheckCircleIcon className="h-4 w-4 text-green-500" />
                    ) : (
                      <ExclamationTriangleIcon className="h-4 w-4 text-yellow-500" />
                    )}
                    <span className="text-sm text-gray-600">
                      Data {dataOverview.recommendations.data_freshness}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    {!dataOverview.recommendations.sync_needed ? (
                      <CheckCircleIcon className="h-4 w-4 text-green-500" />
                    ) : (
                      <ClockIcon className="h-4 w-4 text-yellow-500" />
                    )}
                    <span className="text-sm text-gray-600">
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
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Player Historical Analysis</h3>
            <div className="mb-4">
              <p className="text-sm text-gray-600 mb-2">
                Try searching for: Josh Allen, Christian McCaffrey, Tyreek Hill, or Travis Kelce
              </p>
              {process.env.NODE_ENV === 'development' && (
                <div className="mt-2 p-2 bg-gray-100 rounded text-xs">
                  <div>Search Query: {searchQuery}</div>
                  <div>Search Results Count: {playerSearchResults.length}</div>
                  <div>Loading: {loading ? 'Yes' : 'No'}</div>
                  <div>Error: {error || 'None'}</div>
                  <div className="mt-2 space-x-2">
                    <button 
                      onClick={() => searchPlayers('Josh')}
                      className="px-2 py-1 bg-blue-500 text-white rounded text-xs"
                    >
                      Test Josh
                    </button>
                    <button 
                      onClick={() => loadPlayerSummary(1)}
                      className="px-2 py-1 bg-green-500 text-white rounded text-xs"
                    >
                      Load Josh Allen Summary
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  searchPlayers(e.target.value)
                }}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                placeholder="Search for a player..."
              />
              
              {/* Search Results */}
              {playerSearchResults.length > 0 && (
                <div className="absolute z-10 mt-1 w-full bg-white shadow-lg rounded-md border border-gray-200 max-h-60 overflow-auto">
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
                      className={`w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center justify-between ${
                        !player.id ? 'opacity-60' : ''
                      }`}
                    >
                      <div>
                        <span className="font-medium">{player.full_name || player.name}</span>
                        <span className="text-sm text-gray-500 ml-2">
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
            <div className="bg-white rounded-lg shadow p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-blue-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500">Loading historical data...</p>
            </div>
          )}

          {playerSummary && (
            <div className="space-y-6">
              {/* Player Header */}
              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xl font-bold text-gray-900">{playerSummary.player_name}</h3>
                    <p className="text-gray-600">{playerSummary.position} • {playerSummary.seasons_analyzed} seasons analyzed</p>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-blue-600">
                      {playerSummary.historical_average.toFixed(1)}
                    </div>
                    <div className="text-sm text-gray-500">Avg PPR Points</div>
                  </div>
                </div>
              </div>

              {/* Career Trends */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white rounded-lg shadow p-6">
                  <h4 className="font-medium text-gray-900 mb-4">Career Trend</h4>
                  {playerSummary.career_trend ? (
                    <div className="space-y-3">
                      <div className="flex items-center space-x-2">
                        {getTrendIcon(playerSummary.career_trend.direction)}
                        <span className="font-medium">
                          {playerSummary.career_trend.direction.charAt(0).toUpperCase() + 
                           playerSummary.career_trend.direction.slice(1)} Trend
                        </span>
                      </div>
                      <div className="text-sm text-gray-600">
                        <p>Strength: {(playerSummary.career_trend.strength * 100).toFixed(1)}%</p>
                        <p>Performance Change: {playerSummary.career_trend.performance_change > 0 ? '+' : ''}
                           {playerSummary.career_trend.performance_change.toFixed(1)}%</p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No career trend data available</p>
                  )}
                </div>

                <div className="bg-white rounded-lg shadow p-6">
                  <h4 className="font-medium text-gray-900 mb-4">Recent Form</h4>
                  {playerSummary.recent_trend ? (
                    <div className="space-y-3">
                      <div className="flex items-center space-x-2">
                        {getTrendIcon(playerSummary.recent_trend.direction)}
                        <span className="font-medium">
                          {playerSummary.recent_trend.direction.charAt(0).toUpperCase() + 
                           playerSummary.recent_trend.direction.slice(1)} (Recent)
                        </span>
                      </div>
                      <div className="text-sm text-gray-600">
                        <p>Strength: {(playerSummary.recent_trend.strength * 100).toFixed(1)}%</p>
                        <p>Performance Change: {playerSummary.recent_trend.performance_change > 0 ? '+' : ''}
                           {playerSummary.recent_trend.performance_change.toFixed(1)}%</p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No recent trend data available</p>
                  )}
                </div>
              </div>

              {/* Season Summaries */}
              <div className="bg-white rounded-lg shadow p-6">
                <h4 className="font-medium text-gray-900 mb-4">Season-by-Season Performance</h4>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Season
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Games
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Avg Points
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Consistency
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Ceiling/Floor
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Trend
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {playerSummary.season_summaries.map((season) => {
                        const consistency = getConsistencyGrade(season.consistency_score)
                        return (
                          <tr key={season.season}>
                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                              {season.season}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                              {season.games_played}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                              {season.avg_points.toFixed(1)}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                              <span className={`font-medium ${consistency.color}`}>
                                {consistency.grade}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                              {season.ceiling.toFixed(1)} / {season.floor.toFixed(1)}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm">
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
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Advanced Analysis</h3>
          <p className="text-gray-600">Advanced statistical analysis and predictive modeling coming soon...</p>
        </div>
      )}
    </div>
  )
}
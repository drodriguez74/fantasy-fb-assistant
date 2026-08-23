import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../hooks/useAuth'
import { waiverWire, notifications as notificationsApi, getErrorMessage } from '../services/api'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { getPositionColor } from '../components/players/playerDisplay'
import type { Notification } from '../types'
import {
  PlusIcon,
  FireIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  ClockIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  CheckCircleIcon,
  BellIcon,
  AdjustmentsHorizontalIcon,
  MagnifyingGlassIcon
} from '@heroicons/react/24/outline'

interface WaiverRecommendation {
  player_id: number
  player_name: string
  position: string
  team: string
  recommendation_type: string
  priority: string
  confidence_score: number
  reason: string
  projected_points: number | null
  ownership_percentage: number | null
  trend_direction: string
  add_count_24h?: number
  component_scores?: {
    performance: number
    opportunity: number
    matchup: number
    ownership: number
    trend: number
  }
}

// The "Alerts" tab now reads the app's real in-app notification center
// (see backend/app/services/notification_service.py) instead of the old
// GET /waiver-wire/alerts stub, which queried a WaiverWireAlert table
// nothing ever wrote to. `Notification` is the real, shared shape used by
// the navbar bell too -- see src/types/index.ts.

interface TrendingPlayer {
  player_id: number
  player_name: string
  position: string
  team: string
  // Real live snapshot from Sleeper's trending add/drop feed (last 24h) --
  // see WaiverWireService.get_live_trending_players. Not a historical
  // ownership/pickup-rate time series; Sleeper doesn't expose one.
  trend_direction: 'up' | 'down'
  count_24h: number
  reason: string
}

interface RosterAddDropCandidate {
  player_id: number
  player_name: string
  priority?: string
  reason?: string
  confidence?: number
  projected_points?: number
  drop_score?: number
}

interface AddDropAnalysis {
  add_candidates?: RosterAddDropCandidate[]
  drop_candidates?: RosterAddDropCandidate[]
}

// Helper function to get current NFL week
function getCurrentNFLWeek(): number {
  // Simple calculation - NFL season typically starts first week of September
  // This is a basic implementation, could be made more sophisticated
  const now = new Date()
  const month = now.getMonth() + 1 // JavaScript months are 0-indexed

  if (month >= 9 && month <= 12) {
    // September to December - regular season
    return Math.min(Math.floor((now.getDate() + (month - 9) * 30) / 7) + 1, 18)
  } else if (month === 1) {
    // January - playoffs
    return 19
  } else {
    // Off-season, default to week 1
    return 1
  }
}

// The confidence_score on a recommendation is a real ratio (this player's
// live Sleeper add-count over the single most-added player's count in
// today's trending pool -- see WaiverWireService.get_live_trending_recommendations),
// not a placeholder. add_count_24h carries the raw number that ratio was
// built from; fall back to parsing it out of `reason` for any recommendation
// shape that doesn't carry the field directly.
function getAddCount(rec: WaiverRecommendation): number | null {
  if (typeof rec.add_count_24h === 'number') {
    return rec.add_count_24h
  }
  const match = rec.reason?.match(/([\d,]+)\s+adds/)
  if (match) {
    return parseInt(match[1].replace(/,/g, ''), 10)
  }
  return null
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(4, Math.round(value * 100))
  return (
    <div className="w-full bg-ink-100 rounded-full h-2">
      <div className="bg-accent-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  )
}

export function WaiverWirePage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'recommendations' | 'trending' | 'alerts' | 'analyzer'>('recommendations')
  const [recommendations, setRecommendations] = useState<WaiverRecommendation[]>([])
  const [trendingPlayers, setTrendingPlayers] = useState<TrendingPlayer[]>([])
  const [alerts, setAlerts] = useState<Notification[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Filters
  const [selectedPosition, setSelectedPosition] = useState<string>('')
  const [selectedPriority, setSelectedPriority] = useState<string>('')
  const [currentWeek, setCurrentWeek] = useState(getCurrentNFLWeek())
  const [trendDirection, setTrendDirection] = useState('up')

  // Roster analyzer
  const [rosterPlayerIds, setRosterPlayerIds] = useState<string>('')
  const [addDropAnalysis, setAddDropAnalysis] = useState<AddDropAnalysis | null>(null)

  const loadRecommendations = useCallback(async () => {
    try {
      setLoading(true)
      setError('')

      const params: { week: number; position?: string; priority?: string } = { week: currentWeek }
      if (selectedPosition) {
        params.position = selectedPosition
      }
      if (selectedPriority) {
        params.priority = selectedPriority
      }

      const response = await waiverWire.getRecommendations(params)
      setRecommendations(response.data.recommendations || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load waiver recommendations'))
    } finally {
      setLoading(false)
    }
  }, [currentWeek, selectedPosition, selectedPriority])

  const loadTrendingPlayers = useCallback(async () => {
    try {
      setLoading(true)

      const params: { week: number; trend_direction: string; position?: string } = {
        week: currentWeek,
        trend_direction: trendDirection
      }
      if (selectedPosition) {
        params.position = selectedPosition
      }

      const response = await waiverWire.getTrending(params)
      setTrendingPlayers(response.data.trending_players || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load trending players'))
    } finally {
      setLoading(false)
    }
  }, [currentWeek, trendDirection, selectedPosition])

  const loadAlerts = useCallback(async () => {
    try {
      setLoading(true)

      // Real in-app notifications (see NotificationBell for the same data
      // source) rather than the old dead WaiverWireAlert-backed endpoint.
      const response = await notificationsApi.list({ page_size: 20 })
      setAlerts(response.data.notifications || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load alerts'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user) {
      loadRecommendations()
    }
  }, [user, loadRecommendations])

  useEffect(() => {
    if (user && activeTab === 'trending') {
      loadTrendingPlayers()
    }
  }, [user, activeTab, loadTrendingPlayers])

  useEffect(() => {
    if (user && activeTab === 'alerts') {
      loadAlerts()
    }
  }, [user, activeTab, loadAlerts])

  const analyzeRoster = async () => {
    try {
      if (!rosterPlayerIds.trim()) {
        setError('Please enter player IDs separated by commas')
        return
      }

      setLoading(true)
      setError('')

      const playerIds = rosterPlayerIds.split(',').map(id => parseInt(id.trim())).filter(id => !isNaN(id))

      const response = await waiverWire.analyzeRoster({
        roster_player_ids: playerIds,
        week: currentWeek,
        season: 2024
      })

      setAddDropAnalysis(response.data.roster_analysis)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to analyze roster'))
    } finally {
      setLoading(false)
    }
  }

  const generateRecommendations = async () => {
    try {
      setLoading(true)
      setError('')

      await waiverWire.generateRecommendations({
        week: currentWeek,
        force_refresh: true
      })

      await loadRecommendations()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to generate recommendations'))
    } finally {
      setLoading(false)
    }
  }

  const getPriorityBadgeColor = (priority: string) => {
    const colors: Record<string, string> = {
      urgent: 'bg-danger-100 text-danger-800',
      high: 'bg-warning-100 text-warning-800',
      medium: 'bg-accent-100 text-accent-800',
      low: 'bg-ink-100 text-ink-600',
      watch: 'bg-ink-100 text-ink-500'
    }
    return colors[priority] || 'bg-ink-100 text-ink-600'
  }

  const getTrendIcon = (direction: string) => {
    switch (direction) {
      case 'up':
        return <ArrowTrendingUpIcon className="h-4 w-4 text-success-600" />
      case 'down':
        return <ArrowTrendingDownIcon className="h-4 w-4 text-danger-600" />
      default:
        return <div className="h-4 w-4 bg-ink-300 rounded-full" />
    }
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-ink-400" />
          <h3 className="mt-2 text-sm font-medium text-ink-900">Authentication Required</h3>
          <p className="mt-1 text-sm text-ink-500">Please sign in to access the waiver wire.</p>
        </div>
      </div>
    )
  }

  const tabs = [
    { id: 'recommendations', name: 'Recommendations', icon: PlusIcon },
    { id: 'trending', name: 'Trending', icon: FireIcon },
    { id: 'alerts', name: 'Alerts', icon: BellIcon },
    { id: 'analyzer', name: 'Roster Analyzer', icon: AdjustmentsHorizontalIcon },
  ]

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-ink-900">Waiver Wire</h1>
            <p className="text-ink-600 mt-2">
              Who's available, who's trending, and who you should drop to make room.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-ink-700">Week:</label>
              <select
                value={currentWeek}
                onChange={(e) => setCurrentWeek(parseInt(e.target.value))}
                className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
              >
                {Array.from({ length: 18 }, (_, i) => i + 1).map(week => (
                  <option key={week} value={week}>Week {week}</option>
                ))}
              </select>
            </div>
            <button
              onClick={generateRecommendations}
              disabled={loading}
              className="bg-accent-500 text-white px-4 py-2 rounded-lg hover:bg-accent-600 disabled:opacity-50 flex items-center space-x-2"
            >
              <ChartBarIcon className="h-4 w-4" />
              <span>Refresh</span>
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
      <div className="border-b border-ink-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as 'recommendations' | 'trending' | 'alerts' | 'analyzer')}
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
      {activeTab === 'recommendations' && (
        <div className="space-y-6">
          {/* Filters */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Waiver Wire Recommendations</h3>
            <div className="flex space-x-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">Position</label>
                <select
                  value={selectedPosition}
                  onChange={(e) => setSelectedPosition(e.target.value)}
                  className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                >
                  <option value="">All Positions</option>
                  <option value="QB">Quarterback</option>
                  <option value="RB">Running Back</option>
                  <option value="WR">Wide Receiver</option>
                  <option value="TE">Tight End</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">Priority</label>
                <select
                  value={selectedPriority}
                  onChange={(e) => setSelectedPriority(e.target.value)}
                  className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                >
                  <option value="">All Priorities</option>
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                  <option value="watch">Watch</option>
                </select>
              </div>
            </div>
          </div>

          {/* Recommendations List */}
          {loading ? (
            <div className="bg-white rounded-lg shadow p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-accent-600 mx-auto mb-2" />
              <p className="text-sm text-ink-500">Loading recommendations...</p>
            </div>
          ) : recommendations.length === 0 ? (
            <div className="bg-white rounded-lg shadow p-6 text-center">
              <MagnifyingGlassIcon className="mx-auto h-12 w-12 text-ink-400" />
              <h3 className="mt-2 text-sm font-medium text-ink-900">No recommendations found</h3>
              <p className="mt-1 text-sm text-ink-500">
                Try adjusting your filters or refresh the recommendations.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {recommendations.map((rec) => {
                const addCount = getAddCount(rec)
                return (
                  <div key={rec.player_id} className="bg-white rounded-lg shadow p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2">
                          <h4 className="text-lg font-medium text-ink-900">{rec.player_name}</h4>
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(rec.position)}`}>
                            {rec.position}
                          </span>
                          <span className="text-sm text-ink-500">{rec.team}</span>
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPriorityBadgeColor(rec.priority)}`}>
                            {rec.priority.toUpperCase()}
                          </span>
                        </div>

                        <p className="text-sm text-ink-600 mb-3">{rec.reason}</p>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm mb-4">
                          <div>
                            <span className="font-medium text-ink-700">Projected Points:</span>
                            <span className="ml-2">{rec.projected_points?.toFixed(1) || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="font-medium text-ink-700">Ownership:</span>
                            <span className="ml-2">
                              {rec.ownership_percentage != null ? `${rec.ownership_percentage.toFixed(1)}%` : 'N/A'}
                            </span>
                          </div>
                          <div className="flex items-center">
                            <span className="font-medium text-ink-700">Trend:</span>
                            <span className="ml-2 flex items-center space-x-1">
                              {getTrendIcon(rec.trend_direction)}
                              <span>{rec.trend_direction}</span>
                            </span>
                          </div>
                        </div>

                        <div className="max-w-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-ink-700">Confidence</span>
                            <DataConfidenceBadge level="computed" />
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="flex-1">
                              <ConfidenceBar value={rec.confidence_score} />
                            </div>
                            <span className="text-sm text-ink-700 font-medium w-10 text-right">
                              {(rec.confidence_score * 100).toFixed(0)}%
                            </span>
                          </div>
                          {addCount != null && (
                            <p className="mt-1 text-xs text-ink-500">
                              {addCount.toLocaleString()} adds &middot; 24h
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="ml-4">
                        <button className="bg-accent-500 text-white px-4 py-2 rounded-lg hover:bg-accent-600 flex items-center space-x-2">
                          <PlusIcon className="h-4 w-4" />
                          <span>Add</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'trending' && (
        <div className="space-y-6">
          {/* Trending Filters */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Trending Players</h3>
            <div className="flex space-x-4">
              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">Trend Direction</label>
                <select
                  value={trendDirection}
                  onChange={(e) => setTrendDirection(e.target.value)}
                  className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                >
                  <option value="up">Trending Up</option>
                  <option value="down">Trending Down</option>
                  <option value="both">Both Directions</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">Position</label>
                <select
                  value={selectedPosition}
                  onChange={(e) => setSelectedPosition(e.target.value)}
                  className="rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                >
                  <option value="">All Positions</option>
                  <option value="QB">Quarterback</option>
                  <option value="RB">Running Back</option>
                  <option value="WR">Wide Receiver</option>
                  <option value="TE">Tight End</option>
                </select>
              </div>
            </div>
          </div>

          {/* Trending Players List -- real live snapshot from Sleeper's
              trending add/drop feed (last 24h), not a historical trend
              line. See WaiverWireService.get_live_trending_players. */}
          {loading ? (
            <div className="bg-white rounded-lg shadow p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-accent-600 mx-auto mb-2" />
              <p className="text-sm text-ink-500">Loading trending players...</p>
            </div>
          ) : trendingPlayers.length === 0 ? (
            <div className="bg-white rounded-lg shadow p-6 text-center py-8">
              <FireIcon className="mx-auto h-12 w-12 text-ink-400" />
              <h3 className="mt-2 text-sm font-medium text-ink-900">No trending players found</h3>
              <p className="mt-1 text-sm text-ink-500">
                Try a different direction or clear the position filter.
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-lg shadow overflow-hidden">
              <table className="min-w-full divide-y divide-ink-200">
                <thead className="bg-ink-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Player
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Direction
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Adds/Drops (24h)
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Source
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-ink-200">
                  {trendingPlayers.map((player) => (
                    <tr key={`${player.trend_direction}-${player.player_id}`} className="hover:bg-ink-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="flex-shrink-0">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                              {player.position}
                            </span>
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-ink-900">{player.player_name}</div>
                            <div className="text-sm text-ink-500">{player.team}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          {getTrendIcon(player.trend_direction)}
                          <span className={`ml-1 text-sm font-medium ${
                            player.trend_direction === 'up' ? 'text-success-700' : 'text-danger-700'
                          }`}>
                            {player.trend_direction === 'up' ? 'Trending up' : 'Trending down'}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink-900">
                        {player.count_24h.toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-sm text-ink-500">
                        {player.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'alerts' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Waiver Wire Alerts</h3>
            <p className="text-sm text-ink-500 mb-4">
              Real, backend-tracked notifications generated from genuine waiver-wire
              signal -- the same feed behind the bell icon in the navbar.
            </p>
            {alerts.length === 0 ? (
              <div className="text-center py-8">
                <BellIcon className="mx-auto h-12 w-12 text-ink-400" />
                <h3 className="mt-2 text-sm font-medium text-ink-900">No alerts</h3>
                <p className="mt-1 text-sm text-ink-500">
                  You'll see important waiver wire notifications here.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {alerts.map((alert) => (
                  <div key={alert.id} className={`border-l-4 p-4 ${
                    alert.is_read ? 'border-ink-300 bg-ink-50' : 'border-accent-500 bg-accent-50'
                  }`}>
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <BellIcon className={`h-5 w-5 ${alert.is_read ? 'text-ink-400' : 'text-accent-400'}`} />
                      </div>
                      <div className="ml-3 flex-1">
                        <h4 className="text-sm font-medium text-ink-900">{alert.title}</h4>
                        <p className="mt-1 text-sm text-ink-600">{alert.body}</p>
                        <div className="mt-2 flex items-center space-x-4 text-xs text-ink-500">
                          <span>{new Date(alert.created_at).toLocaleString()}</span>
                          {!alert.is_read && (
                            <>
                              <span>•</span>
                              <span className="font-medium text-accent-700">Unread</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'analyzer' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-ink-900 mb-4">Roster Add/Drop Analyzer</h3>
            <p className="text-sm text-ink-600 mb-4">
              Enter your current roster player IDs to get personalized add/drop recommendations.
            </p>

            <div className="flex space-x-4 mb-4">
              <div className="flex-1">
                <label className="block text-sm font-medium text-ink-700 mb-1">
                  Player IDs (comma-separated)
                </label>
                <input
                  type="text"
                  value={rosterPlayerIds}
                  onChange={(e) => setRosterPlayerIds(e.target.value)}
                  placeholder="1, 2, 3, 4..."
                  className="block w-full rounded-md border-ink-300 shadow-sm focus:border-accent-500 focus:ring-accent-500"
                />
                <p className="mt-1 text-xs text-ink-500">
                  Example: 1, 2, 3, 4 (Josh Allen, Christian McCaffrey, Tyreek Hill, Travis Kelce)
                </p>
              </div>
              <div className="flex items-end">
                <button
                  onClick={analyzeRoster}
                  disabled={loading}
                  className="bg-accent-500 text-white px-4 py-2 rounded-lg hover:bg-accent-600 disabled:opacity-50 flex items-center space-x-2"
                >
                  <ChartBarIcon className="h-4 w-4" />
                  <span>Analyze</span>
                </button>
              </div>
            </div>

            {addDropAnalysis && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                {/* Add Candidates */}
                <div>
                  <h4 className="font-medium text-ink-900 mb-3">Top Add Candidates</h4>
                  <div className="space-y-3">
                    {addDropAnalysis.add_candidates?.slice(0, 5).map((player) => (
                      <div key={player.player_id} className="border border-ink-200 rounded p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium">{player.player_name}</span>
                          <span className={`px-2 py-1 rounded text-xs ${getPriorityBadgeColor(player.priority || '')}`}>
                            {player.priority}
                          </span>
                        </div>
                        <p className="text-sm text-ink-600">{player.reason}</p>
                        <div className="mt-2 text-xs text-ink-500">
                          Confidence: {((player.confidence ?? 0) * 100).toFixed(0)}% •
                          Projected: {player.projected_points?.toFixed(1) || 'N/A'} pts
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Drop Candidates */}
                <div>
                  <h4 className="font-medium text-ink-900 mb-3">Drop Candidates</h4>
                  <div className="space-y-3">
                    {addDropAnalysis.drop_candidates?.map((player) => (
                      <div key={player.player_id} className="border border-danger-200 rounded p-3 bg-danger-50">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium">{player.player_name}</span>
                          <span className="text-xs text-danger-600">
                            Drop Score: {((player.drop_score ?? 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-sm text-ink-600">{player.reason}</p>
                      </div>
                    ))}
                    {(!addDropAnalysis.drop_candidates || addDropAnalysis.drop_candidates.length === 0) && (
                      <div className="text-center py-4 text-ink-500">
                        <CheckCircleIcon className="mx-auto h-8 w-8 text-success-500 mb-2" />
                        <p className="text-sm">Your roster looks solid! No obvious drop candidates.</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

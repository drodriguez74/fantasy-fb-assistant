import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from '../hooks/useAuth'
import { waiverWire, matchupAnalysis, notifications as notificationsApi, leagues as leaguesApi, getErrorMessage } from '../services/api'
import { RecommendationsTab } from '../components/waivers/page/RecommendationsTab'
import { TrendingTab } from '../components/waivers/page/TrendingTab'
import { AlertsTab } from '../components/waivers/page/AlertsTab'
import { LeagueWideStreamingTab } from '../components/waivers/page/LeagueWideStreamingTab'
import { StreamingBoardsView } from '../components/waivers/page/parts'
import {
  LEAGUE_STORAGE_KEY,
  getCurrentNFLWeek,
  readStoredLeagueId,
  type ConnectedLeagueOption,
  type DefenseStreamingRecommendations,
  type LineupImpact,
  type PositionOutlook,
  type PositionPressure,
  type StreamingBoards,
  type TabId,
  type TrendingPlayer,
  type WaiverPosition,
  type WaiverRecommendation,
} from '../components/waivers/page/types'
import type { Notification } from '../types'
import {
  PlusIcon,
  FireIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  BellIcon,
  ShieldCheckIcon
} from '@heroicons/react/24/outline'

export function WaiverWirePage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<TabId>('recommendations')
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

  // Personalization: real roster-need / bye-week / scoring-format weighting
  // against one of the user's connected leagues, opt-in via a dropdown --
  // see WaiverWireService.get_live_trending_recommendations's user_roster/
  // league_settings params. Only leagues with a team_id set can actually
  // have their roster fetched (see /leagues/{id}/settings), so those are
  // the only ones offered here.
  const [connectedLeagues, setConnectedLeagues] = useState<ConnectedLeagueOption[]>([])
  const [selectedLeagueId, setSelectedLeagueId] = useState<number | ''>('')
  const [waiverPosition, setWaiverPosition] = useState<WaiverPosition | null>(null)
  const [positionPressure, setPositionPressure] = useState<PositionPressure | null>(null)
  // The lineup-impact engine (GET /leagues/{id}/waiver-recommendations) --
  // the primary list whenever a league is selected.
  const [lineupImpact, setLineupImpact] = useState<LineupImpact | null>(null)
  const [lineupLoading, setLineupLoading] = useState(false)
  const [lineupError, setLineupError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  // Defense/kicker streaming (matchup_analysis endpoints)
  const [streamingCurrentDefense, setStreamingCurrentDefense] = useState<string>('')
  const autoDefenseRef = useRef('')
  const [streamingBoards, setStreamingBoards] = useState<StreamingBoards | null>(null)
  const [boardsLoading, setBoardsLoading] = useState(false)
  const [boardsError, setBoardsError] = useState('')
  const [streamingData, setStreamingData] = useState<DefenseStreamingRecommendations | null>(null)
  const [kickerOutlook, setKickerOutlook] = useState<PositionOutlook | null>(null)
  const [streamingLoading, setStreamingLoading] = useState(false)
  const [streamingError, setStreamingError] = useState('')

  const loadRecommendations = useCallback(async () => {
    // With a league selected the lineup-impact engine is the list; the
    // league-wide trending feed stays on the Trending tab.
    if (selectedLeagueId !== '') return
    try {
      setLoading(true)
      setError('')

      const params: { week: number; position?: string; priority?: string; league_id?: number } = { week: currentWeek }
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
    // refreshKey: the Refresh button re-runs this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentWeek, selectedPosition, selectedPriority, selectedLeagueId, refreshKey])

  // Load the user's connected leagues once, to populate the personalization
  // dropdown. Only leagues with a team_id can have their roster fetched by
  // the backend (see _fetch_connected_roster_and_settings), so filter down
  // to those -- offering a league that can't actually be personalized would
  // silently no-op and be confusing.
  useEffect(() => {
    if (!user) return
    leaguesApi.getAll()
      .then((response) => {
        const all = (response.data || []) as ConnectedLeagueOption[]
        const usable = all.filter((l) => !!l.team_id)
        setConnectedLeagues(usable)
        // Default to the user's league (last one picked here, else the
        // first) -- advice for your own roster beats the generic feed.
        const remembered = readStoredLeagueId()
        const pick = usable.find((l) => l.id === remembered) ?? usable[0]
        if (pick) setSelectedLeagueId((current) => (current === '' ? pick.id : current))
      })
      .catch(() => setConnectedLeagues([]))
  }, [user])

  // Real waiver standing for whichever league is selected to personalize
  // against -- FAAB remaining or priority rank, whichever this league
  // actually runs on. Not fetched until a league is chosen (same opt-in as
  // personalization above).
  useEffect(() => {
    if (selectedLeagueId === '') {
      setWaiverPosition(null)
      return
    }
    leaguesApi.getWaiverPosition(selectedLeagueId)
      .then((response) => setWaiverPosition(response.data))
      .catch(() => setWaiverPosition(null))
  }, [selectedLeagueId])

  // Real per-league competition signal (other teams' actual roster depth
  // per position) -- same opt-in as waiver position above. Cached ~1hr
  // server-side (roster composition barely moves intra-week), so this is
  // cheap to fetch alongside it.
  useEffect(() => {
    if (selectedLeagueId === '') {
      setPositionPressure(null)
      return
    }
    leaguesApi.getPositionPressure(selectedLeagueId)
      .then((response) => setPositionPressure(response.data))
      .catch(() => setPositionPressure(null))
  }, [selectedLeagueId])

  useEffect(() => {
    setLineupImpact(null)
    setLineupError('')
    if (selectedLeagueId === '') return
    let cancelled = false
    setLineupLoading(true)
    leaguesApi.getWaiverRecommendations(selectedLeagueId)
      .then((response) => {
        if (cancelled) return
        const w = response.data.waiver_recommendations
        if (!w || w.error) {
          setLineupError(w?.error || response.data.error || "Couldn't score this league's free agents right now.")
          return
        }
        // The league's real current week beats the date-based guess the
        // picker starts on (it drives the Trending and Streaming tabs).
        if (typeof w.current_week === 'number') setCurrentWeek(w.current_week)
        // Your real defense, so DEF streaming compares against it without
        // typing. Replaces an earlier auto-fill, never what the user typed.
        const mine: string = w.my_defense || ''
        const previousAuto = autoDefenseRef.current  // read before the updater runs
        autoDefenseRef.current = mine
        setStreamingCurrentDefense((current) => (current === '' || current === previousAuto ? mine : current))
        setLineupImpact({
          recs: w.recommendations ?? [],
          watchOnly: !!w.watch_only,
          teamNeeds: w.team_needs ?? [],
          basis: w.basis,
        })
      })
      .catch((err) => !cancelled && setLineupError(getErrorMessage(err, "Couldn't score this league's free agents right now.")))
      .finally(() => !cancelled && setLineupLoading(false))
    return () => {
      cancelled = true
    }
  }, [selectedLeagueId, refreshKey])

  const selectLeague = (id: number | '') => {
    setSelectedLeagueId(id)
    try {
      if (id === '') localStorage.removeItem(LEAGUE_STORAGE_KEY)
      else localStorage.setItem(LEAGUE_STORAGE_KEY, String(id))
    } catch {
      // Storage unavailable (private mode) -- the choice just isn't remembered.
    }
  }

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

  const loadStreamingTargets = useCallback(async () => {
    try {
      setStreamingLoading(true)
      setStreamingError('')

      const [defenseRes, kickerRes] = await Promise.all([
        matchupAnalysis.getDefenseStreaming(currentWeek, streamingCurrentDefense.trim() || undefined),
        matchupAnalysis.getPositionOutlook('K', 3).catch(() => null),
      ])

      setStreamingData(defenseRes.data.recommendations ?? null)
      setKickerOutlook(kickerRes?.data?.position_outlook ?? null)
    } catch (err) {
      setStreamingError(getErrorMessage(err, 'Failed to load defensive streaming targets'))
      setStreamingData(null)
    } finally {
      setStreamingLoading(false)
    }
  }, [currentWeek, streamingCurrentDefense])

  useEffect(() => {
    if (user && activeTab === 'streaming' && selectedLeagueId === '') {
      loadStreamingTargets()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, activeTab, currentWeek, selectedLeagueId])

  useEffect(() => {
    setStreamingBoards(null)
    setBoardsError('')
    if (activeTab !== 'streaming' || selectedLeagueId === '') return
    let cancelled = false
    setBoardsLoading(true)
    leaguesApi.getStreaming(selectedLeagueId)
      .then((response) => !cancelled && setStreamingBoards(response.data))
      .catch((err) => !cancelled && setBoardsError(getErrorMessage(err, "Couldn't load streaming options for this league.")))
      .finally(() => !cancelled && setBoardsLoading(false))
    return () => {
      cancelled = true
    }
  }, [activeTab, selectedLeagueId, refreshKey])

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-faint" />
          <h3 className="mt-2 text-sm font-medium text-body">Sign in required</h3>
          <p className="mt-1 text-sm text-muted">Sign in to pull waiver targets for your league.</p>
        </div>
      </div>
    )
  }

  const tabs = [
    { id: 'recommendations', name: 'Recommendations', icon: PlusIcon },
    { id: 'trending', name: 'Trending', icon: FireIcon },
    { id: 'streaming', name: 'DEF/K Streaming', icon: ShieldCheckIcon },
    { id: 'alerts', name: 'Alerts', icon: BellIcon },
  ]

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Waiver Wire</h1>
            <p className="text-muted mt-2">
              Who's available, who's trending, and who you should drop to make room.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-body">Week:</label>
              <select
                value={currentWeek}
                onChange={(e) => setCurrentWeek(parseInt(e.target.value))}
                className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
              >
                {Array.from({ length: 18 }, (_, i) => i + 1).map(week => (
                  <option key={week} value={week}>Week {week}</option>
                ))}
              </select>
            </div>
            <button
              onClick={() => setRefreshKey((k) => k + 1)}
              disabled={loading || lineupLoading}
              className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark disabled:opacity-50 flex items-center space-x-2"
            >
              <ChartBarIcon className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="yard-divider mb-6" aria-hidden="true" />

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
                onClick={() => setActiveTab(tab.id as TabId)}
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
      {activeTab === 'recommendations' && (
        <RecommendationsTab recommendations={recommendations} loading={loading} selectedPosition={selectedPosition} setSelectedPosition={setSelectedPosition} selectedPriority={selectedPriority} setSelectedPriority={setSelectedPriority} connectedLeagues={connectedLeagues} selectedLeagueId={selectedLeagueId} selectLeague={selectLeague} waiverPosition={waiverPosition} positionPressure={positionPressure} lineupImpact={lineupImpact} lineupLoading={lineupLoading} lineupError={lineupError} />
      )}

      {activeTab === 'trending' && (
        <TrendingTab trendingPlayers={trendingPlayers} loading={loading} selectedPosition={selectedPosition} setSelectedPosition={setSelectedPosition} trendDirection={trendDirection} setTrendDirection={setTrendDirection} />
      )}

      {activeTab === 'alerts' && (
        <AlertsTab alerts={alerts} />
      )}

      {activeTab === 'streaming' && selectedLeagueId !== '' && (
        <StreamingBoardsView data={streamingBoards} loading={boardsLoading} error={boardsError} />
      )}

      {activeTab === 'streaming' && selectedLeagueId === '' && (
        <LeagueWideStreamingTab currentWeek={currentWeek} streamingCurrentDefense={streamingCurrentDefense} setStreamingCurrentDefense={setStreamingCurrentDefense} streamingData={streamingData} kickerOutlook={kickerOutlook} streamingLoading={streamingLoading} streamingError={streamingError} loadStreamingTargets={loadStreamingTargets} />
      )}

    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../hooks/useAuth'
import { api, getErrorMessage } from '../services/api'

// The live-draft router is mounted at /draft/live-draft (see
// backend/app/api/v1/router.py), not /live-draft — every call below has to
// include that prefix or it 404s against the real backend.
const LIVE_DRAFT_API_PREFIX = '/draft/live-draft'

// api.ts hardcodes its axios baseURL to http://localhost:8000/api/v1 (no env
// var / relative-origin derivation exists to reuse here), so mirror that
// same origin for the WebSocket instead of a second, independent hardcode
// that could drift from it.
function liveDraftWsUrl(sessionId: string): string {
  const httpBase = api.defaults.baseURL || 'http://localhost:8000/api/v1'
  const wsBase = httpBase.replace(/^http/, 'ws')
  return `${wsBase}${LIVE_DRAFT_API_PREFIX}/ws/${sessionId}`
}

interface DraftSession {
  session_id: string
  platform: string
  league_id: string
  started_at: string
  status: 'active' | 'completed'
}

interface Player {
  player_id: string
  full_name: string
  position: string
  team: string
  projected_points?: number
  adp?: number
  tier?: number
}

interface DraftRecommendation {
  player: Player
  reason: string
  confidence: number
  tier: number
}

interface TeamAnalysis {
  roster_needs: string[]
  positional_strength: Record<string, number>
  next_best_pick: string
}

type DraftWebSocketMessage =
  | { type: 'recommendations_update'; data: { top_recommendations: DraftRecommendation[] } }
  | { type: 'pick_update' }
  | { type: 'error'; message: string }

interface League {
  id: number
  league_name: string
  platform: string
  league_id: string
  league_key: string
  season: number
  league_size: number
  scoring_format: string
  draft_status: string
  can_start_session: boolean
}

export function LiveDraftPage() {
  const { user } = useAuth()
  const [isConnected, setIsConnected] = useState(false)
  const [currentSession, setCurrentSession] = useState<DraftSession | null>(null)
  const [recommendations, setRecommendations] = useState<DraftRecommendation[]>([])
  const [draftBoard, setDraftBoard] = useState<Player[]>([])
  const [userRoster, setUserRoster] = useState<Player[]>([])
  const [teamAnalysis, setTeamAnalysis] = useState<TeamAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [wsConnected, setWsConnected] = useState(false)
  const [availableLeagues, setAvailableLeagues] = useState<League[]>([])
  const [selectedLeague, setSelectedLeague] = useState<League | null>(null)
  
  const wsRef = useRef<WebSocket | null>(null)

  // WebSocket connection management
  const connectWebSocket = (sessionId: string) => {
    if (wsRef.current) {
      wsRef.current.close()
    }

    wsRef.current = new WebSocket(liveDraftWsUrl(sessionId))

    wsRef.current.onopen = () => {
      setWsConnected(true)
    }

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data)
    }

    wsRef.current.onclose = () => {
      setWsConnected(false)
    }

    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error)
      setWsConnected(false)
    }
  }

  const handleWebSocketMessage = (data: DraftWebSocketMessage) => {
    switch (data.type) {
      case 'recommendations_update':
        setRecommendations(data.data.top_recommendations || [])
        break
      case 'pick_update':
        fetchDraftData()
        break
      case 'error':
        setError(data.message)
        break
    }
  }

  // Start a new draft session
  const startDraftSession = async () => {
    if (!selectedLeague) {
      setError('Please select a league')
      return
    }

    try {
      setLoading(true)
      setError('')

      const draftSettings = {
        platform: selectedLeague.platform.toLowerCase(),
        league_id: selectedLeague.league_id,
        scoring_format: selectedLeague.scoring_format,
        league_size: selectedLeague.league_size
      }

      const response = await api.post(`${LIVE_DRAFT_API_PREFIX}/start-session`, draftSettings)
      const session = response.data
      
      setCurrentSession(session)
      setIsConnected(true)

      // Connect WebSocket
      connectWebSocket(session.session_id)

      // Load initial data. setCurrentSession above doesn't update
      // `currentSession` synchronously (React batches state updates), so
      // fetchDraftData's own read of that state would still see the
      // pre-session null and bail out immediately. Pass the session we just
      // got back explicitly so the very first load actually fires.
      await fetchDraftData(session)

    } catch (err) {
      setError(getErrorMessage(err, 'Failed to start draft session'))
    } finally {
      setLoading(false)
    }
  }

  // Fetch current draft data
  const fetchDraftData = async (session: DraftSession | null = currentSession) => {
    if (!session) return

    try {
      const [recsResponse, boardResponse, analysisResponse] = await Promise.all([
        api.get(`${LIVE_DRAFT_API_PREFIX}/recommendations/${session.session_id}`),
        api.get(`${LIVE_DRAFT_API_PREFIX}/draft-board/${session.session_id}`),
        api.get(`${LIVE_DRAFT_API_PREFIX}/team-analysis/${session.session_id}`)
      ])

      setRecommendations(recsResponse.data.top_recommendations || [])

      // draft-board groups players by position (draft_board.QB.players, etc);
      // flatten it into the single list this page renders.
      const draftBoardByPosition = boardResponse.data.draft_board || {}
      const flatBoard: Player[] = Object.values(draftBoardByPosition).flatMap(
        (entry: unknown) => ((entry as { players?: Player[] })?.players) || []
      )
      setDraftBoard(flatBoard)

      // team-analysis's roster is a list of {player, pick_number, round,
      // timestamp} picks, not bare Player objects.
      const roster: Array<{ player: Player }> = analysisResponse.data.roster || []
      setUserRoster(roster.map((pick) => pick.player).filter(Boolean))

      // team-analysis's own "team_analysis" field is a free-text AI
      // narrative string, not the {roster_needs, next_best_pick} shape this
      // page renders — build that from the real structured fields the
      // endpoint does return instead.
      setTeamAnalysis({
        roster_needs: analysisResponse.data.positional_needs?.top_needs || [],
        positional_strength: {},
        next_best_pick: analysisResponse.data.next_pick_suggestions?.[0] || ''
      })

    } catch (err) {
      console.error('Failed to fetch draft data:', err)
    }
  }

  // Make a draft pick
  const makePick = async (player: Player) => {
    if (!currentSession) return

    try {
      await api.post(`${LIVE_DRAFT_API_PREFIX}/update-pick`, {
        session_id: currentSession.session_id,
        player_picked: player
      })
      
      // Data will be updated via WebSocket
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to record pick'))
    }
  }

  // Manually flag a player as drafted by some OTHER team. Distinct from
  // makePick (which records the session user's own pick): ESPN's live
  // draft feed is confirmed to never reflect real in-progress picks (see
  // CLAUDE.md), so Available Players silently includes already-drafted
  // players for an entire draft unless corrected this way.
  const markPlayerDrafted = async (player: Player) => {
    if (!currentSession) return

    try {
      await api.post(`${LIVE_DRAFT_API_PREFIX}/mark-drafted`, {
        session_id: currentSession.session_id,
        player_id: player.player_id
      })

      // Data will be updated via WebSocket
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to mark player as drafted'))
    }
  }

  // End draft session
  const endSession = async () => {
    if (!currentSession) return

    try {
      await api.delete(`${LIVE_DRAFT_API_PREFIX}/session/${currentSession.session_id}`)
      setCurrentSession(null)
      setIsConnected(false)
      setRecommendations([])
      setDraftBoard([])
      setUserRoster([])
      setTeamAnalysis(null)
      
      if (wsRef.current) {
        wsRef.current.close()
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to end session'))
    }
  }

  // Load available leagues
  useEffect(() => {
    if (user) {
      loadAvailableLeagues()
    }
  }, [user])

  const loadAvailableLeagues = async () => {
    try {
      const response = await api.get('/draft/my-leagues')
      const leagues = response.data.leagues || []
      setAvailableLeagues(leagues)
      
      // Auto-select first league if available
      if (leagues.length > 0) {
        setSelectedLeague(leagues[0])
      }
    } catch (err) {
      console.error('Failed to load leagues:', err)
      setError('Failed to load available leagues')
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  if (!user) {
    return (
      <div className="text-center py-12">
        <p className="text-muted">Please log in to use the Live Draft Assistant.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Live Draft Assistant</h1>
          <p className="text-muted mt-2">
            Connect a live draft and get a pick recommendation on every clock, updated as picks come in.
          </p>
        </div>

        {wsConnected && (
          <div className="flex items-center space-x-2 text-success-600">
            <div className="w-2 h-2 bg-success-600 rounded-full animate-pulse"></div>
            <span className="text-sm font-medium">Live</span>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-danger-50 border border-danger-200 text-danger-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {!isConnected ? (
        <div className="bg-surface rounded-lg border border-hairline p-6">
          <h2 className="text-xl font-semibold text-body mb-4">Start Draft Session</h2>

          {availableLeagues.length === 0 ? (
            <div className="text-center py-8">
              <div className="text-faint text-4xl mb-4"></div>
              <h3 className="text-lg font-semibold text-body mb-2">No Leagues Connected</h3>
              <p className="text-muted mb-4">
                Connect your ESPN or Yahoo league first to use the Live Draft Assistant
              </p>
              <button
                onClick={() => window.location.href = '/leagues'}
                className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark"
              >
                Connect League
              </button>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <label className="block text-sm font-medium text-body mb-2">
                  Select League
                </label>
                <select
                  value={selectedLeague?.id || ''}
                  onChange={(e) => {
                    const league = availableLeagues.find(l => l.id === parseInt(e.target.value))
                    setSelectedLeague(league || null)
                  }}
                  className="w-full px-3 py-2 border border-line rounded-md focus:outline-none focus:ring-2 focus:ring-volt"
                >
                  <option value="">Choose a league...</option>
                  {availableLeagues.map((league) => (
                    <option key={league.id} value={league.id}>
                      {league.league_name} ({league.platform} • {league.league_size} teams • {league.scoring_format})
                    </option>
                  ))}
                </select>
              </div>

              {selectedLeague && (
                <div className="bg-surface-2 rounded-lg p-4 mb-6">
                  <h3 className="font-medium text-body mb-2">League Details</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted">Platform:</span>
                      <span className="ml-2 font-medium">{selectedLeague.platform}</span>
                    </div>
                    <div>
                      <span className="text-muted">Size:</span>
                      <span className="ml-2 font-stat tabular-nums font-medium">{selectedLeague.league_size} teams</span>
                    </div>
                    <div>
                      <span className="text-muted">Scoring:</span>
                      <span className="ml-2 font-medium">{selectedLeague.scoring_format}</span>
                    </div>
                    <div>
                      <span className="text-muted">Season:</span>
                      <span className="ml-2 font-stat tabular-nums font-medium">{selectedLeague.season}</span>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          <button
            onClick={startDraftSession}
            disabled={loading}
            className="w-full bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                <span>Starting Session...</span>
              </>
            ) : (
              <span>Start Live Draft</span>
            )}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Main Draft Board */}
          <div className="xl:col-span-2 space-y-6">
            {/* Top Recommendations */}
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-body">AI Recommendations</h2>
                {wsConnected && (
                  <span className="text-sm text-success-600">Live Updates</span>
                )}
              </div>

              {recommendations.length > 0 ? (
                <div className="space-y-3">
                  {recommendations.slice(0, 5).map((rec, index) => (
                    <div
                      key={rec.player.player_id}
                      className="flex items-center justify-between p-4 bg-highlight rounded-lg border border-hairline hover:border-accent-ink transition-all cursor-pointer"
                      onClick={() => makePick(rec.player)}
                    >
                      <div className="flex-1">
                        <div className="flex items-center space-x-3">
                          <div className="w-8 h-8 bg-volt text-volt-ink rounded-full flex items-center justify-center font-stat font-bold text-sm">
                            {index + 1}
                          </div>
                          <div>
                            <h3 className="font-semibold text-body">{rec.player.full_name}</h3>
                            <p className="text-sm text-muted">
                              {rec.player.position} - {rec.player.team}
                            </p>
                          </div>
                        </div>
                        <p className="text-sm text-body mt-2">{rec.reason}</p>
                      </div>

                      <div className="text-right ml-4">
                        <div className="text-sm font-medium text-body">
                          Tier {rec.tier}
                        </div>
                        <div className="text-xs font-stat tabular-nums text-muted">
                          {rec.confidence}% confidence
                        </div>
                        {rec.player.projected_points && (
                          <div className="text-xs font-stat tabular-nums text-muted">
                            Proj: {rec.player.projected_points.toFixed(1)} pts
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-line mx-auto mb-4"></div>
                  Loading recommendations...
                </div>
              )}
            </div>

            {/* Draft Board */}
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <h2 className="text-xl font-semibold text-body mb-4">Available Players</h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-96 overflow-y-auto">
                {draftBoard.slice(0, 20).map((player) => (
                  <div
                    key={player.player_id}
                    className="flex items-center justify-between p-3 bg-surface-2 rounded-lg hover:bg-surface-2 cursor-pointer transition-colors"
                    onClick={() => makePick(player)}
                  >
                    <div>
                      <div className="font-medium text-body">{player.full_name}</div>
                      <div className="text-sm text-muted">
                        {player.position} - {player.team}
                      </div>
                    </div>
                    <div className="text-right flex items-center gap-3">
                      <div>
                        {player.projected_points && (
                          <div className="text-sm font-stat tabular-nums font-medium text-body">
                            {player.projected_points.toFixed(1)} pts
                          </div>
                        )}
                        {player.adp && (
                          <div className="text-xs font-stat tabular-nums text-muted">
                            ADP: {player.adp.toFixed(1)}
                          </div>
                        )}
                      </div>
                      {/* ESPN's live draft feed doesn't reflect real
                          in-progress picks (see CLAUDE.md) -- this lets the
                          user manually correct the pool when someone else
                          drafts a player shown here as still available. */}
                      <button
                        type="button"
                        title="Mark as drafted by another team"
                        onClick={(e) => {
                          e.stopPropagation()
                          markPlayerDrafted(player)
                        }}
                        className="text-xs text-faint hover:text-danger-600 border border-line hover:border-danger-300 rounded px-2 py-1 transition-colors"
                      >
                        Mark gone
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Session Info */}
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-body">Draft Session</h2>
                <button
                  onClick={endSession}
                  className="text-sm text-danger-600 hover:text-danger-700"
                >
                  End Session
                </button>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted">Platform:</span>
                  <span className="font-medium capitalize">{currentSession?.platform}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">League:</span>
                  <span className="font-medium">{currentSession?.league_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Status:</span>
                  <span className="font-medium text-success-600 capitalize">
                    {currentSession?.status}
                  </span>
                </div>
              </div>
            </div>

            {/* Your Roster */}
            <div className="bg-surface rounded-lg border border-hairline p-6">
              <h2 className="text-lg font-semibold text-body mb-4">Your Roster</h2>

              {userRoster.length > 0 ? (
                <div className="space-y-3">
                  {userRoster.map((player, index) => (
                    <div key={player.player_id} className="flex items-center space-x-3">
                      <div className="w-6 h-6 bg-surface-2 text-body rounded-full flex items-center justify-center font-stat text-xs font-bold">
                        {index + 1}
                      </div>
                      <div>
                        <div className="font-medium text-body">{player.full_name}</div>
                        <div className="text-sm text-muted">
                          {player.position} - {player.team}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted text-sm">
                  Your draft picks will appear here
                </p>
              )}
            </div>

            {/* Team Analysis */}
            {teamAnalysis && (
              <div className="bg-surface rounded-lg border border-hairline p-6">
                <h2 className="text-lg font-semibold text-body mb-4">Team Analysis</h2>

                <div className="space-y-4">
                  {teamAnalysis.roster_needs && teamAnalysis.roster_needs.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-body mb-2">Roster Needs</h3>
                      <div className="flex flex-wrap gap-1">
                        {teamAnalysis.roster_needs.map((need, index) => (
                          <span
                            key={`need-${need}-${index}`}
                            className="px-2 py-1 bg-warning-100 text-warning-800 rounded-full text-xs font-medium"
                          >
                            {need}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {teamAnalysis.next_best_pick && (
                    <div>
                      <h3 className="text-sm font-medium text-body mb-2">Next Best Pick</h3>
                      <p className="text-sm text-body font-medium">
                        {teamAnalysis.next_best_pick}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
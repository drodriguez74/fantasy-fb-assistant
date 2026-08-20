import { useState, useEffect, useCallback } from 'react'
import { PlusIcon, StarIcon } from '@heroicons/react/24/outline'
import { draft } from '../services/api'

interface DraftSettings {
  scoringFormat: 'PPR' | 'Half PPR' | 'Standard'
  teamCount: number
  draftPosition: number
}

interface Player {
  sleeper_id: string
  full_name: string
  position: string
  team: string
  projected_points?: number
  adp?: number
  trending_count?: number
}

interface DraftedPlayer extends Player {
  round: number
  pick: number
}

interface Recommendation {
  player_name: string
  position: string
  reasoning: string
  confidence: number
}

export function DraftPage() {
  const [settings, setSettings] = useState<DraftSettings>({
    scoringFormat: 'PPR',
    teamCount: 12,
    draftPosition: 6
  })
  
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [availablePlayers, setAvailablePlayers] = useState<Player[]>([])
  const [draftedPlayers, setDraftedPlayers] = useState<DraftedPlayer[]>([])
  const [trendingPlayers, setTrendingPlayers] = useState<Player[]>([])
  const [loading, setLoading] = useState(false)
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null)
  const [selectedPosition, setSelectedPosition] = useState<string>('ALL')
  const [currentRound, setCurrentRound] = useState(1)

  const positions = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DEF']
  
  // Calculate team needs based on drafted players
  const getTeamNeeds = useCallback((): string[] => {
    const positionCounts = draftedPlayers.reduce((acc, player) => {
      acc[player.position] = (acc[player.position] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const needs: string[] = []
    const idealCounts = { RB: 2, WR: 2, QB: 1, TE: 1 }

    Object.entries(idealCounts).forEach(([pos, ideal]) => {
      const current = positionCounts[pos] || 0
      if (current < ideal) {
        needs.push(pos)
      }
    })

    return needs.length > 0 ? needs : ['RB', 'WR']
  }, [draftedPlayers])

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      setLoading(true)
      try {
        // Get trending players for draft insights
        const trending = await draft.getTrendingCandidates({ hours: 48, limit: 25 })
        setTrendingPlayers(trending.data.candidates || [])

        // Get positional rankings to populate available players
        const rbRankings = await draft.getPositionalRankings('RB', { limit: 20 })
        const wrRankings = await draft.getPositionalRankings('WR', { limit: 20 })
        const qbRankings = await draft.getPositionalRankings('QB', { limit: 15 })
        
        const allPlayers = [
          ...(rbRankings.data.players || []),
          ...(wrRankings.data.players || []),
          ...(qbRankings.data.players || [])
        ]
        
        // Remove duplicates based on sleeper_id
        const uniquePlayers = allPlayers.reduce((acc: Player[], player) => {
          if (!acc.find(p => p.sleeper_id === player.sleeper_id)) {
            acc.push(player)
          }
          return acc
        }, [] as Player[])
        
        setAvailablePlayers(uniquePlayers)
      } catch (error) {
        console.error('Error loading draft data:', error)
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [])

  const getCurrentPick = useCallback((): number => {
    const roundPick = ((currentRound - 1) * settings.teamCount) + settings.draftPosition
    return roundPick
  }, [currentRound, settings])

  const generateRecommendations = useCallback(async () => {
    if (availablePlayers.length === 0) return

    setRecommendationsError(null)

    try {
      const teamNeeds = getTeamNeeds()
      const currentPick = getCurrentPick()

      // Filter out already drafted players
      const draftedIds = new Set(draftedPlayers.map(p => p.sleeper_id))
      const available = availablePlayers
        .filter(p => !draftedIds.has(p.sleeper_id))
        .slice(0, 20) // Top 20 available

      const result = await draft.getDraftRecommendations({
        available_players: available,
        team_needs: teamNeeds,
        draft_position: currentPick,
        scoring_format: settings.scoringFormat,
        league_size: settings.teamCount
      })

      setRecommendations(result.data.recommendations || [])
    } catch (error) {
      // Don't fabricate recommendations when the real call fails -- a made-up
      // confidence score and templated reasoning would look identical to a
      // genuine AI recommendation. Surface the failure instead.
      console.error('Error generating recommendations:', error)
      setRecommendations([])
      setRecommendationsError("Couldn't load recommendations. Try refreshing.")
    }
  }, [availablePlayers, draftedPlayers, settings, getTeamNeeds, getCurrentPick])

  // Get recommendations when settings or drafted players change
  useEffect(() => {
    if (availablePlayers.length > 0) {
      generateRecommendations()
    }
  }, [availablePlayers, generateRecommendations])

  const draftPlayer = (player: Player) => {
    const pick = getCurrentPick()
    const draftedPlayer: DraftedPlayer = {
      ...player,
      round: currentRound,
      pick: pick
    }
    
    setDraftedPlayers([...draftedPlayers, draftedPlayer])
    
    // Advance to next round if this was your pick
    if ((pick - 1) % settings.teamCount === settings.draftPosition - 1) {
      setCurrentRound(prev => prev + 1)
    }
  }

  const filteredPlayers = selectedPosition === 'ALL' 
    ? availablePlayers 
    : availablePlayers.filter(p => p.position === selectedPosition)

  const draftedIds = new Set(draftedPlayers.map(p => p.sleeper_id))
  const availableFilteredPlayers = filteredPlayers.filter(p => !draftedIds.has(p.sleeper_id))

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading draft data...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Draft Assistant</h1>
        <p className="text-gray-600 mt-2">
          AI-powered draft recommendations optimized for {settings.scoringFormat} scoring
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          
          {/* AI Recommendations */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">AI Recommendations</h2>
              <span className="text-sm text-gray-500">
                Round {currentRound}, Pick {getCurrentPick()}
              </span>
            </div>
            
            <div className="space-y-3">
              {recommendations.length > 0 ? recommendations.map((rec, index) => (
                <div key={`rec-${rec.player_name}-${index}`} className="flex items-center justify-between p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-gray-900">{rec.player_name}</span>
                      <span className="text-sm text-gray-500">{rec.position}</span>
                      <StarIcon className="w-4 h-4 text-yellow-500" />
                    </div>
                    <p className="text-sm text-gray-700">{rec.reasoning}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-green-600">
                      {rec.confidence}% confidence
                    </div>
                    <button
                      onClick={() => {
                        const player = availablePlayers.find(p => 
                          p.full_name === rec.player_name || 
                          p.full_name.includes(rec.player_name)
                        )
                        if (player) draftPlayer(player)
                      }}
                      className="mt-2 px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700"
                    >
                      Draft
                    </button>
                  </div>
                </div>
              )) : recommendationsError ? (
                <div className="text-center py-8 text-red-600">
                  <p>{recommendationsError}</p>
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <p>Configure your draft settings to get AI recommendations</p>
                </div>
              )}
            </div>
          </div>

          {/* Available Players */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Available Players</h2>
              <select 
                value={selectedPosition}
                onChange={(e) => setSelectedPosition(e.target.value)}
                className="rounded-md border-gray-300 text-sm"
              >
                {positions.map(pos => (
                  <option key={pos} value={pos}>{pos}</option>
                ))}
              </select>
            </div>
            
            <div className="max-h-96 overflow-y-auto">
              <div className="space-y-2">
                {availableFilteredPlayers.slice(0, 50).map((player) => (
                  <div key={player.sleeper_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{player.full_name}</span>
                        <span className="text-sm text-gray-500">{player.position} - {player.team}</span>
                        {trendingPlayers.some(tp => tp.sleeper_id === player.sleeper_id) && (
                          <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                            Trending
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {player.projected_points && (
                        <div className="text-right">
                          <div className="text-sm font-medium">Proj: {player.projected_points}</div>
                        </div>
                      )}
                      <button
                        onClick={() => draftPlayer(player)}
                        className="p-1 text-blue-600 hover:text-blue-800"
                        title="Draft player"
                      >
                        <PlusIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          
          {/* Draft Settings */}
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Draft Settings</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Scoring Format
                </label>
                <select 
                  value={settings.scoringFormat}
                  onChange={(e) => setSettings({...settings, scoringFormat: e.target.value as DraftSettings['scoringFormat']})}
                  className="w-full rounded-md border-gray-300"
                >
                  <option value="PPR">PPR</option>
                  <option value="Half PPR">Half PPR</option>
                  <option value="Standard">Standard</option>
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Team Count
                </label>
                <select 
                  value={settings.teamCount}
                  onChange={(e) => setSettings({...settings, teamCount: Number(e.target.value)})}
                  className="w-full rounded-md border-gray-300"
                >
                  <option value={8}>8 Teams</option>
                  <option value={10}>10 Teams</option>
                  <option value={12}>12 Teams</option>
                  <option value={14}>14 Teams</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Your Draft Position
                </label>
                <select 
                  value={settings.draftPosition}
                  onChange={(e) => setSettings({...settings, draftPosition: Number(e.target.value)})}
                  className="w-full rounded-md border-gray-300"
                >
                  {Array.from({length: settings.teamCount}, (_, i) => (
                    <option key={i + 1} value={i + 1}>Position {i + 1}</option>
                  ))}
                </select>
              </div>

              <button
                onClick={generateRecommendations}
                className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700"
              >
                Refresh Recommendations
              </button>
            </div>
          </div>

          {/* Your Team */}
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">
              Your Team ({draftedPlayers.length})
            </h2>
            
            {draftedPlayers.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {draftedPlayers.map((player) => (
                  <div key={`drafted-${player.sleeper_id}-${player.round}-${player.pick}`} className="p-2 bg-green-50 rounded border border-green-200">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-medium text-sm">{player.full_name}</span>
                        <span className="text-xs text-gray-500 ml-2">{player.position}</span>
                      </div>
                      <span className="text-xs text-gray-600">
                        R{player.round}P{player.pick}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500 text-sm">
                  Your drafted players will appear here
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Click the + button next to players to draft them
                </p>
              </div>
            )}

            {draftedPlayers.length > 0 && (
              <button
                onClick={() => {
                  setDraftedPlayers([])
                  setCurrentRound(1)
                }}
                className="w-full mt-4 text-sm text-gray-600 hover:text-gray-800"
              >
                Reset Draft
              </button>
            )}
          </div>

          {/* Team Needs */}
          {draftedPlayers.length > 0 && (
            <div className="card">
              <h2 className="text-lg font-semibold mb-2">Team Needs</h2>
              <div className="flex flex-wrap gap-2">
                {getTeamNeeds().map(need => (
                  <span key={need} className="px-2 py-1 bg-orange-100 text-orange-800 text-xs rounded">
                    {need}
                  </span>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
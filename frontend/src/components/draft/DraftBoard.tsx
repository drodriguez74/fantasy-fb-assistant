import { PlusIcon, StarIcon } from '@heroicons/react/24/outline'
import { DraftRecommendation, Player } from '../../types'
import { getPositionColor, injuryStatusClasses } from '../players/playerDisplay'

interface DraftBoardProps {
  recommendations: DraftRecommendation[]
  availablePlayers: Player[]
  onPlayerSelect: (player: Player) => void
  selectedPosition: string
  onPositionChange: (position: string) => void
}

export function DraftBoard({ 
  recommendations, 
  availablePlayers, 
  onPlayerSelect, 
  selectedPosition, 
  onPositionChange 
}: DraftBoardProps) {
  const positions = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DEF']
  
  const filteredPlayers = selectedPosition === 'ALL' 
    ? availablePlayers 
    : availablePlayers.filter(p => p.position === selectedPosition)

  const getPlayerRank = (player: Player): number => {
    const index = availablePlayers.findIndex(p => p.id === player.id)
    return index >= 0 ? index + 1 : 999
  }

  return (
    <div className="space-y-6">
      {/* Position Filter */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold text-ink-900">Available Players</h2>
        <select
          value={selectedPosition}
          onChange={(e) => onPositionChange(e.target.value)}
          className="rounded-md border-ink-300 text-sm focus:border-accent-500 focus:ring-accent-500"
        >
          {positions.map(pos => (
            <option key={pos} value={pos}>{pos}</option>
          ))}
        </select>
      </div>

      {/* Recommendations Section */}
      {recommendations.length > 0 && (
        <div className="bg-accent-50 rounded-lg border border-accent-200 p-4">
          <h3 className="text-lg font-medium text-accent-900 mb-3 flex items-center">
            <StarIcon className="h-5 w-5 mr-2" />
            AI Recommendations
          </h3>
          <div className="space-y-2">
            {recommendations.slice(0, 3).map((rec, index) => (
              <div key={index} className="bg-white rounded-md p-3 border border-accent-100 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{rec.player.name}</span>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPositionColor(rec.player.position)}`}>
                        {rec.player.position}
                      </span>
                      <span className="text-sm text-ink-500">{rec.player.team}</span>
                    </div>
                    <p className="text-sm text-ink-600 mt-1">{rec.reasoning}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-success-700">
                      Score: {rec.score.toFixed(1)}
                    </div>
                    <button
                      onClick={() => onPlayerSelect(rec.player)}
                      className="mt-1 px-3 py-1 bg-accent-500 text-white text-xs rounded hover:bg-accent-600 transition-colors"
                    >
                      Draft
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Player List */}
      <div className="bg-white rounded-lg shadow-sm border border-ink-200">
        <div className="max-h-96 overflow-y-auto">
          {filteredPlayers.length > 0 ? (
            <div className="divide-y divide-ink-200">
              {filteredPlayers.slice(0, 50).map((player) => (
                <div key={player.id} className="p-4 hover:bg-ink-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-ink-500 w-8">
                          #{getPlayerRank(player)}
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-ink-900">{player.name}</span>
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                              {player.position}
                            </span>
                            <span className="text-sm text-ink-500">{player.team}</span>
                          </div>
                          <div className="flex items-center gap-4 mt-1 text-xs text-ink-500">
                            {player.projected_points && (
                              <span>Proj: {player.projected_points.toFixed(1)}</span>
                            )}
                            {player.adp && (
                              <span>ADP: {player.adp.toFixed(1)}</span>
                            )}
                            {player.bye_week && (
                              <span>Bye: {player.bye_week}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {player.injury_status && player.injury_status.toUpperCase() !== 'HEALTHY' && (
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${injuryStatusClasses(player.injury_status)}`}>
                          {player.injury_status}
                        </span>
                      )}
                      <button
                        onClick={() => onPlayerSelect(player)}
                        className="p-2 text-accent-600 hover:text-accent-800 hover:bg-accent-50 rounded transition-colors"
                        title="Draft player"
                      >
                        <PlusIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center text-ink-500">
              <p>No players available for {selectedPosition}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
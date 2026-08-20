import { PlusIcon, StarIcon } from '@heroicons/react/24/outline'
import { DraftRecommendation, Player } from '../../types'

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

  const getPositionColor = (position: string): string => {
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

  return (
    <div className="space-y-6">
      {/* Position Filter */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Available Players</h2>
        <select 
          value={selectedPosition}
          onChange={(e) => onPositionChange(e.target.value)}
          className="rounded-md border-gray-300 text-sm focus:border-blue-500 focus:ring-blue-500"
        >
          {positions.map(pos => (
            <option key={pos} value={pos}>{pos}</option>
          ))}
        </select>
      </div>

      {/* Recommendations Section */}
      {recommendations.length > 0 && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200 p-4">
          <h3 className="text-lg font-medium text-blue-900 mb-3 flex items-center">
            <StarIcon className="h-5 w-5 mr-2" />
            AI Recommendations
          </h3>
          <div className="space-y-2">
            {recommendations.slice(0, 3).map((rec, index) => (
              <div key={index} className="bg-white rounded-md p-3 border border-blue-100">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{rec.player.name}</span>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPositionColor(rec.player.position)}`}>
                        {rec.player.position}
                      </span>
                      <span className="text-sm text-gray-500">{rec.player.team}</span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">{rec.reasoning}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-green-600">
                      Score: {rec.score.toFixed(1)}
                    </div>
                    <button
                      onClick={() => onPlayerSelect(rec.player)}
                      className="mt-1 px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 transition-colors"
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
      <div className="bg-white rounded-lg shadow border border-gray-200">
        <div className="max-h-96 overflow-y-auto">
          {filteredPlayers.length > 0 ? (
            <div className="divide-y divide-gray-200">
              {filteredPlayers.slice(0, 50).map((player) => (
                <div key={player.id} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-500 w-8">
                          #{getPlayerRank(player)}
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-900">{player.name}</span>
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                              {player.position}
                            </span>
                            <span className="text-sm text-gray-500">{player.team}</span>
                          </div>
                          <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
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
                      {player.injury_status && player.injury_status !== 'HEALTHY' && (
                        <span className="px-2 py-1 bg-red-100 text-red-800 text-xs rounded">
                          {player.injury_status}
                        </span>
                      )}
                      <button
                        onClick={() => onPlayerSelect(player)}
                        className="p-2 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors"
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
            <div className="p-8 text-center text-gray-500">
              <p>No players available for {selectedPosition}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
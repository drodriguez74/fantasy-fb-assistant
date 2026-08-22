import { TrashIcon } from '@heroicons/react/24/outline'
import { Player } from '../../types'
import { getPositionColor } from '../players/playerDisplay'

interface DraftedPlayer extends Player {
  round: number
  pick: number
}

interface TeamRosterProps {
  draftedPlayers: DraftedPlayer[]
  onRemovePlayer?: (playerId: number) => void
  onResetDraft: () => void
  showActions?: boolean
}

export function TeamRoster({ 
  draftedPlayers, 
  onRemovePlayer, 
  onResetDraft, 
  showActions = true 
}: TeamRosterProps) {
  const getPositionCount = (position: string): number => {
    return draftedPlayers.filter(p => p.position === position).length
  }

  const getRosterNeeds = (): string[] => {
    const counts = {
      QB: getPositionCount('QB'),
      RB: getPositionCount('RB'),
      WR: getPositionCount('WR'),
      TE: getPositionCount('TE'),
      K: getPositionCount('K'),
      DEF: getPositionCount('DEF')
    }

    const needs: string[] = []
    
    // Standard roster requirements
    if (counts.QB < 1) needs.push('QB')
    if (counts.RB < 2) needs.push('RB')
    if (counts.WR < 2) needs.push('WR')
    if (counts.TE < 1) needs.push('TE')
    if (counts.K < 1) needs.push('K')
    if (counts.DEF < 1) needs.push('DEF')

    return needs
  }

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">
          Your Team ({draftedPlayers.length})
        </h2>
        {draftedPlayers.length > 0 && showActions && (
          <button
            onClick={onResetDraft}
            className="text-sm text-gray-600 hover:text-gray-800 transition-colors"
          >
            Reset Draft
          </button>
        )}
      </div>
      
      {draftedPlayers.length > 0 ? (
        <>
          {/* Drafted Players List */}
          <div className="space-y-2 max-h-64 overflow-y-auto mb-4">
            {draftedPlayers.map((player) => (
              <div key={`${player.id}-${player.round}-${player.pick}`} className="flex items-center justify-between p-3 bg-green-50 rounded-md border border-green-200">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{player.name}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                      {player.position}
                    </span>
                    <span className="text-xs text-gray-500">{player.team}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                    <span>Round {player.round}, Pick {player.pick}</span>
                    {player.projected_points && (
                      <span>Proj: {player.projected_points.toFixed(1)}</span>
                    )}
                  </div>
                </div>
                {showActions && onRemovePlayer && (
                  <button
                    onClick={() => onRemovePlayer(player.id)}
                    className="p-1 text-red-600 hover:text-red-800 transition-colors"
                    title="Remove from team"
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Roster Summary */}
          <div className="bg-gray-50 rounded-md p-3 mb-4">
            <h4 className="text-sm font-medium text-gray-900 mb-2">Position Count</h4>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {['QB', 'RB', 'WR', 'TE', 'K', 'DEF'].map(pos => (
                <div key={pos} className="flex justify-between">
                  <span>{pos}:</span>
                  <span className="font-medium">{getPositionCount(pos)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Team Needs */}
          {getRosterNeeds().length > 0 && (
            <div className="bg-orange-50 rounded-md p-3">
              <h4 className="text-sm font-medium text-orange-900 mb-2">Roster Needs</h4>
              <div className="flex flex-wrap gap-1">
                {getRosterNeeds().map(need => (
                  <span key={need} className="px-2 py-1 bg-orange-100 text-orange-800 text-xs rounded">
                    {need}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
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
    </div>
  )
}
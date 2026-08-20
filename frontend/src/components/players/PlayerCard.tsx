import clsx from 'clsx'
import type { Player, Position } from '../../types'
import { AIAnalysis } from './AIAnalysis'

interface PlayerCardProps {
  player: Player
  onClick?: (player: Player) => void
  showDetails?: boolean
  isDraftMode?: boolean
  isRecommended?: boolean
}

const positionColors: Record<Position, string> = {
  QB: 'bg-red-100 text-red-800',
  RB: 'bg-green-100 text-green-800',
  WR: 'bg-blue-100 text-blue-800',
  TE: 'bg-yellow-100 text-yellow-800',
  K: 'bg-purple-100 text-purple-800',
  DEF: 'bg-gray-100 text-gray-800',
}

const riskColors = {
  LOW: 'text-green-600',
  MEDIUM: 'text-yellow-600',
  HIGH: 'text-red-600',
}

export function PlayerCard({ player, onClick, showDetails = false, isDraftMode = false, isRecommended = false }: PlayerCardProps) {
  const handleClick = () => {
    if (onClick) onClick(player)
  }

  return (
    <div
      className={clsx(
        'bg-white rounded-lg shadow-sm border p-4 transition-all',
        onClick && 'cursor-pointer hover:shadow-md hover:border-blue-300',
        isRecommended && 'border-blue-500 bg-blue-50',
        isDraftMode && 'hover:bg-gray-50'
      )}
      onClick={handleClick}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-2">
            <h3 className="text-lg font-semibold text-gray-900">{player.name}</h3>
            <span className={clsx('px-2 py-1 text-xs font-medium rounded-full', positionColors[player.position])}>
              {player.position}
            </span>
            {isRecommended && (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                Recommended
              </span>
            )}
          </div>
          
          <p className="text-sm text-gray-600 mb-2">{player.team}</p>
          
          {showDetails && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                {player.projected_points && (
                  <div>
                    <span className="text-gray-500">Projected:</span>
                    <span className="ml-1 font-medium">{player.projected_points.toFixed(1)} pts</span>
                  </div>
                )}
                {player.adp && (
                  <div>
                    <span className="text-gray-500">ADP:</span>
                    <span className="ml-1 font-medium">{player.adp.toFixed(1)}</span>
                  </div>
                )}
                {player.bye_week && (
                  <div>
                    <span className="text-gray-500">Bye:</span>
                    <span className="ml-1 font-medium">Week {player.bye_week}</span>
                  </div>
                )}
                {player.risk_level && (
                  <div>
                    <span className="text-gray-500">Risk:</span>
                    <span className={clsx('ml-1 font-medium', riskColors[player.risk_level])}>
                      {player.risk_level}
                    </span>
                  </div>
                )}
              </div>
              
              {player.injury_status && player.injury_status !== 'Healthy' && (
                <div className="text-sm">
                  <span className="text-red-600 font-medium">⚠️ {player.injury_status}</span>
                </div>
              )}
              
              
              {/* AI Analysis Component */}
              <AIAnalysis player={player} showButton={showDetails} />
            </div>
          )}
        </div>
        
        {isDraftMode && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleClick()
            }}
            className="ml-4 bg-blue-600 text-white px-3 py-1 rounded text-sm hover:bg-blue-700"
          >
            Draft
          </button>
        )}
      </div>
    </div>
  )
}
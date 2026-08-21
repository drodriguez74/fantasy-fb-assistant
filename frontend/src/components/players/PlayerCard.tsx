import clsx from 'clsx'
import type { Player } from '../../types'
import { positionColors, riskColors, injuryStatusClasses } from './playerDisplay'

interface PlayerCardProps {
  player: Player
  onClick?: (player: Player) => void
  showDetails?: boolean
  isDraftMode?: boolean
  isRecommended?: boolean
}

export function PlayerCard({ player, onClick, showDetails = false, isDraftMode = false, isRecommended = false }: PlayerCardProps) {
  const handleClick = () => {
    if (onClick) onClick(player)
  }

  const isHealthy = !player.injury_status || player.injury_status.toUpperCase() === 'HEALTHY'

  return (
    <div
      className={clsx(
        'bg-white rounded-lg shadow-sm border p-4 transition-shadow',
        onClick && 'cursor-pointer hover:shadow-md hover:border-accent-300',
        isRecommended && 'border-accent-500 bg-accent-50',
        !isRecommended && 'border-ink-200',
        isDraftMode && 'hover:bg-ink-50'
      )}
      onClick={handleClick}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-2">
            <h3 className="text-lg font-semibold text-ink-900">{player.name}</h3>
            <span className={clsx('px-2 py-1 text-xs font-medium rounded-full', positionColors[player.position])}>
              {player.position}
            </span>
            {isRecommended && (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-accent-100 text-accent-800">
                Recommended
              </span>
            )}
          </div>

          <p className="text-sm text-ink-600 mb-2 flex items-center gap-2">
            <span>{player.team}</span>
            {player.bye_week && (
              <span className="px-1.5 py-0.5 text-xs font-medium bg-ink-100 text-ink-600 rounded">
                Bye: {player.bye_week}
              </span>
            )}
          </p>

          {showDetails && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                {player.projected_points && (
                  <div>
                    <span className="text-ink-500">Projected:</span>
                    <span className="ml-1 font-medium">{player.projected_points.toFixed(1)} pts</span>
                  </div>
                )}
                {player.adp && (
                  <div>
                    <span className="text-ink-500">ADP:</span>
                    <span className="ml-1 font-medium">{player.adp.toFixed(1)}</span>
                  </div>
                )}
                {player.risk_level && (
                  <div>
                    <span className="text-ink-500">Risk:</span>
                    <span className={clsx('ml-1 font-medium', riskColors[player.risk_level])}>
                      {player.risk_level}
                    </span>
                  </div>
                )}
              </div>

              {!isHealthy && player.injury_status && (
                <div>
                  <span className={clsx('inline-flex items-center px-2 py-1 rounded-full text-xs font-medium', injuryStatusClasses(player.injury_status))}>
                    {player.injury_status}
                  </span>
                </div>
              )}

              {onClick && (
                <p className="text-xs text-accent-600 font-medium">
                  View player &rarr; get AI insights
                </p>
              )}
            </div>
          )}
        </div>

        {isDraftMode && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleClick()
            }}
            className="ml-4 bg-accent-500 text-white px-3 py-1 rounded text-sm hover:bg-accent-600 transition-colors"
          >
            Draft
          </button>
        )}
      </div>
    </div>
  )
}
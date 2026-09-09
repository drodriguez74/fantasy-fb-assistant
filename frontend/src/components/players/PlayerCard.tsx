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
        'bg-surface rounded-lg border p-4 transition-colors',
        onClick && 'cursor-pointer hover:border-accent-ink',
        isRecommended && 'border-accent-ink bg-highlight',
        !isRecommended && 'border-hairline',
        isDraftMode && 'hover:bg-surface-2'
      )}
      onClick={handleClick}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h3 className="text-base font-semibold text-body truncate">{player.name}</h3>
            <span className={clsx('px-1.5 py-0.5 text-[10px] font-medium rounded', positionColors[player.position])}>
              {player.position}
            </span>
            {isRecommended && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-highlight text-accent-ink">
                Rec
              </span>
            )}
          </div>

          <p className="text-xs font-stat text-muted flex items-center gap-2">
            <span>{player.team}</span>
            {player.bye_week && <span className="text-faint">&middot; BYE {player.bye_week}</span>}
            {!isHealthy && player.injury_status && (
              <span className={clsx('inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium', injuryStatusClasses(player.injury_status))}>
                {player.injury_status}
              </span>
            )}
          </p>

          {showDetails && (player.projected_points || player.adp || player.consensus || player.risk_level) && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs font-stat">
              {player.consensus && (
                <span className="text-muted">
                  RANK <span className="text-body font-medium">#{player.consensus.consensus_rank}</span>
                </span>
              )}
              {player.projected_points != null && (
                <span className="text-muted">
                  PROJ <span className="text-body font-medium">{player.projected_points.toFixed(1)}</span>
                </span>
              )}
              {player.adp != null && (
                <span className="text-muted">
                  ADP <span className="text-body font-medium">{player.adp.toFixed(1)}</span>
                </span>
              )}
              {player.risk_level && (
                <span className="text-muted">
                  RISK <span className={clsx('font-medium', riskColors[player.risk_level])}>{player.risk_level}</span>
                </span>
              )}
            </div>
          )}

          {showDetails && onClick && (
            <p className="mt-3 text-xs font-stat text-accent-ink">
              View player &rarr;
            </p>
          )}
        </div>

        {isDraftMode && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleClick()
            }}
            className="ml-4 bg-volt text-volt-ink px-3 py-1 rounded text-sm hover:bg-volt-dark transition-colors"
          >
            Draft
          </button>
        )}
      </div>
    </div>
  )
}
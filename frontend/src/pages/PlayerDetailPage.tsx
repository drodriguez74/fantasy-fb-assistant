import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { AIAnalysis } from '../components/players/AIAnalysis'
import { positionColors, riskColors, injuryStatusClasses } from '../components/players/playerDisplay'
import type { Player } from '../types'

// Player detail view. Reached by clicking a card in the Players list, which
// hands us the already-fetched Player object via router state -- so opening
// this page costs zero extra network calls. "Get AI Insights" lives here as
// a single, deliberate action for one player instead of a button rendered on
// every row of a 4,000+ player list (see PlayerCard.tsx / AIAnalysis.tsx).
export function PlayerDetailPage() {
  const { playerId } = useParams<{ playerId: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  const player = (location.state as { player?: Player } | null)?.player

  if (!player) {
    // Direct link / page refresh with no state carried over. We deliberately
    // don't fall back to fetching GET /players/{id} here -- that endpoint
    // also triggers a full Sleeper player-stats pull (18+ sequential weekly
    // requests), which is exactly the kind of unscoped expensive call this
    // page exists to avoid making implicitly. Send the user back to the list
    // instead of paying that cost just to redisplay a name.
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-warning-50 border border-warning-200 text-warning-800 px-4 py-3 rounded-md">
          We don't have this player's details loaded. Please open this page by clicking a
          player from the list.
        </div>
        <button
          onClick={() => navigate('/players')}
          className="mt-4 flex items-center text-accent-ink hover:text-accent-ink"
        >
          <ArrowLeftIcon className="h-4 w-4 mr-1" />
          Back to Players
        </button>
      </div>
    )
  }

  const isHealthy = !player.injury_status || player.injury_status.toUpperCase() === 'HEALTHY'

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <button
        onClick={() => navigate('/players')}
        className="flex items-center text-accent-ink hover:text-accent-ink text-sm font-medium"
      >
        <ArrowLeftIcon className="h-4 w-4 mr-1" />
        Back to Players
      </button>

      <div className="bg-surface rounded-lg border border-hairline p-6">
        <div className="flex items-center space-x-3 mb-2">
          <h1 className="font-display font-bold uppercase tracking-tight text-2xl text-body">{player.name}</h1>
          <span className={clsx('px-2 py-1 text-xs font-medium rounded-full', positionColors[player.position])}>
            {player.position}
          </span>
        </div>

        <p className="text-sm text-muted mb-4 flex items-center gap-2">
          <span>{player.team}</span>
          {player.bye_week && (
            <span className="px-1.5 py-0.5 text-xs font-medium bg-surface-2 text-muted rounded">
              Bye: {player.bye_week}
            </span>
          )}
          {playerId && <span className="text-faint">&middot; ID {playerId}</span>}
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm mb-4">
          {player.projected_points != null && (
            <div>
              <span className="text-muted block">Projected</span>
              <span className="font-stat tabular-nums font-medium">{player.projected_points.toFixed(1)} pts</span>
            </div>
          )}
          {player.adp != null && (
            <div>
              <span className="text-muted block">ADP</span>
              <span className="font-stat tabular-nums font-medium">{player.adp.toFixed(1)}</span>
            </div>
          )}
          {player.risk_level && (
            <div>
              <span className="text-muted block">Risk</span>
              <span className={clsx('font-medium', riskColors[player.risk_level])}>
                {player.risk_level}
              </span>
            </div>
          )}
        </div>

        {!isHealthy && player.injury_status && (
          <div className="mb-4">
            <span className={clsx('inline-flex items-center px-2 py-1 rounded-full text-xs font-medium', injuryStatusClasses(player.injury_status))}>
              {player.injury_status}
            </span>
          </div>
        )}

        {/* Deliberate, single-player, on-demand AI insights action -- the
            same component previously rendered once per row in the list. */}
        <AIAnalysis player={player} showButton={true} />
      </div>
    </div>
  )
}

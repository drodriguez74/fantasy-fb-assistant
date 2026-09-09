import { getPositionColor } from '../players/playerDisplay'

interface PickLogPlayer {
  sleeper_id: string
  full_name: string
  position: string
  team: string
}

export interface PickLogEntry {
  overallPick: number
  round: number
  pickInRound: number
  team: number
  player: PickLogPlayer
  isUser: boolean
  reason?: string
}

interface DraftPickLogProps {
  picks: PickLogEntry[]
}

export function DraftPickLog({ picks }: DraftPickLogProps) {
  const ordered = [...picks].sort((a, b) => b.overallPick - a.overallPick)

  return (
    <div className="bg-surface rounded-lg border border-hairline p-6">
      <h2 className="text-lg font-semibold mb-4 text-body">Draft Board</h2>

      {ordered.length === 0 ? (
        <p className="text-sm text-muted">
          Picks will appear here once the draft starts, including what the other teams took.
        </p>
      ) : (
        <div className="max-h-80 overflow-y-auto space-y-1.5">
          {ordered.map((pick) => (
            <div
              key={pick.overallPick}
              className={`p-2.5 rounded-md text-sm ${
                pick.isUser ? 'bg-highlight border border-highlight-line' : 'bg-surface-2 border border-hairline'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs text-muted shrink-0 w-12">
                    R{pick.round}.{String(pick.pickInRound).padStart(2, '0')}
                  </span>
                  <span className={`font-medium shrink-0 ${pick.isUser ? 'text-accent-ink' : 'text-body'}`}>
                    {pick.isUser ? 'You' : `Team ${pick.team}`}
                  </span>
                  <span className="text-faint shrink-0">&rarr;</span>
                  <span className="font-medium text-body truncate">{pick.player.full_name}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${getPositionColor(pick.player.position)}`}
                  >
                    {pick.player.position}
                  </span>
                  <span className="text-xs text-muted shrink-0">{pick.player.team}</span>
                </div>
                <span className="text-xs text-faint shrink-0">#{pick.overallPick}</span>
              </div>
              {pick.reason && (
                <p className="text-xs text-muted mt-1 ml-14">{pick.reason}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

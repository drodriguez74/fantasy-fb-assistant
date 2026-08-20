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

const POSITION_COLORS: Record<string, string> = {
  QB: 'bg-red-100 text-red-800',
  RB: 'bg-green-100 text-green-800',
  WR: 'bg-blue-100 text-blue-800',
  TE: 'bg-purple-100 text-purple-800',
  K: 'bg-yellow-100 text-yellow-800',
  DEF: 'bg-gray-100 text-gray-800',
}

export function DraftPickLog({ picks }: DraftPickLogProps) {
  const ordered = [...picks].sort((a, b) => b.overallPick - a.overallPick)

  return (
    <div className="card">
      <h2 className="text-lg font-semibold mb-4">Draft Board</h2>

      {ordered.length === 0 ? (
        <p className="text-sm text-gray-500">
          Picks will appear here once the draft starts, including what the other teams took.
        </p>
      ) : (
        <div className="max-h-80 overflow-y-auto space-y-1.5">
          {ordered.map((pick) => (
            <div
              key={pick.overallPick}
              className={`p-2.5 rounded-md text-sm ${
                pick.isUser ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50 border border-gray-100'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs text-gray-500 shrink-0 w-12">
                    R{pick.round}.{String(pick.pickInRound).padStart(2, '0')}
                  </span>
                  <span className={`font-medium shrink-0 ${pick.isUser ? 'text-blue-900' : 'text-gray-700'}`}>
                    {pick.isUser ? 'You' : `Team ${pick.team}`}
                  </span>
                  <span className="text-gray-300 shrink-0">&rarr;</span>
                  <span className="font-medium text-gray-900 truncate">{pick.player.full_name}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${
                      POSITION_COLORS[pick.player.position] || 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {pick.player.position}
                  </span>
                  <span className="text-xs text-gray-500 shrink-0">{pick.player.team}</span>
                </div>
                <span className="text-xs text-gray-400 shrink-0">#{pick.overallPick}</span>
              </div>
              {pick.reason && (
                <p className="text-xs text-gray-500 mt-1 ml-14">{pick.reason}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Cover + over/under same-game parlays from GET /betting/board's
// `game_combos` (backend/app/services/betting_service.py::game_combos).
export interface GameCombo {
  label: string
  prob: number
  fair_odds: number | null
}

export interface GameComboSet {
  game: string
  kickoff?: string
  favorite: string
  modeled: boolean
  combos: GameCombo[]
}

const odds = (o: number | null) => (o == null ? '—' : o > 0 ? `+${o}` : `${o}`)

export function GameCombos({ games }: { games?: GameComboSet[] }) {
  if (!games || games.length === 0) return null
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-medium text-body">Cover + over/under combos</h3>
        <p className="text-xs text-muted mt-1 leading-relaxed">
          Each combo's chance of hitting and its fair odds (no vig). Our odds feed doesn't carry same-game parlay prices, so
          compare these with your sportsbook's price for the same combo: if the book pays more than the fair odds, it's value.
          A favorite that covers usually means more points, so cover + over is priced as related.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {games.map((g) => (
          <div key={g.game} className="rounded-lg border border-hairline bg-surface p-3">
            <div className="flex items-baseline justify-between">
              <span className="font-medium text-body">{g.game}</span>
              <span className="stat-nums text-[11px] text-faint">{g.favorite} favored</span>
            </div>
            <ul className="mt-2 space-y-1">
              {g.combos.map((c) => (
                <li key={c.label} className="flex items-baseline gap-3 stat-nums text-xs">
                  <span className="text-body flex-1">{c.label}</span>
                  <span className="text-muted w-14 text-right">{(c.prob * 100).toFixed(1)}%</span>
                  <span className="text-faint w-14 text-right">{odds(c.fair_odds)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

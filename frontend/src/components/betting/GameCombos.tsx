// Cover + over/under same-game parlays from GET /betting/board's
// `game_combos` (backend/app/services/betting_service.py::game_combos).
import { useState } from 'react'

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
  const [open, setOpen] = useState(false)
  if (!games || games.length === 0) return null
  return (
    <div className="rounded-lg border border-hairline bg-surface">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-baseline gap-3 px-4 py-3 text-left" aria-expanded={open}>
        <span className="text-sm font-medium text-body">Cover + over/under combos</span>
        <span className="text-xs text-faint">{games.length} games · fair odds for same-game parlays</span>
        <span className="ml-auto text-xs text-accent-ink">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3">
          <p className="text-xs text-muted leading-relaxed">
            Each combo's chance of hitting and its fair odds (no vig). Compare with your sportsbook's same-game parlay price:
            if the book pays more than the fair odds, it's value. A favorite that covers usually means more points, so
            those combos are priced as related.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {games.map((g) => (
              <div key={g.game} className="rounded-lg border border-hairline p-3">
                <div className="flex items-baseline justify-between">
                  <span className="font-medium text-body">{g.game}</span>
                  <span className="stat-nums text-[11px] text-faint">{g.favorite} favored</span>
                </div>
                <table className="w-full mt-2 stat-nums text-xs">
                  <thead>
                    <tr className="text-faint text-left">
                      <th className="font-normal py-0.5">Combo</th>
                      <th className="font-normal text-right">Chance</th>
                      <th className="font-normal text-right">Fair odds</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.combos.map((c) => (
                      <tr key={c.label}>
                        <td className="text-body py-0.5">{c.label}</td>
                        <td className="text-muted text-right">{(c.prob * 100).toFixed(1)}%</td>
                        <td className="text-faint text-right">{odds(c.fair_odds)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

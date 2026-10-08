// "Correlated stacks" on the PrizePicks tab: picks in one game that move
// together (a QB and his own receivers in the same direction, opposing backs
// apart), plus one pick from another game. PrizePicks pays fixed multipliers
// that assume independent picks, so a positively correlated stack hits more
// often than the payout assumes. Every chance here is the books' own (no
// projections); the lift comes from correlations measured on real games
// (betting_service.correlated_stacks). Edge uses the payouts set under Best
// entries, so a state's real multipliers flow through.
import type { Power } from './prizePicksEntriesData'

export interface StackLeg {
  player: string
  team?: string | null
  game: string
  market: string
  market_label?: string
  side: 'More' | 'Less'
  line: number
  p_win: number
}

export interface Stack {
  size: number
  type: 'power'
  legs: StackLeg[]
  p_all: number
  p_independent: number
  lift: number | null
  payout: number
}

const whole = (p: number) => `${Math.round(p * 100)}%`
const oneDp = (p: number) => `${(p * 100).toFixed(1)}%`

export function CorrelatedStacks({ stacks, power }: { stacks?: Stack[]; power: Power | null }) {
  if (!stacks || stacks.length === 0) return null
  const priced = stacks
    .map((s) => {
      const payout = power?.[String(s.size)] ?? s.payout
      return { ...s, payout, ev: s.p_all * payout - 1 }
    })
    .sort((a, b) => b.ev - a.ev)
  const good = priced.filter((s) => s.ev > 0)
  return (
    <section className="rounded-lg border border-hairline bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display font-bold uppercase tracking-tight text-sm text-body">Correlated stacks</h3>
        <span className="text-xs text-muted">Books' chances only · edge from picks that move together</span>
      </div>
      <p className="text-xs text-muted mt-1 leading-relaxed">
        A QB and his own receivers going the same way hit together more often than PrizePicks' payout assumes (measured on
        real games). Each stack adds one pick from another team, which PrizePicks requires.
      </p>
      {good.length === 0 ? (
        <p className="text-xs text-muted mt-3">No stack has a positive edge at your payouts right now.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {good.slice(0, 6).map((s) => (
            <div key={s.legs.map((l) => `${l.player}${l.market}${l.side}`).join('|')} className="rounded-lg border border-hairline p-3">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 stat-nums text-xs">
                <span className="text-sm font-semibold text-body">{s.size}-pick Power</span>
                <span className="text-success-700" title="Expected profit per $1 at your payout">
                  Edge +{(s.ev * 100).toFixed(1)}%
                </span>
                <span>
                  <span className="text-body">{oneDp(s.p_all)}</span> <span className="text-faint">all hit</span>
                </span>
                <span className="text-faint">vs {oneDp(s.p_independent)} if independent</span>
                <span className="text-faint">at {s.payout}x · needs {(1 / s.p_all).toFixed(1)}x</span>
              </div>
              <ul className="mt-2 space-y-0.5 text-sm">
                {s.legs.map((l, i) => (
                  <li key={`${l.player}-${l.market}`} className="flex items-baseline gap-2">
                    <span className="min-w-0 flex-1 truncate text-body">
                      {l.player} <span className="text-faint text-xs">{l.team}</span>{' '}
                      <span className="font-medium">{l.side}</span> <span className="stat-nums">{l.line}</span>{' '}
                      <span className="text-muted">{(l.market_label ?? l.market).toString().toLowerCase()}</span>
                      {i === s.legs.length - 1 && <span className="text-xs text-faint"> · other team</span>}
                    </span>
                    <span className="stat-nums text-xs text-faint shrink-0">books {whole(l.p_win)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-faint mt-3">
        Tracked and graded like every suggestion: Track record shows whether stacks hit as often as we say.
      </p>
    </section>
  )
}

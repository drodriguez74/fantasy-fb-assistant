// "Safest picks" on the PrizePicks tab: the PrizePicks picks most likely to
// win (calibrated win chance, our model and ESPN behind them; see
// betting_service.most_likely), each with the payout it needs. Goblins pay
// less, so a high win chance is only worth it if PrizePicks' multiplier beats
// what the chance requires -- the founder's 2026-10-07 screenshots (1.2x for
// two goblins, 1.9x for one) were both below it.
import { type MostLikely, kickoffLabel } from './betTypes'
import { AddButton } from './TicketTray'
import type { TicketActions } from './ticketTypes'
import { chance } from './format'
import { SectionHeader } from './ui'

// The total payout multiplier at which a ticket with this chance breaks even.
const breakEven = (p: number) => (p > 0 ? `${(1 / p).toFixed(2)}x` : '—')

export function SafestPicks({ data, ticket }: { data?: MostLikely; ticket?: TicketActions }) {
  if (!data) return null
  return (
    <section className="rounded-lg border border-hairline bg-surface p-4">
      <SectionHeader title="Safest picks" meta={`${chance(data.min_p_win)}+ to win · model and ESPN agree`} />
      {data.picks.length === 0 ? (
        <p className="text-xs text-muted mt-2">
          No pick reaches {chance(data.min_p_win)} with our model behind it. Upload today's board to include goblins.
        </p>
      ) : (
        <>
          <ul className="mt-2 divide-y divide-hairline">
            {data.picks.map((p) => (
              <li key={`${p.player}-${p.market}`} className="py-2 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-body break-words">
                    <span className="font-medium">{p.player}</span> {p.side} {p.line} {(p.market_label ?? '').toLowerCase()}
                    {p.odds_type !== 'standard' && (
                      <span className="ml-1.5 text-xs text-muted border border-hairline rounded px-1 capitalize">{p.odds_type}</span>
                    )}
                  </p>
                  <p className="stat-nums text-xs text-muted truncate">
                    {p.market_prob != null && `Books ${chance(p.market_prob)}`}
                    {p.game && ` · ${p.game}`}
                    {kickoffLabel(p.kickoff) && ` · ${kickoffLabel(p.kickoff)}`}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <div className="stat-nums text-xl font-bold text-body leading-none">{chance(p.p_win)}</div>
                  <div className="text-xs text-faint mt-1">to win</div>
                </div>
                {ticket && <AddButton active={ticket.has(p)} onClick={() => ticket.toggle(p)} />}
              </li>
            ))}
          </ul>
          {data.safest_pair && (
            <div className="mt-2 border-t border-hairline pt-2.5">
              <p className="text-sm text-body">
                <span className="font-medium">Safest 2-pick:</span> {data.safest_pair.legs.join(' + ')}
              </p>
              <p className="stat-nums text-xs text-muted mt-0.5">
                {chance(data.safest_pair.p_both)} both hit · worth it only if PrizePicks pays at least{' '}
                <span className="text-body font-medium">{breakEven(data.safest_pair.p_both)}</span> (shown as "$1 to pay
                $X"). Two goblins usually pay less than that.
              </p>
            </div>
          )}
        </>
      )}
    </section>
  )
}

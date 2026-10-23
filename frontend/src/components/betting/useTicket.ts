// The PrizePicks entry-builder ticket, held by the Bets page (2026-10-12
// review: it lived inside the PrizePicks tab and emptied on every tab switch).
// One pick per player and stat (a new line on the same stat replaces the old
// one; two stats of one player can sit together, priced with the measured
// same-player correlation since 2026-10-22), at most 6.
import { useMemo, useState } from 'react'
import { legKey, type TicketActions, type TicketLeg } from './ticketTypes'

export interface Ticket extends TicketActions {
  picks: TicketLeg[]
  remove: (l: TicketLeg) => void
  clear: () => void
}

const same = (a: TicketLeg, b: TicketLeg) => legKey(a) === legKey(b) && a.side === b.side && a.line === b.line

export function useTicket(): Ticket {
  const [picks, setPicks] = useState<TicketLeg[]>([])
  return useMemo(
    () => ({
      picks,
      has: (l) => picks.some((p) => same(p, l)),
      toggle: (l) =>
        setPicks((ps) =>
          ps.some((p) => same(p, l)) ? ps.filter((p) => legKey(p) !== legKey(l)) : [...ps.filter((p) => legKey(p) !== legKey(l)), l].slice(0, 6),
        ),
      addAll: (ls) =>
        setPicks((ps) => {
          const keys = new Set(ls.map(legKey))
          return [...ps.filter((p) => !keys.has(legKey(p))), ...ls].slice(-6)
        }),
      remove: (l) => setPicks((ps) => ps.filter((p) => legKey(p) !== legKey(l))),
      clear: () => setPicks([]),
    }),
    [picks],
  )
}

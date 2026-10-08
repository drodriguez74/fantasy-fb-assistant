// Shared types for the entry-builder tray (TicketTray) and the pick rows that add to it.
export interface TicketLeg {
  player: string
  team?: string | null
  game?: string
  market: string
  market_label?: string
  side: 'More' | 'Less'
  line: number
  p_win: number
  odds_type?: string
}

export const legKey = (l: TicketLeg) => `${l.player}|${l.market}`

// What pick rows can do with the ticket.
export interface TicketActions {
  has: (l: TicketLeg) => boolean
  toggle: (l: TicketLeg) => void
  addAll: (ls: TicketLeg[]) => void
}

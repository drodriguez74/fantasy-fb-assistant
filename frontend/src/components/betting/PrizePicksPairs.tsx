// PrizePicks 2-pick Power Plays from GET /betting/board's `prizepicks`
// section -- backend/app/services/betting_service.py::prizepicks_pairs.
export interface PrizePicksLeg {
  player: string
  team?: string | null
  game?: string
  market: string
  market_label: string
  projection: number
  espn_projection?: number | null
  line: number
  side: 'More' | 'Less'
  p_win: number
  model_prob: number
  market_prob: number
  book_line: number
}

export interface PrizePicksPair {
  legs: [PrizePicksLeg, PrizePicksLeg]
  same_game: boolean
  correlation: number
  joint_prob: number
  independent_prob: number
  ev: number
  units: number
  confidence: 'high' | 'strong' | 'lean' | 'none'
}

export interface PrizePicksBoard {
  payout: number
  breakeven_leg: number
  legs: PrizePicksLeg[]
  pairs: PrizePicksPair[]
  positive_ev_pairs: number
}

const pct = (p: number) => `${(p * 100).toFixed(1)}%`

function Leg({ leg }: { leg: PrizePicksLeg }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium text-body">{leg.player}</span>
        <span className="stat-nums text-xs text-faint">{leg.team} · {leg.game}</span>
      </div>
      <p className="text-sm text-body">
        <span className={`font-semibold ${leg.side === 'More' ? 'text-success-700' : 'text-accent-ink'}`}>{leg.side}</span>{' '}
        <span className="stat-nums">{leg.line}</span> <span className="text-muted">{leg.market_label}</span>
      </p>
      <p className="stat-nums text-[11px] text-faint">
        Hit {pct(leg.p_win)} · market {pct(leg.market_prob)} · model {pct(leg.model_prob)} · proj {leg.projection.toFixed(1)}
        {leg.espn_projection != null && ` · ESPN ${leg.espn_projection.toFixed(1)}`}
        {leg.book_line !== leg.line && ` · books at ${leg.book_line}`}
      </p>
    </div>
  )
}

export function PrizePicksPairs({ data }: { data?: PrizePicksBoard }) {
  if (!data || data.pairs.length === 0) {
    return (
      <div className="bg-surface rounded-lg border border-hairline p-6 text-center text-sm text-muted">
        No PrizePicks lines matched this week's priced props.
      </div>
    )
  }
  const positive = data.pairs.filter((p) => p.ev > 0)
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted leading-relaxed">
        2-pick Power Play pays {data.payout}x, so two unrelated picks each need {pct(data.breakeven_leg)} to break even.
        Picks from the same game are priced together: a QB and his receiver tend to hit or miss together, which raises the
        chance both land. Picks ESPN's projection disagrees with are left out. {data.positive_ev_pairs} pairs have positive
        expected value; most weeks few or none will, because PrizePicks' lines usually match the books.
      </p>
      {(positive.length ? positive : data.pairs.slice(0, 10)).map((pair) => (
        <div
          key={`${pair.legs[0].player}-${pair.legs[0].market}-${pair.legs[1].player}-${pair.legs[1].market}`}
          className="border border-hairline rounded-lg p-4 bg-surface"
        >
          <div className="flex items-start gap-3">
            <div className={`shrink-0 rounded-md px-2.5 py-1.5 text-center ${pair.units > 0 ? 'bg-success-100 text-success-800' : 'bg-surface-2 text-muted'}`}>
              <div className="stat-nums text-base font-semibold leading-none">{pair.units > 0 ? `${pair.units}u` : '—'}</div>
              <div className="stat-nums text-[9px] tracking-wider uppercase mt-0.5">{pair.units > 0 ? pair.confidence : 'no bet'}</div>
            </div>
            <div className="min-w-0 flex-1 grid gap-3 sm:grid-cols-2">
              <Leg leg={pair.legs[0]} />
              <Leg leg={pair.legs[1]} />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 stat-nums text-xs">
            <span><span className="text-faint">Both hit </span><span className="text-body">{pct(pair.joint_prob)}</span></span>
            <span>
              <span className="text-faint">EV </span>
              <span className={pair.ev > 0 ? 'text-success-700' : 'text-muted'}>{pair.ev > 0 ? '+' : ''}{(pair.ev * 100).toFixed(1)}%</span>
            </span>
            {pair.correlation !== 0 && (
              <span className="text-faint">
                Same game, {pair.correlation > 0 ? 'hit together' : 'pull apart'} (ρ {pair.correlation > 0 ? '+' : ''}{pair.correlation}) · unrelated would be {pct(pair.independent_prob)}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

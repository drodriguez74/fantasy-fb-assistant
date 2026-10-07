// "This week's card": the bets actually worth placing, across player props,
// game lines and PrizePicks, in kickoff order -- what a bettor opens the page
// for. Everything else on the page is the evidence behind it.
import { useState } from 'react'
import { type Board, type BoardRow, SIZE_LABEL, dollars, kickoffLabel, odds } from './betTypes'
import { rankEntries, type EntriesState } from './prizePicksEntriesData'

function pickLabel(row: BoardRow): string {
  if (row.type === 'player_prop') {
    const what = row.market === 'player_anytime_td' ? 'Anytime TD' : `${row.side} ${row.line} ${row.market_label.toLowerCase()}`
    return `${row.player} ${what}`
  }
  if (row.market === 'spread' && row.line != null) {
    return `${row.side} ${row.line > 0 ? `+${row.line}` : row.line === 0 ? 'PK' : row.line}`
  }
  return `${row.game} ${row.side} ${row.line}`
}

function BankrollInput({ bankroll, onChange }: { bankroll: number | null; onChange: (v: number | null) => void }) {
  const [draft, setDraft] = useState(bankroll ? String(bankroll) : '')
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      Bankroll
      <span className="relative">
        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-faint">$</span>
        <input
          type="number"
          min="0"
          inputMode="decimal"
          value={draft}
          placeholder="1000"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => onChange(Number(draft) > 0 ? Number(draft) : null)}
          className="w-24 rounded border-line bg-surface-2 pl-5 pr-2 py-1 text-body stat-nums"
          aria-label="Bankroll in dollars"
        />
      </span>
    </label>
  )
}

export function ThisWeekCard({
  board,
  entries,
  bankroll,
  setBankroll,
  onOpen,
}: {
  board: Board
  entries?: EntriesState
  bankroll: number | null
  setBankroll: (v: number | null) => void
  onOpen: (tab: 'props' | 'games' | 'college' | 'prizepicks') => void
}) {
  const bets = [...(board.player_props ?? []), ...(board.game_props ?? [])]
    .filter((r) => r.units > 0)
    .sort((a, b) => (a.kickoff ?? '').localeCompare(b.kickoff ?? ''))
  const bestEntry = entries ? rankEntries(entries.entries).find((e) => e.ev > 0) : undefined
  const totalUnits = bets.reduce((sum, r) => sum + r.units, 0)

  return (
    <section className="rounded-xl border border-volt bg-surface p-4 sm:p-5" aria-labelledby="this-week-card">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 id="this-week-card" className="font-display font-bold uppercase tracking-tight text-xl text-body">
            This week's card
          </h2>
          <p className="text-xs text-muted mt-0.5">
            {bets.length === 0
              ? 'No bets clear the bar right now.'
              : `${bets.length} bet${bets.length === 1 ? '' : 's'} · ${totalUnits}u${
                  dollars(totalUnits, bankroll) ? ` (${dollars(totalUnits, bankroll)})` : ''
                } total`}
            {board.watch_count ? ` ${board.watch_count} more on the watch list.` : ''}
          </p>
        </div>
        <BankrollInput bankroll={bankroll} onChange={setBankroll} />
      </div>

      {bets.length > 0 && (
        <ul className="mt-4 divide-y divide-hairline">
          {bets.map((r) => (
            <li key={`${r.game}-${r.player ?? ''}-${r.market}`} className="py-2.5 flex items-center gap-3">
              <div className="w-14 shrink-0 text-center">
                <div className="stat-nums text-base font-bold text-body leading-none">{r.units}u</div>
                <div className="stat-nums text-[9px] uppercase tracking-wider text-faint mt-0.5">{SIZE_LABEL[r.confidence]}</div>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-body font-medium truncate">{pickLabel(r)}</p>
                <p className="stat-nums text-[11px] text-muted">
                  {odds(r.price)} at {r.book}
                  {r.min_price != null && ` · still a bet at ${odds(r.min_price)} or better`}
                  {r.type === 'player_prop' || r.market === 'spread' ? ` · ${r.game}` : ''}
                  {kickoffLabel(r.kickoff) && ` · ${kickoffLabel(r.kickoff)}`}
                </p>
              </div>
              {dollars(r.units, bankroll) && (
                <span className="stat-nums text-sm font-semibold text-body shrink-0">{dollars(r.units, bankroll)}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {bestEntry && (
        <button
          onClick={() => onOpen('prizepicks')}
          className="mt-3 w-full text-left rounded-lg border border-hairline px-3 py-2.5 hover:border-volt"
        >
          <p className="text-sm text-body">
            <span className="font-medium">PrizePicks:</span> best entry is a {bestEntry.size}-pick{' '}
            {bestEntry.type === 'power' ? 'Power' : 'Flex'}{' '}
            <span className="stat-nums text-success-700">EV +{(bestEntry.ev * 100).toFixed(1)}%</span>
          </p>
          <p className="text-[11px] text-muted truncate">
            {bestEntry.legs.map((l) => `${l.player} ${l.side} ${l.line}`).join(' · ')}
          </p>
        </button>
      )}

      {!bankroll && bets.length > 0 && (
        <p className="text-[11px] text-faint mt-3">Enter your bankroll to see each bet in dollars (1u = 1% of bankroll).</p>
      )}
    </section>
  )
}

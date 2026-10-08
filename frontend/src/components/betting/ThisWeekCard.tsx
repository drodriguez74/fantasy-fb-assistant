// "This week's card": the bets actually worth placing, across player props,
// game lines and PrizePicks, in kickoff order -- what a bettor opens the page
// for. Everything else on the page is the evidence behind it.
import { useState } from 'react'
import { type Board, type BoardRow, dollars, kickoffLabel, odds } from './betTypes'
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

const whole = (p: number) => `${Math.round(p * 100)}%`

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

const TOP = 5

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
  onOpen: (tab: 'play' | 'prizepicks') => void
}) {
  // Biggest stakes first; the full list lives in the Player props / Game lines tabs.
  const bets = [...(board.player_props ?? []), ...(board.game_props ?? [])]
    .filter((r) => r.units > 0)
    .sort((a, b) => Number(Boolean(a.card_fill)) - Number(Boolean(b.card_fill)) || b.units - a.units)
  const shown = bets.slice(0, TOP)
  const bestEntry = entries ? rankEntries(entries.entries).find((e) => e.ev > 0) : undefined
  const totalUnits = bets.reduce((sum, r) => sum + r.units, 0)
  const fills = bets.filter((r) => r.card_fill).length
  const real = bets.length - fills

  return (
    <section className="rounded-xl border border-hairline bg-surface p-4 sm:p-5" aria-labelledby="this-week-card">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 id="this-week-card" className="font-display font-bold uppercase tracking-tight text-xl text-body">
            This week's best bets
          </h2>
          <p className="text-xs text-muted mt-1">
            {bets.length === 0
              ? 'No lines available right now.'
              : `${real ? `${real} bet${real === 1 ? '' : 's'}` : 'No bets clear the bar'}${
                  fills ? ` + ${fills} best available` : ''
                } · ${totalUnits}u${dollars(totalUnits, bankroll) ? ` (${dollars(totalUnits, bankroll)})` : ''} total`}
            {board.watch_count ? ` · ${board.watch_count} on the watch list` : ''}
          </p>
        </div>
        <BankrollInput bankroll={bankroll} onChange={setBankroll} />
      </div>

      {shown.length > 0 && (
        <ul className="mt-3 divide-y divide-hairline">
          {shown.map((r) => (
            <li key={`${r.game}-${r.player ?? ''}-${r.market}`} className="py-2.5 flex items-center gap-3">
              <div
                className={`w-14 shrink-0 rounded-md py-1 text-center stat-nums ${
                  r.card_fill ? 'border border-volt text-body' : 'bg-volt text-volt-ink'
                }`}
              >
                <div className="text-sm font-bold leading-none">{r.units}u</div>
                <div className="text-xs mt-0.5 leading-none">{dollars(r.units, bankroll) ?? (r.card_fill ? 'fill' : '')}</div>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-body font-medium truncate">{pickLabel(r)}</p>
                <p className="stat-nums text-xs text-muted truncate">
                  {odds(r.price)} at {r.book}
                  {r.type === 'player_prop' || r.market === 'spread' ? ` · ${r.game}` : ''}
                  {kickoffLabel(r.kickoff) && ` · ${kickoffLabel(r.kickoff)}`}
                  {r.card_fill && ' · best available'}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <div className="stat-nums text-xl font-bold text-body leading-none">{whole(r.p_win)}</div>
                <div className="text-xs text-faint mt-1">to win</div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {bets.length > TOP && (
        <button onClick={() => onOpen('play')} className="mt-1 text-xs text-body underline">
          See all {bets.length} bets
        </button>
      )}
      {fills > 0 && (
        <p className="mt-2 text-xs text-muted">
          "Best available" fills the card to 3 when fewer lines clear the bar: a flat 0.5u, not a measured edge, tracked
          separately.
        </p>
      )}

      {bestEntry && (
        <button
          onClick={() => onOpen('prizepicks')}
          className="mt-4 w-full text-left rounded-lg border border-hairline px-3 py-2.5 hover:border-line"
        >
          <p className="text-sm text-body">
            <span className="font-medium">Best PrizePicks entry:</span> {bestEntry.size}-pick{' '}
            {bestEntry.type === 'power' ? 'Power' : 'Flex'}{' '}
            <span className="stat-nums text-success-700">+{(bestEntry.ev * 100).toFixed(1)}% edge</span>
          </p>
          <p className="text-xs text-muted truncate">{bestEntry.legs.map((l) => `${l.player} ${l.side} ${l.line}`).join(' · ')}</p>
        </button>
      )}

      {board.most_likely && board.most_likely.picks.length > 0 && (
        <button
          onClick={() => onOpen('prizepicks')}
          className="mt-3 w-full text-left rounded-lg border border-hairline px-3 py-2.5 hover:border-line"
        >
          <p className="text-sm text-body">
            <span className="font-medium">Safest PrizePicks picks:</span> {board.most_likely.picks.length} at{' '}
            {whole(board.most_likely.min_p_win)}+ to win
          </p>
          <p className="text-xs text-muted truncate">
            {board.most_likely.picks
              .slice(0, 3)
              .map((p) => `${p.player} ${p.side} ${p.line} (${whole(p.p_win)})`)
              .join(' · ')}
          </p>
        </button>
      )}

      {!bankroll && bets.length > 0 && (
        <p className="text-xs text-faint mt-3">Enter your bankroll to see each bet in dollars (1u = 1% of bankroll).</p>
      )}
    </section>
  )
}

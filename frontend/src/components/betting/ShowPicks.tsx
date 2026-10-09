// The Shows tab: picks made on radio shows and podcasts, one section per
// show, graded like ours and compared with what our board said. Tracked
// only -- a show never moves a price (backend/app/services/analyst_picks.py).
import { useState } from 'react'
import { type Show, type ShowPick, type ShowRecord, boardView, lineNote, showPickText } from './showTypes'

const STATUS_STYLE: Record<string, string> = {
  won: 'bg-success-100 text-success-800',
  lost: 'bg-danger-100 text-danger-700',
  pending: 'bg-surface-2 text-muted',
  push: 'bg-surface-2 text-muted',
  void: 'bg-surface-2 text-muted',
}

const recordText = (r: ShowRecord) => {
  const settled = r.won + r.lost
  if (!settled) return r.pending ? `${r.pending} pending` : '—'
  return `${r.won}-${r.lost}${r.push ? `-${r.push}` : ''}`
}

const dateLabel = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })

function PickRow({ p }: { p: ShowPick }) {
  const note = lineNote(p)
  return (
    <li className="py-3 space-y-1">
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_STYLE[p.status]}`}>{p.status}</span>
        <span className="text-sm font-medium text-body break-words">{showPickText(p)}</span>
        {p.conviction === 'lean' && <span className="text-xs text-faint">lean</span>}
      </div>
      <p className="text-xs text-muted">
        {p.analyst}
        {p.segment ? ` · ${p.segment}` : ''}
        {!p.line_stated && ' · no number given; our board line used'}
        {p.actual != null && ` · Final: ${p.actual}`}
      </p>
      {p.quote && <p className="text-xs text-faint italic break-words">"{p.quote}"</p>}
      <p className="stat-nums text-xs text-muted break-words">
        {boardView(p)}
        {note && ` · ${note}`}
      </p>
    </li>
  )
}

function ShowSection({ show, sport }: { show: Show; sport: 'nfl' | 'cfb' }) {
  const [open, setOpen] = useState(true)
  const picks = show.picks.filter((p) => p.sport === sport)
  const episodes = [...new Set(picks.map((p) => p.aired_on))]
  const r = show.record
  const moves = show.line_moves
  const agreed = show.vs_board.agreed
  const disagreed = show.vs_board.disagreed
  return (
    <section className="rounded-lg border border-hairline bg-surface">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="w-full flex items-baseline gap-3 px-4 py-3 text-left">
        <span className="min-w-0">
          <span className="block text-base font-semibold text-body">{show.source}</span>
          <span className="block text-xs text-muted">
            {show.network ? `${show.network} · ` : ''}
            {episodes.length} episode{episodes.length === 1 ? '' : 's'}
          </span>
        </span>
        <span className="ml-auto text-right shrink-0">
          <span className="block stat-nums text-lg font-semibold text-body">{recordText(r)}</span>
          <span className="block text-xs text-faint">bets</span>
        </span>
      </button>
      {open && (
        <div className="border-t border-hairline px-4 pb-2">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 py-3">
            {[
              ['Hit rate', r.hit_rate == null ? '—' : `${Math.round(r.hit_rate * 100)}%`],
              ['Units (1u flat)', r.won + r.lost ? `${r.units > 0 ? '+' : ''}${r.units.toFixed(2)}` : '—'],
              ['Leans', recordText(show.leans)],
              ['Pending', String(r.pending + show.leans.pending)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-hairline p-3">
                <div className="stat-nums text-xs uppercase tracking-wider text-faint">{label}</div>
                <div className="stat-nums text-lg font-semibold text-body mt-1">{value}</div>
              </div>
            ))}
          </div>
          <div className="text-xs text-muted space-y-1 pb-2">
            <p className="stat-nums">
              By host: {show.analysts.map((a) => `${a.analyst} ${recordText(a)}`).join(' · ')}
            </p>
            {agreed.won + agreed.lost + disagreed.won + disagreed.lost > 0 && (
              <p className="stat-nums">
                When our model leaned the same way: {recordText(agreed)} · the other way: {recordText(disagreed)}
              </p>
            )}
            {moves.picks > 0 && (
              <p className="stat-nums">
                Their numbers vs our board's: {moves.toward} better · {moves.away} worse · {moves.unchanged} the same
                (some of that is just a different book).
              </p>
            )}
          </div>
          {episodes.map((day) => (
            <div key={day}>
              <h4 className="text-xs uppercase tracking-wider text-faint pt-2">{dateLabel(day)}</h4>
              <ul className="divide-y divide-hairline">
                {picks
                  .filter((p) => p.aired_on === day)
                  .map((p) => (
                    <PickRow key={p.id} p={p} />
                  ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function ShowPicks({ shows, error, sport }: { shows: Show[] | null; error: string; sport: 'nfl' | 'cfb' }) {
  const mine = (shows ?? []).filter((s) => s.sports.includes(sport))
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted leading-relaxed">
        Picks from radio shows and podcasts, one section per show. They're graded like ours and checked against what our
        board said, but they never change a price: a show earns a say only if its graded record beats the market over a
        few hundred picks. To add an episode, drop its transcript in <code>backend/transcripts/</code> and ask Claude to
        import it.
      </p>
      {error && <p className="text-xs text-warning-700">{error}</p>}
      {!shows && !error && <p className="text-sm text-muted">Loading shows...</p>}
      {shows && mine.length === 0 && (
        <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
          No {sport === 'cfb' ? 'college' : 'NFL'} show picks yet.
        </div>
      )}
      {mine.map((show) => (
        <ShowSection key={show.source} show={show} sport={sport} />
      ))}
    </div>
  )
}

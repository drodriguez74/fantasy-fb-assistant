// The Shows tab: picks made on radio shows and podcasts, one section per
// show. Each upcoming pick gets a verdict -- should you tail it? -- checked
// against the live board and phrased from the show's side. Shows never move
// a price (backend/app/services/analyst_picks.py); their records are tracked
// so a show can earn trust over a real sample.
import type { BoardRow } from './betTypes'
import {
  type Show,
  type ShowPick,
  type ShowRecord,
  type Verdict,
  type VerdictKey,
  VERDICT_ORDER,
  ourReadThen,
  showPickText,
  verdictFor,
} from './showTypes'

// A record means something only past this many graded picks (hit rate hidden until then).
const JUDGE_AT = 20

// Volt only for the two verdicts that mean "act": tail, or bet the other side.
const CHIP: Record<VerdictKey, string> = {
  tail: 'bg-volt text-volt-ink font-semibold',
  fade: 'bg-volt text-volt-ink font-semibold',
  lean: 'border border-line text-body',
  pass: 'border border-hairline text-muted',
  unknown: 'border border-hairline text-faint',
  started: 'border border-hairline text-faint',
  won: 'bg-success-100 text-success-800',
  lost: 'bg-danger-100 text-danger-700',
  push: 'bg-surface-2 text-muted',
}

const dateLabel = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })

const settled = (r: ShowRecord) => r.won + r.lost

function recordLine(r: ShowRecord, what: string) {
  const n = settled(r)
  if (!n) return r.pending ? `${r.pending} ${what} pending.` : null
  const units = `${r.units > 0 ? '+' : ''}${r.units.toFixed(2)}u`
  const rate = n >= JUDGE_AT && r.hit_rate != null ? ` · ${Math.round(r.hit_rate * 100)}%` : ''
  return `${r.won}-${r.lost}${r.push ? `-${r.push}` : ''} on ${what}${rate} · ${units} at 1u each.`
}

function PickRow({ p, v }: { p: ShowPick; v: Verdict }) {
  const graded = ['won', 'lost', 'push'].includes(v.key)
  const then = graded ? ourReadThen(p) : null
  return (
    <li className="py-3 flex gap-3">
      <span className={`w-20 shrink-0 self-start rounded-md px-1.5 py-1 text-center text-xs ${CHIP[v.key]}`}>{v.label}</span>
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-medium text-body break-words">
          {showPickText(p)}
          {p.conviction === 'lean' && <span className="ml-1.5 text-xs font-normal text-faint">their lean</span>}
        </p>
        <p className="text-xs text-muted break-words">
          {v.reason}
          {v.lineNote && ` ${v.lineNote}`}
          {then && ` ${then} before kickoff.`}
        </p>
        <p className="text-xs text-faint break-words">
          {p.analyst}
          {p.segment ? `, ${p.segment}` : ''}, {dateLabel(p.aired_on)}
          {!p.line_stated && ' (no number given; our line used)'}
          {p.quote && <span className="italic">: "{p.quote}"</span>}
        </p>
      </div>
      {v.ours != null && !graded && (
        <div className="shrink-0 text-right">
          <div className="stat-nums text-lg font-bold leading-none text-body">{Math.round(v.ours * 100)}%</div>
          <div className="text-xs text-faint mt-1">our chance</div>
        </div>
      )}
    </li>
  )
}

function ShowSection({ show, picks }: { show: Show; picks: { p: ShowPick; v: Verdict }[] }) {
  const upcoming = picks.filter(({ v }) => !['won', 'lost', 'push'].includes(v.key))
  const graded = picks.filter(({ v }) => ['won', 'lost', 'push'].includes(v.key))
  const n = settled(show.record)
  const bets = recordLine(show.record, 'bets')
  const leans = recordLine(show.leans, 'their leans')
  const agreed = show.vs_board.agreed
  const disagreed = show.vs_board.disagreed
  const moves = show.line_moves
  return (
    <section className="rounded-lg border border-hairline bg-surface">
      <header className="px-4 pt-3 pb-2">
        <h3 className="text-base font-semibold text-body">{show.source}</h3>
        <p className="text-xs text-muted">
          {show.network ? `${show.network}. ` : ''}
          {bets ?? 'No graded bets yet.'}
          {n > 0 && n < JUDGE_AT && ` Too few to judge: ${n} of ${JUDGE_AT} graded.`}
        </p>
        {(leans || settled(agreed) + settled(disagreed) > 0 || moves.picks > 0) && (
          <details className="mt-1 text-xs text-muted">
            <summary className="cursor-pointer text-faint">More on this show</summary>
            <div className="mt-1 space-y-0.5 stat-nums">
              {leans && <p>{leans}</p>}
              {settled(agreed) + settled(disagreed) > 0 && (
                <p>
                  When our model agreed: {agreed.won}-{agreed.lost} · when it disagreed: {disagreed.won}-{disagreed.lost}
                </p>
              )}
              {moves.picks > 0 && (
                <p>
                  Their number vs our board's when imported: {moves.toward} better, {moves.away} worse, {moves.unchanged}{' '}
                  the same (partly just a different book).
                </p>
              )}
              {show.analysts.length > 1 && (
                <p>By host: {show.analysts.map((a) => `${a.analyst} ${a.won}-${a.lost}${a.pending ? ` (${a.pending} pending)` : ''}`).join(', ')}</p>
              )}
            </div>
          </details>
        )}
      </header>
      {upcoming.length > 0 && (
        <ul className="border-t border-hairline divide-y divide-hairline px-4">
          {upcoming.map(({ p, v }) => (
            <PickRow key={p.id} p={p} v={v} />
          ))}
        </ul>
      )}
      {graded.length > 0 && (
        <details className="border-t border-hairline px-4 py-2" open={upcoming.length === 0}>
          <summary className="cursor-pointer text-xs text-muted py-1">Graded ({graded.length})</summary>
          <ul className="divide-y divide-hairline">
            {graded.map(({ p, v }) => (
              <PickRow key={p.id} p={p} v={v} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

export function ShowPicks({
  shows,
  error,
  onRetry,
  sport,
  rows,
}: {
  shows: Show[] | null
  error: string
  onRetry: () => void
  sport: 'nfl' | 'cfb'
  // The live board's lines for this sport: verdicts use today's prices.
  rows: BoardRow[]
}) {
  const sections = (shows ?? [])
    .filter((s) => s.sports.includes(sport))
    .map((show) => {
      const picks = show.picks
        .filter((p) => p.sport === sport)
        .map((p) => ({ p, v: verdictFor(p, rows) }))
        .sort(
          (a, b) =>
            VERDICT_ORDER.indexOf(a.v.key) - VERDICT_ORDER.indexOf(b.v.key) ||
            new Date(a.p.kickoff ?? 0).getTime() - new Date(b.p.kickoff ?? 0).getTime(),
        )
      return { show, picks }
    })
  const open = sections.flatMap((s) => s.picks).filter(({ v }) => !['won', 'lost', 'push', 'started'].includes(v.key))
  const count = (k: VerdictKey) => open.filter(({ v }) => v.key === k).length
  const tails = open.filter(({ v }) => v.key === 'tail' || v.key === 'fade')

  if (error) {
    return (
      <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted flex flex-wrap items-center gap-3">
        <span>Couldn't load the show picks.</span>
        <button onClick={onRetry} className="text-body underline">
          Try again
        </button>
      </div>
    )
  }
  if (!shows) return <p className="text-sm text-muted">Loading show picks...</p>
  if (sections.length === 0) {
    return (
      <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
        No {sport === 'cfb' ? 'college' : 'NFL'} show picks yet. Send Claude a transcript to add an episode.
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-hairline bg-surface p-4">
        <p className="text-sm text-body">
          <span className="font-medium">Should you tail them?</span>{' '}
          {open.length === 0
            ? 'Nothing upcoming right now.'
            : [
                count('tail') && `${count('tail')} to tail`,
                count('fade') && `${count('fade')} to fade`,
                count('lean') && `${count('lean')} lean${count('lean') === 1 ? '' : 's'}`,
                count('pass') && `${count('pass')} to pass`,
                count('unknown') && `${count('unknown')} we can't check`,
              ]
                .filter(Boolean)
                .join(' · ')}
        </p>
        {tails.length > 0 && (
          <p className="text-xs text-muted mt-1">{tails.map(({ p, v }) => `${v.label}: ${showPickText(p)}`).join(' · ')}</p>
        )}
        <p className="text-xs text-faint mt-2">
          Checked against today's prices. Tail only what's also on our card; a show's record carries no weight until it has
          a real sample.
        </p>
      </div>
      {sections.map(({ show, picks }) => (
        <ShowSection key={show.source} show={show} picks={picks} />
      ))}
    </div>
  )
}

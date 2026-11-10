// PrizePicks 2-pick Power Plays from GET /betting/board's `prizepicks`
// section -- backend/app/services/betting_service.py (prizepicks_pairs, and
// price_uploaded_board when the user has uploaded today's board).
import { useDeferredValue, useMemo, useRef, useState, type ReactNode } from 'react'
import { ShowMore } from './ShowMore'
import { betting, getErrorMessage } from '../../services/api'
import { PrizePicksEntries } from './PrizePicksEntries'
import type { EntriesState } from './prizePicksEntriesData'
import { SafestPicks } from './SafestPicks'
import { CorrelatedStacks, type Stack } from './CorrelatedStacks'
import { AddButton, TicketTray } from './TicketTray'
import type { TicketActions } from './ticketTypes'
import type { Ticket } from './useTicket'
import { matchesQuery, type MostLikely } from './betTypes'
import { PlayerSearch } from './PlayerSearch'
import { chance, signedPct } from './format'
import { Explainer } from './ui'
export interface PrizePicksLeg {
  player: string
  team?: string | null
  game?: string
  market: string
  market_label: string
  projection: number | null
  espn_projection?: number | null
  line: number
  side: 'More' | 'Less'
  p_win: number
  model_prob: number | null
  market_prob: number
  book_line: number | null
}

export interface PrizePicksAltLine extends PrizePicksLeg {
  odds_type: 'goblin' | 'demon' | 'discount'
}

// One line of the uploaded board, for search (betting_service.board_lines).
export interface PrizePicksBoardLine extends PrizePicksLeg {
  odds_type: 'standard' | 'goblin' | 'demon' | 'discount'
  espn_agrees?: boolean | null
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
  source: 'upload' | 'odds_api' | null
  // Which pick'em app the uploaded lines came from (a pasted Betr board, or a PrizePicks file).
  platform?: 'betr' | 'prizepicks'
  detail?: string
  uploaded_at?: string
  lines_priced?: number
  lines_unmatched?: number
  goblins?: PrizePicksAltLine[]
  demons?: PrizePicksAltLine[]
  // Betr special lines: discounted, or far from the books' line (payout unknown).
  discounts?: PrizePicksAltLine[]
  stacks?: Stack[]
  board_lines?: PrizePicksBoardLine[]
}



function Leg({ leg }: { leg: PrizePicksLeg }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium text-body">{leg.player}</span>
        <span className="stat-nums text-xs text-faint">{leg.team} · {leg.game}</span>
      </div>
      <p className="text-sm text-body">
        <span className="font-semibold text-body">{leg.side}</span>{' '}
        <span className="stat-nums">{leg.line}</span> <span className="text-muted">{leg.market_label}</span>
      </p>
      <p className="stat-nums text-xs text-faint">
        {chance(leg.p_win)} to hit · books {chance(leg.market_prob)}
        {leg.projection != null && ` · Sleeper ${leg.projection.toFixed(1)}`}
        {leg.espn_projection != null && ` · ESPN ${leg.espn_projection.toFixed(1)}`}
        {leg.book_line != null && leg.book_line !== leg.line && ` · books at ${leg.book_line}`}
      </p>
    </div>
  )
}

function ageLabel(iso?: string) {
  if (!iso) return ''
  const hours = (Date.now() - new Date(iso).getTime()) / 3_600_000
  return hours < 1 ? 'under an hour ago' : `${Math.round(hours)}h ago`
}

const BETR_URL = 'https://picks.betr.app/picks/home/NFL'

function UploadPanel({ data, onUploaded }: { data?: PrizePicksBoard; onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null)
  const shots = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const run = async (send: () => Promise<string>) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await send())
      onUploaded()
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't read that."))
    } finally {
      setBusy(false)
    }
  }
  const paste = () =>
    run(async () => {
      const r = (await betting.pasteBetrBoard(text)).data
      setText('')
      return `Added ${r.added} Betr lines (${r.lines} on the board now). Paste another stat tab to add more.`
    })
  const readShots = (files: File[]) =>
    run(async () => {
      try {
        const r = (await betting.uploadBetrScreenshots(files)).data
        const warn = r.warnings?.length ? ` Note: ${r.warnings.join(' ')}` : ''
        return `Read ${r.cards_read} cards from ${files.length} screenshot${files.length === 1 ? '' : 's'}: added ${r.added} Betr lines (${r.lines} on the board now).${warn}`
      } finally {
        if (shots.current) shots.current.value = ''
      }
    })
  // A screenshot copied to the clipboard (Cmd+Ctrl+Shift+4 on a Mac) pasted into the box.
  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const images = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith('image/'))
    if (images.length) {
      e.preventDefault()
      readShots(images)
    }
  }
  const upload = (file: File) =>
    run(async () => {
      try {
        return `Loaded ${(await betting.uploadPrizePicksBoard(file)).data.lines} PrizePicks lines.`
      } finally {
        if (input.current) input.current.value = ''
      }
    })

  // Boards expire at 36h (prizepicks_board); past 12h lines have likely moved.
  const hours = data?.uploaded_at ? (Date.now() - new Date(data.uploaded_at).getTime()) / 3_600_000 : 0
  const uploaded = data?.source === 'upload'
  const app = data?.platform === 'betr' ? 'Betr' : 'PrizePicks'
  const stale = uploaded && hours >= 12
  return (
    <div className="rounded-lg border border-hairline bg-surface p-4 text-xs text-muted space-y-2">
      {stale && (
        <p className="rounded-md border border-warning-700 px-3 py-2 text-sm text-warning-700">
          This board is {Math.round(hours)} hours old, so {app}'s lines have likely moved. Paste fresh lines before you
          build an entry{hours >= 30 ? `; it stops being used in ${Math.max(0, Math.round(36 - hours))} hours` : ''}.
        </p>
      )}
      <p className="text-sm text-body">
        {uploaded
          ? `Using your ${app} board, updated ${ageLabel(data?.uploaded_at)} (${data?.lines_priced} lines priced${
              data?.lines_unmatched ? `; ${data.lines_unmatched} not on the books' board yet` : ''
            }).`
          : "Using PrizePicks' standard lines from our odds feed. Paste Betr's lines to price your app's board."}
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        onPaste={onPaste}
        placeholder="Paste a screenshot of Betr's board here (or its text)"
        className="w-full rounded-md border border-hairline bg-surface-2 p-2 text-sm text-body placeholder:text-faint"
        aria-label="Pasted Betr board"
      />
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={paste}
          disabled={busy || !text.trim()}
          className="bg-volt text-volt-ink px-3 py-1.5 rounded-lg hover:bg-volt-dark disabled:opacity-50 text-sm"
        >
          {busy ? 'Reading...' : 'Add Betr lines'}
        </button>
        <button
          onClick={() => shots.current?.click()}
          disabled={busy}
          className="border border-line px-3 py-1.5 rounded-lg text-sm text-body disabled:opacity-50"
        >
          Upload screenshots
        </button>
        <input
          ref={shots}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          className="hidden"
          onChange={(e) => e.target.files?.length && readShots(Array.from(e.target.files))}
        />
        <button onClick={() => input.current?.click()} disabled={busy} className="text-xs text-muted underline">
          Upload a PrizePicks file instead
        </button>
        <input
          ref={input}
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
      </div>
      {/* The how-to only matters when there's no board from today; otherwise one tap away. */}
      <details open={!uploaded}>
        <summary className="cursor-pointer text-body underline w-fit">How to add Betr's lines</summary>
        <p className="mt-1">
          Open{' '}
          <a href={BETR_URL} target="_blank" rel="noreferrer" className="text-body underline">
            Betr's NFL page
          </a>{' '}
          and pick a stat tab (Receiving Yds, Passing Yds, Rushing Yds, Receptions...). Screenshot the cards to the
          clipboard (Cmd+Ctrl+Shift+4 on a Mac) and paste into the box, or save screenshots and use Upload screenshots
          (several at once is fine). Each screenshot takes a few seconds to read. Each one is added to the board, and a
          newer line replaces the old one; lines older than 36 hours are dropped. The app never signs into Betr.
        </p>
      </details>
      {message && <p className="text-success-700">{message}</p>}
      {error && <p className="text-warning-700">{error}</p>}
    </div>
  )
}

function Fold({ title, summary, defaultOpen = false, children }: { title: string; summary: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-lg border border-hairline bg-surface">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-baseline gap-3 px-4 py-3 text-left" aria-expanded={open}>
        <span className="text-sm font-medium text-body">{title}</span>
        <span className="text-xs text-faint">{summary}</span>
        <span className="ml-auto text-xs text-muted">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && <div className="px-4 pb-4 space-y-3">{children}</div>}
    </div>
  )
}

function AltLines({ rows, note, ticket }: { rows?: PrizePicksAltLine[]; note: string; ticket?: TicketActions }) {
  if (!rows || rows.length === 0) return null
  return (
    <>
      <p className="text-xs text-faint">{note}</p>
      <ShowMore
        items={rows}
        limit={12}
        className="divide-y divide-hairline"
        noun="more lines"
        render={(r) => (
          <li key={`${r.player}-${r.market}-${r.line}`} className="py-2 flex items-baseline gap-3">
            <span className="stat-nums text-sm font-semibold text-body w-14 shrink-0">{chance(r.p_win)}</span>
            <span className="min-w-0 text-sm text-body">
              {r.player} <span className="text-faint text-xs">{r.team}</span>{' '}
              <span className="text-body font-medium">{r.side}</span>{' '}
              <span className="stat-nums">{r.line}</span> <span className="text-muted">{r.market_label}</span>
            </span>
            <span className="ml-auto stat-nums text-xs text-faint shrink-0 hidden sm:inline">
              {r.projection != null ? `Sleeper ${r.projection.toFixed(1)}` : `books at ${r.book_line ?? '—'}`}
              {r.espn_projection != null && ` · ESPN ${r.espn_projection.toFixed(1)}`}
            </span>
            {ticket && <AddButton active={ticket.has(r)} onClick={() => ticket.toggle(r)} />}
          </li>
        )}
      />
    </>
  )
}

const ODDS_TAG: Record<string, string> = { goblin: 'Goblin', demon: 'Demon', discount: 'Special' }

function SearchResults({ rows, query, ticket }: { rows: PrizePicksBoardLine[]; query: string; ticket: TicketActions }) {
  if (rows.length === 0) {
    return (
      <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">
        No PrizePicks line matches "{query.trim()}" on this board. Lines the books don't quote can't be priced, so they
        aren't here.
      </div>
    )
  }
  return (
    <ShowMore
      items={rows}
      limit={20}
      className="rounded-lg border border-hairline bg-surface divide-y divide-hairline px-4"
      noun="more matches"
      render={(r) => (
        <li key={`${r.player}-${r.market}-${r.line}-${r.odds_type}`} className="py-2.5 flex items-baseline gap-3">
          <span className="stat-nums text-sm font-semibold text-body w-14 shrink-0">{chance(r.p_win)}</span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm text-body">
              {r.player} <span className="text-faint text-xs">{r.team}</span>{' '}
              <span className="text-body font-medium">{r.side}</span> <span className="stat-nums">{r.line}</span>{' '}
              <span className="text-muted">{r.market_label}</span>
              {ODDS_TAG[r.odds_type] && <span className="ml-1.5 text-xs text-faint">{ODDS_TAG[r.odds_type]}</span>}
            </span>
            <span className="block stat-nums text-xs text-faint">
              books {chance(r.market_prob)}
              {r.projection != null && ` · Sleeper ${r.projection.toFixed(1)}`}
              {r.espn_projection != null && ` · ESPN ${r.espn_projection.toFixed(1)}`}
              {r.book_line != null && r.book_line !== r.line && ` · books at ${r.book_line}`}
              {r.espn_agrees === false && ' · ESPN leans the other way'}
            </span>
          </span>
          <AddButton active={ticket.has(r)} onClick={() => ticket.toggle(r)} />
        </li>
      )}
    />
  )
}

function PairCard({ pair }: { pair: PrizePicksPair }) {
  return (
    <div className={`border rounded-lg p-4 bg-surface ${pair.ev > 0 ? 'border-line' : 'border-hairline opacity-70'}`}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Leg leg={pair.legs[0]} />
        <Leg leg={pair.legs[1]} />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 stat-nums text-xs">
        <span><span className="text-body">{chance(pair.joint_prob)}</span> <span className="text-faint">both hit</span></span>
        <span className={pair.ev > 0 ? 'text-success-700' : 'text-muted'}>
          Edge {signedPct(pair.ev)}
        </span>
        {pair.units > 0 && <span className="text-body">{pair.units}u</span>}
        {pair.correlation !== 0 && (
          <span className="text-faint">
            Same game: {pair.correlation > 0 ? 'these tend to hit together' : 'these tend to pull apart'}
          </span>
        )}
      </div>
    </div>
  )
}

/** The PrizePicks tab: board status, safest picks, best entries by size, 2-pick pairs, then goblins/demons. */
export function PrizePicksPairs({
  data,
  onUploaded,
  entries,
  mostLikely,
  ticket,
}: {
  data?: PrizePicksBoard
  onUploaded: () => void
  entries: EntriesState
  mostLikely?: MostLikely
  // Held by the page, so it survives a tab switch.
  ticket: Ticket
}) {
  const positive = data?.pairs.filter((p) => p.ev > 0) ?? []
  const [query, setQuery] = useState('')
  // The box updates at once; a board of 1,000+ lines is filtered when typing pauses.
  const search = useDeferredValue(query)
  const searching = search.trim() !== ''
  // Every priced line of an uploaded board; without an upload, the lines we have.
  const searchable: PrizePicksBoardLine[] = useMemo(
    () =>
      data?.board_lines ?? [
        ...(data?.legs ?? []).map((l) => ({ ...l, odds_type: 'standard' as const })),
        ...(data?.goblins ?? []),
        ...(data?.demons ?? []),
        ...(data?.discounts ?? []),
      ],
    [data],
  )
  const results = useMemo(
    () => (searching ? searchable.filter((l) => matchesQuery(search, l.player, l.team, l.game)) : []),
    [searching, search, searchable],
  )
  return (
    // Room under the page for the collapsed tray bar.
    <div className={`space-y-5 ${ticket.picks.length ? 'pb-16' : ''}`}>
      <UploadPanel data={data} onUploaded={onUploaded} />
      {searchable.length > 0 && (
        <PlayerSearch value={query} onChange={setQuery} count={searching ? results.length : undefined} />
      )}
      {searching ? (
        <SearchResults rows={results} query={search} ticket={ticket} />
      ) : (
        <>
          <CorrelatedStacks stacks={data?.stacks} power={entries.power} ticket={ticket} />
          <PrizePicksEntries state={entries} ticket={ticket} />
          <SafestPicks data={mostLikely} ticket={ticket} />
          {data && data.pairs.length > 0 && (
            <Fold
              title="2-pick pairs"
              summary={positive.length ? `${positive.length} profitable` : 'none profitable this week'}
              defaultOpen={positive.length > 0}
            >
              <Explainer>
                <p>
                  A 2-pick pays {data.payout}x, so each pick needs about {chance(data.breakeven_leg)} to break even. Pairs
                  never use teammates (an entry needs two teams).{' '}
                  {data.platform === 'betr'
                    ? 'On Betr every pick comes from a different game: Betr pays less when two picks share a game (2.8x instead of 3x), so same-game pairs and stacks are left out.'
                    : 'Opponents in the same game are priced together.'}
                </p>
              </Explainer>
              {(positive.length ? positive : data.pairs.slice(0, 5)).map((pair) => (
                <PairCard key={`${pair.legs[0].player}-${pair.legs[0].market}-${pair.legs[1].player}-${pair.legs[1].market}`} pair={pair} />
              ))}
            </Fold>
          )}
          {!data?.pairs.length && data?.detail && (
            <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">{data.detail}</div>
          )}
          {(data?.discounts?.length ?? 0) > 0 && (
            <Fold title="Special lines" summary="discounted or far from the books' line · most likely to hit">
              <AltLines
                ticket={ticket}
                rows={data?.discounts}
                note="Betr discounted these lines, or set them far from the books' line, so they may pay less than a standard pick. Check the multiplier Betr shows before counting on one. They're never used in the pairs or entries above."
              />
            </Fold>
          )}
          {(data?.goblins?.length ?? 0) > 0 && (
            <Fold title="Goblins" summary="easier lines, smaller payout · most likely to hit">
              <AltLines
                ticket={ticket}
                rows={data?.goblins}
                note="The file has no payouts, so compare with PrizePicks' multiplier: two 85% picks hit together about 72% of the time, so that pair needs at least 1.4x."
              />
            </Fold>
          )}
          {(data?.demons?.length ?? 0) > 0 && (
            <Fold title="Demons" summary="harder lines, bigger payout · most likely to hit">
              <AltLines ticket={ticket} rows={data?.demons} note="Compare each hit chance with the multiplier PrizePicks shows." />
            </Fold>
          )}
        </>
      )}
      <TicketTray
        legs={ticket.picks}
        onRemove={ticket.remove}
        onClear={ticket.clear}
        power={entries.power}
        flex={entries.flex}
      />
    </div>
  )
}

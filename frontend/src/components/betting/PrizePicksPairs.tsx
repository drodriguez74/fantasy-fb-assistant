// PrizePicks 2-pick Power Plays from GET /betting/board's `prizepicks`
// section -- backend/app/services/betting_service.py (prizepicks_pairs, and
// price_uploaded_board when the user has uploaded today's board).
import { useRef, useState, type ReactNode } from 'react'
import { betting, getErrorMessage } from '../../services/api'
import { PrizePicksEntries } from './PrizePicksEntries'
import type { EntriesState } from './prizePicksEntriesData'
import { SafestPicks } from './SafestPicks'
import type { MostLikely } from './betTypes'
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
  odds_type: 'goblin' | 'demon'
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
  detail?: string
  uploaded_at?: string
  lines_priced?: number
  lines_unmatched?: number
  goblins?: PrizePicksAltLine[]
  demons?: PrizePicksAltLine[]
}

const BOARD_URL = 'https://api.prizepicks.com/projections?league_id=9&per_page=1000'

const pct = (p: number) => `${(p * 100).toFixed(1)}%`

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
        {pct(leg.p_win)} to hit · books {pct(leg.market_prob)}
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

function UploadPanel({ data, onUploaded }: { data?: PrizePicksBoard; onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const upload = async (file: File) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const response = await betting.uploadPrizePicksBoard(file)
      setMessage(`Loaded ${response.data.lines} NFL lines.`)
      onUploaded()
    } catch (err) {
      setError(getErrorMessage(err, "Couldn't read that file."))
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="rounded-lg border border-hairline bg-surface p-4 text-xs text-muted space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-body">
          {data?.source === 'upload'
            ? `Using your PrizePicks board, uploaded ${ageLabel(data.uploaded_at)} (${data.lines_priced} lines priced).`
            : "Using PrizePicks' standard lines from our odds feed. Upload today's board for goblins, demons and every line."}
        </p>
        <button
          onClick={() => input.current?.click()}
          disabled={busy}
          className="bg-volt text-volt-ink px-3 py-1.5 rounded-lg hover:bg-volt-dark disabled:opacity-50 text-sm"
        >
          {busy ? 'Uploading...' : 'Upload board'}
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
      <details open={data?.source !== 'upload'}>
        <summary className="cursor-pointer text-body underline w-fit">How to upload</summary>
        <p className="mt-1">
          Once a day: open{' '}
          <a href={BOARD_URL} target="_blank" rel="noreferrer" className="text-body underline break-all">
            PrizePicks' NFL board data
          </a>{' '}
          in your browser, press Cmd+S (Ctrl+S on Windows) to save it, then upload the file here. PrizePicks blocks
          automatic downloads, so this step has to come from your browser. Uploads older than 36 hours are ignored.
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

function AltLines({ rows, note }: { rows?: PrizePicksAltLine[]; note: string }) {
  if (!rows || rows.length === 0) return null
  return (
    <>
      <p className="text-xs text-faint">{note}</p>
      <ul className="divide-y divide-hairline">
        {rows.slice(0, 12).map((r) => (
          <li key={`${r.player}-${r.market}-${r.line}`} className="py-2 flex items-baseline gap-3">
            <span className="stat-nums text-sm font-semibold text-body w-14 shrink-0">{pct(r.p_win)}</span>
            <span className="min-w-0 text-sm text-body">
              {r.player} <span className="text-faint text-xs">{r.team}</span>{' '}
              <span className="text-body font-medium">{r.side}</span>{' '}
              <span className="stat-nums">{r.line}</span> <span className="text-muted">{r.market_label}</span>
            </span>
            <span className="ml-auto stat-nums text-xs text-faint shrink-0 hidden sm:inline">
              {r.projection != null ? `Sleeper ${r.projection.toFixed(1)}` : `books at ${r.book_line ?? '—'}`}
              {r.espn_projection != null && ` · ESPN ${r.espn_projection.toFixed(1)}`}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}

function PairCard({ pair }: { pair: PrizePicksPair }) {
  return (
    <div className={`border rounded-lg p-4 bg-surface ${pair.ev > 0 ? 'border-line' : 'border-hairline opacity-80'}`}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Leg leg={pair.legs[0]} />
        <Leg leg={pair.legs[1]} />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 stat-nums text-xs">
        <span><span className="text-body">{pct(pair.joint_prob)}</span> <span className="text-faint">both hit</span></span>
        <span className={pair.ev > 0 ? 'text-success-700' : 'text-muted'}>
          Edge {pair.ev > 0 ? '+' : ''}{(pair.ev * 100).toFixed(1)}%
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
}: {
  data?: PrizePicksBoard
  onUploaded: () => void
  entries: EntriesState
  mostLikely?: MostLikely
}) {
  const positive = data?.pairs.filter((p) => p.ev > 0) ?? []
  return (
    <div className="space-y-5">
      <UploadPanel data={data} onUploaded={onUploaded} />
      <SafestPicks data={mostLikely} />
      <PrizePicksEntries state={entries} />
      {data && data.pairs.length > 0 && (
        <Fold
          title="2-pick pairs"
          summary={positive.length ? `${positive.length} profitable` : 'none profitable this week'}
          defaultOpen={positive.length > 0}
        >
          <p className="text-xs text-muted leading-relaxed">
            A 2-pick Power Play pays {data.payout}x, so each pick needs about {pct(data.breakeven_leg)} to break even. Pairs
            never use teammates (PrizePicks needs two teams); opponents in the same game are priced together.
          </p>
          {(positive.length ? positive : data.pairs.slice(0, 5)).map((pair) => (
            <PairCard key={`${pair.legs[0].player}-${pair.legs[0].market}-${pair.legs[1].player}-${pair.legs[1].market}`} pair={pair} />
          ))}
        </Fold>
      )}
      {!data?.pairs.length && data?.detail && (
        <div className="bg-surface rounded-lg border border-hairline p-4 text-sm text-muted">{data.detail}</div>
      )}
      {(data?.goblins?.length ?? 0) > 0 && (
        <Fold title="Goblins" summary="easier lines, smaller payout · most likely to hit">
          <AltLines
            rows={data?.goblins}
            note="The file has no payouts, so compare with PrizePicks' multiplier: two 85% picks hit together about 72% of the time, so that pair needs at least 1.4x."
          />
        </Fold>
      )}
      {(data?.demons?.length ?? 0) > 0 && (
        <Fold title="Demons" summary="harder lines, bigger payout · most likely to hit">
          <AltLines rows={data?.demons} note="Compare each hit chance with the multiplier PrizePicks shows." />
        </Fold>
      )}
    </div>
  )
}

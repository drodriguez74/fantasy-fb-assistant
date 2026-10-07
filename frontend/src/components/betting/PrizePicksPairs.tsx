// PrizePicks 2-pick Power Plays from GET /betting/board's `prizepicks`
// section -- backend/app/services/betting_service.py (prizepicks_pairs, and
// price_uploaded_board when the user has uploaded today's board).
import { useRef, useState } from 'react'
import { betting, getErrorMessage } from '../../services/api'
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
        <span className={`font-semibold ${leg.side === 'More' ? 'text-success-700' : 'text-accent-ink'}`}>{leg.side}</span>{' '}
        <span className="stat-nums">{leg.line}</span> <span className="text-muted">{leg.market_label}</span>
      </p>
      <p className="stat-nums text-[11px] text-faint">
        Hit {pct(leg.p_win)} · market {pct(leg.market_prob)}
        {leg.model_prob != null && ` · model ${pct(leg.model_prob)}`}
        {leg.projection != null && ` · proj ${leg.projection.toFixed(1)}`}
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
      <p>
        Once a day: open{' '}
        <a href={BOARD_URL} target="_blank" rel="noreferrer" className="text-accent-ink underline break-all">
          PrizePicks' NFL board data
        </a>{' '}
        in your browser, press Cmd+S (Ctrl+S on Windows) to save it, then upload the file here. PrizePicks blocks automatic
        downloads, so this step has to come from your browser. Uploads older than 36 hours are ignored.
      </p>
      {message && <p className="text-success-700">{message}</p>}
      {error && <p className="text-warning-700">{error}</p>}
    </div>
  )
}

function AltLines({ title, note, rows }: { title: string; note: string; rows?: PrizePicksAltLine[] }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className="rounded-lg border border-hairline bg-surface">
      <div className="px-4 pt-3">
        <h4 className="text-sm font-medium text-body">{title}</h4>
        <p className="text-[11px] text-faint mt-0.5">{note}</p>
      </div>
      <ul className="divide-y divide-hairline mt-2">
        {rows.slice(0, 12).map((r) => (
          <li key={`${r.player}-${r.market}-${r.line}`} className="px-4 py-2 flex items-baseline gap-3">
            <span className="stat-nums text-sm font-semibold text-body w-14 shrink-0">{pct(r.p_win)}</span>
            <span className="min-w-0 text-sm text-body">
              {r.player} <span className="text-faint text-xs">{r.team}</span>{' '}
              <span className={r.side === 'More' ? 'text-success-700' : 'text-accent-ink'}>{r.side}</span>{' '}
              <span className="stat-nums">{r.line}</span> <span className="text-muted">{r.market_label}</span>
            </span>
            <span className="ml-auto stat-nums text-[11px] text-faint shrink-0 hidden sm:inline">
              {r.projection != null ? `proj ${r.projection.toFixed(1)}` : `books at ${r.book_line ?? '—'}`}
              {r.espn_projection != null && ` · ESPN ${r.espn_projection.toFixed(1)}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function PrizePicksPairs({ data, onUploaded }: { data?: PrizePicksBoard; onUploaded: () => void }) {
  const positive = data?.pairs.filter((p) => p.ev > 0) ?? []
  return (
    <div className="space-y-3">
      <UploadPanel data={data} onUploaded={onUploaded} />
      {!data || data.pairs.length === 0 ? (
        <div className="bg-surface rounded-lg border border-hairline p-6 text-center text-sm text-muted">
          {data?.detail ?? "No PrizePicks lines matched this week's priced props."}
        </div>
      ) : (
        <>
          <p className="text-xs text-muted leading-relaxed">
            2-pick Power Play pays {data.payout}x, so two unrelated picks each need {pct(data.breakeven_leg)} to break even.
            PrizePicks requires players from two different teams, so pairs never use teammates. Opponents in the same game are
            priced together: a shootout lifts both quarterbacks. Picks ESPN's projection disagrees with are left out.{' '}
            {data.positive_ev_pairs} pairs have positive expected value; most weeks few or none will, because PrizePicks' lines
            usually match the books.
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
                    Same game, {pair.correlation > 0 ? 'tend to hit together' : 'tend to pull apart'} (ρ {pair.correlation > 0 ? '+' : ''}{pair.correlation}) · unrelated would be {pct(pair.independent_prob)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </>
      )}
      <AltLines
        title="Goblins: most likely to hit"
        note="Easier lines with a smaller payout. The file doesn't include payouts, so check PrizePicks' multiplier: two picks at 85% hit together about 72% of the time, so that pair needs to pay at least 1.4x."
        rows={data?.goblins}
      />
      <AltLines
        title="Demons: most likely to hit"
        note="Harder lines with a bigger payout. Compare the hit chance here with the multiplier PrizePicks shows."
        rows={data?.demons}
      />
    </div>
  )
}

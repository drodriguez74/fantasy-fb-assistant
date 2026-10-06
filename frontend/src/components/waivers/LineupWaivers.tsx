import type { ReactNode } from 'react'
import { getPositionColor } from '../players/playerDisplay'
import { PlayerAvatar } from '../players/PlayerAvatar'

// One recommendation from the lineup-impact waiver engine
// (GET /leagues/{id}/waiver-recommendations -> league_advice_service.
// build_waiver_advice), shared by League Detail's Waiver tab and the
// Waivers page so both show the same advice the same way.
export interface LineupWaiverRec {
  player: {
    name: string
    position?: { value?: string }
    projected_points?: number
    week_projection?: number
    team?: string
    ownership_percentage?: number | null
    trending_adds?: number
    espn_player_id?: number | null
  }
  reason?: string
  priority?: number
  // league_value_model: "upgrade" (improves your team for the season),
  // "streamer" (this week only), "watch" (best available at a weak spot,
  // not yet a clear upgrade).
  kind?: 'upgrade' | 'streamer' | 'watch'
  season_gain?: number
  week_gain?: number
  // The roster player this add would replace (best possible drop), with
  // his rest-of-season projection. null when the roster has an open spot.
  drop_candidate?: {
    name: string
    position?: string
    projected_points?: number | null
    position_matched: boolean
  } | null
  value_delta?: number | null
  // Real, priority-aware claim suggestion (ESPN/Yahoo) -- see
  // WaiverWireService.compute_bid_tier. null/undefined when this team's
  // real waiver standing couldn't be determined.
  bid_tier?: {
    bid_type: 'faab' | 'priority'
    suggested_bid?: number
    bid_range?: [number, number]
    budget_remaining?: number
    recommendation?: 'use_claim' | 'hold_priority'
    reasoning?: string
  } | null
}

export interface TeamNeed {
  position: string
  my_starter_avg: number
  league_median: number | null
  rank: number
  teams: number
}

export function WaiverKindBadge({ kind }: { kind: 'upgrade' | 'streamer' | 'watch' }) {
  const styles = {
    upgrade: 'bg-success-100 text-success-800',
    streamer: 'bg-warning-100 text-warning-800',
    watch: 'bg-surface-2 text-muted',
  } as const
  const labels = { upgrade: 'Season upgrade', streamer: 'This week only', watch: 'Watch' } as const
  return <span className={`stat-nums text-[10px] px-1.5 py-0.5 rounded ${styles[kind]}`}>{labels[kind]}</span>
}

// Where this team's starters rank against every team's starters, by
// position (1 = best) -- the needs every waiver/trade call is aimed at.
export function TeamNeedsStrip({ needs }: { needs: TeamNeed[] }) {
  return (
    <div className="bg-surface rounded-lg border border-hairline p-4">
      <div className="stat-nums text-[10px] tracking-wider text-muted mb-3">YOUR STARTERS VS THE LEAGUE</div>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {needs.map((n) => {
          const weak = n.rank > (n.teams * 2) / 3
          const strong = n.rank <= n.teams / 3
          return (
            <div key={n.position} className={`rounded-md border p-2 text-center ${weak ? 'border-danger-200 bg-danger-50' : strong ? 'border-success-200 bg-success-50' : 'border-hairline bg-surface-2'}`}>
              <div className="text-xs font-semibold text-body">{n.position}</div>
              <div className={`stat-nums text-sm font-semibold ${weak ? 'text-danger-700' : strong ? 'text-success-700' : 'text-body'}`}>
                {n.rank}<span className="text-[10px] text-faint">/{n.teams}</span>
              </div>
              <div className="stat-nums text-[10px] text-faint">{n.my_starter_avg.toFixed(0)} vs {n.league_median?.toFixed(0) ?? '—'}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function bidText(bid: NonNullable<LineupWaiverRec['bid_tier']>): string {
  if (bid.bid_type === 'faab') {
    const range = bid.bid_range ? ` (range $${bid.bid_range[0]}–$${bid.bid_range[1]})` : ''
    return `Suggested bid: $${bid.suggested_bid} of $${bid.budget_remaining} FAAB${range}`
  }
  return bid.recommendation === 'use_claim' ? 'Worth using your waiver claim' : 'Hold your waiver priority'
}

// `badges` / `children` let a page add its own per-league context (e.g. the
// Waivers page's competition signal) without forking the card.
export function LineupWaiverCard({
  rec,
  badges,
  children,
}: {
  rec: LineupWaiverRec
  badges?: ReactNode
  children?: ReactNode
}) {
  const position = rec.player.position?.value
  return (
    <div className="border border-hairline rounded-lg p-4 hover:bg-surface-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <PlayerAvatar
            playerId={rec.player.espn_player_id ?? undefined}
            name={rec.player.name}
            position={position}
            team={rec.player.team}
            size={36}
          />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`inline-flex items-center justify-center w-9 h-6 rounded text-[11px] font-semibold ${getPositionColor(position ?? '')}`}>
                {position || '—'}
              </span>
              <h4 className="font-medium text-body">{rec.player.name}</h4>
              {rec.player.team && <span className="stat-nums text-xs text-faint">{rec.player.team}</span>}
              {rec.kind && <WaiverKindBadge kind={rec.kind} />}
              {badges}
            </div>
            <p className="text-sm text-muted mt-2 leading-relaxed">{rec.reason}</p>
            {rec.drop_candidate && rec.kind !== 'watch' && (
              <p className="text-xs text-faint mt-1">
                Drop {rec.drop_candidate.name} ({rec.drop_candidate.position}, {rec.drop_candidate.projected_points?.toFixed(0)} proj)
              </p>
            )}
            {rec.bid_tier && (
              <p className="text-xs text-faint mt-1" title={rec.bid_tier.reasoning}>
                {bidText(rec.bid_tier)}
              </p>
            )}
            {children}
          </div>
        </div>
        {/* Stacks under the text on phones so the reason keeps its width. */}
        <div className="shrink-0 stat-nums flex flex-wrap items-baseline gap-x-3 pl-12 sm:block sm:pl-0 sm:text-right">
          {rec.season_gain != null && rec.kind !== 'streamer' && (
            <div className={`text-sm font-semibold ${rec.season_gain >= 5 ? 'text-success-700' : 'text-muted'}`}>
              {rec.season_gain >= 0 ? '+' : ''}{rec.season_gain.toFixed(1)} season
            </div>
          )}
          {rec.week_gain != null && (rec.kind === 'streamer' || rec.week_gain >= 2) && (
            <div className="text-sm font-semibold text-success-700">+{rec.week_gain.toFixed(1)} this week</div>
          )}
          {rec.player.projected_points != null && (
            <div className="text-xs text-muted">{rec.player.projected_points.toFixed(0)} ROS proj</div>
          )}
          {rec.player.ownership_percentage != null && (
            <div className="text-xs text-faint">{Math.round(rec.player.ownership_percentage)}% owned</div>
          )}
        </div>
      </div>
    </div>
  )
}

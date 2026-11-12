// Small display pieces shared by the Waivers page tabs.
import { ArrowTrendingDownIcon, ArrowTrendingUpIcon, ClockIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { DataConfidenceBadge } from '../../common/DataConfidenceBadge'
import { PlayerAvatar } from '../../players/PlayerAvatar'
import { LineupWaiverCard, TeamNeedsStrip } from '../LineupWaivers'
import { COMPETITION_LABEL, formatTeamNames, COMPETITION_CLASS, type PositionPressure, type StreamingPlayer, type StreamingBoards, type LineupImpact } from './types'

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(4, Math.round(value * 100))
  return (
    <div className="w-full bg-surface-2 rounded-full h-2">
      <div className="bg-accent-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  )
}

// Matchup ratings from matchup_analysis_service.py are on a 0-10 scale
// (5.0 = neutral), not a 0-1 ratio -- share the same bar visual but scale
// against 10 instead of reusing ConfidenceBar directly.
export function MatchupRatingBar({ rating }: { rating: number }) {
  const pct = Math.max(4, Math.min(100, Math.round((rating / 10) * 100)))
  return (
    <div className="w-full bg-surface-2 rounded-full h-2">
      <div className="bg-accent-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  )
}

// See the DefenseStreamingTarget comment above -- the two shapes this app
// renders carry the team abbreviation under different field names.
export function LeagueWaiverList({
  loading,
  error,
  impact,
  position,
  pressure,
}: {
  loading: boolean
  error: string
  impact: LineupImpact | null
  position: string
  pressure: PositionPressure | null
}) {
  if (loading) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
        <p className="text-sm text-muted">Scoring every free agent against your lineup...</p>
      </div>
    )
  }
  if (error || !impact) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
        <p className="text-sm text-muted">{error || 'No waiver advice for this league right now.'}</p>
      </div>
    )
  }
  const recs = position ? impact.recs.filter((r) => r.player.position?.value === position) : impact.recs
  return (
    <div className="space-y-4">
      {impact.teamNeeds.length > 0 && <TeamNeedsStrip needs={impact.teamNeeds} />}
      <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="text-base font-medium text-body">
              {impact.watchOnly ? 'No clear upgrade for your lineup yet' : 'Best adds for your lineup'}
            </h3>
            {impact.watchOnly && (
              <p className="text-xs text-muted mt-0.5">Best available at your weakest spots, worth watching.</p>
            )}
          </div>
          <DataConfidenceBadge level="computed" label="Lineup impact" />
        </div>
        {recs.length === 0 ? (
          <p className="text-sm text-muted">
            {position ? `No ${position} on the wire improves your team right now.` : 'Nothing on the wire improves your team right now.'}
          </p>
        ) : (
          <div className="space-y-3">
            {recs.map((rec) => {
              const pos = rec.player.position?.value || ''
              const competition = pressure?.supported ? pressure.position_pressure?.[pos] : undefined
              const thin = competition && (competition.this_week.teams_in_need > 0 || competition.season.teams_in_need > 0)
              return (
                <LineupWaiverCard
                  key={rec.player.name}
                  rec={rec}
                  badges={
                    competition && rec.kind !== 'watch' ? (
                      <span
                        className={`stat-nums text-[10px] px-1.5 py-0.5 rounded ${COMPETITION_CLASS[competition.level]}`}
                        title={`${competition.season.teams_in_need} of ${competition.season.total_teams} other teams look thin at ${pos} all season`}
                      >
                        {COMPETITION_LABEL[competition.level]}
                      </span>
                    ) : undefined
                  }
                >
                  {thin && rec.kind !== 'watch' && (
                    <p className="text-xs text-faint mt-1">
                      {competition.this_week.teams_in_need > 0
                        ? <>Also short at {pos} this week: <span className="text-body">{formatTeamNames(competition.this_week.team_names)}</span>. </>
                        : null}
                      {competition.season.teams_in_need > 0
                        ? <>Thin at {pos} all season: <span className="text-body">{formatTeamNames(competition.season.team_names)}</span>.</>
                        : null}
                    </p>
                  )}
                </LineupWaiverCard>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// Vegas context line for a DEF/K: who they play and the implied total that
// matters (opponent's for a defense, own team's for a kicker), colored by
// whether it helps.
export function VegasLine({ vegas, position }: { vegas: StreamingPlayer['vegas']; position: string }) {
  if (!vegas) return null
  const n = vegas.key_number
  const good = position === 'DEF' ? n <= 19 : n >= 25
  const bad = position === 'DEF' ? n >= 24 : n <= 19
  const label = position === 'DEF' ? `${vegas.opponent} implied` : 'team implied'
  return (
    <span className="stat-nums text-[11px] text-faint">
      {vegas.home ? 'vs' : '@'} {vegas.opponent} ·{' '}
      <span className={good ? 'text-success-700' : bad ? 'text-danger-700' : 'text-muted'}>
        {label} {n.toFixed(1)}
      </span>
    </span>
  )
}

// This week's DEF/K streaming menu for the selected league: the user's own
// starter, then the best free agents by this week's real projection.
export function StreamingBoardsView({ data, loading, error }: { data: StreamingBoards | null; loading: boolean; error: string }) {
  if (loading) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
        <p className="text-sm text-muted">Projecting this week's defenses and kickers...</p>
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
        <p className="text-sm text-muted">{error || 'No streaming data for this league right now.'}</p>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        Week {data.current_week ?? '?'} projections ({data.projection_source}). Edge = their projection minus your starter's.
        {data.odds_source
          ? ` Implied totals: ${data.odds_source} -- for a defense, lower opponent points is better; for a kicker, higher team points.`
          : ''}
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {data.boards.map((board) => {
          const label = board.position === 'DEF' ? 'Defense' : 'Kicker'
          const best = board.options[0]
          return (
            <div key={board.position} className="bg-surface rounded-lg border border-hairline p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3 mb-3">
                <h3 className="text-base font-medium text-body">{label} — this week</h3>
                <DataConfidenceBadge level="computed" label="Your league" />
              </div>
              <div className="flex items-center justify-between gap-3 rounded-md bg-surface-2 px-3 py-2 mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="stat-nums text-[10px] tracking-wider text-muted">YOURS</span>
                  <div className="min-w-0">
                    <div className="text-sm text-body truncate">{board.current?.name ?? `No healthy ${label.toLowerCase()}`}</div>
                    {board.current && <VegasLine vegas={board.current.vegas} position={board.position} />}
                  </div>
                </div>
                <span className="stat-nums text-sm text-body">
                  {board.current ? (board.current.week_projection ?? 0).toFixed(1) : '—'}
                  {board.current && (board.current.week_projection ?? 0) === 0 && <span className="text-xs text-danger-700"> bye/out</span>}
                </span>
              </div>
              <p className="text-xs text-muted mb-2">
                {best && best.week_edge >= 2
                  ? `Stream ${best.player.name}: +${best.week_edge.toFixed(1)} over yours this week.`
                  : best && best.week_edge > 0
                    ? 'Marginal edges only -- keeping yours is fine.'
                    : 'Keep yours -- nothing on the wire projects higher this week.'}
              </p>
              <div className="divide-y divide-hairline">
                {board.options.map(({ player, week_edge }) => (
                  <div key={player.name} className="flex items-center justify-between gap-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <PlayerAvatar
                        playerId={player.espn_player_id ?? undefined}
                        name={player.name}
                        position={board.position}
                        team={player.team}
                        size={28}
                      />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-sm text-body truncate">{player.name}</span>
                          {player.ownership_percentage != null && (
                            <span className="stat-nums text-[10px] text-faint shrink-0">{Math.round(player.ownership_percentage)}%</span>
                          )}
                        </div>
                        <VegasLine vegas={player.vegas} position={board.position} />
                      </div>
                    </div>
                    <div className="stat-nums text-sm shrink-0 text-right">
                      <span className="text-body">{(player.week_projection ?? 0).toFixed(1)}</span>
                      <span className={`ml-3 inline-block w-12 font-semibold ${week_edge >= 2 ? 'text-success-700' : week_edge > 0 ? 'text-body' : 'text-muted'}`}>
                        {week_edge > 0 ? '+' : ''}{week_edge.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function TrendIcon({ direction }: { direction: string }) {
  switch (direction) {
    case 'up':
      return <ArrowTrendingUpIcon className="h-4 w-4 text-success-600" />
    case 'down':
      return <ArrowTrendingDownIcon className="h-4 w-4 text-danger-600" />
    default:
      return <div className="h-4 w-4 bg-faint rounded-full" />
  }
}

import type { Dispatch, SetStateAction } from 'react'
import { ClockIcon, MagnifyingGlassIcon, ShieldCheckIcon } from '@heroicons/react/24/outline'
import { DataConfidenceBadge } from '../../common/DataConfidenceBadge'
import { getPositionColor } from '../../players/playerDisplay'
import { PlayerAvatar } from '../../players/PlayerAvatar'
import { ConfidenceBar, LeagueWaiverList, TrendIcon } from './parts'
import { COMPETITION_LABEL, formatTeamNames, COMPETITION_CLASS, getAddCount, getPriorityBadgeColor, type WaiverRecommendation, type ConnectedLeagueOption, type WaiverPosition, type PositionPressure, type LineupImpact } from './types'

interface RecommendationsTabProps {
  recommendations: WaiverRecommendation[]
  loading: boolean
  selectedPosition: string
  setSelectedPosition: Dispatch<SetStateAction<string>>
  selectedPriority: string
  setSelectedPriority: Dispatch<SetStateAction<string>>
  connectedLeagues: ConnectedLeagueOption[]
  selectedLeagueId: number | ''
  selectLeague: (id: number | '') => void
  waiverPosition: WaiverPosition | null
  positionPressure: PositionPressure | null
  lineupImpact: LineupImpact | null
  lineupLoading: boolean
  lineupError: string
}

export function RecommendationsTab({ recommendations, loading, selectedPosition, setSelectedPosition, selectedPriority, setSelectedPriority, connectedLeagues, selectedLeagueId, selectLeague, waiverPosition, positionPressure, lineupImpact, lineupLoading, lineupError }: RecommendationsTabProps) {
  return (
      <div className="space-y-6">
        {/* Filters */}
        <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-4">Recommended claims</h3>
          <div className="flex flex-wrap gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-body mb-1">Position</label>
              <select
                value={selectedPosition}
                onChange={(e) => setSelectedPosition(e.target.value)}
                className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
              >
                <option value="">All Positions</option>
                <option value="QB">Quarterback</option>
                <option value="RB">Running Back</option>
                <option value="WR">Wide Receiver</option>
                <option value="TE">Tight End</option>
                {selectedLeagueId !== '' && <option value="K">Kicker</option>}
                {selectedLeagueId !== '' && <option value="DEF">Defense</option>}
              </select>
            </div>
            {selectedLeagueId === '' && (
            <div>
              <label className="block text-sm font-medium text-body mb-1">Priority</label>
              <select
                value={selectedPriority}
                onChange={(e) => setSelectedPriority(e.target.value)}
                className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
              >
                <option value="">All Priorities</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="watch">Watch</option>
              </select>
            </div>
            )}
            <div>
              <label className="block text-sm font-medium text-body mb-1">League</label>
              <select
                value={selectedLeagueId}
                onChange={(e) => selectLeague(e.target.value ? parseInt(e.target.value) : '')}
                className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
              >
                <option value="">No league (league-wide trending)</option>
                {connectedLeagues.map((league) => (
                  <option key={league.id} value={league.id}>
                    {league.league_name || `${league.platform} League`}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="text-xs text-muted">
            {selectedLeagueId !== ''
              ? lineupImpact?.basis || 'Every free agent in your league, scored by what he adds to your best starting lineup.'
              : connectedLeagues.length > 0
                ? "League-wide Sleeper trending adds, not checked against your roster. Pick a league for advice built on your lineup."
                : "League-wide Sleeper trending adds. Connect a league to get advice built on your own lineup."}
          </p>
        </div>

        {/* Waiver position -- real FAAB balance or priority rank for the
            selected league, so a recommendation can be read against
            whether a claim is actually realistic. */}
        {selectedLeagueId !== '' && waiverPosition?.supported && (
          <div className="flex flex-wrap items-center gap-3 bg-surface-2 border border-hairline rounded-lg px-4 py-3">
            <ShieldCheckIcon className="h-5 w-5 text-accent-ink shrink-0" />
            {waiverPosition.waiver_type === 'faab' ? (
              <p className="text-sm text-body">
                <span className="font-semibold">${waiverPosition.budget_remaining}</span> of ${waiverPosition.total_budget} FAAB remaining
                {typeof waiverPosition.budget_spent === 'number' && (
                  <span className="text-muted"> &mdash; ${waiverPosition.budget_spent} spent this season</span>
                )}
              </p>
            ) : (
              <p className="text-sm text-body">
                Waiver priority: <span className="font-semibold">#{waiverPosition.waiver_rank}</span> of {waiverPosition.total_teams}
                <span className="text-muted"> &mdash; moves to the back after you win a claim</span>
              </p>
            )}
            <DataConfidenceBadge level="computed" label="Your league" />
          </div>
        )}
        {selectedLeagueId !== '' && waiverPosition && !waiverPosition.supported && (
          <p className="text-xs text-faint">{waiverPosition.detail}</p>
        )}

        {selectedLeagueId !== '' && (
          <LeagueWaiverList
            loading={lineupLoading}
            error={lineupError}
            impact={lineupImpact}
            position={selectedPosition}
            pressure={positionPressure}
          />
        )}

        {/* League-wide trending list (no league selected) */}
        {selectedLeagueId !== '' ? null : loading ? (
          <div className="bg-surface rounded-lg shadow p-6 text-center">
            <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
            <p className="text-sm text-muted">Scoring the wire...</p>
          </div>
        ) : recommendations.length === 0 ? (
          <div className="bg-surface rounded-lg shadow p-6 text-center">
            <MagnifyingGlassIcon className="mx-auto h-12 w-12 text-faint" />
            <h3 className="mt-2 text-sm font-medium text-body">Nothing worth claiming right now</h3>
            <p className="mt-1 text-sm text-muted">
              Try adjusting your filters or refresh the recommendations.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {recommendations.map((rec) => {
              const addCount = getAddCount(rec)
              const competition = positionPressure?.supported
                ? positionPressure.position_pressure?.[rec.position]
                : undefined
              return (
                <div key={rec.player_id} className="bg-surface rounded-lg shadow p-4 sm:p-6 border-l-2 border-l-transparent hover:border-l-volt transition-colors">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-3 mb-2">
                        <PlayerAvatar
                          playerId={rec.espn_player_id}
                          name={rec.player_name}
                          position={rec.position}
                          team={rec.team}
                          size={40}
                        />
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h4 className="text-lg font-medium text-body">{rec.player_name}</h4>
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(rec.position)}`}>
                              {rec.position}
                            </span>
                            <span className="text-sm text-muted">{rec.team}</span>
                            {rec.on_bye_this_week && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-danger-100 text-danger-800">
                                BYE this week
                              </span>
                            )}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPriorityBadgeColor(rec.priority)}`}>
                              {rec.priority.toUpperCase()}
                            </span>
                            {rec.rank != null && rec.total_candidates != null && (
                              <span className="stat-nums text-[11px] text-faint" title="This player's rank in today's real Sleeper trending-add pool, after filtering to actual free agents in your league">
                                #{rec.rank} of {rec.total_candidates} trending
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        {rec.roster_need === 'needs_attention' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success-100 text-success-800">
                            Fills a roster need
                          </span>
                        )}
                        {rec.roster_need === 'overstocked' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-2 text-muted">
                            Position already deep
                          </span>
                        )}
                        {rec.bye_week_flag && !rec.on_bye_this_week && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-danger-100 text-danger-800">
                            On bye Week {rec.bye_week}
                          </span>
                        )}
                        {rec.pass_catcher_boost && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink">
                            PPR target-share edge
                          </span>
                        )}
                        {competition && (
                          <span
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${COMPETITION_CLASS[competition.level]}`}
                            title={`${competition.season.teams_in_need} of ${competition.season.total_teams} other teams look thin at ${rec.position} all season`}
                          >
                            {COMPETITION_LABEL[competition.level]}
                          </span>
                        )}
                      </div>

                      <p className="text-sm text-muted mb-3">{rec.reason}</p>
                      {competition && (competition.this_week.teams_in_need > 0 || competition.season.teams_in_need > 0) && (
                        <p className="text-xs text-faint mb-3">
                          {competition.this_week.teams_in_need > 0 && (
                            <>
                              Likely in the market <em>this week</em>:{' '}
                              <span className="text-body font-medium">{formatTeamNames(competition.this_week.team_names)}</span>
                              {' '}(starting {rec.position} out/bye, no healthy bench cover).{' '}
                            </>
                          )}
                          {competition.season.teams_in_need > 0 && (
                            <>
                              Thin at {rec.position} all season:{' '}
                              <span className="text-body font-medium">{formatTeamNames(competition.season.team_names)}</span>.
                            </>
                          )}
                        </p>
                      )}
                      {rec.league_scoring_context?.scoring_format && (
                        <p className="text-xs text-faint mb-3">
                          League scoring: {rec.league_scoring_context.scoring_format}
                          {rec.league_scoring_context.points_per_reception != null &&
                            ` (${rec.league_scoring_context.points_per_reception} pts/reception)`}
                          {' '}-- shown for context, not the primary ranking signal.
                        </p>
                      )}
                      {rec.bid_tier && (
                        <div className="flex flex-wrap items-center gap-2 mb-3">
                          {rec.bid_tier.bid_type === 'faab' ? (
                            <span
                              className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink"
                              title={
                                rec.bid_tier.bid_range
                                  ? `Suggested range: $${rec.bid_tier.bid_range[0]}-$${rec.bid_tier.bid_range[1]} of your real $${rec.bid_tier.budget_remaining} remaining FAAB`
                                  : rec.bid_tier.note
                              }
                            >
                              Suggested bid: ${rec.bid_tier.suggested_bid}
                            </span>
                          ) : (
                            <span
                              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                rec.bid_tier.recommendation === 'use_claim'
                                  ? 'bg-highlight text-accent-ink'
                                  : 'bg-surface-2 text-muted'
                              }`}
                              title={rec.bid_tier.reasoning}
                            >
                              {rec.bid_tier.recommendation === 'use_claim' ? 'Use your claim' : 'Hold priority'}
                            </span>
                          )}
                        </div>
                      )}

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-4">
                        <div>
                          <span className="block text-xs text-muted">Season Proj (ESPN)</span>
                          <span className="font-stat tabular-nums">
                            {rec.projected_points != null ? rec.projected_points.toFixed(1) : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="block text-xs text-muted">Owned</span>
                          <span className="font-stat tabular-nums">
                            {rec.ownership_percentage != null ? `${rec.ownership_percentage.toFixed(1)}%` : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="block text-xs text-muted">24h Adds</span>
                          <span className="font-stat tabular-nums">
                            {addCount != null ? addCount.toLocaleString() : 'N/A'}
                          </span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-xs text-muted">Trend</span>
                          <span className="flex items-center gap-1">
                            <TrendIcon direction={rec.trend_direction} />
                            <span>{rec.trend_direction}</span>
                          </span>
                        </div>
                      </div>

                      <div className="max-w-sm">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-body">Confidence</span>
                          <DataConfidenceBadge level="computed" />
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="flex-1">
                            <ConfidenceBar value={rec.confidence_score} />
                          </div>
                          <span className="text-sm font-stat tabular-nums text-body font-medium w-10 text-right">
                            {(rec.confidence_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    </div>

                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
  )
}

import type { Dispatch, SetStateAction } from 'react'
import { ClockIcon, ExclamationTriangleIcon, NoSymbolIcon, ShieldCheckIcon } from '@heroicons/react/24/outline'
import { DataConfidenceBadge } from '../../common/DataConfidenceBadge'
import { MatchupRatingBar } from './parts'
import { getTeamAbbr, getPriorityBadgeColor, type DefenseStreamingRecommendations, type PositionOutlook } from './types'

interface LeagueWideStreamingTabProps {
  currentWeek: number
  streamingCurrentDefense: string
  setStreamingCurrentDefense: Dispatch<SetStateAction<string>>
  streamingData: DefenseStreamingRecommendations | null
  kickerOutlook: PositionOutlook | null
  streamingLoading: boolean
  streamingError: string
  loadStreamingTargets: () => Promise<void>
}

export function LeagueWideStreamingTab({ currentWeek, streamingCurrentDefense, setStreamingCurrentDefense, streamingData, kickerOutlook, streamingLoading, streamingError, loadStreamingTargets }: LeagueWideStreamingTabProps) {
  return (
      <div className="space-y-6">
        <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-1">Defense Streaming Targets — Week {currentWeek}</h3>
          <p className="text-sm text-muted mb-4">
            Ranked by how tough this week's matchup is, not by name recognition — the defenses opposing teams
            have historically struggled to move the ball against.
          </p>
          <div className="flex items-end space-x-4 mb-2">
            <div>
              <label className="block text-sm font-medium text-body mb-1">Your current DEF (optional)</label>
              <input
                type="text"
                value={streamingCurrentDefense}
                onChange={(e) => setStreamingCurrentDefense(e.target.value.toUpperCase())}
                placeholder="e.g. NYJ"
                maxLength={4}
                className="block w-32 rounded-md border-line focus:border-accent-ink focus:ring-volt uppercase"
              />
            </div>
            <button
              onClick={loadStreamingTargets}
              disabled={streamingLoading}
              className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark disabled:opacity-50 flex items-center space-x-2"
            >
              <ShieldCheckIcon className="h-4 w-4" />
              <span>{streamingCurrentDefense ? 'Compare to my DEF' : 'Refresh'}</span>
            </button>
          </div>
        </div>

        {streamingError && (
          <div className="bg-danger-50 border border-danger-200 rounded-md p-4">
            <div className="flex">
              <ExclamationTriangleIcon className="h-5 w-5 text-danger-400" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-danger-800">Error</h3>
                <div className="mt-2 text-sm text-danger-700">{streamingError}</div>
              </div>
            </div>
          </div>
        )}

        {streamingLoading ? (
          <div className="bg-surface rounded-lg shadow p-6 text-center">
            <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
            <p className="text-sm text-muted">Loading matchup data...</p>
          </div>
        ) : !streamingError && (streamingData?.error || (!streamingData?.streaming_recommendations?.length && !streamingData?.defenses_to_avoid?.length)) ? (
          <div className="bg-surface rounded-lg shadow p-6 text-center">
            <DataConfidenceBadge level="insufficient" className="mb-3" />
            <h3 className="mt-1 text-sm font-medium text-body">No defensive matchup data for Week {currentWeek} yet</h3>
            <p className="mt-1 text-sm text-muted max-w-md mx-auto">
              This week's defensive rankings haven't been computed yet. Check back closer to kickoff, or try
              an earlier week that's already been played.
            </p>
          </div>
        ) : (
          <>
            {!!streamingData?.streaming_recommendations?.length && (
              <div className="space-y-4">
                {streamingData.streaming_recommendations.map((target) => (
                  <div key={getTeamAbbr(target)} className="bg-surface rounded-lg shadow p-4 sm:p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2 flex-wrap gap-y-1">
                          <h4 className="text-lg font-medium text-body">
                            {target.team_name || `${getTeamAbbr(target)} Defense`}
                          </h4>
                          <span className="text-sm text-muted">
                            {(target.is_home_game ?? target.is_home) ? 'vs' : '@'} {target.opponent || 'TBD'}
                          </span>
                          {target.waiver_priority && (
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPriorityBadgeColor(target.waiver_priority.toLowerCase())}`}>
                              {target.waiver_priority.toUpperCase()} PRIORITY
                            </span>
                          )}
                          {target.availability_tier && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-2 text-muted">
                              {target.availability_tier}
                            </span>
                          )}
                        </div>

                        {!!target.key_factors?.length && (
                          <div className="flex flex-wrap gap-2 mb-3">
                            {target.key_factors.map((factor, idx) => (
                              <span key={idx} className="text-xs bg-surface-2 text-muted px-2 py-1 rounded">
                                {factor}
                              </span>
                            ))}
                          </div>
                        )}

                        <div className="max-w-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-body">Matchup Rating</span>
                            <DataConfidenceBadge level="heuristic" label="Composite rating" />
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="flex-1">
                              <MatchupRatingBar rating={target.matchup_rating} />
                            </div>
                            <span className="text-sm font-stat tabular-nums text-body font-medium w-12 text-right">
                              {target.matchup_rating.toFixed(1)}/10
                            </span>
                          </div>
                          {(target.avg_points_allowed != null || target.recent_trend != null) && (
                            <p className="mt-1 text-xs text-muted">
                              {target.avg_points_allowed != null && `${target.avg_points_allowed.toFixed(1)} pts allowed (season avg)`}
                              {target.avg_points_allowed != null && target.recent_trend != null && ' · '}
                              {target.recent_trend != null && `${target.recent_trend.toFixed(1)} last 4 wks`}
                            </p>
                          )}
                          {!!streamingData?.current_defense && target.improvement_over_current != null && (
                            <p className="mt-1 text-xs text-success-700 font-medium">
                              +{target.improvement_over_current.toFixed(1)} better than your current DEF
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!!streamingData?.defenses_to_avoid?.length && (
              <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
                <h4 className="font-medium text-body mb-3 flex items-center space-x-2">
                  <NoSymbolIcon className="h-5 w-5 text-danger-500" />
                  <span>Defenses to Avoid This Week</span>
                </h4>
                <div className="space-y-3">
                  {streamingData.defenses_to_avoid.map((target) => (
                    <div key={getTeamAbbr(target)} className="border border-danger-200 bg-danger-50 rounded p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-body">
                          {target.team_name || `${getTeamAbbr(target)} Defense`}
                          <span className="ml-2 text-sm font-normal text-muted">
                            {(target.is_home_game ?? target.is_home) ? 'vs' : '@'} {target.opponent || 'TBD'}
                          </span>
                        </span>
                        <span className="text-xs font-stat tabular-nums text-danger-700 font-medium">
                          {target.matchup_rating.toFixed(1)}/10
                        </span>
                      </div>
                      {target.recommendation && <p className="text-sm text-muted">{target.recommendation}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Kicker matchup outlook -- smaller secondary section, same data source */}
        <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
          <h4 className="font-medium text-body mb-1">Kicker Matchup Outlook</h4>
          <p className="text-sm text-muted mb-4">Best and worst upcoming matchups for streaming a kicker.</p>
          {!kickerOutlook || kickerOutlook.error || !Object.keys(kickerOutlook.weekly_outlook || {}).length ? (
            <div className="text-center py-4">
              <DataConfidenceBadge level="insufficient" />
              <p className="mt-2 text-sm text-muted">No kicker matchup data available yet for the upcoming weeks.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(kickerOutlook.weekly_outlook).map(([week, outlook]) => (
                <div key={week} className="border border-hairline rounded p-3">
                  <div className="text-sm font-medium text-body mb-2">Week {week}</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-xs uppercase text-muted">Best matchups</span>
                      <ul className="mt-1 space-y-1">
                        {outlook.best_matchups.map((m) => (
                          <li key={m.team} className="flex justify-between text-body">
                            <span>{m.team}</span>
                            <span className="font-stat tabular-nums text-success-700">{m.rating.toFixed(1)}/10</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <span className="text-xs uppercase text-muted">Worst matchups</span>
                      <ul className="mt-1 space-y-1">
                        {outlook.worst_matchups.map((m) => (
                          <li key={m.team} className="flex justify-between text-body">
                            <span>{m.team}</span>
                            <span className="font-stat tabular-nums text-danger-700">{m.rating.toFixed(1)}/10</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
  )
}

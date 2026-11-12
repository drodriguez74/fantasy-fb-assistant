import { CalendarDaysIcon, CheckCircleIcon, ClockIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { DataConfidenceBadge } from '../../common/DataConfidenceBadge'
import { PlayerAvatar } from '../../players/PlayerAvatar'
import { injuryTag } from '../../players/playerDisplay'
import { getGradeColor } from './display'
import { type RosterAnalysis, type ByeWeekRadarData } from './types'

interface RosterTabProps {
  rosterAnalysis: RosterAnalysis
  byeWeekRadar: ByeWeekRadarData | null
  byeWeekRadarLoading: boolean
  byeWeekRadarError: string
}

export function RosterTab({ rosterAnalysis, byeWeekRadar, byeWeekRadarLoading, byeWeekRadarError }: RosterTabProps) {
  return (
      <div className="space-y-6">
        {/* Roster Summary */}
        <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-medium text-body">Roster Analysis</h3>
              <p className="text-sm text-muted">
                {rosterAnalysis.team_name} • {rosterAnalysis.total_players} players
              </p>
            </div>
            <span className="inline-flex items-center gap-2">
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getGradeColor(rosterAnalysis.overall_grade?.grade || 'N/A')}`}>
                Grade: {rosterAnalysis.overall_grade?.grade || 'N/A'}
              </span>
              <DataConfidenceBadge level={rosterAnalysis.overall_grade?.grade && rosterAnalysis.overall_grade.grade !== 'N/A' ? 'computed' : 'insufficient'} />
            </span>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium text-success-700 mb-2">Strengths</h4>
              <ul className="space-y-1">
                {(rosterAnalysis.strengths_weaknesses?.strengths || rosterAnalysis.strengths || []).map((strength: string, index: number) => (
                  <li key={`strength-${index}-${strength.slice(0, 20)}`} className="text-sm text-muted flex items-start space-x-2">
                    <CheckCircleIcon className="h-4 w-4 text-success-500 mt-0.5" />
                    <span>{strength}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-danger-700 mb-2">Weaknesses</h4>
              <ul className="space-y-1">
                {(rosterAnalysis.strengths_weaknesses?.weaknesses || rosterAnalysis.weaknesses || []).map((weakness: string, index: number) => (
                  <li key={`weakness-${index}-${weakness.slice(0, 20)}`} className="text-sm text-muted flex items-start space-x-2">
                    <ExclamationTriangleIcon className="h-4 w-4 text-danger-500 mt-0.5" />
                    <span>{weakness}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Current Roster */}
        <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-4">Current Roster</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium text-accent-ink mb-2">Starting Lineup</h4>
              <div className="space-y-2">
                {(rosterAnalysis.composition?.starting_lineup || []).map((player, index: number) => (
                  <div key={`starter-${player.name}-${index}`} className="flex items-center justify-between gap-2 p-2 bg-highlight rounded">
                    <div className="flex items-center gap-2 min-w-0">
                      <PlayerAvatar playerId={player.player_id} name={player.name} position={player.position} team={player.team} size={28} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-body truncate">
                          {player.name}
                          {injuryTag(player.injury_status) && (
                            <span className={`ml-1.5 text-[10px] px-1 py-px rounded font-medium ${injuryTag(player.injury_status)!.className}`}>
                              {injuryTag(player.injury_status)!.label}
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-muted">{player.position} • {player.team}</p>
                      </div>
                    </div>
                    <span className="shrink-0 text-xs text-accent-ink">{player.total_points || 0} pts</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-medium text-body mb-2">Bench Players</h4>
              <div className="space-y-2">
                {(rosterAnalysis.composition?.bench_players || rosterAnalysis.players || []).slice(0, 6).map((player, index: number) => (
                  <div key={`bench-${player.name}-${index}`} className="flex items-center justify-between gap-2 p-2 bg-surface-2 rounded">
                    <div className="flex items-center gap-2 min-w-0">
                      <PlayerAvatar playerId={player.player_id} name={player.name} position={player.position} team={player.team} size={28} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-body truncate">
                          {player.name}
                          {injuryTag(player.injury_status) && (
                            <span className={`ml-1.5 text-[10px] px-1 py-px rounded font-medium ${injuryTag(player.injury_status)!.className}`}>
                              {injuryTag(player.injury_status)!.label}
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-muted">{player.position} • {player.team}</p>
                      </div>
                    </div>
                    <span className="shrink-0 text-xs text-muted">{player.total_points || 0} pts</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Bye Week Radar */}
        <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-body flex items-center gap-2">
              <CalendarDaysIcon className="h-5 w-5 text-accent-ink" />
              Bye Week Radar
            </h3>
            {byeWeekRadar?.supported && (
              <DataConfidenceBadge level="computed" />
            )}
          </div>

          {byeWeekRadarLoading && !byeWeekRadar && (
            <div className="text-center py-6">
              <ClockIcon className="animate-spin h-6 w-6 text-accent-ink mx-auto mb-2" />
              <p className="text-sm text-muted">Checking your roster's upcoming byes...</p>
            </div>
          )}
          {!byeWeekRadarLoading && byeWeekRadarError && (
            <p className="text-sm text-danger-700">{byeWeekRadarError}</p>
          )}
          {!byeWeekRadarLoading && byeWeekRadar && !byeWeekRadar.supported && (
            <p className="text-sm text-muted">{byeWeekRadar.detail || 'Bye week radar is only available for ESPN leagues today.'}</p>
          )}
          {!byeWeekRadarLoading && byeWeekRadar?.supported && (
            (byeWeekRadar.upcoming_byes?.length ?? 0) === 0 ? (
              <p className="text-sm text-muted">No rostered player has an upcoming bye week left this season.</p>
            ) : (
              <div className="space-y-2">
                {byeWeekRadar.upcoming_byes!.map((b, index) => (
                  <div
                    key={`${b.player_name}-${index}`}
                    className={`flex items-center justify-between gap-2 p-2 rounded ${
                      b.weeks_until_bye === 0 ? 'bg-warning-50' : 'bg-surface-2'
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-body truncate">{b.player_name}</p>
                      <p className="text-xs text-muted">{b.position} • {b.team}</p>
                    </div>
                    <span className="shrink-0 stat-nums text-xs text-accent-ink">
                      {b.weeks_until_bye === 0
                        ? 'BYE THIS WEEK'
                        : b.weeks_until_bye === 1
                        ? `WK ${b.bye_week} · NEXT WEEK`
                        : `WK ${b.bye_week} · IN ${b.weeks_until_bye} WEEKS`}
                    </span>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

      </div>
  )
}

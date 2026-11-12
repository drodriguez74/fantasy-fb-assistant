import { ClockIcon, TrophyIcon } from '@heroicons/react/24/outline'
import { relTime, type MatchupHistoryData } from './types'

interface MatchupsTabProps {
  matchupHistory: MatchupHistoryData | null
  matchupHistoryLoading: boolean
  matchupHistoryError: string
}

export function MatchupsTab({ matchupHistory, matchupHistoryLoading, matchupHistoryError }: MatchupsTabProps) {
  return (
      <div className="space-y-6">
        {matchupHistoryLoading && !matchupHistory && (
          <div className="bg-surface rounded-lg border border-hairline p-8 text-center">
            <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
            <p className="text-sm text-muted">Loading your season schedule...</p>
          </div>
        )}
        {!matchupHistoryLoading && matchupHistoryError && (
          <div className="bg-danger-50 border border-danger-200 rounded-md p-4">
            <p className="text-sm text-danger-700">{matchupHistoryError}</p>
          </div>
        )}
        {!matchupHistoryLoading && matchupHistory && !matchupHistory.supported && (
          <div className="bg-surface rounded-lg border border-hairline p-8 text-center">
            <TrophyIcon className="mx-auto h-8 w-8 text-faint mb-2" />
            <p className="text-sm text-muted">{matchupHistory.detail || 'Matchup history is only available for ESPN leagues today.'}</p>
          </div>
        )}
        {!matchupHistoryLoading && matchupHistory?.supported && matchupHistory.matchups && (
          <div className="bg-surface rounded-lg border border-hairline overflow-hidden">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between p-4 sm:p-6 border-b border-hairline">
              <div>
                <h3 className="text-lg font-medium text-body">Season Schedule</h3>
                <p className="text-sm text-muted">Through Week {matchupHistory.through_week}</p>
              </div>
              {matchupHistory.record && (
                <div className="stat-nums text-2xl font-bold text-body">
                  {matchupHistory.record.wins}-{matchupHistory.record.losses}
                  {matchupHistory.record.ties > 0 ? `-${matchupHistory.record.ties}` : ''}
                </div>
              )}
            </div>
            <div className="divide-y divide-hairline">
              {matchupHistory.matchups.map((m) => (
                <div key={m.week} className="flex items-center gap-3 px-4 sm:px-6 py-3">
                  <span className="stat-nums text-xs text-faint w-14 shrink-0">WK {m.week}</span>
                  <span className="flex-1 min-w-0 truncate text-sm text-body">
                    {m.result === 'bye' ? 'Bye week' : `vs ${m.opponent_name}`}
                  </span>
                  {m.result !== 'bye' && m.result !== 'upcoming' && (
                    <span className="stat-nums text-sm tabular-nums text-muted shrink-0">
                      {m.my_score.toFixed(1)} &ndash; {m.opponent_score.toFixed(1)}
                    </span>
                  )}
                  <span
                    className={`shrink-0 inline-flex items-center justify-center w-16 rounded-full px-2 py-0.5 text-xs font-semibold ${
                      m.result === 'win'
                        ? 'bg-success-100 text-success-800'
                        : m.result === 'loss'
                        ? 'bg-danger-100 text-danger-800'
                        : m.result === 'tie'
                        ? 'bg-warning-100 text-warning-800'
                        : 'bg-surface-2 text-muted'
                    }`}
                  >
                    {m.result === 'upcoming' ? 'UPCOMING' : m.result === 'bye' ? 'BYE' : m.result.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
            {matchupHistory._cache && (
              <div className="px-4 sm:px-6 py-2 border-t border-hairline stat-nums text-[10px] tracking-wider text-faint">
                UPDATED {relTime(matchupHistory._cache.as_of).toUpperCase()}
              </div>
            )}
          </div>
        )}
      </div>
  )
}

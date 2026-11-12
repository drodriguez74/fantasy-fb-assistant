import { formatPoints } from './display'
import { type RosterAnalysis, type StandingsData } from './types'

interface StandingsTabProps {
  rosterAnalysis: RosterAnalysis | null
  standingsData: StandingsData
}

export function StandingsTab({ rosterAnalysis, standingsData }: StandingsTabProps) {
  return (
      <div className="space-y-6">
        <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-4">League Standings</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-hairline">
              <thead className="bg-surface-2">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Rank
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Team
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Record
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Points For
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Points Against
                  </th>
                </tr>
              </thead>
              <tbody className="bg-surface divide-y divide-hairline">
                {standingsData.teams.map((team) => (
                  <tr key={`team-${team.name || team.team_name}-${team.rank}`} className={team.rank <= standingsData.playoff_teams ? 'bg-success-50' : ''}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-body">
                      {team.rank}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                      {team.team_name || team.name}
                      {team.team_name === rosterAnalysis?.team_name && (
                        <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink">
                          You
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                      {team.wins}-{team.losses}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                      {formatPoints(team.points_for)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-body">
                      {formatPoints(team.points_against)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
  )
}

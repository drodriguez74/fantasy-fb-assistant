import type { Dispatch, SetStateAction } from 'react'
import { ClockIcon, FireIcon } from '@heroicons/react/24/outline'
import { getPositionColor } from '../../players/playerDisplay'
import { TrendIcon } from './parts'
import { type TrendingPlayer } from './types'

interface TrendingTabProps {
  trendingPlayers: TrendingPlayer[]
  loading: boolean
  selectedPosition: string
  setSelectedPosition: Dispatch<SetStateAction<string>>
  trendDirection: string
  setTrendDirection: Dispatch<SetStateAction<string>>
}

export function TrendingTab({ trendingPlayers, loading, selectedPosition, setSelectedPosition, trendDirection, setTrendDirection }: TrendingTabProps) {
  return (
      <div className="space-y-6">
        {/* Trending Filters */}
        <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
          <h3 className="text-lg font-medium text-body mb-4">Trending Players</h3>
          <div className="flex flex-wrap gap-4">
            <div>
              <label className="block text-sm font-medium text-body mb-1">Trend Direction</label>
              <select
                value={trendDirection}
                onChange={(e) => setTrendDirection(e.target.value)}
                className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
              >
                <option value="up">Trending Up</option>
                <option value="down">Trending Down</option>
                <option value="both">Both Directions</option>
              </select>
            </div>
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
              </select>
            </div>
          </div>
        </div>

        {/* Trending Players List -- real live snapshot from Sleeper's
            trending add/drop feed (last 24h), not a historical trend
            line. See WaiverWireService.get_live_trending_players. */}
        {loading ? (
          <div className="bg-surface rounded-lg shadow p-6 text-center">
            <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
            <p className="text-sm text-muted">Pulling adds...</p>
          </div>
        ) : trendingPlayers.length === 0 ? (
          <div className="bg-surface rounded-lg shadow p-6 text-center py-8">
            <FireIcon className="mx-auto h-12 w-12 text-faint" />
            <h3 className="mt-2 text-sm font-medium text-body">No movement on the wire</h3>
            <p className="mt-1 text-sm text-muted">
              Try a different direction or clear the position filter.
            </p>
          </div>
        ) : (
          <div className="bg-surface rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-hairline">
              <thead className="bg-surface-2">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Player
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Direction
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Adds/Drops (24h)
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Source
                  </th>
                </tr>
              </thead>
              <tbody className="bg-surface divide-y divide-hairline">
                {trendingPlayers.map((player) => (
                  <tr key={`${player.trend_direction}-${player.player_id}`} className="hover:bg-surface-2">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                            {player.position}
                          </span>
                        </div>
                        <div className="ml-4">
                          <div className="text-sm font-medium text-body">{player.player_name}</div>
                          <div className="text-sm text-muted">{player.team}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <TrendIcon direction={player.trend_direction} />
                        <span className={`ml-1 text-sm font-medium ${
                          player.trend_direction === 'up' ? 'text-success-700' : 'text-danger-700'
                        }`}>
                          {player.trend_direction === 'up' ? 'Trending up' : 'Trending down'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-stat tabular-nums font-medium text-body">
                      {player.count_24h.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-sm text-muted">
                      {player.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
  )
}

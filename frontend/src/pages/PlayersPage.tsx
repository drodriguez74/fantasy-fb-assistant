import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import { players, getErrorMessage } from '../services/api'
import { PlayerCard } from '../components/players/PlayerCard'
import { injuryStatusClasses } from '../components/players/playerDisplay'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import type { Player, Position } from '../types'

interface PaginationInfo {
  total_count: number
  total_pages: number
  current_page: number
  page_size: number
  has_next: boolean
  has_previous: boolean
  next_page?: number
  previous_page?: number
}

export function PlayersPage() {
  const navigate = useNavigate()
  const [playerList, setPlayerList] = useState<Player[]>([])
  const [pagination, setPagination] = useState<PaginationInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedPosition, setSelectedPosition] = useState<Position | ''>('')
  const [sort, setSort] = useState<'rank' | 'bye_week' | 'consensus' | ''>('')
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('cards')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  useEffect(() => {
    setCurrentPage(1) // Reset to first page when position or sort changes
  }, [selectedPosition, sort])

  const loadPlayers = useCallback(async () => {
    try {
      setLoading(true)
      const params = {
        ...(selectedPosition ? { position: selectedPosition } : {}),
        ...(sort ? { sort } : {}),
        page: currentPage,
        page_size: pageSize
      }
      const response = await players.getAll(params)
      setPlayerList(response.data?.players || [])
      setPagination(response.data?.pagination || null)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load players'))
    } finally {
      setLoading(false)
    }
  }, [selectedPosition, sort, currentPage, pageSize])

  useEffect(() => {
    loadPlayers()
  }, [loadPlayers])

  const filteredPlayers = playerList.filter(player =>
    player.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    player.team.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Navigate to the focused per-player view, handing along the already-
  // fetched Player object so the detail page renders instantly with no
  // extra request. AI insights are generated there, on demand, for this one
  // player -- not as a button rendered on every one of the 4,000+ rows here.
  const openPlayer = (player: Player) => {
    navigate(`/players/${player.sleeper_id ?? player.id}`, { state: { player } })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-accent-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-ink-900">Player Rankings</h1>
        <p className="text-ink-600 mt-2">
          Comprehensive player analysis and PPR rankings
        </p>
      </div>

      {error && (
        <div className="bg-danger-50 border border-danger-200 text-danger-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
        <select
          value={selectedPosition}
          onChange={(e) => setSelectedPosition(e.target.value as Position | '')}
          className="px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
        >
          <option value="">All Positions</option>
          <option value="QB">QB</option>
          <option value="RB">RB</option>
          <option value="WR">WR</option>
          <option value="TE">TE</option>
          <option value="K">K</option>
          <option value="DEF">DEF</option>
        </select>

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as 'rank' | 'bye_week' | 'consensus' | '')}
          className="px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
        >
          <option value="">Sort: Relevance</option>
          <option value="rank">Rank (ADP)</option>
          <option value="consensus">Consensus Rank</option>
          <option value="bye_week">Bye Week</option>
        </select>

        <input
          type="text"
          placeholder="Search players..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
        />

        <div className="flex rounded-md border border-ink-300">
          <button
            onClick={() => setViewMode('cards')}
            className={`px-3 py-2 text-sm font-medium rounded-l-md ${
              viewMode === 'cards'
                ? 'bg-accent-500 text-white'
                : 'bg-white text-ink-700 hover:bg-ink-50'
            }`}
          >
            Cards
          </button>
          <button
            onClick={() => setViewMode('table')}
            className={`px-3 py-2 text-sm font-medium rounded-r-md border-l ${
              viewMode === 'table'
                ? 'bg-accent-500 text-white'
                : 'bg-white text-ink-700 hover:bg-ink-50'
            }`}
          >
            Table
          </button>
        </div>
      </div>

      {viewMode === 'cards' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredPlayers.map((player) => (
            <PlayerCard
              key={player.id}
              player={player}
              showDetails={true}
              onClick={openPlayer}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-ink-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-ink-200">
              <thead className="bg-ink-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Player
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Position
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Team
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Projected Points
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                    ADP
                  </th>
                  {sort === 'consensus' && (
                    <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                      Consensus
                    </th>
                  )}
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-500 uppercase tracking-wider">
                    Bye Week
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-ink-200">
                {filteredPlayers.map((player) => (
                  <tr
                    key={player.id}
                    className="hover:bg-ink-50 cursor-pointer"
                    onClick={() => openPlayer(player)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div>
                          <div className="text-sm font-medium text-ink-900">{player.name}</div>
                          {player.injury_status && player.injury_status.toUpperCase() !== 'HEALTHY' && (
                            <span className={`inline-flex mt-1 px-1.5 py-0.5 rounded text-xs font-medium ${injuryStatusClasses(player.injury_status)}`}>
                              {player.injury_status}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 text-xs font-medium bg-ink-100 text-ink-800 rounded-full">
                        {player.position}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-500">
                      {player.team}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-900">
                      {player.projected_points ? player.projected_points.toFixed(1) : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-500">
                      {player.adp ? player.adp.toFixed(1) : '-'}
                    </td>
                    {sort === 'consensus' && (
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-500">
                        {player.consensus ? (
                          <div className="flex items-center gap-2">
                            <span className="text-ink-900 font-medium">#{player.consensus.consensus_rank}</span>
                            <DataConfidenceBadge
                              level="computed"
                              label={player.consensus.source_count > 1 ? '2 sources' : '1 source'}
                            />
                          </div>
                        ) : '-'}
                      </td>
                    )}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-500">
                      {player.bye_week ? `Week ${player.bye_week}` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {filteredPlayers.length === 0 && !loading && (
        <div className="text-center py-12">
          <p className="text-ink-500">No players found matching your criteria.</p>
        </div>
      )}

      {/* Pagination Controls */}
      {pagination && pagination.total_pages > 1 && (
        <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-ink-200 sm:px-6">
          <div className="flex-1 flex justify-between items-center">
            <div className="flex items-center text-sm text-ink-700">
              <span>
                Showing page {pagination.current_page} of {pagination.total_pages}
                ({pagination.total_count} total players)
              </span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setCurrentPage(1)
                }}
                className="ml-4 border-ink-300 rounded-md text-sm"
              >
                <option value={25}>25 per page</option>
                <option value={50}>50 per page</option>
                <option value={100}>100 per page</option>
              </select>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => setCurrentPage(pagination.previous_page!)}
                disabled={!pagination.has_previous}
                className={`relative inline-flex items-center px-2 py-2 rounded-l-md border text-sm font-medium ${
                  pagination.has_previous
                    ? 'border-ink-300 bg-white text-ink-500 hover:bg-ink-50'
                    : 'border-ink-300 bg-ink-100 text-ink-300 cursor-not-allowed'
                }`}
              >
                <ChevronLeftIcon className="h-5 w-5" />
              </button>

              {/* Page Numbers */}
              <div className="flex items-center space-x-1">
                {(() => {
                  // Calculate page numbers ensuring uniqueness
                  const maxPagesToShow = Math.min(5, pagination.total_pages)
                  const startPage = Math.max(1, pagination.current_page - 2)
                  const endPage = Math.min(pagination.total_pages, startPage + maxPagesToShow - 1)
                  const adjustedStartPage = Math.max(1, endPage - maxPagesToShow + 1)

                  const pageNumbers = []
                  for (let i = adjustedStartPage; i <= endPage; i++) {
                    pageNumbers.push(i)
                  }

                  return pageNumbers.map((pageNum) => (
                    <button
                      key={pageNum}
                      onClick={() => setCurrentPage(pageNum)}
                      className={`relative inline-flex items-center px-4 py-2 border text-sm font-medium ${
                        pageNum === pagination.current_page
                          ? 'z-10 bg-accent-50 border-accent-500 text-accent-600'
                          : 'bg-white border-ink-300 text-ink-500 hover:bg-ink-50'
                      }`}
                    >
                      {pageNum}
                    </button>
                  ))
                })()}
              </div>

              <button
                onClick={() => setCurrentPage(pagination.next_page!)}
                disabled={!pagination.has_next}
                className={`relative inline-flex items-center px-2 py-2 rounded-r-md border text-sm font-medium ${
                  pagination.has_next
                    ? 'border-ink-300 bg-white text-ink-500 hover:bg-ink-50'
                    : 'border-ink-300 bg-ink-100 text-ink-300 cursor-not-allowed'
                }`}
              >
                <ChevronRightIcon className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
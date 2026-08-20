import { useState, useEffect, useCallback, useRef } from 'react'
import { trade, getErrorMessage } from '../services/api'
import {
  ArrowsRightLeftIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  ScaleIcon,
} from '@heroicons/react/24/outline'

interface TradeSearchResult {
  sleeper_id: string
  name: string
  position: string
  team: string | null
  search_rank: number | null
}

interface TradePlayerValue extends TradeSearchResult {
  is_active: boolean
  value: number
}

interface TradeSideResult {
  players: TradePlayerValue[]
  total_value: number
}

interface TradeVerdict {
  winner: 'side_a' | 'side_b' | 'even'
  value_difference: number
  summary: string
}

interface TradeAnalysisResult {
  side_a: TradeSideResult
  side_b: TradeSideResult
  verdict: TradeVerdict
  warnings: string[]
  value_model: { basis: string; description: string }
}

type Side = 'a' | 'b'

function PlayerPicker({
  label,
  selected,
  onAdd,
  onRemove,
}: {
  label: string
  selected: TradeSearchResult[]
  onAdd: (player: TradeSearchResult) => void
  onRemove: (sleeperId: string) => void
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TradeSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (query.trim().length < 2) {
      setResults([])
      return
    }

    debounceRef.current = setTimeout(async () => {
      try {
        setSearching(true)
        const response = await trade.searchPlayers(query.trim(), 8)
        setResults(response.data?.players || [])
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 300)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  const alreadySelected = (sleeperId: string) => selected.some((p) => p.sleeper_id === sleeperId)

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-3">{label}</h3>

      <div className="relative mb-3">
        <MagnifyingGlassIcon className="h-4 w-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search players by name..."
          className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {query.trim().length >= 2 && (
        <div className="mb-3 border border-gray-200 rounded-md divide-y divide-gray-100 max-h-56 overflow-y-auto">
          {searching ? (
            <div className="px-3 py-2 text-sm text-gray-500">Searching...</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-2 text-sm text-gray-500">No active players found.</div>
          ) : (
            results.map((player) => (
              <button
                key={player.sleeper_id}
                type="button"
                disabled={alreadySelected(player.sleeper_id)}
                onClick={() => {
                  onAdd(player)
                  setQuery('')
                  setResults([])
                }}
                className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between ${
                  alreadySelected(player.sleeper_id)
                    ? 'text-gray-300 cursor-not-allowed'
                    : 'hover:bg-blue-50 text-gray-800'
                }`}
              >
                <span>
                  {player.name}{' '}
                  <span className="text-gray-500">
                    ({player.position} - {player.team || 'FA'})
                  </span>
                </span>
                {alreadySelected(player.sleeper_id) && <span className="text-xs">Added</span>}
              </button>
            ))
          )}
        </div>
      )}

      <div className="space-y-2">
        {selected.length === 0 ? (
          <p className="text-sm text-gray-400 italic">No players added yet.</p>
        ) : (
          selected.map((player) => (
            <div
              key={player.sleeper_id}
              className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-md px-3 py-2"
            >
              <span className="text-sm text-gray-800">
                {player.name}{' '}
                <span className="text-gray-500">
                  ({player.position} - {player.team || 'FA'})
                </span>
              </span>
              <button
                type="button"
                onClick={() => onRemove(player.sleeper_id)}
                className="text-gray-400 hover:text-red-500"
                aria-label={`Remove ${player.name}`}
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function ValueBar({ value, maxValue }: { value: number; maxValue: number }) {
  const pct = maxValue > 0 ? Math.max(4, Math.round((value / maxValue) * 100)) : 0
  return (
    <div className="w-full bg-gray-200 rounded-full h-2 mt-1">
      <div className="bg-blue-600 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  )
}

function SideResultCard({ title, side, maxValue }: { title: string; side: TradeSideResult; maxValue: number }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-lg font-medium text-gray-900">{title}</h4>
        <span className="text-2xl font-bold text-gray-900">{side.total_value.toFixed(1)}</span>
      </div>
      <div className="space-y-3">
        {side.players.map((player) => (
          <div key={player.sleeper_id}>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-800">
                {player.name}{' '}
                <span className="text-gray-500">
                  ({player.position} - {player.team || 'FA'})
                </span>
                {!player.is_active && (
                  <span className="ml-2 text-xs text-red-600 font-medium">Retired/inactive</span>
                )}
              </span>
              <span className="font-medium text-gray-900">{player.value.toFixed(1)}</span>
            </div>
            <ValueBar value={player.value} maxValue={maxValue} />
          </div>
        ))}
      </div>
    </div>
  )
}

export function TradeAnalyzerPage() {
  const [sideA, setSideA] = useState<TradeSearchResult[]>([])
  const [sideB, setSideB] = useState<TradeSearchResult[]>([])
  const [result, setResult] = useState<TradeAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const addPlayer = useCallback((side: Side, player: TradeSearchResult) => {
    const setter = side === 'a' ? setSideA : setSideB
    setter((prev) => (prev.some((p) => p.sleeper_id === player.sleeper_id) ? prev : [...prev, player]))
  }, [])

  const removePlayer = useCallback((side: Side, sleeperId: string) => {
    const setter = side === 'a' ? setSideA : setSideB
    setter((prev) => prev.filter((p) => p.sleeper_id !== sleeperId))
  }, [])

  const analyzeTrade = async () => {
    if (sideA.length === 0 || sideB.length === 0) {
      setError('Add at least one player to each side of the trade.')
      return
    }

    try {
      setLoading(true)
      setError('')
      const response = await trade.analyze({
        side_a_gives: sideA.map((p) => p.sleeper_id),
        side_b_gives: sideB.map((p) => p.sleeper_id),
      })
      setResult(response.data)
    } catch (err) {
      setResult(null)
      setError(getErrorMessage(err, 'Failed to analyze trade'))
    } finally {
      setLoading(false)
    }
  }

  const maxValue = result
    ? Math.max(
        1,
        ...result.side_a.players.map((p) => p.value),
        ...result.side_b.players.map((p) => p.value)
      )
    : 1

  const verdictStyle =
    result?.verdict.winner === 'even'
      ? 'bg-gray-50 border-gray-300 text-gray-800'
      : 'bg-blue-50 border-blue-300 text-blue-900'

  return (
    <div className="max-w-6xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="mb-6">
        <div className="flex items-center gap-2">
          <ScaleIcon className="h-8 w-8 text-blue-600" />
          <h1 className="text-3xl font-bold text-gray-900">Trade Analyzer</h1>
        </div>
        <p className="text-gray-600 mt-2">
          Propose a trade and see which side comes out ahead, based on real player ranking data.
        </p>
      </div>

      {/* Honesty disclaimer -- this is a heuristic, not AI */}
      <div className="mb-6 bg-amber-50 border border-amber-200 rounded-md p-4 flex gap-3">
        <InformationCircleIcon className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-amber-800">
          <p className="font-medium">This is a simple heuristic, not AI analysis.</p>
          <p className="mt-1">
            Player value is calculated from Sleeper's own player ranking data (search rank), on a
            curve where higher-demand players are worth more. It does not account for your league's
            scoring settings, roster needs, injuries beyond active-roster status, or matchups. Treat
            it as one data point, not a verdict.
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-md p-4 flex gap-3">
          <ExclamationTriangleIcon className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <PlayerPicker
          label="Side A gives"
          selected={sideA}
          onAdd={(p) => addPlayer('a', p)}
          onRemove={(id) => removePlayer('a', id)}
        />
        <PlayerPicker
          label="Side B gives"
          selected={sideB}
          onAdd={(p) => addPlayer('b', p)}
          onRemove={(id) => removePlayer('b', id)}
        />
      </div>

      <div className="flex justify-center mb-8">
        <button
          onClick={analyzeTrade}
          disabled={loading}
          className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center space-x-2 font-medium"
        >
          <ArrowsRightLeftIcon className="h-5 w-5" />
          <span>{loading ? 'Analyzing...' : 'Analyze Trade'}</span>
        </button>
      </div>

      {result && (
        <div className="space-y-6">
          <div className={`border rounded-lg p-6 text-center ${verdictStyle}`}>
            <p className="text-lg font-semibold">{result.verdict.summary}</p>
          </div>

          {result.warnings.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <div className="flex gap-2 mb-1">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-400 flex-shrink-0" />
                <p className="text-sm font-medium text-red-800">Value warnings</p>
              </div>
              <ul className="text-sm text-red-700 list-disc list-inside space-y-0.5">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SideResultCard title="Side A gives" side={result.side_a} maxValue={maxValue} />
            <SideResultCard title="Side B gives" side={result.side_b} maxValue={maxValue} />
          </div>

          <div className="bg-gray-50 border border-gray-200 rounded-md p-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
              How this value is calculated
            </p>
            <p className="text-sm text-gray-600">{result.value_model.description}</p>
          </div>
        </div>
      )}
    </div>
  )
}

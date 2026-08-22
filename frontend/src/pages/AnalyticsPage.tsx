import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { api, players as playersApi, getErrorMessage } from '../services/api'
import {
  ChartBarIcon,
  BeakerIcon,
  CalculatorIcon,
  CpuChipIcon,
  ArrowTrendingUpIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  AdjustmentsHorizontalIcon,
  PresentationChartLineIcon,
  UserGroupIcon,
  LightBulbIcon,
  RocketLaunchIcon
} from '@heroicons/react/24/outline'

interface PredictionResult {
  player_id: number
  player_name: string
  position: string
  weeks_ahead: number
  predictions: Record<string, number>
  confidence_scores: Record<string, number>
  model_type: string
  data_points_used: number
}

interface LineupPlayer {
  player_id: number
  name: string
  position: string
  projected_points: number
  salary: number
  variance: number
}

interface OptimizationResult {
  optimization_type: string
  selected_players: LineupPlayer[]
  total_salary: number
  salary_cap: number
  projected_points: number
  objective_value: number
}

interface CorrelationResult {
  position_filter?: string
  players_analyzed: number
  strong_correlations: Array<{
    player1_name: string
    player2_name: string
    correlation: number
    correlation_type: string
  }>
}

export function AnalyticsPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'predictions' | 'optimization' | 'correlations' | 'clustering' | 'visualization'>('predictions')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Prediction state
  const [selectedPlayerId, setSelectedPlayerId] = useState<number>(1) // Default to Josh Allen
  const [weeksAhead, setWeeksAhead] = useState(4)
  const [modelType, setModelType] = useState('ensemble')
  const [predictionResult, setPredictionResult] = useState<PredictionResult | null>(null)

  // Optimization state
  const [optimizationType, setOptimizationType] = useState('maximize_points')
  const [salaryCap, setSalaryCap] = useState(50000)
  const [optimizationResult, setOptimizationResult] = useState<OptimizationResult | null>(null)
  const [optimizerPoolSize, setOptimizerPoolSize] = useState<number | null>(null)

  // Correlation state
  const [correlationPosition, setCorrelationPosition] = useState<string>('')
  const [correlationResult, setCorrelationResult] = useState<CorrelationResult | null>(null)

  // Available sample players for testing
  const samplePlayers = [
    { id: 1, name: 'Josh Allen', position: 'QB' },
    { id: 2, name: 'Christian McCaffrey', position: 'RB' },
    { id: 3, name: 'Tyreek Hill', position: 'WR' },
    { id: 4, name: 'Travis Kelce', position: 'TE' }
  ]

  // How many top-ranked (by real, live Sleeper search_rank) players per
  // position to pull in as optimizer candidates -- enough for the solver to
  // have a genuine choice while keeping the request a reasonable size.
  const OPTIMIZER_POOL_SIZE: Record<string, number> = {
    QB: 10, RB: 20, WR: 20, TE: 10, DEF: 10, K: 10
  }

  // Sleeper's free API (the only player data source wired into this app --
  // see sleeper_service.py) doesn't expose real weekly fantasy-point
  // projections or DFS salaries, and this app has no other projections/DFS
  // integration. So projected_points/salary/variance below are estimated
  // from each player's real Sleeper rank using typical PPR scoring tiers,
  // not looked up from a real projections feed. The player pool itself
  // (identity, team, position) is real, live Sleeper data -- not a
  // hardcoded sample -- and the UI labels the estimate as such.
  const POSITION_POINT_CURVE: Record<string, { base: number; step: number; floor: number }> = {
    QB: { base: 26, step: 0.9, floor: 8 },
    RB: { base: 22, step: 0.8, floor: 4 },
    WR: { base: 20, step: 0.7, floor: 4 },
    TE: { base: 15, step: 0.7, floor: 3 },
    K: { base: 9, step: 0.25, floor: 4 },
    DEF: { base: 9, step: 0.25, floor: 3 }
  }

  const estimatePlayerValue = (position: string, rankIndex: number) => {
    const curve = POSITION_POINT_CURVE[position] ?? { base: 12, step: 0.6, floor: 3 }
    const projected_points = Math.max(curve.floor, curve.base - rankIndex * curve.step)
    const salary = Math.round((500 + projected_points * 380) / 100) * 100
    const variance = Math.round((projected_points * 0.2 + rankIndex * 0.1) * 10) / 10
    return { projected_points, salary, variance }
  }

  // Fetch a real, live player pool from Sleeper (via the same /players/
  // endpoint PlayersPage.tsx uses), ranked per-position, to feed the
  // optimizer -- replacing the old hardcoded sample lineup.
  const fetchOptimizerPlayerPool = async (): Promise<LineupPlayer[]> => {
    const positions = Object.keys(OPTIMIZER_POOL_SIZE)
    const settled = await Promise.allSettled(
      positions.map(position =>
        playersApi.getAll({ position, sort: 'rank', page_size: OPTIMIZER_POOL_SIZE[position] })
      )
    )

    const pool: LineupPlayer[] = []
    settled.forEach((result, posIdx) => {
      if (result.status !== 'fulfilled') return
      const position = positions[posIdx]
      const positionPlayers: Array<{ id: number; name: string; position: string }> =
        result.value.data?.players ?? []
      positionPlayers.forEach((p, rankIndex) => {
        const { projected_points, salary, variance } = estimatePlayerValue(position, rankIndex)
        pool.push({
          player_id: p.id,
          name: p.name,
          position: p.position || position,
          projected_points,
          salary,
          variance
        })
      })
    })
    return pool
  }

  const runPlayerPrediction = async () => {
    try {
      setLoading(true)
      setError('')
      
      const response = await fetch('/api/v1/analytics/predict/player-performance', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          player_id: selectedPlayerId,
          weeks_ahead: weeksAhead,
          model_type: modelType
        })
      })

      if (!response.ok) {
        throw new Error('Prediction request failed')
      }

      const data = await response.json()
      setPredictionResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate prediction')
    } finally {
      setLoading(false)
    }
  }

  const runLineupOptimization = async () => {
    try {
      setLoading(true)
      setError('')

      const poolPlayers = await fetchOptimizerPlayerPool()
      if (poolPlayers.length === 0) {
        throw new Error('Could not load the live player pool from Sleeper -- try again in a moment')
      }
      setOptimizerPoolSize(poolPlayers.length)

      // Use the shared axios instance (services/api.ts) rather than a raw
      // relative fetch(): the old '/api/v1/...' path resolved against the
      // frontend's own dev-server origin, not the backend, so this request
      // never actually reached the optimizer regardless of payload.
      const response = await api.post('/analytics/optimize/lineup', {
        players: poolPlayers,
        salary_cap: salaryCap,
        optimization_type: optimizationType,
        lineup_constraints: {
          QB: 1, RB: 2, WR: 3, TE: 1, DEF: 1, K: 1
        }
      })

      setOptimizationResult(response.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to optimize lineup'))
    } finally {
      setLoading(false)
    }
  }

  const runCorrelationAnalysis = async () => {
    try {
      setLoading(true)
      setError('')
      
      const queryParams = new URLSearchParams()
      if (correlationPosition) {
        queryParams.append('position', correlationPosition)
      }
      queryParams.append('min_games', '8')
      
      const response = await fetch(`/api/v1/analytics/correlations/players?${queryParams}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      })

      if (!response.ok) {
        throw new Error('Correlation analysis failed')
      }

      const data = await response.json()
      setCorrelationResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze correlations')
    } finally {
      setLoading(false)
    }
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">Authentication Required</h3>
          <p className="mt-1 text-sm text-gray-500">Please sign in to access advanced analytics.</p>
        </div>
      </div>
    )
  }

  const tabs = [
    { id: 'predictions', name: 'ML Predictions', icon: CpuChipIcon },
    { id: 'optimization', name: 'Lineup Optimizer', icon: CalculatorIcon },
    { id: 'correlations', name: 'Correlations', icon: ArrowTrendingUpIcon },
    { id: 'clustering', name: 'Player Clustering', icon: UserGroupIcon },
    { id: 'visualization', name: 'Advanced Charts', icon: PresentationChartLineIcon },
  ]

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Advanced Analytics</h1>
            <p className="text-gray-600 mt-2">
              Machine learning predictions, optimization algorithms, and statistical analysis
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <BeakerIcon className="h-8 w-8 text-blue-600" />
            <span className="text-sm text-blue-600 bg-blue-50 px-3 py-1 rounded-full">
              Beta
            </span>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <div className="mt-2 text-sm text-red-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as 'predictions' | 'optimization' | 'correlations' | 'clustering' | 'visualization')}
                className={`py-2 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.name}</span>
              </button>
            )
          })}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'predictions' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
              <CpuChipIcon className="h-5 w-5 mr-2" />
              Machine Learning Player Predictions
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Player</label>
                <select
                  value={selectedPlayerId}
                  onChange={(e) => setSelectedPlayerId(Number(e.target.value))}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 w-full"
                >
                  {samplePlayers.map(player => (
                    <option key={player.id} value={player.id}>
                      {player.name} ({player.position})
                    </option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Weeks Ahead</label>
                <input
                  type="number"
                  value={weeksAhead}
                  onChange={(e) => setWeeksAhead(Number(e.target.value))}
                  min="1"
                  max="17"
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 w-full"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Model Type</label>
                <select
                  value={modelType}
                  onChange={(e) => setModelType(e.target.value)}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 w-full"
                >
                  <option value="ensemble">Ensemble (Recommended)</option>
                  <option value="linear">Linear Regression</option>
                  <option value="rf">Random Forest</option>
                  <option value="gb">Gradient Boosting</option>
                </select>
              </div>
              
              <div className="flex items-end">
                <button
                  onClick={runPlayerPrediction}
                  disabled={loading}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center space-x-2 w-full justify-center"
                >
                  {loading ? <ClockIcon className="h-4 w-4 animate-spin" /> : <RocketLaunchIcon className="h-4 w-4" />}
                  <span>{loading ? 'Predicting...' : 'Predict'}</span>
                </button>
              </div>
            </div>

            {predictionResult && (
              <div className="border-t pt-6">
                <h4 className="font-medium text-gray-900 mb-4">Prediction Results</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h5 className="font-medium text-gray-700 mb-2">Model Predictions</h5>
                    <div className="space-y-2">
                      {Object.entries(predictionResult.predictions).map(([model, prediction]) => (
                        <div key={model} className="flex justify-between items-center p-2 bg-gray-50 rounded">
                          <span className="capitalize">{model.replace('_', ' ')}</span>
                          <span className="font-semibold">{prediction.toFixed(1)} pts</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h5 className="font-medium text-gray-700 mb-2">Confidence Scores</h5>
                    <div className="space-y-2">
                      {Object.entries(predictionResult.confidence_scores).map(([model, confidence]) => (
                        <div key={model} className="flex justify-between items-center p-2 bg-gray-50 rounded">
                          <span className="capitalize">{model.replace('_', ' ')}</span>
                          <div className="flex items-center space-x-2">
                            <div className="w-16 bg-gray-200 rounded-full h-2">
                              <div 
                                className="bg-green-600 h-2 rounded-full" 
                                style={{ width: `${confidence * 100}%` }}
                              ></div>
                            </div>
                            <span className="text-sm">{(confidence * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="mt-4 p-3 bg-blue-50 rounded">
                  <p className="text-sm text-blue-700">
                    <strong>Data Points Used:</strong> {predictionResult.data_points_used} games |
                    <strong> Forecast Period:</strong> {predictionResult.weeks_ahead} weeks
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'optimization' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-1 flex items-center">
              <CalculatorIcon className="h-5 w-5 mr-2" />
              Lineup Optimization Engine
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Optimizes from the top available players (live Sleeper data), ranked per position.
              Projected points and salary are estimated from that ranking, not a real DFS salary
              feed or verified weekly projections -- this is not your own roster.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Salary Cap</label>
                <input
                  type="number"
                  value={salaryCap}
                  onChange={(e) => setSalaryCap(Number(e.target.value))}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 w-full"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Optimization Type</label>
                <select
                  value={optimizationType}
                  onChange={(e) => setOptimizationType(e.target.value)}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 w-full"
                >
                  <option value="maximize_points">Maximize Points</option>
                  <option value="risk_adjusted">Risk Adjusted</option>
                  <option value="ceiling_optimizer">Ceiling Optimizer</option>
                </select>
              </div>
              
              <div className="flex items-end">
                <button
                  onClick={runLineupOptimization}
                  disabled={loading}
                  className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center space-x-2 w-full justify-center"
                >
                  {loading ? <ClockIcon className="h-4 w-4 animate-spin" /> : <AdjustmentsHorizontalIcon className="h-4 w-4" />}
                  <span>{loading ? 'Optimizing...' : 'Optimize'}</span>
                </button>
              </div>
            </div>

            {optimizationResult && (
              <div className="border-t pt-6">
                <h4 className="font-medium text-gray-900 mb-1">Optimal Lineup</h4>
                {optimizerPoolSize !== null && (
                  <p className="text-sm text-gray-500 mb-4">
                    Selected from {optimizerPoolSize} live Sleeper players.
                  </p>
                )}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div>
                    <h5 className="font-medium text-gray-700 mb-2">Selected Players</h5>
                    <div className="space-y-2">
                      {optimizationResult.selected_players.map(player => (
                        <div key={player.player_id} className="flex justify-between items-center p-3 border border-gray-200 rounded">
                          <div>
                            <span className="font-medium">{player.name}</span>
                            <span className="text-sm text-gray-500 ml-2">({player.position})</span>
                          </div>
                          <div className="text-right">
                            <div className="font-semibold">{player.projected_points.toFixed(1)} pts</div>
                            <div className="text-sm text-gray-500">${player.salary.toLocaleString()}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h5 className="font-medium text-gray-700 mb-2">Optimization Summary</h5>
                    <div className="space-y-3">
                      <div className="flex justify-between p-2 bg-gray-50 rounded">
                        <span>Total Projected Points</span>
                        <span className="font-semibold text-green-600">{optimizationResult.projected_points.toFixed(1)}</span>
                      </div>
                      <div className="flex justify-between p-2 bg-gray-50 rounded">
                        <span>Total Salary Used</span>
                        <span className="font-semibold">${optimizationResult.total_salary.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between p-2 bg-gray-50 rounded">
                        <span>Salary Remaining</span>
                        <span className="font-semibold">${(optimizationResult.salary_cap - optimizationResult.total_salary).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between p-2 bg-blue-50 rounded">
                        <span>Objective Value</span>
                        <span className="font-semibold text-blue-600">{optimizationResult.objective_value.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'correlations' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
              <ArrowTrendingUpIcon className="h-5 w-5 mr-2" />
              Player Correlation Analysis
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Position Filter</label>
                <select
                  value={correlationPosition}
                  onChange={(e) => setCorrelationPosition(e.target.value)}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 w-full"
                >
                  <option value="">All Positions</option>
                  <option value="QB">Quarterback</option>
                  <option value="RB">Running Back</option>
                  <option value="WR">Wide Receiver</option>
                  <option value="TE">Tight End</option>
                </select>
              </div>
              
              <div className="flex items-end">
                <button
                  onClick={runCorrelationAnalysis}
                  disabled={loading}
                  className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center space-x-2 w-full justify-center"
                >
                  {loading ? <ClockIcon className="h-4 w-4 animate-spin" /> : <LightBulbIcon className="h-4 w-4" />}
                  <span>{loading ? 'Analyzing...' : 'Analyze'}</span>
                </button>
              </div>
            </div>

            {correlationResult && (
              <div className="border-t pt-6">
                <h4 className="font-medium text-gray-900 mb-4">
                  Strong Correlations Found ({correlationResult.strong_correlations.length})
                </h4>
                <div className="space-y-3">
                  {correlationResult.strong_correlations.slice(0, 10).map((correlation, index) => (
                    <div key={`correlation-${correlation.player1_name}-${correlation.player2_name}-${index}`} className="flex justify-between items-center p-3 border border-gray-200 rounded">
                      <div>
                        <span className="font-medium">{correlation.player1_name}</span>
                        <span className="text-gray-500 mx-2">↔</span>
                        <span className="font-medium">{correlation.player2_name}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className={`px-2 py-1 rounded text-xs ${
                          correlation.correlation_type === 'positive' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {correlation.correlation_type}
                        </span>
                        <span className="font-semibold">{(correlation.correlation * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 p-3 bg-gray-50 rounded">
                  <p className="text-sm text-gray-700">
                    Analyzed {correlationResult.players_analyzed} players. 
                    Positive correlations indicate players whose performances tend to move together.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'clustering' && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <UserGroupIcon className="h-5 w-5 mr-2" />
            Player Performance Clustering
          </h3>
          <div className="text-center py-12">
            <BeakerIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900">Feature Coming Soon</h3>
            <p className="mt-1 text-sm text-gray-500">
              K-means clustering to group players by performance characteristics
            </p>
          </div>
        </div>
      )}

      {activeTab === 'visualization' && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <PresentationChartLineIcon className="h-5 w-5 mr-2" />
            Advanced Data Visualizations
          </h3>
          <div className="text-center py-12">
            <ChartBarIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900">Interactive Charts Coming Soon</h3>
            <p className="mt-1 text-sm text-gray-500">
              Advanced visualizations with correlation heatmaps, performance clusters, and trend analysis
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
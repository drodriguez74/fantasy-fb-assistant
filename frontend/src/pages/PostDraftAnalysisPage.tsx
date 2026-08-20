import { useState, useEffect } from 'react'
import { api, getErrorMessage } from '../services/api'
import {
  TrophyIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  FireIcon,
  ShieldCheckIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  PlusIcon,
  UserGroupIcon,
  AcademicCapIcon
} from '@heroicons/react/24/outline'

interface RosterPlayer {
  player_id?: number
  player_name: string
  position: string
  team: string
  round?: number
  pick?: number
}

interface PlayerEvaluation {
  player_info: {
    name: string
    position: string
    team: string
    draft_round?: number
  }
  value_analysis: {
    value_grade: string
    value_category: string
  }
  season_outlook: {
    outlook: string
  }
  risk_assessment: {
    risk_level: string
    risk_factors?: string[]
  }
}

interface RosterAnalysis {
  // The backend returns arbitrary roster-composition data that this page never renders;
  // kept as `unknown` rather than guessing at a shape nothing here depends on.
  composition: unknown
  player_evaluations: PlayerEvaluation[]
  strengths_weaknesses: {
    strengths?: string[]
    weaknesses?: string[]
  }
  overall_grade: {
    grade: string
    description: string
    score: number
    player_count: number
    avg_player_value: number
  }
}

interface WaiverTarget {
  player_name: string
  position: string
  team: string
  adjusted_priority: number
  roster_fit: string
  personalized_reasoning: string
  confidence_score: number
  recommendation_type: string
  reason: string
}

interface UserLeague {
  id: number
  name: string
  platform: string
  scoring_format: string
  season: number
  is_active: boolean
}

export function PostDraftAnalysisPage() {
  const [roster, setRoster] = useState<RosterPlayer[]>([])
  const [analysis, setAnalysis] = useState<RosterAnalysis | null>(null)
  const [waiverTargets, setWaiverTargets] = useState<WaiverTarget[]>([])
  const [userLeagues, setUserLeagues] = useState<UserLeague[]>([])
  const [showImportOptions, setShowImportOptions] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [currentWeek, setCurrentWeek] = useState(1)

  // Load user leagues on component mount
  useEffect(() => {
    fetchUserLeagues()
  }, [])

  const fetchUserLeagues = async () => {
    try {
      const response = await api.get('/post-draft/user-leagues')
      setUserLeagues(response.data.leagues)
    } catch (err) {
      console.error('Failed to fetch user leagues:', err)
    }
  }

  const importRosterFromLeague = async (leagueId: number) => {
    try {
      setLoading(true)
      setError('')
      
      const response = await api.get(`/post-draft/import-roster/${leagueId}`)
      setRoster(response.data.roster)
      setShowImportOptions(false)

    } catch (err) {
      setError(getErrorMessage(err, 'Failed to import roster'))
    } finally {
      setLoading(false)
    }
  }

  const analyzeRoster = async () => {
    if (!roster.length) return
    
    try {
      setLoading(true)
      setError('')
      
      const response = await api.post('/post-draft/analyze-roster', {
        roster: roster,
        league_settings: {
          scoring_format: 'PPR',
          league_size: 12
        }
      })
      
      setAnalysis(response.data.analysis.roster_analysis)

    } catch (err) {
      setError(getErrorMessage(err, 'Failed to analyze roster'))
    } finally {
      setLoading(false)
    }
  }

  const getPersonalizedWaivers = async () => {
    if (!roster.length) return
    
    try {
      setLoading(true)
      
      const response = await api.post(`/post-draft/personalized-waivers?week=${currentWeek}`, {
        roster: roster,
        league_settings: {
          scoring_format: 'PPR',
          league_size: 12
        }
      })
      
      setWaiverTargets(response.data.personalized_recommendations.personalized_targets || [])

    } catch (err) {
      setError(getErrorMessage(err, 'Failed to get waiver recommendations'))
    } finally {
      setLoading(false)
    }
  }

  const addPlayerToRoster = () => {
    setRoster([...roster, {
      player_name: '',
      position: 'RB',
      team: '',
      round: roster.length + 1
    }])
  }

  const updateRosterPlayer = (index: number, field: keyof RosterPlayer, value: string | number) => {
    const updated = [...roster]
    updated[index] = { ...updated[index], [field]: value }
    setRoster(updated)
  }

  const removePlayerFromRoster = (index: number) => {
    setRoster(roster.filter((_, i) => i !== index))
  }

  const getGradeColor = (grade: string): string => {
    const colors: Record<string, string> = {
      'A': 'bg-green-100 text-green-800',
      'B': 'bg-blue-100 text-blue-800',
      'C': 'bg-yellow-100 text-yellow-800',
      'D': 'bg-orange-100 text-orange-800',
      'F': 'bg-red-100 text-red-800'
    }
    return colors[grade] || 'bg-gray-100 text-gray-800'
  }

  const getPriorityColor = (priority: number): string => {
    if (priority >= 80) return 'bg-red-100 text-red-800'
    if (priority >= 60) return 'bg-yellow-100 text-yellow-800'
    return 'bg-green-100 text-green-800'
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Post-Draft Analysis</h1>
        <p className="text-gray-600 mt-2">
          Evaluate your roster and get personalized waiver wire recommendations
        </p>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <div className="mt-2 text-sm text-red-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Roster Input */}
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center">
                <UserGroupIcon className="h-6 w-6 mr-2 text-blue-600" />
                Your Roster
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowImportOptions(!showImportOptions)}
                  className="flex items-center text-green-600 hover:text-green-700 text-sm"
                >
                  <ArrowTrendingDownIcon className="h-4 w-4 mr-1" />
                  Import from League
                </button>
                <button
                  onClick={addPlayerToRoster}
                  className="flex items-center text-blue-600 hover:text-blue-700 text-sm"
                >
                  <PlusIcon className="h-4 w-4 mr-1" />
                  Add Player
                </button>
              </div>
            </div>

            {/* League Import Options */}
            {showImportOptions && (
              <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h3 className="text-sm font-medium text-blue-900 mb-3">Import Roster from Connected League</h3>
                {userLeagues.length > 0 ? (
                  <div className="space-y-2">
                    {userLeagues.map((league) => (
                      <button
                        key={league.id}
                        onClick={() => importRosterFromLeague(league.id)}
                        disabled={loading}
                        className="w-full text-left p-3 bg-white border border-blue-200 rounded-md hover:bg-blue-50 disabled:opacity-50"
                      >
                        <div className="flex justify-between items-center">
                          <div>
                            <div className="font-medium text-gray-900">{league.name}</div>
                            <div className="text-sm text-gray-500">
                              {league.platform.toUpperCase()} • {league.scoring_format} • {league.season}
                            </div>
                          </div>
                          <div className="text-xs text-blue-600">Import</div>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-gray-600">
                    No connected leagues found. Connect a league first to import your roster.
                  </div>
                )}
              </div>
            )}

            <div className="space-y-3 max-h-96 overflow-y-auto">
              {roster.map((player, index) => (
                <div key={index} className="flex items-center gap-2 p-3 bg-gray-50 rounded-md">
                  <input
                    type="text"
                    placeholder="Player name"
                    value={player.player_name}
                    onChange={(e) => updateRosterPlayer(index, 'player_name', e.target.value)}
                    className="flex-1 text-sm border-gray-300 rounded-md"
                  />
                  <select
                    value={player.position}
                    onChange={(e) => updateRosterPlayer(index, 'position', e.target.value)}
                    className="text-sm border-gray-300 rounded-md"
                  >
                    <option value="QB">QB</option>
                    <option value="RB">RB</option>
                    <option value="WR">WR</option>
                    <option value="TE">TE</option>
                    <option value="K">K</option>
                    <option value="DEF">DEF</option>
                  </select>
                  <input
                    type="text"
                    placeholder="Team"
                    value={player.team}
                    onChange={(e) => updateRosterPlayer(index, 'team', e.target.value)}
                    className="w-16 text-sm border-gray-300 rounded-md"
                  />
                  <input
                    type="number"
                    placeholder="Rd"
                    value={player.round || ''}
                    onChange={(e) => updateRosterPlayer(index, 'round', parseInt(e.target.value))}
                    className="w-16 text-sm border-gray-300 rounded-md"
                  />
                  <button
                    onClick={() => removePlayerFromRoster(index)}
                    className="text-red-600 hover:text-red-800 text-sm"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-2 mt-4">
              <button
                onClick={analyzeRoster}
                disabled={loading || roster.length === 0}
                className="flex-1 bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Analyzing...' : 'Analyze Roster'}
              </button>
              <button
                onClick={getPersonalizedWaivers}
                disabled={loading || roster.length === 0}
                className="flex-1 bg-green-600 text-white py-2 px-4 rounded-md hover:bg-green-700 disabled:opacity-50"
              >
                Get Waiver Targets
              </button>
            </div>
          </div>

          {/* Week Selector */}
          <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Current Week
            </label>
            <select
              value={currentWeek}
              onChange={(e) => setCurrentWeek(parseInt(e.target.value))}
              className="w-full rounded-md border-gray-300"
            >
              {Array.from({length: 18}, (_, i) => (
                <option key={i + 1} value={i + 1}>Week {i + 1}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Analysis Results */}
        <div className="space-y-6">
          {/* Roster Grade */}
          {analysis?.overall_grade && (
            <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
              <div className="flex items-center mb-4">
                <AcademicCapIcon className="h-6 w-6 mr-2 text-purple-600" />
                <h2 className="text-xl font-semibold">Roster Grade</h2>
              </div>
              
              <div className="text-center mb-4">
                <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full text-2xl font-bold ${getGradeColor(analysis.overall_grade.grade)}`}>
                  {analysis.overall_grade.grade}
                </div>
                <p className="text-lg font-medium text-gray-900 mt-2">
                  {analysis.overall_grade.description}
                </p>
                <p className="text-sm text-gray-600">
                  Score: {analysis.overall_grade.score}/100
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="bg-gray-50 rounded p-3">
                  <div className="text-gray-600">Players</div>
                  <div className="font-medium">{analysis.overall_grade.player_count}</div>
                </div>
                <div className="bg-gray-50 rounded p-3">
                  <div className="text-gray-600">Avg Value</div>
                  <div className="font-medium">{analysis.overall_grade.avg_player_value}</div>
                </div>
              </div>
            </div>
          )}

          {/* Strengths & Weaknesses */}
          {analysis?.strengths_weaknesses && (
            <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
              <div className="flex items-center mb-4">
                <ChartBarIcon className="h-6 w-6 mr-2 text-indigo-600" />
                <h2 className="text-xl font-semibold">Roster Analysis</h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Strengths */}
                <div>
                  <h3 className="font-medium text-green-800 mb-3 flex items-center">
                    <ShieldCheckIcon className="h-5 w-5 mr-1" />
                    Strengths
                  </h3>
                  <div className="space-y-2">
                    {analysis.strengths_weaknesses.strengths?.map((strength: string, index: number) => (
                      <div key={index} className="flex items-start">
                        <ArrowTrendingUpIcon className="h-4 w-4 text-green-600 mt-0.5 mr-2 flex-shrink-0" />
                        <span className="text-sm text-gray-700">{strength}</span>
                      </div>
                    ))}
                    {(!analysis.strengths_weaknesses.strengths || analysis.strengths_weaknesses.strengths.length === 0) && (
                      <p className="text-sm text-gray-500 italic">No major strengths identified</p>
                    )}
                  </div>
                </div>

                {/* Weaknesses */}
                <div>
                  <h3 className="font-medium text-red-800 mb-3 flex items-center">
                    <ExclamationTriangleIcon className="h-5 w-5 mr-1" />
                    Areas for Improvement
                  </h3>
                  <div className="space-y-2">
                    {analysis.strengths_weaknesses.weaknesses?.map((weakness: string, index: number) => (
                      <div key={index} className="flex items-start">
                        <ArrowTrendingDownIcon className="h-4 w-4 text-red-600 mt-0.5 mr-2 flex-shrink-0" />
                        <span className="text-sm text-gray-700">{weakness}</span>
                      </div>
                    ))}
                    {(!analysis.strengths_weaknesses.weaknesses || analysis.strengths_weaknesses.weaknesses.length === 0) && (
                      <p className="text-sm text-green-600 italic">No major weaknesses identified</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Personalized Waiver Targets */}
          {waiverTargets.length > 0 && (
            <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold flex items-center">
                  <FireIcon className="h-6 w-6 mr-2 text-orange-600" />
                  Personalized Waiver Targets
                </h2>
                <span className="text-sm text-gray-500">Week {currentWeek}</span>
              </div>

              <div className="space-y-3">
                {waiverTargets.slice(0, 8).map((target, index) => (
                  <div key={index} className="p-4 border border-gray-200 rounded-lg hover:border-blue-300 transition-colors">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{target.player_name}</span>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPriorityColor(target.adjusted_priority)}`}>
                          {target.position} - {target.team}
                        </span>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPriorityColor(target.adjusted_priority)}`}>
                          {target.adjusted_priority}% Priority
                        </span>
                      </div>
                      <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                        {target.roster_fit}
                      </span>
                    </div>
                    
                    <p className="text-sm text-gray-700 mb-2">
                      <strong>Why for your roster:</strong> {target.personalized_reasoning}
                    </p>
                    
                    <p className="text-xs text-gray-600">
                      <strong>Analysis:</strong> {target.reason}
                    </p>
                  </div>
                ))}
              </div>

              <button
                onClick={getPersonalizedWaivers}
                className="w-full mt-4 bg-orange-600 text-white py-2 px-4 rounded-md hover:bg-orange-700"
              >
                Refresh Waiver Targets
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Player Evaluations */}
      {analysis?.player_evaluations && (
        <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
          <div className="flex items-center mb-6">
            <TrophyIcon className="h-6 w-6 mr-2 text-yellow-600" />
            <h2 className="text-xl font-semibold">Individual Player Analysis</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {analysis.player_evaluations.map((evaluation, index: number) => (
              <div key={index} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-gray-900">{evaluation.player_info.name}</h3>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${getGradeColor(evaluation.value_analysis.value_grade)}`}>
                    {evaluation.value_analysis.value_grade}
                  </span>
                </div>
                
                <div className="text-sm text-gray-600 space-y-1">
                  <p><strong>Position:</strong> {evaluation.player_info.position} - {evaluation.player_info.team}</p>
                  <p><strong>Draft:</strong> Round {evaluation.player_info.draft_round}</p>
                  <p><strong>Value:</strong> {evaluation.value_analysis.value_category}</p>
                  <p><strong>Outlook:</strong> {evaluation.season_outlook.outlook}</p>
                  <p><strong>Risk:</strong> {evaluation.risk_assessment.risk_level}</p>
                </div>

                {(evaluation.risk_assessment.risk_factors?.length ?? 0) > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <p className="text-xs text-gray-500 font-medium mb-1">Risk Factors:</p>
                    <ul className="text-xs text-gray-600 space-y-1">
                      {evaluation.risk_assessment.risk_factors?.slice(0, 2).map((factor: string, i: number) => (
                        <li key={i}>• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="text-center">
        <button
          onClick={() => {
            analyzeRoster()
            getPersonalizedWaivers()
          }}
          disabled={loading || roster.length === 0}
          className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-8 py-3 rounded-lg hover:from-blue-700 hover:to-purple-700 disabled:opacity-50 font-medium"
        >
          {loading ? 'Analyzing...' : 'Complete Analysis'}
        </button>
      </div>
    </div>
  )
}
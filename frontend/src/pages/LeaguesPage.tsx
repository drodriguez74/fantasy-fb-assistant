import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { leagues, getErrorMessage } from '../services/api'
import { useAuth } from '../hooks/useAuth'

interface League {
  id: number
  platform: string
  league_name: string
  league_key?: string
  season: number
  scoring_format?: string
  league_size?: number
  is_commissioner: boolean
  is_active: boolean
  added_at: string
  team_id?: string | null
}

interface TeamOption {
  team_id: string
  team_name?: string
  owner?: string
}

export function LeaguesPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [userLeagues, setUserLeagues] = useState<League[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [connecting, setConnecting] = useState(false)

  // ESPN connect flow: form -> pick-team -> connected. The team pick step
  // exists because the connect call alone never captured *which* team in
  // the league is the user's own, leaving team_id permanently null and
  // blocking roster/matchup analysis downstream.
  const [showEspnModal, setShowEspnModal] = useState(false)
  const [espnStep, setEspnStep] = useState<'form' | 'pick-team'>('form')
  const [espnForm, setEspnForm] = useState({
    leagueId: '',
    season: 2025,
    swid: '',
    espnS2: ''
  })
  const [espnTeams, setEspnTeams] = useState<TeamOption[]>([])
  const [selectedEspnTeamId, setSelectedEspnTeamId] = useState('')
  const [testingConnection, setTestingConnection] = useState(false)
  const [loadingTeams, setLoadingTeams] = useState(false)

  // Sleeper connect flow. Sleeper's API is public (no OAuth/cookies), so
  // there was previously no connect UI for it at all -- this mirrors the
  // ESPN form -> pick-team -> connected shape for consistency.
  const [showSleeperModal, setShowSleeperModal] = useState(false)
  const [sleeperStep, setSleeperStep] = useState<'form' | 'pick-team'>('form')
  const [sleeperForm, setSleeperForm] = useState({ leagueId: '', username: '' })
  const [sleeperTeams, setSleeperTeams] = useState<TeamOption[]>([])
  const [selectedSleeperTeamId, setSelectedSleeperTeamId] = useState('')

  // Quick fallback for leagues connected before this fix (or connected
  // without picking a team): let the user type their team ID directly
  // rather than having to disconnect and reconnect.
  const [settingTeamForLeagueId, setSettingTeamForLeagueId] = useState<number | null>(null)
  const [manualTeamId, setManualTeamId] = useState('')

  useEffect(() => {
    if (user) {
      loadUserLeagues()
    }
  }, [user])

  const loadUserLeagues = async () => {
    try {
      setLoading(true)
      const response = await leagues.getAll()
      setUserLeagues(response.data || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load leagues'))
    } finally {
      setLoading(false)
    }
  }

  const connectYahooLeague = async () => {
    try {
      setConnecting(true)
      setError('')
      
      // Get Yahoo auth URL
      const authResponse = await leagues.getYahooAuthUrl()
      const authUrl = authResponse.data.auth_url
      
      // Open Yahoo OAuth in new window
      window.open(authUrl, 'yahooAuth', 'width=600,height=700')
      
      // Listen for the callback
      const handleCallback = (event: MessageEvent) => {
        if (event.data.type === 'YAHOO_AUTH_SUCCESS') {
          window.removeEventListener('message', handleCallback)
          handleYahooCallback(event.data.code)
        } else if (event.data.type === 'YAHOO_AUTH_ERROR') {
          window.removeEventListener('message', handleCallback)
          setError('Yahoo authentication failed')
          setConnecting(false)
        }
      }
      
      window.addEventListener('message', handleCallback)
      
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to start Yahoo connection'))
      setConnecting(false)
    }
  }

  const handleYahooCallback = async (authorizationCode: string) => {
    try {
      const response = await leagues.connectYahoo(authorizationCode)
      
      if (response.data.success) {
        await loadUserLeagues()
        setConnecting(false)
      } else {
        setError('Failed to connect Yahoo leagues')
        setConnecting(false)
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to connect Yahoo leagues'))
      setConnecting(false)
    }
  }

  const disconnectLeague = async (leagueId: number) => {
    if (!confirm('Are you sure you want to disconnect this league?')) return

    try {
      await leagues.disconnect(leagueId)
      await loadUserLeagues()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to disconnect league'))
    }
  }

  const testEspnConnection = async () => {
    if (!espnForm.leagueId) {
      setError('Please enter an ESPN League ID')
      return
    }

    try {
      setTestingConnection(true)
      setError('')
      
      const response = await leagues.testEspnConnection(
        espnForm.leagueId,
        espnForm.season,
        espnForm.swid || undefined,
        espnForm.espnS2 || undefined
      )
      
      if (response.data.connected) {
        setError('')
        // Show success message or automatically proceed to connect
        return true
      } else {
        setError(response.data.error || 'Failed to connect to ESPN league')
        return false
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to test ESPN connection'))
      return false
    } finally {
      setTestingConnection(false)
    }
  }

  // Step 1 -> 2: validate the connection, then load the league's teams so
  // the user can pick which one is theirs before we persist anything.
  const proceedToEspnTeamPick = async () => {
    const connectionTest = await testEspnConnection()
    if (!connectionTest) return

    try {
      setLoadingTeams(true)
      setError('')
      const response = await leagues.getEspnTeams(
        espnForm.leagueId,
        espnForm.season,
        espnForm.swid || undefined,
        espnForm.espnS2 || undefined
      )
      setEspnTeams(response.data.teams || [])
      setSelectedEspnTeamId('')
      setEspnStep('pick-team')
    } catch (err) {
      // Team lookup failing shouldn't block connecting the league entirely --
      // fall through to the picker with an empty list so the user can still
      // skip and connect without a team selected.
      setEspnTeams([])
      setEspnStep('pick-team')
      setError(getErrorMessage(err, 'Could not load teams for this league; you can still connect and set your team later'))
    } finally {
      setLoadingTeams(false)
    }
  }

  const connectEspnLeague = async () => {
    try {
      setConnecting(true)
      setError('')

      const response = await leagues.connectEspn(
        espnForm.leagueId,
        espnForm.season,
        espnForm.swid || undefined,
        espnForm.espnS2 || undefined,
        selectedEspnTeamId || undefined
      )

      if (response.data.success) {
        await loadUserLeagues()
        closeEspnModal()
      } else {
        setError('Failed to connect ESPN league')
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to connect ESPN league'))
    } finally {
      setConnecting(false)
    }
  }

  const closeEspnModal = () => {
    setShowEspnModal(false)
    setEspnStep('form')
    setEspnForm({ leagueId: '', season: 2025, swid: '', espnS2: '' })
    setEspnTeams([])
    setSelectedEspnTeamId('')
  }

  const closeSleeperModal = () => {
    setShowSleeperModal(false)
    setSleeperStep('form')
    setSleeperForm({ leagueId: '', username: '' })
    setSleeperTeams([])
    setSelectedSleeperTeamId('')
  }

  const proceedToSleeperTeamPick = async () => {
    if (!sleeperForm.leagueId) {
      setError('Please enter a Sleeper League ID')
      return
    }

    try {
      setLoadingTeams(true)
      setError('')
      const response = await leagues.getSleeperTeams(sleeperForm.leagueId, sleeperForm.username || undefined)
      setSleeperTeams(response.data.teams || [])
      setSelectedSleeperTeamId(response.data.suggested_team_id || '')
      setSleeperStep('pick-team')
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to find that Sleeper league'))
    } finally {
      setLoadingTeams(false)
    }
  }

  const connectSleeperLeague = async () => {
    try {
      setConnecting(true)
      setError('')

      const response = await leagues.connectSleeper(
        sleeperForm.leagueId,
        selectedSleeperTeamId || undefined,
        sleeperForm.username || undefined
      )

      if (response.data.success) {
        await loadUserLeagues()
        closeSleeperModal()
      } else {
        setError('Failed to connect Sleeper league')
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to connect Sleeper league'))
    } finally {
      setConnecting(false)
    }
  }

  const startSettingTeamId = (league: League) => {
    setSettingTeamForLeagueId(league.id)
    setManualTeamId(league.team_id || '')
  }

  const saveManualTeamId = async (leagueId: number) => {
    if (!manualTeamId.trim()) return
    try {
      setError('')
      await leagues.updateSettings(leagueId, { team_id: manualTeamId.trim() })
      setSettingTeamForLeagueId(null)
      setManualTeamId('')
      await loadUserLeagues()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to set team ID'))
    }
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <p className="text-ink-500">Please log in to manage your fantasy leagues.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-ink-900">My Fantasy Leagues</h1>
          <p className="text-ink-600 mt-2">
            Connect your fantasy leagues to get AI-powered insights
          </p>
        </div>

        <div className="flex space-x-3">
          <button
            onClick={connectYahooLeague}
            disabled={connecting}
            className="inline-flex items-center space-x-2 rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-sm transition-colors hover:bg-ink-50 disabled:opacity-50"
          >
            {connecting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-ink-400"></div>
                <span>Connecting...</span>
              </>
            ) : (
              <>
                <span className="flex h-5 w-5 items-center justify-center rounded bg-[#6001d2] text-[11px] font-bold text-white">Y!</span>
                <span>Yahoo</span>
              </>
            )}
          </button>

          <button
            onClick={() => setShowEspnModal(true)}
            disabled={connecting}
            className="inline-flex items-center space-x-2 rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-sm transition-colors hover:bg-ink-50 disabled:opacity-50"
          >
            <span className="flex h-5 w-5 items-center justify-center rounded bg-[#d00e35] text-[9px] font-bold text-white">ESPN</span>
            <span>Connect</span>
          </button>

          <button
            onClick={() => setShowSleeperModal(true)}
            disabled={connecting}
            className="inline-flex items-center space-x-2 rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-sm transition-colors hover:bg-ink-50 disabled:opacity-50"
          >
            <span className="flex h-5 w-5 items-center justify-center rounded bg-[#00ceb8] text-[9px] font-bold text-white">SL</span>
            <span>Sleeper</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-danger-50 border border-danger-200 text-danger-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {userLeagues.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <div className="text-ink-400 text-6xl mb-4">🏈</div>
              <h3 className="text-xl font-semibold text-ink-900 mb-2">No Leagues Connected</h3>
              <p className="text-ink-500 mb-6">
                Connect your fantasy leagues from Yahoo, ESPN, or Sleeper to get started with AI-powered analysis
              </p>
              <div className="flex space-x-3 justify-center">
                <button
                  onClick={connectYahooLeague}
                  disabled={connecting}
                  className="inline-flex items-center space-x-2 rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-sm transition-colors hover:bg-ink-50 disabled:opacity-50"
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded bg-[#6001d2] text-[11px] font-bold text-white">Y!</span>
                  <span>Yahoo</span>
                </button>
                <button
                  onClick={() => setShowEspnModal(true)}
                  disabled={connecting}
                  className="inline-flex items-center space-x-2 rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-sm transition-colors hover:bg-ink-50 disabled:opacity-50"
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded bg-[#d00e35] text-[9px] font-bold text-white">ESPN</span>
                  <span>Connect</span>
                </button>
                <button
                  onClick={() => setShowSleeperModal(true)}
                  disabled={connecting}
                  className="inline-flex items-center space-x-2 rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-900 shadow-sm transition-colors hover:bg-ink-50 disabled:opacity-50"
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded bg-[#00ceb8] text-[9px] font-bold text-white">SL</span>
                  <span>Sleeper</span>
                </button>
              </div>
            </div>
          ) : (
            userLeagues.map((league) => (
              <div
                key={league.id}
                className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center space-x-2">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      league.platform === 'YAHOO' ? 'bg-[#6001d2]' :
                      league.platform === 'ESPN' ? 'bg-[#d00e35]' :
                      league.platform === 'SLEEPER' ? 'bg-[#00ceb8]' : 'bg-ink-100'
                    }`}>
                      {league.platform === 'YAHOO' ? (
                        <span className="text-white font-bold">Y!</span>
                      ) : league.platform === 'ESPN' ? (
                        <span className="text-white font-bold text-xs">ESPN</span>
                      ) : league.platform === 'SLEEPER' ? (
                        <span className="text-white font-bold text-xs">SL</span>
                      ) : (
                        <span className="text-ink-600">🏈</span>
                      )}
                    </div>
                    <div>
                      <h3 className="font-semibold text-ink-900">{league.league_name}</h3>
                      <p className="text-sm text-ink-500">{league.platform} • {league.season}</p>
                    </div>
                  </div>

                  {league.is_commissioner && (
                    <span className="px-2 py-1 text-xs font-medium bg-accent-100 text-accent-800 rounded-full">
                      Commissioner
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                  <div>
                    <span className="text-ink-500">Teams:</span>
                    <span className="ml-1 font-medium text-ink-900">{league.league_size || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-ink-500">Scoring:</span>
                    <span className="ml-1 font-medium text-ink-900">{league.scoring_format || 'Standard'}</span>
                  </div>
                </div>

                {!league.team_id && (league.platform === 'ESPN' || league.platform === 'SLEEPER') && (
                  <div className="mb-4 rounded-md border border-warning-200 bg-warning-50 px-3 py-2 text-sm">
                    {settingTeamForLeagueId === league.id ? (
                      <div className="flex items-center space-x-2">
                        <input
                          type="text"
                          value={manualTeamId}
                          onChange={(e) => setManualTeamId(e.target.value)}
                          placeholder="Your team ID"
                          className="min-w-0 flex-1 rounded border border-ink-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
                        />
                        <button
                          onClick={() => saveManualTeamId(league.id)}
                          className="rounded bg-accent-500 px-2 py-1 text-xs font-medium text-white hover:bg-accent-600"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setSettingTeamForLeagueId(null)}
                          className="text-xs text-ink-500 hover:text-ink-700"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between">
                        <span className="text-warning-800">Team not set -- roster &amp; matchup analysis need this</span>
                        <button
                          onClick={() => startSettingTeamId(league)}
                          className="ml-2 whitespace-nowrap text-xs font-medium text-accent-700 hover:text-accent-900 underline"
                        >
                          Set team ID
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <div className="flex space-x-2">
                  <button
                    onClick={() => navigate(`/leagues/${league.id}`)}
                    className="flex-1 bg-accent-500 text-white px-3 py-2 rounded text-sm hover:bg-accent-600 transition-colors"
                  >
                    View Analysis
                  </button>
                  <button
                    onClick={() => navigate(`/leagues/${league.id}?tab=standings`)}
                    className="flex-1 bg-ink-100 text-ink-700 px-3 py-2 rounded text-sm hover:bg-ink-200 transition-colors"
                  >
                    Standings
                  </button>
                  <button
                    onClick={() => disconnectLeague(league.id)}
                    className="px-3 py-2 bg-danger-100 text-danger-600 rounded text-sm hover:bg-danger-200 transition-colors"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Instructions */}
      <div className="bg-accent-50 border border-accent-200 rounded-lg p-6">
        <h3 className="font-semibold text-accent-900 mb-2">🤖 AI-Powered League Analysis</h3>
        <p className="text-accent-800 text-sm">
          Once connected, you'll get personalized insights including roster analysis,
          start/sit recommendations, waiver wire targets, and trade suggestions powered by AI.
          Works with Yahoo Fantasy, ESPN Fantasy Football, and Sleeper leagues.
        </p>
      </div>

      {/* ESPN Connection Modal */}
      {showEspnModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-ink-900">Connect ESPN League</h3>
              <button
                onClick={closeEspnModal}
                className="text-ink-400 hover:text-ink-600"
              >
                ✕
              </button>
            </div>

            {espnStep === 'form' ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink-700 mb-1">
                    League ID <span className="text-danger-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={espnForm.leagueId}
                    onChange={(e) => setEspnForm(prev => ({ ...prev, leagueId: e.target.value }))}
                    className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                    placeholder="e.g., 123456789"
                  />
                  <p className="text-xs text-ink-500 mt-1">
                    Find this in your ESPN league URL: fantasy.espn.com/.../leagues/{espnForm.leagueId || 'LEAGUE_ID'}
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-700 mb-1">Season</label>
                  <input
                    type="number"
                    value={espnForm.season}
                    onChange={(e) => setEspnForm(prev => ({ ...prev, season: parseInt(e.target.value) }))}
                    className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                    min="2020"
                    max="2026"
                  />
                </div>

                <div className="border-t border-ink-200 pt-4">
                  <h4 className="font-medium text-ink-900 mb-2">Private League Access (Optional)</h4>
                  <p className="text-xs text-ink-500 mb-3">
                    Only needed for private leagues. Find these cookies in your browser when logged into ESPN.
                  </p>

                  <div className="space-y-3">
                    <div>
                      <label className="block text-sm font-medium text-ink-700 mb-1">SWID</label>
                      <input
                        type="text"
                        value={espnForm.swid}
                        onChange={(e) => setEspnForm(prev => ({ ...prev, swid: e.target.value }))}
                        className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                        placeholder="Optional - for private leagues"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-ink-700 mb-1">ESPN_S2</label>
                      <input
                        type="text"
                        value={espnForm.espnS2}
                        onChange={(e) => setEspnForm(prev => ({ ...prev, espnS2: e.target.value }))}
                        className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                        placeholder="Optional - for private leagues"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex space-x-3 pt-4">
                  <button
                    onClick={proceedToEspnTeamPick}
                    disabled={connecting || testingConnection || loadingTeams || !espnForm.leagueId}
                    className="flex-1 bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                  >
                    {testingConnection || loadingTeams ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        <span>{testingConnection ? 'Testing...' : 'Loading teams...'}</span>
                      </>
                    ) : (
                      <span>Continue</span>
                    )}
                  </button>
                  <button
                    onClick={closeEspnModal}
                    className="px-4 py-2 text-ink-600 border border-ink-300 rounded-md hover:bg-ink-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink-700 mb-1">
                    Which team is yours?
                  </label>
                  {espnTeams.length > 0 ? (
                    <select
                      value={selectedEspnTeamId}
                      onChange={(e) => setSelectedEspnTeamId(e.target.value)}
                      className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                    >
                      <option value="">I'll set this later</option>
                      {espnTeams.map((team) => (
                        <option key={team.team_id} value={team.team_id}>
                          {team.team_name}{team.owner ? ` (${team.owner})` : ''}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <p className="text-sm text-ink-500">
                      Couldn't load the team list for this league. You can still connect and set your team ID later.
                    </p>
                  )}
                  <p className="text-xs text-ink-500 mt-1">
                    This tells the assistant which roster is yours, so roster and matchup analysis work.
                  </p>
                </div>

                <div className="flex space-x-3 pt-4">
                  <button
                    onClick={connectEspnLeague}
                    disabled={connecting}
                    className="flex-1 bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                  >
                    {connecting ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        <span>Connecting...</span>
                      </>
                    ) : (
                      <span>Connect League</span>
                    )}
                  </button>
                  <button
                    onClick={() => setEspnStep('form')}
                    className="px-4 py-2 text-ink-600 border border-ink-300 rounded-md hover:bg-ink-50"
                  >
                    Back
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sleeper Connection Modal */}
      {showSleeperModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-ink-900">Connect Sleeper League</h3>
              <button
                onClick={closeSleeperModal}
                className="text-ink-400 hover:text-ink-600"
              >
                ✕
              </button>
            </div>

            {sleeperStep === 'form' ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink-700 mb-1">
                    League ID <span className="text-danger-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={sleeperForm.leagueId}
                    onChange={(e) => setSleeperForm(prev => ({ ...prev, leagueId: e.target.value }))}
                    className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                    placeholder="e.g., 987654321012345678"
                  />
                  <p className="text-xs text-ink-500 mt-1">
                    Find this in your Sleeper league URL, or in the app under League Settings.
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink-700 mb-1">
                    Your Sleeper Username (Optional)
                  </label>
                  <input
                    type="text"
                    value={sleeperForm.username}
                    onChange={(e) => setSleeperForm(prev => ({ ...prev, username: e.target.value }))}
                    className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                    placeholder="Optional - helps us auto-detect your team"
                  />
                  <p className="text-xs text-ink-500 mt-1">
                    Sleeper's data is public, so no password or login is needed -- just the league ID.
                  </p>
                </div>

                <div className="flex space-x-3 pt-4">
                  <button
                    onClick={proceedToSleeperTeamPick}
                    disabled={connecting || loadingTeams || !sleeperForm.leagueId}
                    className="flex-1 bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                  >
                    {loadingTeams ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        <span>Looking up league...</span>
                      </>
                    ) : (
                      <span>Continue</span>
                    )}
                  </button>
                  <button
                    onClick={closeSleeperModal}
                    className="px-4 py-2 text-ink-600 border border-ink-300 rounded-md hover:bg-ink-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink-700 mb-1">
                    Which team is yours?
                  </label>
                  {sleeperTeams.length > 0 ? (
                    <select
                      value={selectedSleeperTeamId}
                      onChange={(e) => setSelectedSleeperTeamId(e.target.value)}
                      className="w-full px-3 py-2 border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500"
                    >
                      <option value="">I'll set this later</option>
                      {sleeperTeams.map((team) => (
                        <option key={team.team_id} value={team.team_id}>
                          {team.team_name}{team.owner ? ` (${team.owner})` : ''}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <p className="text-sm text-ink-500">
                      Couldn't load the team list for this league. You can still connect and set your team ID later.
                    </p>
                  )}
                  <p className="text-xs text-ink-500 mt-1">
                    This tells the assistant which roster is yours, so roster and matchup analysis work.
                  </p>
                </div>

                <div className="flex space-x-3 pt-4">
                  <button
                    onClick={connectSleeperLeague}
                    disabled={connecting}
                    className="flex-1 bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                  >
                    {connecting ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        <span>Connecting...</span>
                      </>
                    ) : (
                      <span>Connect League</span>
                    )}
                  </button>
                  <button
                    onClick={() => setSleeperStep('form')}
                    className="px-4 py-2 text-ink-600 border border-ink-300 rounded-md hover:bg-ink-50"
                  >
                    Back
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
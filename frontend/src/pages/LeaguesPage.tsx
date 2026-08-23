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
}

export function LeaguesPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [userLeagues, setUserLeagues] = useState<League[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [showEspnModal, setShowEspnModal] = useState(false)
  const [espnForm, setEspnForm] = useState({
    leagueId: '',
    season: 2025,
    swid: '',
    espnS2: ''
  })
  const [testingConnection, setTestingConnection] = useState(false)

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
      const popup = window.open(authUrl, 'yahooAuth', 'width=600,height=700')

      if (!popup) {
        // window.open returned null -- almost always a browser popup blocker.
        setError('Your browser blocked the Yahoo sign-in popup. Please allow popups for this site and try again.')
        setConnecting(false)
        return
      }

      // Listen for the callback
      const handleCallback = (event: MessageEvent) => {
        if (event.data.type === 'YAHOO_AUTH_SUCCESS') {
          cleanup()
          handleYahooCallback(event.data.code)
        } else if (event.data.type === 'YAHOO_AUTH_ERROR') {
          cleanup()
          setError('Yahoo authentication failed')
          setConnecting(false)
        }
      }

      // If the popup lands on a page we don't control (e.g. Yahoo's own
      // OAuth error page for a misconfigured client_id/redirect_uri) it
      // never reaches our /yahoo/callback route, so postMessage never
      // fires. Without this, the popup being closed -- by the user, or
      // because Yahoo itself dead-ends the flow -- left `connecting` stuck
      // true forever, with the Yahoo/ESPN buttons disabled until a full
      // page reload.
      const closedPoll = window.setInterval(() => {
        if (popup.closed) {
          cleanup()
          setError('Yahoo sign-in was closed before it completed. Please try again.')
          setConnecting(false)
        }
      }, 500)

      function cleanup() {
        window.removeEventListener('message', handleCallback)
        window.clearInterval(closedPoll)
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

  const connectEspnLeague = async () => {
    const connectionTest = await testEspnConnection()
    if (!connectionTest) return

    try {
      setConnecting(true)
      setError('')
      
      const response = await leagues.connectEspn(
        espnForm.leagueId,
        espnForm.season,
        espnForm.swid || undefined,
        espnForm.espnS2 || undefined
      )
      
      if (response.data.success) {
        await loadUserLeagues()
        setShowEspnModal(false)
        setEspnForm({ leagueId: '', season: 2024, swid: '', espnS2: '' })
      } else {
        setError('Failed to connect ESPN league')
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to connect ESPN league'))
    } finally {
      setConnecting(false)
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
            Connect your fantasy leagues to get personalized insights
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
                Connect your fantasy leagues from Yahoo or ESPN to get started with personalized analysis
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
                      league.platform === 'ESPN' ? 'bg-[#d00e35]' : 'bg-ink-100'
                    }`}>
                      {league.platform === 'YAHOO' ? (
                        <span className="text-white font-bold">Y!</span>
                      ) : league.platform === 'ESPN' ? (
                        <span className="text-white font-bold text-xs">ESPN</span>
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
        <h3 className="font-semibold text-accent-900 mb-2">📊 League Analysis</h3>
        <p className="text-accent-800 text-sm">
          Once connected, you'll get personalized insights including roster analysis,
          start/sit recommendations, waiver wire targets, and trade suggestions based on
          your roster and league data. Works with both Yahoo Fantasy and ESPN Fantasy
          Football leagues.
        </p>
      </div>

      {/* ESPN Connection Modal */}
      {showEspnModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-ink-900">Connect ESPN League</h3>
              <button
                onClick={() => setShowEspnModal(false)}
                className="text-ink-400 hover:text-ink-600"
              >
                ✕
              </button>
            </div>

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
                  onClick={connectEspnLeague}
                  disabled={connecting || testingConnection || !espnForm.leagueId}
                  className="flex-1 bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
                >
                  {connecting || testingConnection ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>{testingConnection ? 'Testing...' : 'Connecting...'}</span>
                    </>
                  ) : (
                    <span>Connect League</span>
                  )}
                </button>
                <button
                  onClick={() => setShowEspnModal(false)}
                  className="px-4 py-2 text-ink-600 border border-ink-300 rounded-md hover:bg-ink-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
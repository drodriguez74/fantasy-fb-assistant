import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { leagues } from '../services/api'
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load leagues')
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
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start Yahoo connection')
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to connect Yahoo leagues')
      setConnecting(false)
    }
  }

  const disconnectLeague = async (leagueId: number) => {
    if (!confirm('Are you sure you want to disconnect this league?')) return

    try {
      await leagues.disconnect(leagueId)
      await loadUserLeagues()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to disconnect league')
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to test ESPN connection')
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to connect ESPN league')
    } finally {
      setConnecting(false)
    }
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Please log in to manage your fantasy leagues.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">My Fantasy Leagues</h1>
          <p className="text-gray-600 mt-2">
            Connect your fantasy leagues to get AI-powered insights
          </p>
        </div>
        
        <div className="flex space-x-3">
          <button
            onClick={connectYahooLeague}
            disabled={connecting}
            className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center space-x-2"
          >
            {connecting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                <span>Connecting...</span>
              </>
            ) : (
              <>
                <span className="font-bold">Y!</span>
                <span>Yahoo</span>
              </>
            )}
          </button>
          
          <button
            onClick={() => setShowEspnModal(true)}
            disabled={connecting}
            className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center space-x-2"
          >
            <span className="font-bold">ESPN</span>
            <span>Connect</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {userLeagues.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <div className="text-gray-400 text-6xl mb-4">🏈</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">No Leagues Connected</h3>
              <p className="text-gray-500 mb-6">
                Connect your fantasy leagues from Yahoo or ESPN to get started with AI-powered analysis
              </p>
              <div className="flex space-x-3 justify-center">
                <button
                  onClick={connectYahooLeague}
                  disabled={connecting}
                  className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center space-x-2"
                >
                  <span className="font-bold">Y!</span>
                  <span>Yahoo</span>
                </button>
                <button
                  onClick={() => setShowEspnModal(true)}
                  disabled={connecting}
                  className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center space-x-2"
                >
                  <span className="font-bold">ESPN</span>
                  <span>Connect</span>
                </button>
              </div>
            </div>
          ) : (
            userLeagues.map((league) => (
              <div
                key={league.id}
                className="bg-white rounded-lg shadow-sm border p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center space-x-2">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      league.platform === 'YAHOO' ? 'bg-purple-100' :
                      league.platform === 'ESPN' ? 'bg-red-100' : 'bg-gray-100'
                    }`}>
                      {league.platform === 'YAHOO' ? (
                        <span className="text-purple-600 font-bold">Y!</span>
                      ) : league.platform === 'ESPN' ? (
                        <span className="text-red-600 font-bold text-xs">ESPN</span>
                      ) : (
                        <span className="text-gray-600">🏈</span>
                      )}
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">{league.league_name}</h3>
                      <p className="text-sm text-gray-500">{league.platform} • {league.season}</p>
                    </div>
                  </div>
                  
                  {league.is_commissioner && (
                    <span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full">
                      Commissioner
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                  <div>
                    <span className="text-gray-500">Teams:</span>
                    <span className="ml-1 font-medium">{league.league_size || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Scoring:</span>
                    <span className="ml-1 font-medium">{league.scoring_format || 'Standard'}</span>
                  </div>
                </div>

                <div className="flex space-x-2">
                  <button
                    onClick={() => navigate(`/leagues/${league.id}`)}
                    className="flex-1 bg-blue-600 text-white px-3 py-2 rounded text-sm hover:bg-blue-700"
                  >
                    View Analysis
                  </button>
                  <button
                    onClick={() => navigate(`/leagues/${league.id}?tab=standings`)}
                    className="flex-1 bg-gray-100 text-gray-700 px-3 py-2 rounded text-sm hover:bg-gray-200"
                  >
                    Standings
                  </button>
                  <button
                    onClick={() => disconnectLeague(league.id)}
                    className="px-3 py-2 bg-red-100 text-red-600 rounded text-sm hover:bg-red-200"
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
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="font-semibold text-blue-900 mb-2">🤖 AI-Powered League Analysis</h3>
        <p className="text-blue-800 text-sm">
          Once connected, you'll get personalized insights including roster analysis, 
          start/sit recommendations, waiver wire targets, and trade suggestions powered by AI.
          Works with both Yahoo Fantasy and ESPN Fantasy Football leagues.
        </p>
      </div>

      {/* ESPN Connection Modal */}
      {showEspnModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Connect ESPN League</h3>
              <button
                onClick={() => setShowEspnModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  League ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={espnForm.leagueId}
                  onChange={(e) => setEspnForm(prev => ({ ...prev, leagueId: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
                  placeholder="e.g., 123456789"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Find this in your ESPN league URL: fantasy.espn.com/.../leagues/{espnForm.leagueId || 'LEAGUE_ID'}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Season</label>
                <input
                  type="number"
                  value={espnForm.season}
                  onChange={(e) => setEspnForm(prev => ({ ...prev, season: parseInt(e.target.value) }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
                  min="2020"
                  max="2026"
                />
              </div>

              <div className="border-t pt-4">
                <h4 className="font-medium text-gray-900 mb-2">Private League Access (Optional)</h4>
                <p className="text-xs text-gray-500 mb-3">
                  Only needed for private leagues. Find these cookies in your browser when logged into ESPN.
                </p>
                
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">SWID</label>
                    <input
                      type="text"
                      value={espnForm.swid}
                      onChange={(e) => setEspnForm(prev => ({ ...prev, swid: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
                      placeholder="Optional - for private leagues"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">ESPN_S2</label>
                    <input
                      type="text"
                      value={espnForm.espnS2}
                      onChange={(e) => setEspnForm(prev => ({ ...prev, espnS2: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
                      placeholder="Optional - for private leagues"
                    />
                  </div>
                </div>
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  onClick={connectEspnLeague}
                  disabled={connecting || testingConnection || !espnForm.leagueId}
                  className="flex-1 bg-red-600 text-white py-2 px-4 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
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
                  className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
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
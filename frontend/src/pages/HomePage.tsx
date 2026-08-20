import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { leagues as leaguesApi } from '../services/api'
import {
  ChartBarIcon,
  CpuChipIcon,
  DocumentTextIcon,
  UserGroupIcon,
  TrophyIcon,
  SparklesIcon
} from '@heroicons/react/24/outline'

export function HomePage() {
  const { user } = useAuth()
  // Real account state for the "Welcome back" box below, instead of always
  // showing the same static copy regardless of whether this account has
  // ever connected a league. null = still loading / unknown.
  const [leagueCount, setLeagueCount] = useState<number | null>(null)
  const [leagueCountFailed, setLeagueCountFailed] = useState(false)

  useEffect(() => {
    if (!user) return
    let cancelled = false

    leaguesApi.getAll()
      .then((res) => {
        if (!cancelled) setLeagueCount((res.data || []).length)
      })
      .catch(() => {
        if (!cancelled) setLeagueCountFailed(true)
      })

    return () => {
      cancelled = true
    }
  }, [user])

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gray-900 sm:text-6xl">
          Fantasy Football Assistant
        </h1>
        <p className="mt-6 text-lg leading-8 text-gray-600 max-w-2xl mx-auto">
          Your AI-powered companion for dominating your PPR fantasy football league. 
          Get smart draft picks, waiver wire insights, and expert analysis.
        </p>
        <div className="mt-10 flex items-center justify-center gap-x-6">
          {user ? (
            <Link
              to="/draft"
              className="bg-blue-600 text-white px-8 py-3 rounded-md text-lg font-medium hover:bg-blue-700 transition-colors"
            >
              Start Draft Assistant
            </Link>
          ) : (
            <Link
              to="/auth"
              className="bg-blue-600 text-white px-8 py-3 rounded-md text-lg font-medium hover:bg-blue-700 transition-colors"
            >
              Get Started
            </Link>
          )}
          <Link
            to="/players"
            className="border border-gray-300 text-gray-700 px-8 py-3 rounded-md text-lg font-medium hover:bg-gray-50 transition-colors"
          >
            View Players
          </Link>
        </div>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-16">
        <div className="bg-white rounded-lg shadow-sm border p-6 text-center">
          <div className="w-12 h-12 bg-blue-100 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <CpuChipIcon className="h-6 w-6 text-blue-600" />
          </div>
          <h3 className="text-xl font-semibold mb-2">Smart Draft Assistant</h3>
          <p className="text-gray-600">
            AI-powered recommendations optimized for PPR scoring with real-time updates
          </p>
        </div>
        
        <div className="bg-white rounded-lg shadow-sm border p-6 text-center">
          <div className="w-12 h-12 bg-green-100 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <UserGroupIcon className="h-6 w-6 text-green-600" />
          </div>
          <h3 className="text-xl font-semibold mb-2">Platform Integration</h3>
          <p className="text-gray-600">
            Connect to ESPN, Yahoo, Sleeper and more for seamless league management
          </p>
        </div>
        
        <div className="bg-white rounded-lg shadow-sm border p-6 text-center">
          <div className="w-12 h-12 bg-purple-100 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <DocumentTextIcon className="h-6 w-6 text-purple-600" />
          </div>
          <h3 className="text-xl font-semibold mb-2">AI-Powered Content</h3>
          <p className="text-gray-600">
            Multi-perspective analysis and consensus recommendations for waiver picks
          </p>
        </div>
      </div>

      {/* Stats Section */}
      {user && (
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-6">Welcome back, {user.full_name || user.username}!</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <ChartBarIcon className="h-8 w-8 text-blue-600 mx-auto mb-2" />
              <h3 className="text-lg font-semibold">Quick Actions</h3>
              <div className="space-y-2 mt-4">
                <Link to="/draft" className="block text-blue-600 hover:text-blue-800">Start Draft Session</Link>
                <Link to="/players" className="block text-blue-600 hover:text-blue-800">Browse Players</Link>
                <Link to="/blog" className="block text-blue-600 hover:text-blue-800">View Analysis</Link>
              </div>
            </div>
            <div className="text-center">
              <TrophyIcon className="h-8 w-8 text-green-600 mx-auto mb-2" />
              <h3 className="text-lg font-semibold">Your Leagues</h3>
              {leagueCountFailed && (
                <p className="text-gray-600 mt-2">Couldn't load your league status right now.</p>
              )}
              {!leagueCountFailed && leagueCount === null && (
                <p className="text-gray-600 mt-2">Checking your connected leagues&hellip;</p>
              )}
              {!leagueCountFailed && leagueCount !== null && leagueCount > 0 && (
                <>
                  <p className="text-gray-600 mt-2">
                    You have {leagueCount} league{leagueCount === 1 ? '' : 's'} connected.
                  </p>
                  <Link to="/leagues" className="inline-block mt-2 text-blue-600 hover:text-blue-800 font-medium">
                    View your leagues
                  </Link>
                </>
              )}
              {!leagueCountFailed && leagueCount === 0 && (
                <>
                  <p className="text-gray-600 mt-2">
                    Connect a league to get advice based on your actual roster.
                  </p>
                  <Link to="/leagues" className="inline-block mt-2 text-blue-600 hover:text-blue-800 font-medium">
                    Connect your league &rarr;
                  </Link>
                </>
              )}
            </div>
            <div className="text-center">
              <SparklesIcon className="h-8 w-8 text-purple-600 mx-auto mb-2" />
              <h3 className="text-lg font-semibold">AI Insights</h3>
              <p className="text-gray-600 mt-2">Get personalized recommendations and analysis</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
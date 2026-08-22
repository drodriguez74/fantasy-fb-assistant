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
        <h1 className="text-4xl font-bold text-ink-900 sm:text-6xl">
          Win your league. Or at least stop losing to your cousin.
        </h1>
        <p className="mt-6 text-lg leading-8 text-ink-600 max-w-2xl mx-auto">
          AI-backed draft calls, PPR-tuned rankings, and waiver claims for the people who
          actually read the injury report on a Tuesday.
        </p>
        <div className="mt-10 flex items-center justify-center gap-x-6">
          {user ? (
            <Link
              to="/draft"
              className="bg-accent-500 text-white px-8 py-3 rounded-md text-lg font-medium hover:bg-accent-600 transition-colors"
            >
              Start Draft Assistant
            </Link>
          ) : (
            <Link
              to="/auth"
              className="bg-accent-500 text-white px-8 py-3 rounded-md text-lg font-medium hover:bg-accent-600 transition-colors"
            >
              Get Started
            </Link>
          )}
          <Link
            to="/players"
            className="border border-ink-300 text-ink-700 px-8 py-3 rounded-md text-lg font-medium hover:bg-ink-50 transition-colors"
          >
            View Players
          </Link>
        </div>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-16">
        <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 text-center">
          <div className="w-12 h-12 bg-accent-100 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <CpuChipIcon className="h-6 w-6 text-accent-600" />
          </div>
          <h3 className="text-xl font-semibold mb-2 text-ink-900">Draft Assistant</h3>
          <p className="text-ink-600">
            Best-player-available math, but it knows your roster needs before your run of RBs dries up
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 text-center">
          <div className="w-12 h-12 bg-ink-100 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <UserGroupIcon className="h-6 w-6 text-ink-600" />
          </div>
          <h3 className="text-xl font-semibold mb-2 text-ink-900">Platform Integration</h3>
          <p className="text-ink-600">
            Connect ESPN, Yahoo, or Sleeper and pull your real roster in instead of retyping it
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 text-center">
          <div className="w-12 h-12 bg-accent-100 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <DocumentTextIcon className="h-6 w-6 text-accent-600" />
          </div>
          <h3 className="text-xl font-semibold mb-2 text-ink-900">Fantasy Content Library</h3>
          <p className="text-ink-600">
            Rankings and waiver targets built from live data, plus AI-written player deep-dives and injury reports
          </p>
        </div>
      </div>

      {/* Stats Section */}
      {user && (
        <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
          <h2 className="text-2xl font-bold text-ink-900 mb-6">Welcome back, {user.full_name || user.username}!</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <ChartBarIcon className="h-8 w-8 text-accent-600 mx-auto mb-2" />
              <h3 className="text-lg font-semibold text-ink-900">Quick Actions</h3>
              <div className="space-y-2 mt-4">
                <Link to="/draft" className="block text-accent-600 hover:text-accent-800">Start Draft Session</Link>
                <Link to="/players" className="block text-accent-600 hover:text-accent-800">Browse Players</Link>
                <Link to="/blog" className="block text-accent-600 hover:text-accent-800">View Analysis</Link>
              </div>
            </div>
            <div className="text-center">
              <TrophyIcon className="h-8 w-8 text-ink-600 mx-auto mb-2" />
              <h3 className="text-lg font-semibold text-ink-900">Your Leagues</h3>
              {leagueCountFailed && (
                <p className="text-ink-600 mt-2">Couldn't load your league status right now.</p>
              )}
              {!leagueCountFailed && leagueCount === null && (
                <p className="text-ink-600 mt-2">Checking your connected leagues&hellip;</p>
              )}
              {!leagueCountFailed && leagueCount !== null && leagueCount > 0 && (
                <>
                  <p className="text-ink-600 mt-2">
                    You have {leagueCount} league{leagueCount === 1 ? '' : 's'} connected.
                  </p>
                  <Link to="/leagues" className="inline-block mt-2 text-accent-600 hover:text-accent-800 font-medium">
                    View your leagues
                  </Link>
                </>
              )}
              {!leagueCountFailed && leagueCount === 0 && (
                <>
                  <p className="text-ink-600 mt-2">
                    Connect a league to get advice based on your actual roster.
                  </p>
                  <Link to="/leagues" className="inline-block mt-2 text-accent-600 hover:text-accent-800 font-medium">
                    Connect your league &rarr;
                  </Link>
                </>
              )}
            </div>
            <div className="text-center">
              <SparklesIcon className="h-8 w-8 text-accent-600 mx-auto mb-2" />
              <h3 className="text-lg font-semibold text-ink-900">Waiver Wire</h3>
              <p className="text-ink-600 mt-2">See who's worth a claim before your leaguemates do.</p>
              <Link to="/waiver-wire" className="inline-block mt-2 text-accent-600 hover:text-accent-800 font-medium">
                Check the wire &rarr;
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
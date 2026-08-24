import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { leagues as leaguesApi } from '../services/api'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import {
  ChartBarIcon,
  CpuChipIcon,
  DocumentTextIcon,
  UserGroupIcon,
  TrophyIcon,
  SparklesIcon,
  ArrowRightIcon
} from '@heroicons/react/24/outline'

const FEATURES = [
  {
    to: '/draft',
    icon: CpuChipIcon,
    iconBg: 'bg-accent-100',
    iconColor: 'text-accent-600',
    title: 'Draft Assistant',
    body: 'Best-player-available math, but it knows your roster needs before your run of RBs dries up',
    cta: 'Open the draft board'
  },
  {
    to: '/leagues',
    icon: UserGroupIcon,
    iconBg: 'bg-ink-100',
    iconColor: 'text-ink-600',
    title: 'Platform Integration',
    body: 'Connect ESPN, Yahoo, or Sleeper and pull your real roster in instead of retyping it',
    cta: 'Connect a league'
  },
  {
    to: '/blog',
    icon: DocumentTextIcon,
    iconBg: 'bg-accent-100',
    iconColor: 'text-accent-600',
    title: 'Fantasy Content Library',
    body: 'Rankings and waiver targets built from live data, plus AI-written player deep-dives and injury reports',
    cta: 'Browse the library'
  }
] as const

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
        <span className="animate-rise-in animate-rise-in-1 inline-flex items-center gap-2 rounded-sm bg-ink-900 px-3 py-1.5 font-display text-xs font-bold uppercase tracking-[0.15em] text-accent-300">
          On the clock &middot; PPR
        </span>
        <h1 className="animate-rise-in animate-rise-in-2 mt-5 font-display font-black uppercase text-ink-900 text-5xl sm:text-7xl leading-[0.95] tracking-tight">
          Win your league.
          <br />
          <span className="text-accent-500">Or at least stop losing</span>
          <br />
          to your cousin.
        </h1>
        <p className="animate-rise-in animate-rise-in-3 mt-6 text-lg leading-8 text-ink-600 max-w-2xl mx-auto">
          AI-backed draft calls, PPR-tuned rankings, and waiver claims for the people who
          actually read the injury report on a Tuesday.
        </p>
        <div className="animate-rise-in animate-rise-in-4 mt-10 flex items-center justify-center gap-x-6">
          {user ? (
            <Link
              to="/draft"
              className="bg-accent-500 text-white px-8 py-3 rounded-md text-lg font-medium hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-offset-2"
            >
              Start Draft Assistant
            </Link>
          ) : (
            <Link
              to="/auth"
              className="bg-accent-500 text-white px-8 py-3 rounded-md text-lg font-medium hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-offset-2"
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

      <div className="yard-divider" aria-hidden="true" />

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {FEATURES.map(({ to, icon: Icon, iconBg, iconColor, title, body, cta }) => (
          <Link
            key={title}
            to={to}
            className="group bg-white rounded-lg shadow-sm border border-ink-200 p-6 transition-all hover:shadow-md hover:border-accent-300"
          >
            <div className={`w-12 h-12 ${iconBg} rounded-lg mb-4 flex items-center justify-center`}>
              <Icon className={`h-6 w-6 ${iconColor}`} />
            </div>
            <h3 className="text-xl font-semibold mb-2 text-ink-900">{title}</h3>
            <p className="text-ink-600">{body}</p>
            <p className="mt-4 flex items-center gap-1 text-sm font-medium text-accent-600 group-hover:text-accent-700">
              {cta}
              <ArrowRightIcon className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </p>
          </Link>
        ))}
      </div>

      {/* Welcome back / dashboard section */}
      {user && (
        <div className="space-y-4">
          <div>
            <h2 className="font-display font-black uppercase tracking-tight text-2xl text-ink-900">
              Welcome back, {user.full_name || user.username}!
            </h2>
            <p className="mt-1 text-sm text-ink-500">Here's where things stand.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Connected leagues -- the one real computed number in this section */}
            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-4">
              <div className="flex items-center justify-between mb-2">
                <TrophyIcon className="h-7 w-7 text-accent-500" />
                {!leagueCountFailed && leagueCount !== null && <DataConfidenceBadge level="computed" />}
              </div>
              <p className="text-xs font-bold uppercase tracking-wide text-ink-400 mb-1">Connected Leagues</p>
              {leagueCountFailed && (
                <p className="text-sm text-ink-600">Couldn't load your league status right now.</p>
              )}
              {!leagueCountFailed && leagueCount === null && (
                <p className="text-sm text-ink-600">Checking&hellip;</p>
              )}
              {!leagueCountFailed && leagueCount !== null && (
                <>
                  <p className="font-stat text-3xl font-semibold text-ink-900 tabular-nums">{leagueCount}</p>
                  <Link to="/leagues" className="mt-2 inline-block text-sm font-medium text-accent-600 hover:text-accent-800">
                    {leagueCount > 0 ? 'View your leagues' : 'Connect your league'} &rarr;
                  </Link>
                </>
              )}
            </div>

            <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-4">
              <ChartBarIcon className="h-7 w-7 text-accent-500 mb-2" />
              <p className="text-xs font-bold uppercase tracking-wide text-ink-400 mb-3">Quick Actions</p>
              <div className="space-y-2">
                <Link to="/draft" className="block text-sm font-medium text-ink-700 hover:text-accent-600">Start Draft Session</Link>
                <Link to="/players" className="block text-sm font-medium text-ink-700 hover:text-accent-600">Browse Players</Link>
                <Link to="/blog" className="block text-sm font-medium text-ink-700 hover:text-accent-600">View Analysis</Link>
              </div>
            </div>

            <Link
              to="/waiver-wire"
              className="group bg-white rounded-lg shadow-sm border border-ink-200 p-4 transition-all hover:shadow-md hover:border-accent-300"
            >
              <SparklesIcon className="h-7 w-7 text-accent-500 mb-2" />
              <p className="text-xs font-bold uppercase tracking-wide text-ink-400">Waiver Wire</p>
              <p className="mt-1 text-sm text-ink-600">See who's worth a claim before your leaguemates do.</p>
              <p className="mt-2 flex items-center gap-1 text-sm font-medium text-accent-600 group-hover:text-accent-700">
                Check the wire
                <ArrowRightIcon className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </p>
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
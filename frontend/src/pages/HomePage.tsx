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
  ArrowRightIcon,
} from '@heroicons/react/24/outline'

const FEATURES = [
  {
    to: '/leagues',
    icon: CpuChipIcon,
    title: 'This Week',
    body: 'Your real matchup, a start/sit call on every slot, and the waiver moves that swing it',
    cta: 'Open this week',
  },
  {
    to: '/leagues',
    icon: UserGroupIcon,
    title: 'Platform Integration',
    body: 'Connect ESPN, Yahoo, or Sleeper and pull your real roster in instead of retyping it',
    cta: 'Connect a league',
  },
  {
    to: '/blog',
    icon: DocumentTextIcon,
    title: 'Fantasy Content Library',
    body: 'Rankings and waiver targets built from live data, plus AI-written player deep-dives and injury reports',
    cta: 'Browse the library',
  },
] as const

export function HomePage() {
  const { user } = useAuth()
  // Real account state for the "Welcome back" box below. null = still loading.
  const [leagueCount, setLeagueCount] = useState<number | null>(null)
  const [leagueCountFailed, setLeagueCountFailed] = useState(false)

  useEffect(() => {
    if (!user) return
    let cancelled = false

    leaguesApi
      .getAll()
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
    <div className="space-y-14">
      {/* Hero */}
      <div className="relative isolate text-center">
        <div
          className="field-backdrop pointer-events-none absolute inset-x-0 -top-8 -z-10 h-[420px] [mask-image:linear-gradient(to_bottom,black,transparent)]"
          aria-hidden="true"
        />
        <span className="animate-rise-in animate-rise-in-1 inline-flex items-center gap-2 bg-ink-950 px-3 py-1.5 font-stat text-[11px] uppercase tracking-[0.18em] text-volt">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-volt" />
          On the clock &middot; PPR
        </span>
        <h1 className="animate-rise-in animate-rise-in-2 mt-5 font-display font-bold uppercase text-body text-5xl sm:text-7xl leading-[0.92] tracking-tight">
          Your unfair advantage,
          <br />
          <span className="text-accent-ink">every Sunday.</span>
        </h1>
        <p className="animate-rise-in animate-rise-in-3 mt-6 text-lg leading-8 text-muted max-w-2xl mx-auto">
          AI-backed lineup calls, PPR-tuned rankings, and waiver claims &mdash; for the people
          who actually read the injury report on a Tuesday.
        </p>
        <div className="animate-rise-in animate-rise-in-4 mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            to={user ? '/leagues' : '/auth'}
            className="bg-volt text-volt-ink px-8 py-3 font-stat text-sm font-medium hover:bg-volt-dark transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-volt focus-visible:ring-offset-2 focus-visible:ring-offset-page"
          >
            {user ? 'Open This Week' : 'Get Started'}
          </Link>
          <Link
            to="/players"
            className="border border-line text-body px-8 py-3 font-stat text-sm font-medium hover:border-accent-ink hover:text-accent-ink transition-colors"
          >
            View Players
          </Link>
        </div>
      </div>

      <div className="yard-divider" aria-hidden="true" />

      {/* Features */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-hairline border border-hairline">
        {FEATURES.map(({ to, icon: Icon, title, body, cta }, i) => (
          <Link
            key={title}
            to={to}
            className="group bg-surface p-6 transition-colors hover:bg-surface-2"
          >
            <div className="flex items-center justify-between">
              <div className="flex h-11 w-11 items-center justify-center border border-line text-accent-ink">
                <Icon className="h-5 w-5" />
              </div>
              <span className="font-stat text-[11px] tracking-widest text-faint">
                0{i + 1}
              </span>
            </div>
            <h3 className="mt-4 font-display text-2xl font-bold uppercase tracking-tight text-body">
              {title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
            <p className="mt-4 flex items-center gap-1 font-stat text-xs font-medium text-accent-ink">
              {cta}
              <ArrowRightIcon className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </p>
          </Link>
        ))}
      </div>

      {/* Welcome back */}
      {user && (
        <div className="space-y-4">
          <div>
            <h2 className="font-display text-2xl font-bold uppercase tracking-tight text-body">
              Welcome back, {user.full_name || user.username}
            </h2>
            <p className="mt-1 font-stat text-xs text-faint">Here&rsquo;s where things stand.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-hairline border border-hairline">
            {/* Connected leagues — the one real computed number here */}
            <div className="bg-surface p-4">
              <div className="flex items-center justify-between mb-2">
                <TrophyIcon className="h-6 w-6 text-accent-ink" />
                {!leagueCountFailed && leagueCount !== null && (
                  <DataConfidenceBadge level="computed" />
                )}
              </div>
              <p className="font-stat text-[11px] uppercase tracking-widest text-faint mb-1">
                Connected Leagues
              </p>
              {leagueCountFailed && (
                <p className="text-sm text-muted">Couldn&rsquo;t load your league status right now.</p>
              )}
              {!leagueCountFailed && leagueCount === null && (
                <p className="text-sm text-muted">Checking&hellip;</p>
              )}
              {!leagueCountFailed && leagueCount !== null && (
                <>
                  <p className="stat-nums text-4xl font-semibold text-body">{leagueCount}</p>
                  <Link
                    to="/leagues"
                    className="mt-2 inline-block font-stat text-xs font-medium text-accent-ink hover:underline"
                  >
                    {leagueCount > 0 ? 'View your leagues' : 'Connect your league'} &rarr;
                  </Link>
                </>
              )}
            </div>

            <div className="bg-surface p-4">
              <ChartBarIcon className="h-6 w-6 text-accent-ink mb-2" />
              <p className="font-stat text-[11px] uppercase tracking-widest text-faint mb-3">
                Quick Actions
              </p>
              <div className="space-y-2">
                <Link to="/leagues" className="block text-sm font-medium text-muted hover:text-accent-ink">
                  Open This Week
                </Link>
                <Link to="/waiver-wire" className="block text-sm font-medium text-muted hover:text-accent-ink">
                  Waiver Targets
                </Link>
                <Link to="/players" className="block text-sm font-medium text-muted hover:text-accent-ink">
                  Browse Players
                </Link>
                <Link to="/blog" className="block text-sm font-medium text-muted hover:text-accent-ink">
                  View Analysis
                </Link>
              </div>
            </div>

            <Link to="/waiver-wire" className="group bg-surface p-4 transition-colors hover:bg-surface-2">
              <SparklesIcon className="h-6 w-6 text-accent-ink mb-2" />
              <p className="font-stat text-[11px] uppercase tracking-widest text-faint">Waiver Wire</p>
              <p className="mt-1 text-sm text-muted">
                See who&rsquo;s worth a claim before your leaguemates do.
              </p>
              <p className="mt-2 flex items-center gap-1 font-stat text-xs font-medium text-accent-ink">
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

import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { leagues as leaguesApi, getErrorMessage } from '../services/api'
import { PageLoader } from '../components/common/PageLoader'

interface ConnectedLeague {
  id: string
  league_name?: string
}

/**
 * "This Week" is a tab on the league-detail page, not a standalone route.
 * The top-nav "This Week" link lands here, which resolves the user's first
 * connected league and forwards to its This Week tab. No leagues -> the
 * Leagues page (connect one first). This keeps the flagship in-season screen
 * one click from the navbar without duplicating it.
 */
export function ThisWeekRedirectPage() {
  const { user } = useAuth()
  const [target, setTarget] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    let cancelled = false

    leaguesApi
      .getAll()
      .then((res) => {
        if (cancelled) return
        const list: ConnectedLeague[] = res.data || []
        setTarget(list.length > 0 ? `/leagues/${list[0].id}?tab=this-week` : '/leagues')
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'Could not load your leagues.'))
      })

    return () => {
      cancelled = true
    }
  }, [user])

  if (!user) return <Navigate to="/auth" replace />

  if (error) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h1 className="font-display text-2xl font-bold uppercase tracking-tight text-body">
          This Week
        </h1>
        <p className="mt-2 text-sm text-muted">{error}</p>
      </div>
    )
  }

  if (!target) return <PageLoader />

  return <Navigate to={target} replace />
}

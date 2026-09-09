import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  users,
  getErrorMessage,
  type DraftSessionSummary,
  type DraftSessionDetail,
} from '../services/api'
import {
  ExclamationTriangleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  TrophyIcon,
} from '@heroicons/react/24/outline'
import { positionColors } from '../components/players/playerDisplay'

// Small color helper kept local to this page rather than shared -- this
// codebase's other grade-displaying pages (PostDraftAnalysisPage,
// LeagueDetailPage, DraftPage) each define their own copy too, so this
// follows the existing convention rather than introducing a new shared util.
const GRADE_BADGE_COLORS: Record<string, string> = {
  A: 'bg-success-100 text-success-800',
  B: 'bg-highlight text-accent-ink',
  C: 'bg-warning-100 text-warning-800',
  D: 'bg-warning-100 text-warning-800',
  F: 'bg-danger-100 text-danger-800',
}

function getGradeBadgeColor(grade: string | null | undefined): string {
  if (!grade) return 'bg-surface-2 text-muted'
  const base = grade.trim().charAt(0).toUpperCase()
  return GRADE_BADGE_COLORS[base] || 'bg-surface-2 text-body'
}

// draft_settings comes back as a loosely-typed object (it's whatever the
// user's DraftSettings state looked like at save time) -- read the fields we
// know about defensively rather than assuming they're always present/typed.
function formatSettingsSummary(settings: Record<string, unknown>): string {
  const parts: string[] = []
  if (typeof settings.team_count === 'number') parts.push(`${settings.team_count}-team`)
  if (typeof settings.scoring_format === 'string' && settings.scoring_format) {
    parts.push(settings.scoring_format)
  }
  if (typeof settings.total_rounds === 'number') parts.push(`${settings.total_rounds} rounds`)
  return parts.length > 0 ? parts.join(' · ') : 'Mock draft'
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'Unknown date'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function DraftHistoryPage() {
  const [sessions, setSessions] = useState<DraftSessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Detail is fetched lazily per session and cached by session_id so
  // re-expanding an already-viewed entry doesn't refetch it.
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null)
  const [detailsById, setDetailsById] = useState<Record<string, DraftSessionDetail>>({})
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null)
  const [detailErrorsById, setDetailErrorsById] = useState<Record<string, string>>({})

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await users.getDraftHistory()
        if (!cancelled) setSessions(response.data.draft_sessions || [])
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err, 'Failed to load your draft history'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const sortedSessions = useMemo(
    () =>
      [...sessions].sort((a, b) => {
        const aTime = new Date(a.completed_at || a.started_at).getTime()
        const bTime = new Date(b.completed_at || b.started_at).getTime()
        return (Number.isNaN(bTime) ? 0 : bTime) - (Number.isNaN(aTime) ? 0 : aTime)
      }),
    [sessions]
  )

  const toggleSession = useCallback(
    async (sessionId: string) => {
      if (expandedSessionId === sessionId) {
        setExpandedSessionId(null)
        return
      }

      setExpandedSessionId(sessionId)
      if (detailsById[sessionId] || detailLoadingId === sessionId) return

      setDetailLoadingId(sessionId)
      setDetailErrorsById((prev) => {
        if (!(sessionId in prev)) return prev
        const next = { ...prev }
        delete next[sessionId]
        return next
      })

      try {
        const response = await users.getDraftDetail(sessionId)
        setDetailsById((prev) => ({ ...prev, [sessionId]: response.data }))
      } catch (err) {
        setDetailErrorsById((prev) => ({
          ...prev,
          [sessionId]: getErrorMessage(err, "Couldn't load this draft's details"),
        }))
      } finally {
        setDetailLoadingId(null)
      }
    },
    [expandedSessionId, detailsById, detailLoadingId]
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Draft History</h1>
        <p className="text-muted mt-2">Past mock drafts and how they graded out</p>
      </div>

      {error && (
        <div className="bg-danger-50 border border-danger-200 rounded-md p-4 flex items-start gap-3">
          <ExclamationTriangleIcon className="h-5 w-5 text-danger-500 shrink-0 mt-0.5" />
          <p className="text-sm text-danger-800">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-ink"></div>
        </div>
      ) : sortedSessions.length === 0 ? (
        <div className="bg-surface rounded-lg border border-hairline text-center py-12">
          <div className="text-faint text-6xl mb-4"></div>
          <h3 className="text-xl font-semibold text-body mb-2">No mock drafts yet</h3>
          <p className="text-muted mb-6">
            Finish a mock draft to see your grade and roster breakdown here.
          </p>
          <Link
            to="/draft"
            className="inline-flex items-center px-4 py-2 bg-volt text-volt-ink text-sm font-medium rounded-md hover:bg-volt-dark transition-colors"
          >
            Start a mock draft
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {sortedSessions.map((session) => {
            const isExpanded = expandedSessionId === session.session_id
            const detail = detailsById[session.session_id]
            const detailError = detailErrorsById[session.session_id]
            const isDetailLoading = detailLoadingId === session.session_id

            return (
              <div
                key={session.session_id}
                className="bg-surface rounded-lg border border-hairline overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => toggleSession(session.session_id)}
                  className="w-full flex items-center justify-between gap-4 p-4 text-left hover:bg-surface-2 transition-colors"
                  aria-expanded={isExpanded}
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div
                      className={`flex items-center justify-center w-12 h-12 rounded-full font-stat text-lg font-bold shrink-0 ${getGradeBadgeColor(session.draft_grade)}`}
                    >
                      {session.draft_grade || '?'}
                    </div>
                    <div className="min-w-0">
                      <div className="font-medium text-body truncate">
                        {formatSettingsSummary(session.draft_settings)}
                      </div>
                      <div className="text-sm text-muted">
                        {formatDate(session.completed_at || session.started_at)}
                        {!session.is_completed && (
                          <span className="ml-2 text-warning-700 font-medium">In progress</span>
                        )}
                      </div>
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUpIcon className="h-5 w-5 text-faint shrink-0" />
                  ) : (
                    <ChevronDownIcon className="h-5 w-5 text-faint shrink-0" />
                  )}
                </button>

                {isExpanded && (
                  <div className="border-t border-hairline p-4">
                    {isDetailLoading ? (
                      <div className="flex items-center gap-3 py-4">
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-accent-ink"></div>
                        <p className="text-sm text-muted">Loading draft details...</p>
                      </div>
                    ) : detailError ? (
                      <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div className="flex items-start gap-2">
                          <ExclamationTriangleIcon className="h-5 w-5 text-danger-500 shrink-0 mt-0.5" />
                          <p className="text-sm text-danger-800">{detailError}</p>
                        </div>
                        <button
                          onClick={() => toggleSession(session.session_id)}
                          className="px-3 py-1.5 bg-danger-600 text-white text-xs font-medium rounded hover:bg-danger-700 shrink-0"
                        >
                          Retry
                        </button>
                      </div>
                    ) : detail ? (
                      <div className="space-y-4">
                        {detail.final_analysis && (
                          <p className="text-sm text-body bg-surface-2 rounded-md p-3 border border-hairline">
                            {detail.final_analysis}
                          </p>
                        )}

                        {typeof detail.composition_score === 'number' && (
                          <div className="flex items-center gap-2 text-sm text-muted">
                            <TrophyIcon className="h-4 w-4 text-accent-ink" />
                            Composition score: <span className="font-stat tabular-nums font-medium text-body">{detail.composition_score}/100</span>
                          </div>
                        )}

                        <div>
                          <h4 className="text-sm font-semibold text-body mb-2">
                            Your Roster ({detail.user_roster.length})
                          </h4>
                          {detail.user_roster.length === 0 ? (
                            <p className="text-sm text-muted">No drafted players recorded for this session.</p>
                          ) : (
                            <div className="max-h-64 overflow-y-auto space-y-1.5">
                              {[...detail.user_roster]
                                .sort((a, b) => a.pick - b.pick)
                                .map((player) => (
                                  <div
                                    key={`${player.sleeper_id}-${player.pick}`}
                                    className="flex items-center justify-between gap-2 p-2 bg-surface-2 rounded text-sm"
                                  >
                                    <div className="flex items-center gap-2 min-w-0">
                                      <span className="text-xs text-muted shrink-0 w-20">
                                        Rd {player.round} &middot; #{player.pick}
                                      </span>
                                      <span className="font-medium text-body truncate">{player.full_name}</span>
                                      <span
                                        className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${
                                          positionColors[player.position as keyof typeof positionColors] || 'bg-surface-2 text-body'
                                        }`}
                                      >
                                        {player.position}
                                      </span>
                                    </div>
                                    <span className="text-xs text-muted shrink-0">{player.team}</span>
                                  </div>
                                ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

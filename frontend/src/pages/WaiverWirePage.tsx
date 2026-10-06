import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from '../hooks/useAuth'
import { waiverWire, matchupAnalysis, notifications as notificationsApi, leagues as leaguesApi, getErrorMessage } from '../services/api'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { getPositionColor } from '../components/players/playerDisplay'
import { PlayerAvatar } from '../components/players/PlayerAvatar'
import { LineupWaiverCard, TeamNeedsStrip, type LineupWaiverRec, type TeamNeed } from '../components/waivers/LineupWaivers'
import type { Notification } from '../types'
import {
  PlusIcon,
  FireIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  ClockIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  BellIcon,
  MagnifyingGlassIcon,
  ShieldCheckIcon,
  NoSymbolIcon
} from '@heroicons/react/24/outline'

interface WaiverRecommendation {
  player_id: number
  player_name: string
  position: string
  team: string
  recommendation_type: string
  priority: string
  confidence_score: number
  reason: string
  projected_points: number | null
  ownership_percentage: number | null
  trend_direction: string
  add_count_24h?: number
  component_scores?: {
    performance: number
    opportunity: number
    matchup: number
    ownership: number
    trend: number
  }
  // Real personalization fields -- only meaningful when a league was
  // selected to personalize against (see WaiverWireService.
  // get_live_trending_recommendations). null/undefined when unweighted.
  roster_need?: 'needs_attention' | 'overstocked' | null
  bye_week?: number | null
  bye_week_flag?: boolean
  pass_catcher_boost?: boolean
  league_scoring_context?: { scoring_format?: string | null; points_per_reception?: number | null } | null
  // Where this candidate sits in today's real Sleeper trending-add pool
  // (after real per-league availability filtering) -- e.g. rank 3 of 44.
  // Shown instead of just repeating the priority label, which otherwise
  // reads the same ("URGENT"/"HIGH") on nearly every visible card since
  // the list IS the top of that ranking by construction.
  rank?: number
  total_candidates?: number
  // Real per-league signal (ESPN/Yahoo, when a league is selected):
  // true/false from that team's actual current-week lineup, null/undefined
  // when not determinable (no league selected, or this team has zero
  // rostered players anywhere in the league to read a bye off of).
  on_bye_this_week?: boolean | null
  espn_player_id?: number | null
  // Real, priority-aware claim suggestion -- this recommendation's actual
  // priority tier read against your real FAAB balance or rolling-priority
  // rank for the selected league (see WaiverWireService.compute_bid_tier).
  // null/undefined when no waiver position is known (no league selected,
  // non-ESPN league, or team_id not configured).
  bid_tier?: {
    bid_type: 'faab' | 'priority'
    suggested_bid?: number
    bid_range?: [number, number]
    budget_remaining?: number
    note?: string
    recommendation?: 'use_claim' | 'hold_priority'
    waiver_rank?: number | null
    total_teams?: number | null
    reasoning?: string
  } | null
}

interface ConnectedLeagueOption {
  id: number
  league_name: string | null
  platform: string
  team_id: string | null
}

// Real FAAB balance or rolling-priority rank for the selected league -- see
// GET /leagues/{id}/waiver-position. `supported: false` covers non-ESPN
// leagues and leagues with no team_id set yet; `waiver_type` picks which of
// the two mutually-exclusive fields this league actually uses.
interface WaiverPosition {
  supported: boolean
  detail?: string
  waiver_type?: 'faab' | 'priority'
  total_teams?: number
  waiver_rank?: number
  total_budget?: number
  budget_spent?: number
  budget_remaining?: number
}

// Real per-league competition signal -- see GET /leagues/{id}/position-pressure
// and app/services/league_competition.py. Only QB/RB/WR/TE are meaningful
// (K/DEF benches are routinely empty by design in most leagues).
interface PositionPressureEntry {
  season: { teams_in_need: number; total_teams: number; team_names: string[]; ratio: number }
  this_week: { teams_in_need: number; team_names: string[] }
  level: 'high' | 'medium' | 'low'
}
interface PositionPressure {
  supported: boolean
  detail?: string
  position_pressure?: Record<string, PositionPressureEntry>
  other_teams_considered?: number
}

const COMPETITION_LABEL: Record<'high' | 'medium' | 'low', string> = {
  high: 'High competition',
  medium: 'Some competition',
  low: 'Low competition',
}
function formatTeamNames(names: string[], max = 3): string {
  if (names.length <= max) return names.join(', ')
  return `${names.slice(0, max).join(', ')}, +${names.length - max} more`
}

const COMPETITION_CLASS: Record<'high' | 'medium' | 'low', string> = {
  high: 'bg-danger-100 text-danger-800',
  medium: 'bg-warning-100 text-warning-800',
  low: 'bg-success-100 text-success-800',
}

// The "Alerts" tab now reads the app's real in-app notification center
// (see backend/app/services/notification_service.py) instead of the old
// GET /waiver-wire/alerts stub, which queried a WaiverWireAlert table
// nothing ever wrote to. `Notification` is the real, shared shape used by
// the navbar bell too -- see src/types/index.ts.

interface TrendingPlayer {
  player_id: number
  player_name: string
  position: string
  team: string
  // Real live snapshot from Sleeper's trending add/drop feed (last 24h) --
  // see WaiverWireService.get_live_trending_players. Not a historical
  // ownership/pickup-rate time series; Sleeper doesn't expose one.
  trend_direction: 'up' | 'down'
  count_24h: number
  reason: string
}

interface DefenseStreamingTarget {
  player_id?: number
  team_name?: string
  // `streaming_recommendations` entries carry `team_abbreviation`; the plain
  // `defenses_to_avoid` entries (WaiverWireService.get_weekly_defensive_targets
  // pass-through) instead carry `team` -- normalize with getTeamAbbr() below
  // rather than assuming one field name everywhere.
  team_abbreviation?: string
  team?: string
  opponent: string | null
  is_home_game?: boolean
  is_home?: boolean
  matchup_rating: number
  improvement_over_current?: number
  ownership_percentage?: number
  avg_points_allowed?: number
  recent_trend?: number
  availability_tier?: string
  recommendation_strength?: string
  recommendation?: string
  tier?: string
  key_factors?: string[]
  confidence?: number
  waiver_priority?: string
}

interface DefenseStreamingRecommendations {
  week: number
  current_defense?: string | null
  streaming_recommendations?: DefenseStreamingTarget[]
  defenses_to_avoid?: DefenseStreamingTarget[]
  analysis_notes?: string[]
  error?: string
}

interface PositionOutlookWeek {
  best_matchups: { team: string; rating: number; rank: number; points_allowed: number }[]
  worst_matchups: { team: string; rating: number; rank: number; points_allowed: number }[]
  week_average_rating: number
}

interface PositionOutlook {
  position: string
  weeks_analyzed: number
  weekly_outlook: Record<string, PositionOutlookWeek>
  total_rankings_analyzed: number
  error?: string
}

interface StreamingPlayer {
  name: string
  team?: string
  position?: { value?: string }
  week_projection?: number
  ownership_percentage?: number | null
  espn_player_id?: number | null
}

interface StreamingBoards {
  current_week?: number | null
  projection_source: string
  boards: {
    position: string
    current: StreamingPlayer | null
    options: { player: StreamingPlayer; week_edge: number }[]
  }[]
}

type TabId = 'recommendations' | 'trending' | 'alerts' | 'streaming'

interface LineupImpact {
  recs: LineupWaiverRec[]
  watchOnly: boolean
  teamNeeds: TeamNeed[]
  basis?: string
}

const LEAGUE_STORAGE_KEY = 'waivers.leagueId'

function readStoredLeagueId(): number | null {
  try {
    const raw = localStorage.getItem(LEAGUE_STORAGE_KEY)
    return raw ? parseInt(raw, 10) : null
  } catch {
    return null
  }
}

// Helper function to get current NFL week
function getCurrentNFLWeek(): number {
  // Simple calculation - NFL season typically starts first week of September
  // This is a basic implementation, could be made more sophisticated
  const now = new Date()
  const month = now.getMonth() + 1 // JavaScript months are 0-indexed

  if (month >= 9 && month <= 12) {
    // September to December - regular season
    return Math.min(Math.floor((now.getDate() + (month - 9) * 30) / 7) + 1, 18)
  } else if (month === 1) {
    // January - playoffs
    return 19
  } else {
    // Off-season, default to week 1
    return 1
  }
}

// The confidence_score on a recommendation is a real ratio (this player's
// live Sleeper add-count over the single most-added player's count in
// today's trending pool -- see WaiverWireService.get_live_trending_recommendations),
// not a placeholder. add_count_24h carries the raw number that ratio was
// built from; fall back to parsing it out of `reason` for any recommendation
// shape that doesn't carry the field directly.
function getAddCount(rec: WaiverRecommendation): number | null {
  if (typeof rec.add_count_24h === 'number') {
    return rec.add_count_24h
  }
  const match = rec.reason?.match(/([\d,]+)\s+adds/)
  if (match) {
    return parseInt(match[1].replace(/,/g, ''), 10)
  }
  return null
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(4, Math.round(value * 100))
  return (
    <div className="w-full bg-surface-2 rounded-full h-2">
      <div className="bg-accent-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  )
}

// Matchup ratings from matchup_analysis_service.py are on a 0-10 scale
// (5.0 = neutral), not a 0-1 ratio -- share the same bar visual but scale
// against 10 instead of reusing ConfidenceBar directly.
function MatchupRatingBar({ rating }: { rating: number }) {
  const pct = Math.max(4, Math.min(100, Math.round((rating / 10) * 100)))
  return (
    <div className="w-full bg-surface-2 rounded-full h-2">
      <div className="bg-accent-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  )
}

// See the DefenseStreamingTarget comment above -- the two shapes this app
// renders carry the team abbreviation under different field names.
function getTeamAbbr(target: DefenseStreamingTarget): string {
  return target.team_abbreviation || target.team || '?'
}

// The lineup-impact list for the selected league: the same engine and card
// as League Detail's Waiver tab, plus this page's competition signal
// (other teams thin at the position).
function LeagueWaiverList({
  loading,
  error,
  impact,
  position,
  pressure,
}: {
  loading: boolean
  error: string
  impact: LineupImpact | null
  position: string
  pressure: PositionPressure | null
}) {
  if (loading) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
        <p className="text-sm text-muted">Scoring every free agent against your lineup...</p>
      </div>
    )
  }
  if (error || !impact) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
        <p className="text-sm text-muted">{error || 'No waiver advice for this league right now.'}</p>
      </div>
    )
  }
  const recs = position ? impact.recs.filter((r) => r.player.position?.value === position) : impact.recs
  return (
    <div className="space-y-4">
      {impact.teamNeeds.length > 0 && <TeamNeedsStrip needs={impact.teamNeeds} />}
      <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="text-base font-medium text-body">
              {impact.watchOnly ? 'No clear upgrade for your lineup yet' : 'Best adds for your lineup'}
            </h3>
            {impact.watchOnly && (
              <p className="text-xs text-muted mt-0.5">Best available at your weakest spots, worth watching.</p>
            )}
          </div>
          <DataConfidenceBadge level="computed" label="Lineup impact" />
        </div>
        {recs.length === 0 ? (
          <p className="text-sm text-muted">
            {position ? `No ${position} on the wire improves your team right now.` : 'Nothing on the wire improves your team right now.'}
          </p>
        ) : (
          <div className="space-y-3">
            {recs.map((rec) => {
              const pos = rec.player.position?.value || ''
              const competition = pressure?.supported ? pressure.position_pressure?.[pos] : undefined
              const thin = competition && (competition.this_week.teams_in_need > 0 || competition.season.teams_in_need > 0)
              return (
                <LineupWaiverCard
                  key={rec.player.name}
                  rec={rec}
                  badges={
                    competition && rec.kind !== 'watch' ? (
                      <span
                        className={`stat-nums text-[10px] px-1.5 py-0.5 rounded ${COMPETITION_CLASS[competition.level]}`}
                        title={`${competition.season.teams_in_need} of ${competition.season.total_teams} other teams look thin at ${pos} all season`}
                      >
                        {COMPETITION_LABEL[competition.level]}
                      </span>
                    ) : undefined
                  }
                >
                  {thin && rec.kind !== 'watch' && (
                    <p className="text-xs text-faint mt-1">
                      {competition.this_week.teams_in_need > 0
                        ? <>Also short at {pos} this week: <span className="text-body">{formatTeamNames(competition.this_week.team_names)}</span>. </>
                        : null}
                      {competition.season.teams_in_need > 0
                        ? <>Thin at {pos} all season: <span className="text-body">{formatTeamNames(competition.season.team_names)}</span>.</>
                        : null}
                    </p>
                  )}
                </LineupWaiverCard>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// This week's DEF/K streaming menu for the selected league: the user's own
// starter, then the best free agents by this week's real projection.
function StreamingBoardsView({ data, loading, error }: { data: StreamingBoards | null; loading: boolean; error: string }) {
  if (loading) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
        <p className="text-sm text-muted">Projecting this week's defenses and kickers...</p>
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="bg-surface rounded-lg shadow p-6 text-center">
        <ExclamationTriangleIcon className="mx-auto h-8 w-8 text-faint mb-2" />
        <p className="text-sm text-muted">{error || 'No streaming data for this league right now.'}</p>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        Week {data.current_week ?? '?'} projections ({data.projection_source}). Edge = their projection minus your starter's.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {data.boards.map((board) => {
          const label = board.position === 'DEF' ? 'Defense' : 'Kicker'
          const best = board.options[0]
          return (
            <div key={board.position} className="bg-surface rounded-lg border border-hairline p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3 mb-3">
                <h3 className="text-base font-medium text-body">{label} — this week</h3>
                <DataConfidenceBadge level="computed" label="Your league" />
              </div>
              <div className="flex items-center justify-between gap-3 rounded-md bg-surface-2 px-3 py-2 mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="stat-nums text-[10px] tracking-wider text-muted">YOURS</span>
                  <span className="text-sm text-body truncate">{board.current?.name ?? `No healthy ${label.toLowerCase()}`}</span>
                </div>
                <span className="stat-nums text-sm text-body">
                  {board.current ? (board.current.week_projection ?? 0).toFixed(1) : '—'}
                  {board.current && (board.current.week_projection ?? 0) === 0 && <span className="text-xs text-danger-700"> bye/out</span>}
                </span>
              </div>
              <p className="text-xs text-muted mb-2">
                {best && best.week_edge >= 2
                  ? `Stream ${best.player.name}: +${best.week_edge.toFixed(1)} over yours this week.`
                  : best && best.week_edge > 0
                    ? 'Marginal edges only -- keeping yours is fine.'
                    : 'Keep yours -- nothing on the wire projects higher this week.'}
              </p>
              <div className="divide-y divide-hairline">
                {board.options.map(({ player, week_edge }) => (
                  <div key={player.name} className="flex items-center justify-between gap-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <PlayerAvatar
                        playerId={player.espn_player_id ?? undefined}
                        name={player.name}
                        position={board.position}
                        team={player.team}
                        size={28}
                      />
                      <span className="text-sm text-body truncate">{player.name}</span>
                      {player.ownership_percentage != null && (
                        <span className="stat-nums text-[10px] text-faint shrink-0">{Math.round(player.ownership_percentage)}%</span>
                      )}
                    </div>
                    <div className="stat-nums text-sm shrink-0 text-right">
                      <span className="text-body">{(player.week_projection ?? 0).toFixed(1)}</span>
                      <span className={`ml-3 inline-block w-12 font-semibold ${week_edge >= 2 ? 'text-success-700' : week_edge > 0 ? 'text-body' : 'text-muted'}`}>
                        {week_edge > 0 ? '+' : ''}{week_edge.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function WaiverWirePage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<TabId>('recommendations')
  const [recommendations, setRecommendations] = useState<WaiverRecommendation[]>([])
  const [trendingPlayers, setTrendingPlayers] = useState<TrendingPlayer[]>([])
  const [alerts, setAlerts] = useState<Notification[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Filters
  const [selectedPosition, setSelectedPosition] = useState<string>('')
  const [selectedPriority, setSelectedPriority] = useState<string>('')
  const [currentWeek, setCurrentWeek] = useState(getCurrentNFLWeek())
  const [trendDirection, setTrendDirection] = useState('up')

  // Personalization: real roster-need / bye-week / scoring-format weighting
  // against one of the user's connected leagues, opt-in via a dropdown --
  // see WaiverWireService.get_live_trending_recommendations's user_roster/
  // league_settings params. Only leagues with a team_id set can actually
  // have their roster fetched (see /leagues/{id}/settings), so those are
  // the only ones offered here.
  const [connectedLeagues, setConnectedLeagues] = useState<ConnectedLeagueOption[]>([])
  const [selectedLeagueId, setSelectedLeagueId] = useState<number | ''>('')
  const [waiverPosition, setWaiverPosition] = useState<WaiverPosition | null>(null)
  const [positionPressure, setPositionPressure] = useState<PositionPressure | null>(null)
  // The lineup-impact engine (GET /leagues/{id}/waiver-recommendations) --
  // the primary list whenever a league is selected.
  const [lineupImpact, setLineupImpact] = useState<LineupImpact | null>(null)
  const [lineupLoading, setLineupLoading] = useState(false)
  const [lineupError, setLineupError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  // Defense/kicker streaming (matchup_analysis endpoints)
  const [streamingCurrentDefense, setStreamingCurrentDefense] = useState<string>('')
  const autoDefenseRef = useRef('')
  const [streamingBoards, setStreamingBoards] = useState<StreamingBoards | null>(null)
  const [boardsLoading, setBoardsLoading] = useState(false)
  const [boardsError, setBoardsError] = useState('')
  const [streamingData, setStreamingData] = useState<DefenseStreamingRecommendations | null>(null)
  const [kickerOutlook, setKickerOutlook] = useState<PositionOutlook | null>(null)
  const [streamingLoading, setStreamingLoading] = useState(false)
  const [streamingError, setStreamingError] = useState('')

  const loadRecommendations = useCallback(async () => {
    // With a league selected the lineup-impact engine is the list; the
    // league-wide trending feed stays on the Trending tab.
    if (selectedLeagueId !== '') return
    try {
      setLoading(true)
      setError('')

      const params: { week: number; position?: string; priority?: string; league_id?: number } = { week: currentWeek }
      if (selectedPosition) {
        params.position = selectedPosition
      }
      if (selectedPriority) {
        params.priority = selectedPriority
      }
      const response = await waiverWire.getRecommendations(params)
      setRecommendations(response.data.recommendations || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load waiver recommendations'))
    } finally {
      setLoading(false)
    }
    // refreshKey: the Refresh button re-runs this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentWeek, selectedPosition, selectedPriority, selectedLeagueId, refreshKey])

  // Load the user's connected leagues once, to populate the personalization
  // dropdown. Only leagues with a team_id can have their roster fetched by
  // the backend (see _fetch_connected_roster_and_settings), so filter down
  // to those -- offering a league that can't actually be personalized would
  // silently no-op and be confusing.
  useEffect(() => {
    if (!user) return
    leaguesApi.getAll()
      .then((response) => {
        const all = (response.data || []) as ConnectedLeagueOption[]
        const usable = all.filter((l) => !!l.team_id)
        setConnectedLeagues(usable)
        // Default to the user's league (last one picked here, else the
        // first) -- advice for your own roster beats the generic feed.
        const remembered = readStoredLeagueId()
        const pick = usable.find((l) => l.id === remembered) ?? usable[0]
        if (pick) setSelectedLeagueId((current) => (current === '' ? pick.id : current))
      })
      .catch(() => setConnectedLeagues([]))
  }, [user])

  // Real waiver standing for whichever league is selected to personalize
  // against -- FAAB remaining or priority rank, whichever this league
  // actually runs on. Not fetched until a league is chosen (same opt-in as
  // personalization above).
  useEffect(() => {
    if (selectedLeagueId === '') {
      setWaiverPosition(null)
      return
    }
    leaguesApi.getWaiverPosition(selectedLeagueId)
      .then((response) => setWaiverPosition(response.data))
      .catch(() => setWaiverPosition(null))
  }, [selectedLeagueId])

  // Real per-league competition signal (other teams' actual roster depth
  // per position) -- same opt-in as waiver position above. Cached ~1hr
  // server-side (roster composition barely moves intra-week), so this is
  // cheap to fetch alongside it.
  useEffect(() => {
    if (selectedLeagueId === '') {
      setPositionPressure(null)
      return
    }
    leaguesApi.getPositionPressure(selectedLeagueId)
      .then((response) => setPositionPressure(response.data))
      .catch(() => setPositionPressure(null))
  }, [selectedLeagueId])

  useEffect(() => {
    setLineupImpact(null)
    setLineupError('')
    if (selectedLeagueId === '') return
    let cancelled = false
    setLineupLoading(true)
    leaguesApi.getWaiverRecommendations(selectedLeagueId)
      .then((response) => {
        if (cancelled) return
        const w = response.data.waiver_recommendations
        if (!w || w.error) {
          setLineupError(w?.error || response.data.error || "Couldn't score this league's free agents right now.")
          return
        }
        // The league's real current week beats the date-based guess the
        // picker starts on (it drives the Trending and Streaming tabs).
        if (typeof w.current_week === 'number') setCurrentWeek(w.current_week)
        // Your real defense, so DEF streaming compares against it without
        // typing. Replaces an earlier auto-fill, never what the user typed.
        const mine: string = w.my_defense || ''
        const previousAuto = autoDefenseRef.current  // read before the updater runs
        autoDefenseRef.current = mine
        setStreamingCurrentDefense((current) => (current === '' || current === previousAuto ? mine : current))
        setLineupImpact({
          recs: w.recommendations ?? [],
          watchOnly: !!w.watch_only,
          teamNeeds: w.team_needs ?? [],
          basis: w.basis,
        })
      })
      .catch((err) => !cancelled && setLineupError(getErrorMessage(err, "Couldn't score this league's free agents right now.")))
      .finally(() => !cancelled && setLineupLoading(false))
    return () => {
      cancelled = true
    }
  }, [selectedLeagueId, refreshKey])

  const selectLeague = (id: number | '') => {
    setSelectedLeagueId(id)
    try {
      if (id === '') localStorage.removeItem(LEAGUE_STORAGE_KEY)
      else localStorage.setItem(LEAGUE_STORAGE_KEY, String(id))
    } catch {
      // Storage unavailable (private mode) -- the choice just isn't remembered.
    }
  }

  const loadTrendingPlayers = useCallback(async () => {
    try {
      setLoading(true)

      const params: { week: number; trend_direction: string; position?: string } = {
        week: currentWeek,
        trend_direction: trendDirection
      }
      if (selectedPosition) {
        params.position = selectedPosition
      }

      const response = await waiverWire.getTrending(params)
      setTrendingPlayers(response.data.trending_players || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load trending players'))
    } finally {
      setLoading(false)
    }
  }, [currentWeek, trendDirection, selectedPosition])

  const loadAlerts = useCallback(async () => {
    try {
      setLoading(true)

      // Real in-app notifications (see NotificationBell for the same data
      // source) rather than the old dead WaiverWireAlert-backed endpoint.
      const response = await notificationsApi.list({ page_size: 20 })
      setAlerts(response.data.notifications || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load alerts'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user) {
      loadRecommendations()
    }
  }, [user, loadRecommendations])

  useEffect(() => {
    if (user && activeTab === 'trending') {
      loadTrendingPlayers()
    }
  }, [user, activeTab, loadTrendingPlayers])

  useEffect(() => {
    if (user && activeTab === 'alerts') {
      loadAlerts()
    }
  }, [user, activeTab, loadAlerts])

  const loadStreamingTargets = useCallback(async () => {
    try {
      setStreamingLoading(true)
      setStreamingError('')

      const [defenseRes, kickerRes] = await Promise.all([
        matchupAnalysis.getDefenseStreaming(currentWeek, streamingCurrentDefense.trim() || undefined),
        matchupAnalysis.getPositionOutlook('K', 3).catch(() => null),
      ])

      setStreamingData(defenseRes.data.recommendations ?? null)
      setKickerOutlook(kickerRes?.data?.position_outlook ?? null)
    } catch (err) {
      setStreamingError(getErrorMessage(err, 'Failed to load defensive streaming targets'))
      setStreamingData(null)
    } finally {
      setStreamingLoading(false)
    }
  }, [currentWeek, streamingCurrentDefense])

  useEffect(() => {
    if (user && activeTab === 'streaming' && selectedLeagueId === '') {
      loadStreamingTargets()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, activeTab, currentWeek, selectedLeagueId])

  useEffect(() => {
    setStreamingBoards(null)
    setBoardsError('')
    if (activeTab !== 'streaming' || selectedLeagueId === '') return
    let cancelled = false
    setBoardsLoading(true)
    leaguesApi.getStreaming(selectedLeagueId)
      .then((response) => !cancelled && setStreamingBoards(response.data))
      .catch((err) => !cancelled && setBoardsError(getErrorMessage(err, "Couldn't load streaming options for this league.")))
      .finally(() => !cancelled && setBoardsLoading(false))
    return () => {
      cancelled = true
    }
  }, [activeTab, selectedLeagueId, refreshKey])

  const getPriorityBadgeColor = (priority: string) => {
    const colors: Record<string, string> = {
      urgent: 'bg-danger-100 text-danger-800',
      high: 'bg-warning-100 text-warning-800',
      medium: 'bg-highlight text-accent-ink',
      low: 'bg-surface-2 text-muted',
      watch: 'bg-surface-2 text-muted'
    }
    return colors[priority] || 'bg-surface-2 text-muted'
  }

  const getTrendIcon = (direction: string) => {
    switch (direction) {
      case 'up':
        return <ArrowTrendingUpIcon className="h-4 w-4 text-success-600" />
      case 'down':
        return <ArrowTrendingDownIcon className="h-4 w-4 text-danger-600" />
      default:
        return <div className="h-4 w-4 bg-faint rounded-full" />
    }
  }

  if (!user) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center">
          <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-faint" />
          <h3 className="mt-2 text-sm font-medium text-body">Sign in required</h3>
          <p className="mt-1 text-sm text-muted">Sign in to pull waiver targets for your league.</p>
        </div>
      </div>
    )
  }

  const tabs = [
    { id: 'recommendations', name: 'Recommendations', icon: PlusIcon },
    { id: 'trending', name: 'Trending', icon: FireIcon },
    { id: 'streaming', name: 'DEF/K Streaming', icon: ShieldCheckIcon },
    { id: 'alerts', name: 'Alerts', icon: BellIcon },
  ]

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Waiver Wire</h1>
            <p className="text-muted mt-2">
              Who's available, who's trending, and who you should drop to make room.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-body">Week:</label>
              <select
                value={currentWeek}
                onChange={(e) => setCurrentWeek(parseInt(e.target.value))}
                className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
              >
                {Array.from({ length: 18 }, (_, i) => i + 1).map(week => (
                  <option key={week} value={week}>Week {week}</option>
                ))}
              </select>
            </div>
            <button
              onClick={() => setRefreshKey((k) => k + 1)}
              disabled={loading || lineupLoading}
              className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark disabled:opacity-50 flex items-center space-x-2"
            >
              <ChartBarIcon className="h-4 w-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="yard-divider mb-6" aria-hidden="true" />

      {/* Error Display */}
      {error && (
        <div className="mb-6 bg-danger-50 border border-danger-200 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-danger-400" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-danger-800">Error</h3>
              <div className="mt-2 text-sm text-danger-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="border-b border-hairline mb-6">
        <nav className="-mb-px flex gap-6 overflow-x-auto no-scrollbar">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as TabId)}
                className={`shrink-0 whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'border-accent-ink text-accent-ink'
                    : 'border-transparent text-muted hover:text-body hover:border-line'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.name}</span>
              </button>
            )
          })}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'recommendations' && (
        <div className="space-y-6">
          {/* Filters */}
          <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-lg font-medium text-body mb-4">Recommended claims</h3>
            <div className="flex flex-wrap gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-body mb-1">Position</label>
                <select
                  value={selectedPosition}
                  onChange={(e) => setSelectedPosition(e.target.value)}
                  className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
                >
                  <option value="">All Positions</option>
                  <option value="QB">Quarterback</option>
                  <option value="RB">Running Back</option>
                  <option value="WR">Wide Receiver</option>
                  <option value="TE">Tight End</option>
                  {selectedLeagueId !== '' && <option value="K">Kicker</option>}
                  {selectedLeagueId !== '' && <option value="DEF">Defense</option>}
                </select>
              </div>
              {selectedLeagueId === '' && (
              <div>
                <label className="block text-sm font-medium text-body mb-1">Priority</label>
                <select
                  value={selectedPriority}
                  onChange={(e) => setSelectedPriority(e.target.value)}
                  className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
                >
                  <option value="">All Priorities</option>
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                  <option value="watch">Watch</option>
                </select>
              </div>
              )}
              <div>
                <label className="block text-sm font-medium text-body mb-1">League</label>
                <select
                  value={selectedLeagueId}
                  onChange={(e) => selectLeague(e.target.value ? parseInt(e.target.value) : '')}
                  className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
                >
                  <option value="">No league (league-wide trending)</option>
                  {connectedLeagues.map((league) => (
                    <option key={league.id} value={league.id}>
                      {league.league_name || `${league.platform} League`}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <p className="text-xs text-muted">
              {selectedLeagueId !== ''
                ? lineupImpact?.basis || 'Every free agent in your league, scored by what he adds to your best starting lineup.'
                : connectedLeagues.length > 0
                  ? "League-wide Sleeper trending adds, not checked against your roster. Pick a league for advice built on your lineup."
                  : "League-wide Sleeper trending adds. Connect a league to get advice built on your own lineup."}
            </p>
          </div>

          {/* Waiver position -- real FAAB balance or priority rank for the
              selected league, so a recommendation can be read against
              whether a claim is actually realistic. */}
          {selectedLeagueId !== '' && waiverPosition?.supported && (
            <div className="flex flex-wrap items-center gap-3 bg-surface-2 border border-hairline rounded-lg px-4 py-3">
              <ShieldCheckIcon className="h-5 w-5 text-accent-ink shrink-0" />
              {waiverPosition.waiver_type === 'faab' ? (
                <p className="text-sm text-body">
                  <span className="font-semibold">${waiverPosition.budget_remaining}</span> of ${waiverPosition.total_budget} FAAB remaining
                  {typeof waiverPosition.budget_spent === 'number' && (
                    <span className="text-muted"> &mdash; ${waiverPosition.budget_spent} spent this season</span>
                  )}
                </p>
              ) : (
                <p className="text-sm text-body">
                  Waiver priority: <span className="font-semibold">#{waiverPosition.waiver_rank}</span> of {waiverPosition.total_teams}
                  <span className="text-muted"> &mdash; moves to the back after you win a claim</span>
                </p>
              )}
              <DataConfidenceBadge level="computed" label="Your league" />
            </div>
          )}
          {selectedLeagueId !== '' && waiverPosition && !waiverPosition.supported && (
            <p className="text-xs text-faint">{waiverPosition.detail}</p>
          )}

          {selectedLeagueId !== '' && (
            <LeagueWaiverList
              loading={lineupLoading}
              error={lineupError}
              impact={lineupImpact}
              position={selectedPosition}
              pressure={positionPressure}
            />
          )}

          {/* League-wide trending list (no league selected) */}
          {selectedLeagueId !== '' ? null : loading ? (
            <div className="bg-surface rounded-lg shadow p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
              <p className="text-sm text-muted">Scoring the wire...</p>
            </div>
          ) : recommendations.length === 0 ? (
            <div className="bg-surface rounded-lg shadow p-6 text-center">
              <MagnifyingGlassIcon className="mx-auto h-12 w-12 text-faint" />
              <h3 className="mt-2 text-sm font-medium text-body">Nothing worth claiming right now</h3>
              <p className="mt-1 text-sm text-muted">
                Try adjusting your filters or refresh the recommendations.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {recommendations.map((rec) => {
                const addCount = getAddCount(rec)
                const competition = positionPressure?.supported
                  ? positionPressure.position_pressure?.[rec.position]
                  : undefined
                return (
                  <div key={rec.player_id} className="bg-surface rounded-lg shadow p-4 sm:p-6 border-l-2 border-l-transparent hover:border-l-volt transition-colors">
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start gap-3 mb-2">
                          <PlayerAvatar
                            playerId={rec.espn_player_id}
                            name={rec.player_name}
                            position={rec.position}
                            team={rec.team}
                            size={40}
                          />
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <h4 className="text-lg font-medium text-body">{rec.player_name}</h4>
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(rec.position)}`}>
                                {rec.position}
                              </span>
                              <span className="text-sm text-muted">{rec.team}</span>
                              {rec.on_bye_this_week && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-danger-100 text-danger-800">
                                  BYE this week
                                </span>
                              )}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPriorityBadgeColor(rec.priority)}`}>
                                {rec.priority.toUpperCase()}
                              </span>
                              {rec.rank != null && rec.total_candidates != null && (
                                <span className="stat-nums text-[11px] text-faint" title="This player's rank in today's real Sleeper trending-add pool, after filtering to actual free agents in your league">
                                  #{rec.rank} of {rec.total_candidates} trending
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          {rec.roster_need === 'needs_attention' && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success-100 text-success-800">
                              Fills a roster need
                            </span>
                          )}
                          {rec.roster_need === 'overstocked' && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-2 text-muted">
                              Position already deep
                            </span>
                          )}
                          {rec.bye_week_flag && !rec.on_bye_this_week && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-danger-100 text-danger-800">
                              On bye Week {rec.bye_week}
                            </span>
                          )}
                          {rec.pass_catcher_boost && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink">
                              PPR target-share edge
                            </span>
                          )}
                          {competition && (
                            <span
                              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${COMPETITION_CLASS[competition.level]}`}
                              title={`${competition.season.teams_in_need} of ${competition.season.total_teams} other teams look thin at ${rec.position} all season`}
                            >
                              {COMPETITION_LABEL[competition.level]}
                            </span>
                          )}
                        </div>

                        <p className="text-sm text-muted mb-3">{rec.reason}</p>
                        {competition && (competition.this_week.teams_in_need > 0 || competition.season.teams_in_need > 0) && (
                          <p className="text-xs text-faint mb-3">
                            {competition.this_week.teams_in_need > 0 && (
                              <>
                                Likely in the market <em>this week</em>:{' '}
                                <span className="text-body font-medium">{formatTeamNames(competition.this_week.team_names)}</span>
                                {' '}(starting {rec.position} out/bye, no healthy bench cover).{' '}
                              </>
                            )}
                            {competition.season.teams_in_need > 0 && (
                              <>
                                Thin at {rec.position} all season:{' '}
                                <span className="text-body font-medium">{formatTeamNames(competition.season.team_names)}</span>.
                              </>
                            )}
                          </p>
                        )}
                        {rec.league_scoring_context?.scoring_format && (
                          <p className="text-xs text-faint mb-3">
                            League scoring: {rec.league_scoring_context.scoring_format}
                            {rec.league_scoring_context.points_per_reception != null &&
                              ` (${rec.league_scoring_context.points_per_reception} pts/reception)`}
                            {' '}-- shown for context, not the primary ranking signal.
                          </p>
                        )}
                        {rec.bid_tier && (
                          <div className="flex flex-wrap items-center gap-2 mb-3">
                            {rec.bid_tier.bid_type === 'faab' ? (
                              <span
                                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink"
                                title={
                                  rec.bid_tier.bid_range
                                    ? `Suggested range: $${rec.bid_tier.bid_range[0]}-$${rec.bid_tier.bid_range[1]} of your real $${rec.bid_tier.budget_remaining} remaining FAAB`
                                    : rec.bid_tier.note
                                }
                              >
                                Suggested bid: ${rec.bid_tier.suggested_bid}
                              </span>
                            ) : (
                              <span
                                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                  rec.bid_tier.recommendation === 'use_claim'
                                    ? 'bg-highlight text-accent-ink'
                                    : 'bg-surface-2 text-muted'
                                }`}
                                title={rec.bid_tier.reasoning}
                              >
                                {rec.bid_tier.recommendation === 'use_claim' ? 'Use your claim' : 'Hold priority'}
                              </span>
                            )}
                          </div>
                        )}

                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-4">
                          <div>
                            <span className="block text-xs text-muted">Season Proj (ESPN)</span>
                            <span className="font-stat tabular-nums">
                              {rec.projected_points != null ? rec.projected_points.toFixed(1) : 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="block text-xs text-muted">Owned</span>
                            <span className="font-stat tabular-nums">
                              {rec.ownership_percentage != null ? `${rec.ownership_percentage.toFixed(1)}%` : 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="block text-xs text-muted">24h Adds</span>
                            <span className="font-stat tabular-nums">
                              {addCount != null ? addCount.toLocaleString() : 'N/A'}
                            </span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-xs text-muted">Trend</span>
                            <span className="flex items-center gap-1">
                              {getTrendIcon(rec.trend_direction)}
                              <span>{rec.trend_direction}</span>
                            </span>
                          </div>
                        </div>

                        <div className="max-w-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-body">Confidence</span>
                            <DataConfidenceBadge level="computed" />
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="flex-1">
                              <ConfidenceBar value={rec.confidence_score} />
                            </div>
                            <span className="text-sm font-stat tabular-nums text-body font-medium w-10 text-right">
                              {(rec.confidence_score * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      </div>

                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'trending' && (
        <div className="space-y-6">
          {/* Trending Filters */}
          <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-lg font-medium text-body mb-4">Trending Players</h3>
            <div className="flex flex-wrap gap-4">
              <div>
                <label className="block text-sm font-medium text-body mb-1">Trend Direction</label>
                <select
                  value={trendDirection}
                  onChange={(e) => setTrendDirection(e.target.value)}
                  className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
                >
                  <option value="up">Trending Up</option>
                  <option value="down">Trending Down</option>
                  <option value="both">Both Directions</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-body mb-1">Position</label>
                <select
                  value={selectedPosition}
                  onChange={(e) => setSelectedPosition(e.target.value)}
                  className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
                >
                  <option value="">All Positions</option>
                  <option value="QB">Quarterback</option>
                  <option value="RB">Running Back</option>
                  <option value="WR">Wide Receiver</option>
                  <option value="TE">Tight End</option>
                </select>
              </div>
            </div>
          </div>

          {/* Trending Players List -- real live snapshot from Sleeper's
              trending add/drop feed (last 24h), not a historical trend
              line. See WaiverWireService.get_live_trending_players. */}
          {loading ? (
            <div className="bg-surface rounded-lg shadow p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
              <p className="text-sm text-muted">Pulling adds...</p>
            </div>
          ) : trendingPlayers.length === 0 ? (
            <div className="bg-surface rounded-lg shadow p-6 text-center py-8">
              <FireIcon className="mx-auto h-12 w-12 text-faint" />
              <h3 className="mt-2 text-sm font-medium text-body">No movement on the wire</h3>
              <p className="mt-1 text-sm text-muted">
                Try a different direction or clear the position filter.
              </p>
            </div>
          ) : (
            <div className="bg-surface rounded-lg shadow overflow-hidden">
              <table className="min-w-full divide-y divide-hairline">
                <thead className="bg-surface-2">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Player
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Direction
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Adds/Drops (24h)
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                      Source
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-surface divide-y divide-hairline">
                  {trendingPlayers.map((player) => (
                    <tr key={`${player.trend_direction}-${player.player_id}`} className="hover:bg-surface-2">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="flex-shrink-0">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPositionColor(player.position)}`}>
                              {player.position}
                            </span>
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-body">{player.player_name}</div>
                            <div className="text-sm text-muted">{player.team}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          {getTrendIcon(player.trend_direction)}
                          <span className={`ml-1 text-sm font-medium ${
                            player.trend_direction === 'up' ? 'text-success-700' : 'text-danger-700'
                          }`}>
                            {player.trend_direction === 'up' ? 'Trending up' : 'Trending down'}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-stat tabular-nums font-medium text-body">
                        {player.count_24h.toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted">
                        {player.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'alerts' && (
        <div className="space-y-6">
          <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-lg font-medium text-body mb-4">Waiver Wire Alerts</h3>
            <p className="text-sm text-muted mb-4">
              Real, backend-tracked notifications generated from genuine waiver-wire
              signal -- the same feed behind the bell icon in the navbar.
            </p>
            {alerts.length === 0 ? (
              <div className="text-center py-8">
                <BellIcon className="mx-auto h-12 w-12 text-faint" />
                <h3 className="mt-2 text-sm font-medium text-body">No alerts</h3>
                <p className="mt-1 text-sm text-muted">
                  You'll see important waiver wire notifications here.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {alerts.map((alert) => (
                  <div key={alert.id} className={`border-l-4 p-4 ${
                    alert.is_read ? 'border-line bg-surface-2' : 'border-accent-ink bg-highlight'
                  }`}>
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <BellIcon className={`h-5 w-5 ${alert.is_read ? 'text-faint' : 'text-faint'}`} />
                      </div>
                      <div className="ml-3 flex-1">
                        <h4 className="text-sm font-medium text-body">{alert.title}</h4>
                        <p className="mt-1 text-sm text-muted">{alert.body}</p>
                        <div className="mt-2 flex items-center space-x-4 text-xs text-muted">
                          <span>{new Date(alert.created_at).toLocaleString()}</span>
                          {!alert.is_read && (
                            <>
                              <span>•</span>
                              <span className="font-medium text-accent-ink">Unread</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'streaming' && selectedLeagueId !== '' && (
        <StreamingBoardsView data={streamingBoards} loading={boardsLoading} error={boardsError} />
      )}

      {activeTab === 'streaming' && selectedLeagueId === '' && (
        <div className="space-y-6">
          <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-lg font-medium text-body mb-1">Defense Streaming Targets — Week {currentWeek}</h3>
            <p className="text-sm text-muted mb-4">
              Ranked by how tough this week's matchup is, not by name recognition — the defenses opposing teams
              have historically struggled to move the ball against.
            </p>
            <div className="flex items-end space-x-4 mb-2">
              <div>
                <label className="block text-sm font-medium text-body mb-1">Your current DEF (optional)</label>
                <input
                  type="text"
                  value={streamingCurrentDefense}
                  onChange={(e) => setStreamingCurrentDefense(e.target.value.toUpperCase())}
                  placeholder="e.g. NYJ"
                  maxLength={4}
                  className="block w-32 rounded-md border-line focus:border-accent-ink focus:ring-volt uppercase"
                />
              </div>
              <button
                onClick={loadStreamingTargets}
                disabled={streamingLoading}
                className="bg-volt text-volt-ink px-4 py-2 rounded-lg hover:bg-volt-dark disabled:opacity-50 flex items-center space-x-2"
              >
                <ShieldCheckIcon className="h-4 w-4" />
                <span>{streamingCurrentDefense ? 'Compare to my DEF' : 'Refresh'}</span>
              </button>
            </div>
          </div>

          {streamingError && (
            <div className="bg-danger-50 border border-danger-200 rounded-md p-4">
              <div className="flex">
                <ExclamationTriangleIcon className="h-5 w-5 text-danger-400" />
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-danger-800">Error</h3>
                  <div className="mt-2 text-sm text-danger-700">{streamingError}</div>
                </div>
              </div>
            </div>
          )}

          {streamingLoading ? (
            <div className="bg-surface rounded-lg shadow p-6 text-center">
              <ClockIcon className="animate-spin h-8 w-8 text-accent-ink mx-auto mb-2" />
              <p className="text-sm text-muted">Loading matchup data...</p>
            </div>
          ) : !streamingError && (streamingData?.error || (!streamingData?.streaming_recommendations?.length && !streamingData?.defenses_to_avoid?.length)) ? (
            <div className="bg-surface rounded-lg shadow p-6 text-center">
              <DataConfidenceBadge level="insufficient" className="mb-3" />
              <h3 className="mt-1 text-sm font-medium text-body">No defensive matchup data for Week {currentWeek} yet</h3>
              <p className="mt-1 text-sm text-muted max-w-md mx-auto">
                This week's defensive rankings haven't been computed yet. Check back closer to kickoff, or try
                an earlier week that's already been played.
              </p>
            </div>
          ) : (
            <>
              {!!streamingData?.streaming_recommendations?.length && (
                <div className="space-y-4">
                  {streamingData.streaming_recommendations.map((target) => (
                    <div key={getTeamAbbr(target)} className="bg-surface rounded-lg shadow p-4 sm:p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3 mb-2 flex-wrap gap-y-1">
                            <h4 className="text-lg font-medium text-body">
                              {target.team_name || `${getTeamAbbr(target)} Defense`}
                            </h4>
                            <span className="text-sm text-muted">
                              {(target.is_home_game ?? target.is_home) ? 'vs' : '@'} {target.opponent || 'TBD'}
                            </span>
                            {target.waiver_priority && (
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPriorityBadgeColor(target.waiver_priority.toLowerCase())}`}>
                                {target.waiver_priority.toUpperCase()} PRIORITY
                              </span>
                            )}
                            {target.availability_tier && (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-2 text-muted">
                                {target.availability_tier}
                              </span>
                            )}
                          </div>

                          {!!target.key_factors?.length && (
                            <div className="flex flex-wrap gap-2 mb-3">
                              {target.key_factors.map((factor, idx) => (
                                <span key={idx} className="text-xs bg-surface-2 text-muted px-2 py-1 rounded">
                                  {factor}
                                </span>
                              ))}
                            </div>
                          )}

                          <div className="max-w-sm">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm font-medium text-body">Matchup Rating</span>
                              <DataConfidenceBadge level="heuristic" label="Composite rating" />
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="flex-1">
                                <MatchupRatingBar rating={target.matchup_rating} />
                              </div>
                              <span className="text-sm font-stat tabular-nums text-body font-medium w-12 text-right">
                                {target.matchup_rating.toFixed(1)}/10
                              </span>
                            </div>
                            {(target.avg_points_allowed != null || target.recent_trend != null) && (
                              <p className="mt-1 text-xs text-muted">
                                {target.avg_points_allowed != null && `${target.avg_points_allowed.toFixed(1)} pts allowed (season avg)`}
                                {target.avg_points_allowed != null && target.recent_trend != null && ' · '}
                                {target.recent_trend != null && `${target.recent_trend.toFixed(1)} last 4 wks`}
                              </p>
                            )}
                            {!!streamingData?.current_defense && target.improvement_over_current != null && (
                              <p className="mt-1 text-xs text-success-700 font-medium">
                                +{target.improvement_over_current.toFixed(1)} better than your current DEF
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!!streamingData?.defenses_to_avoid?.length && (
                <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
                  <h4 className="font-medium text-body mb-3 flex items-center space-x-2">
                    <NoSymbolIcon className="h-5 w-5 text-danger-500" />
                    <span>Defenses to Avoid This Week</span>
                  </h4>
                  <div className="space-y-3">
                    {streamingData.defenses_to_avoid.map((target) => (
                      <div key={getTeamAbbr(target)} className="border border-danger-200 bg-danger-50 rounded p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-body">
                            {target.team_name || `${getTeamAbbr(target)} Defense`}
                            <span className="ml-2 text-sm font-normal text-muted">
                              {(target.is_home_game ?? target.is_home) ? 'vs' : '@'} {target.opponent || 'TBD'}
                            </span>
                          </span>
                          <span className="text-xs font-stat tabular-nums text-danger-700 font-medium">
                            {target.matchup_rating.toFixed(1)}/10
                          </span>
                        </div>
                        {target.recommendation && <p className="text-sm text-muted">{target.recommendation}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Kicker matchup outlook -- smaller secondary section, same data source */}
          <div className="bg-surface rounded-lg shadow p-4 sm:p-6">
            <h4 className="font-medium text-body mb-1">Kicker Matchup Outlook</h4>
            <p className="text-sm text-muted mb-4">Best and worst upcoming matchups for streaming a kicker.</p>
            {!kickerOutlook || kickerOutlook.error || !Object.keys(kickerOutlook.weekly_outlook || {}).length ? (
              <div className="text-center py-4">
                <DataConfidenceBadge level="insufficient" />
                <p className="mt-2 text-sm text-muted">No kicker matchup data available yet for the upcoming weeks.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {Object.entries(kickerOutlook.weekly_outlook).map(([week, outlook]) => (
                  <div key={week} className="border border-hairline rounded p-3">
                    <div className="text-sm font-medium text-body mb-2">Week {week}</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-xs uppercase text-muted">Best matchups</span>
                        <ul className="mt-1 space-y-1">
                          {outlook.best_matchups.map((m) => (
                            <li key={m.team} className="flex justify-between text-body">
                              <span>{m.team}</span>
                              <span className="font-stat tabular-nums text-success-700">{m.rating.toFixed(1)}/10</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <span className="text-xs uppercase text-muted">Worst matchups</span>
                        <ul className="mt-1 space-y-1">
                          {outlook.worst_matchups.map((m) => (
                            <li key={m.team} className="flex justify-between text-body">
                              <span>{m.team}</span>
                              <span className="font-stat tabular-nums text-danger-700">{m.rating.toFixed(1)}/10</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  )
}

// Response shapes and pure helpers for the Waivers page and its tabs.
import { type LineupWaiverRec, type TeamNeed } from '../LineupWaivers'

export interface WaiverRecommendation {
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

export interface ConnectedLeagueOption {
  id: number
  league_name: string | null
  platform: string
  team_id: string | null
}

// Real FAAB balance or rolling-priority rank for the selected league -- see
// GET /leagues/{id}/waiver-position. `supported: false` covers non-ESPN
// leagues and leagues with no team_id set yet; `waiver_type` picks which of
// the two mutually-exclusive fields this league actually uses.
export interface WaiverPosition {
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
export interface PositionPressureEntry {
  season: { teams_in_need: number; total_teams: number; team_names: string[]; ratio: number }
  this_week: { teams_in_need: number; team_names: string[] }
  level: 'high' | 'medium' | 'low'
}
export interface PositionPressure {
  supported: boolean
  detail?: string
  position_pressure?: Record<string, PositionPressureEntry>
  other_teams_considered?: number
}

export const COMPETITION_LABEL: Record<'high' | 'medium' | 'low', string> = {
  high: 'High competition',
  medium: 'Some competition',
  low: 'Low competition',
}
export function formatTeamNames(names: string[], max = 3): string {
  if (names.length <= max) return names.join(', ')
  return `${names.slice(0, max).join(', ')}, +${names.length - max} more`
}

export const COMPETITION_CLASS: Record<'high' | 'medium' | 'low', string> = {
  high: 'bg-danger-100 text-danger-800',
  medium: 'bg-warning-100 text-warning-800',
  low: 'bg-success-100 text-success-800',
}

// The "Alerts" tab now reads the app's real in-app notification center
// (see backend/app/services/notification_service.py) instead of the old
// GET /waiver-wire/alerts stub, which queried a WaiverWireAlert table
// nothing ever wrote to. `Notification` is the real, shared shape used by
// the navbar bell too -- see src/types/index.ts.

export interface TrendingPlayer {
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

export interface DefenseStreamingTarget {
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

export interface DefenseStreamingRecommendations {
  week: number
  current_defense?: string | null
  streaming_recommendations?: DefenseStreamingTarget[]
  defenses_to_avoid?: DefenseStreamingTarget[]
  analysis_notes?: string[]
  error?: string
}

export interface PositionOutlookWeek {
  best_matchups: { team: string; rating: number; rank: number; points_allowed: number }[]
  worst_matchups: { team: string; rating: number; rank: number; points_allowed: number }[]
  week_average_rating: number
}

export interface PositionOutlook {
  position: string
  weeks_analyzed: number
  weekly_outlook: Record<string, PositionOutlookWeek>
  total_rankings_analyzed: number
  error?: string
}

export interface StreamingPlayer {
  name: string
  team?: string
  position?: { value?: string }
  week_projection?: number
  ownership_percentage?: number | null
  espn_player_id?: number | null
  // This week's Vegas game context (odds_service.py); null on bye or when
  // no odds key is configured.
  vegas?: {
    opponent: string
    home: boolean
    spread: number
    game_total: number
    team_implied_total: number
    opponent_implied_total: number
    // DEF: the opponent's implied total (lower is better); K: his team's.
    key_number: number
  } | null
}

export interface StreamingBoards {
  current_week?: number | null
  projection_source: string
  odds_source?: string | null
  boards: {
    position: string
    current: StreamingPlayer | null
    options: { player: StreamingPlayer; week_edge: number }[]
  }[]
}

export type TabId = 'recommendations' | 'trending' | 'alerts' | 'streaming'

export interface LineupImpact {
  recs: LineupWaiverRec[]
  watchOnly: boolean
  teamNeeds: TeamNeed[]
  basis?: string
}

export const LEAGUE_STORAGE_KEY = 'waivers.leagueId'

export function readStoredLeagueId(): number | null {
  try {
    const raw = localStorage.getItem(LEAGUE_STORAGE_KEY)
    return raw ? parseInt(raw, 10) : null
  } catch {
    return null
  }
}

// Helper function to get current NFL week
export function getCurrentNFLWeek(): number {
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
export function getAddCount(rec: WaiverRecommendation): number | null {
  if (typeof rec.add_count_24h === 'number') {
    return rec.add_count_24h
  }
  const match = rec.reason?.match(/([\d,]+)\s+adds/)
  if (match) {
    return parseInt(match[1].replace(/,/g, ''), 10)
  }
  return null
}

export function getTeamAbbr(target: DefenseStreamingTarget): string {
  return target.team_abbreviation || target.team || '?'
}

// The lineup-impact list for the selected league: the same engine and card
// as League Detail's Waiver tab, plus this page's competition signal
// (other teams thin at the position).

export const getPriorityBadgeColor = (priority: string) => {
  const colors: Record<string, string> = {
    urgent: 'bg-danger-100 text-danger-800',
    high: 'bg-warning-100 text-warning-800',
    medium: 'bg-highlight text-accent-ink',
    low: 'bg-surface-2 text-muted',
    watch: 'bg-surface-2 text-muted'
  }
  return colors[priority] || 'bg-surface-2 text-muted'
}

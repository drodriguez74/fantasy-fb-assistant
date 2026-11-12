// Response shapes and pure helpers for the League Detail page and its tabs.
import type { LineupWaiverRec, TeamNeed } from '../../waivers/LineupWaivers'

export interface LeagueInfo {
  id: number
  name: string
  platform: string
  season: number
  scoring_format: string
  league_size: number
}

export interface RosterPlayer {
  name: string
  player_id?: number | null
  position?: string
  team?: string
  total_points?: number
  projected_points?: number
  injury_status?: string
}

export interface PositionAnalysisEntry {
  grade: string
  summary?: string
  recommendations?: string[]
}

export interface RosterAnalysis {
  team_name?: string
  owner?: string
  roster_size?: number
  total_players: number
  position_analysis?: Record<string, PositionAnalysisEntry>
  composition?: {
    starting_lineup: RosterPlayer[]
    bench_players: RosterPlayer[]
    composition_score: number
  }
  overall_grade: {
    grade: string
    score: number
    description: string
    player_count?: number
    avg_player_value?: number
  }
  strengths_weaknesses?: {
    strengths: string[]
    weaknesses: string[]
  }
  strengths?: string[]
  weaknesses?: string[]
  players?: RosterPlayer[]
  injury_concerns?: { player: string; position?: string; team?: string; status?: string }[]
  last_updated?: string
}

export interface WaiverRecommendation {
  recommendations: LineupWaiverRec[]
  position_needs: Record<string, number>
  team_needs?: TeamNeed[]
  watch_only?: boolean
  basis?: string
  total_available: number
  updated_at: string
}

export interface TradePlayerRef {
  name: string
  position?: string
  team?: string
  projected_points?: number
}

export interface TradeSuggestion {
  // Real, roster-grounded suggestions (ESPN + Yahoo, trade_finder_service) --
  // every player named is a real rostered player on a real other team.
  team_id?: number
  team_name?: string
  you_send?: TradePlayerRef
  // Every player sent (2-for-1 deals); you_send is the first of these.
  you_send_players?: TradePlayerRef[]
  you_receive?: TradePlayerRef
  // Season team-value change for each side (league_value_model).
  my_gain?: number
  their_gain?: number
  value_ratio?: number
  // Legacy AI-generated scenario shape -- no backend path produces it any
  // more; kept so an old cached response still renders.
  target_player?: string
  offer_players?: string[]
  likelihood?: string
  reasoning?: string
}

export interface TradeRecommendation {
  suggestions: TradeSuggestion[]
  trade_deadline: string
  updated_at: string
  // Present on the real roster-grounded path (ESPN + Yahoo) --
  // distinguishes it from the legacy AI-generated shape in the UI.
  basis?: string
  team_needs?: TeamNeed[]
}

export interface StandingsTeam {
  rank: number
  name?: string
  team_name?: string
  wins?: number | string
  losses?: number | string
  // Yahoo sends these as strings (e.g. "458.55"), ESPN as numbers.
  points_for?: number | string
  points_against?: number | string
}

export interface StandingsData {
  teams: StandingsTeam[]
  user_team_rank: number
  total_teams: number
  playoff_teams: number
  updated_at: string
}

export interface ThisWeekPlayer {
  name: string
  player_id?: number | null
  position?: string
  slot_position?: string
  team?: string
  pro_opponent?: string
  injury_status?: string
  projected_points?: number
  points?: number
  game_played?: number
  on_bye?: boolean
}

export interface ThisWeekSwap {
  slot?: string
  bench_out: { name: string; position?: string; projected_points?: number }
  start_in: { name: string; position?: string; team?: string; projected_points?: number }
  delta: number
  // Real signal, not just the point delta: downgraded to 'risky' when the
  // suggested replacement itself carries a live injury designation.
  confidence?: 'strong' | 'moderate' | 'lean' | 'risky'
}

export interface StartSitCall {
  name: string
  position?: string
  slot?: string
  tier: 'locked' | 'comfortable' | 'moderate' | 'toss_up' | 'risky'
  margin: number | null
  best_bench_alternative?: string | null
}

export interface ThisWeekMatchupSide {
  team_name?: string
  live_score?: number
  projected_score?: number
  wins?: number
  losses?: number
  ties?: number
  rank?: number
}

export interface ThisWeekData {
  league_info?: LeagueInfo
  platform_supported: boolean
  detail?: string
  week?: number
  matchup?: {
    my_team: ThisWeekMatchupSide
    opponent: ThisWeekMatchupSide
    projected_margin: number
    favored: 'my_team' | 'opponent' | 'even'
    // Yahoo's own real server-computed win probability for this matchup
    // -- ESPN has no equivalent field, so this is Yahoo-only.
    win_probability?: number | null
  }
  lineup?: ThisWeekPlayer[]
  // The opponent's real lineup for this same matchup (same shape as
  // `lineup`) -- powers the side-by-side H2H view. Real ESPN box-score
  // data, same source as `lineup`.
  opponent_lineup?: ThisWeekPlayer[]
  // `null` (not just an empty-swaps object) when no real per-player
  // projection could be loaded to optimize against; distinct from a real
  // "already optimal" result (swaps: []).
  optimization?: {
    current_projected: number
    optimized_projected: number
    points_gained: number
    swaps: ThisWeekSwap[]
  } | null
  starter_injuries?: { name: string; position?: string; status?: string }[]
  start_sit?: StartSitCall[]
  // Where per-player projections came from when they aren't the
  // platform's own (Yahoo: Sleeper's weekly feed scored with the league's
  // rules). Absent for ESPN, whose projections are its own.
  projection_source?: string | null
  // Explains the projection source, or why optimization is unavailable.
  projection_note?: string
  _cache?: { as_of: string; age_seconds: number; stale: boolean; source: string }
}

// The real "Matchups" screen: this team's actual result every week of the
// season so far (GET /leagues/{id}/matchup-history). Distinct from
// ThisWeekData, which is the live box score for the CURRENT week only.
export interface MatchupHistoryWeek {
  week: number
  opponent_team_id: number | null
  opponent_name: string
  my_score: number
  opponent_score: number
  result: 'win' | 'loss' | 'tie' | 'bye' | 'upcoming'
}
export interface MatchupHistoryData {
  supported: boolean
  detail?: string
  through_week?: number
  matchups?: MatchupHistoryWeek[]
  record?: { wins: number; losses: number; ties: number }
  _cache?: { as_of: string; age_seconds: number; stale: boolean; source: string }
}

export interface UpcomingBye {
  player_name: string
  position: string | null
  team: string
  bye_week: number
  weeks_until_bye: number
  lineup_slot: string | null
}

export interface ByeWeekRadarData {
  supported: boolean
  detail?: string
  team_name?: string
  current_week?: number
  upcoming_byes?: UpcomingBye[]
  _cache?: { as_of: string; age_seconds: number; stale: boolean; source: string }
}

export const STALE_RETRY_DELAYS_MS = [7000, 15000, 30000]

export function relTime(iso?: string): string {
  if (!iso) return ''
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (secs < 45) return 'just now'
  if (secs < 90) return '1 min ago'
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`
  if (secs < 5400) return '1 hr ago'
  return `${Math.round(secs / 3600)} hr ago`
}

export interface H2HRow {
  slot: string
  mine?: ThisWeekPlayer
  theirs?: ThisWeekPlayer
}

// Pairs two same-category lineups (both starters, or both bench) by their
// real ESPN slot_position -- both teams share the same league roster
// requirements, so e.g. "2 RB starters" lines up as two rows even though
// each side's box score lists its own players independently. A slot with
// more of one side than the other (rare -- a bye/IR gap) just leaves the
// short side's cell empty rather than mis-pairing players.
export function pairBySlot(mine: ThisWeekPlayer[], theirs: ThisWeekPlayer[]): H2HRow[] {
  const bucket = (arr: ThisWeekPlayer[]) => {
    const m = new Map<string, ThisWeekPlayer[]>()
    for (const p of arr) {
      const slot = (p.slot_position || '').toUpperCase()
      if (!m.has(slot)) m.set(slot, [])
      m.get(slot)!.push(p)
    }
    return m
  }
  const mineBuckets = bucket(mine)
  const theirBuckets = bucket(theirs)

  const orderedSlots: string[] = []
  const seen = new Set<string>()
  for (const p of [...mine, ...theirs]) {
    const slot = (p.slot_position || '').toUpperCase()
    if (!seen.has(slot)) {
      seen.add(slot)
      orderedSlots.push(slot)
    }
  }

  const rows: H2HRow[] = []
  for (const slot of orderedSlots) {
    const mineArr = mineBuckets.get(slot) || []
    const theirArr = theirBuckets.get(slot) || []
    const n = Math.max(mineArr.length, theirArr.length)
    for (let i = 0; i < n; i++) {
      rows.push({ slot, mine: mineArr[i], theirs: theirArr[i] })
    }
  }
  return rows
}

export type LeagueTab = 'this-week' | 'roster' | 'matchups' | 'standings' | 'waiver' | 'trades' | 'scoring'

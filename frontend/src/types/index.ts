// User and Authentication types
export type User = {
  id: number
  email: string
  username: string
  full_name?: string
  is_active: boolean
  is_verified: boolean
  avatar_url?: string
  bio?: string
  timezone?: string
  preferred_scoring?: string
  favorite_teams?: string[]
  notifications_enabled: boolean
  created_at: string
}

export type LoginRequest = {
  username: string
  password: string
}

export type RegisterRequest = {
  email: string
  username: string
  password: string
  full_name: string
}

export type AuthResponse = {
  access_token: string
  token_type: string
  user: User
}

// Player types
export type Position = 'QB' | 'RB' | 'WR' | 'TE' | 'K' | 'DEF'

export type Player = {
  id: number
  name: string
  team: string
  position: Position
  espn_id?: string
  yahoo_id?: string
  sleeper_id?: string
  projected_points?: number
  adp?: number
  bye_week?: number
  injury_status?: string
  depth_chart_order?: number
  ai_analysis?: string
  risk_level?: 'LOW' | 'MEDIUM' | 'HIGH'
  created_at: string
  updated_at?: string
  consensus?: ConsensusRanking
}

// Real, inspectable consensus ADP rank blended from whichever ranking
// sources are actually available for this player (see backend's
// ConsensusRankingService) -- Sleeper's search_rank always, ESPN's
// percent_owned only when the request has a live ESPN session/league
// context, and FantasyPros' rank_ecr only when the backend has a real
// FANTASYPROS_API_KEY configured. `source_count` (0-3) tells the reader
// whether this is a genuine multi-source blend or degraded to fewer
// sources -- render it dynamically, don't assume a fixed ceiling.
export interface ConsensusRanking {
  consensus_rank: number
  consensus_score: number
  sources: {
    sleeper_rank?: number
    espn_ownership_pct?: number
    fantasypros_rank_ecr?: number
  }
  source_count: number
}

// Draft types
export interface DraftSession {
  id: number
  user_id: number
  session_id: string
  platform: string
  league_id: string
  user_team_id?: string
  draft_settings?: Record<string, unknown>
  is_active: boolean
  is_completed: boolean
  user_roster?: Player[]
  draft_grade?: string
  final_analysis?: string
  recommendations_used?: number
  ai_accuracy_score?: number
  started_at: string
  completed_at?: string
  last_activity: string
}

export interface DraftRecommendation {
  player: Player
  score: number
  reasoning: string
  tier: number
  position_rank: number
  value_over_replacement: number
  injury_risk: string
  bye_week_impact: number
}

export interface DraftPick {
  id: number
  session_id: string
  player_id: number
  team_id: string
  round: number
  pick: number
  timestamp: string
  player: Player
}

// League types
export type PlatformType = 'SLEEPER' | 'ESPN' | 'YAHOO' | 'NFL' | 'CBS'

export interface UserLeague {
  id: number
  user_id: number
  platform: PlatformType
  league_id: string
  league_key?: string
  team_id?: string
  league_name?: string
  season?: number
  scoring_format?: string
  league_size?: number
  is_commissioner: boolean
  is_active: boolean
  enable_notifications: boolean
  auto_draft_assistant: boolean
  added_at: string
  last_synced?: string
}

// Blog and Content types
export interface BlogPost {
  id: number
  title: string
  slug: string
  content: string
  summary?: string
  source_urls?: string[]
  perspectives_count?: number
  consensus_score?: number
  tags?: string
  category?: string
  is_published: boolean
  publish_date?: string
  created_by_ai: boolean
  ai_model_used?: string
  created_at: string
  updated_at?: string
  featured?: boolean
  author?: string
}

export interface ContentGenerationRequest {
  topic: string
  content_type: 'waiver_wire' | 'draft_prep' | 'trade_analysis' | 'start_sit' | 'injury_report'
  settings?: {
    perspectives?: number
    scoring_format?: string
    league_size?: number
    focus_positions?: Position[]
  }
}

// API Response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export interface ApiError {
  detail: string
  status_code: number
}

// Component Props types
export interface PlayerCardProps {
  player: Player
  onClick?: (player: Player) => void
  showDetails?: boolean
  isDraftMode?: boolean
}

export interface DraftBoardProps {
  session: DraftSession
  recommendations: DraftRecommendation[]
  onPlayerSelect: (player: Player) => void
}

// Filter and search types
export interface PlayerFilters {
  position?: Position
  team?: string
  available_only?: boolean
  injury_status?: string
  min_projected_points?: number
  max_adp?: number
}

export interface DraftFilters {
  position?: Position
  tier?: number
  value_threshold?: number
  exclude_bye_weeks?: number[]
}

// In-app notification center types (not device/browser push -- see
// backend/app/models/notification.py for the scoping rationale)
export type NotificationType = 'trending_add' | 'injury_update'

export interface Notification {
  id: number
  type: NotificationType | string
  title: string
  body: string
  is_read: boolean
  created_at: string
}
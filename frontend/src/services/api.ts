import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api/v1'

// Backend error details are sometimes raw exception/traceback text (e.g. a
// leaked SQLAlchemy/psycopg2 error) rather than a friendly message. We never
// want to render that verbatim to end users, so treat anything that "looks"
// like internal/technical error output as unsafe to display.
function looksLikeRawServerError(text: string): boolean {
  if (text.length > 300) return true
  const rawErrorSignals = [
    'Traceback',
    'File "',
    'psycopg2',
    'sqlalchemy',
    'SQLAlchemy',
    '[SQL:',
    'Background on this error at:',
    'sqlalche.me',
    'StatementError',
  ]
  return rawErrorSignals.some((signal) => text.includes(signal))
}

// Narrow an unknown error (typically from an axios request) down to a
// human-readable message, falling back to a caller-supplied default when the
// error doesn't carry a recognizable `detail` string, or when that string
// looks like raw/technical server internals that shouldn't be shown to users.
export function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail) {
      if (looksLikeRawServerError(detail)) {
        console.error('Suppressed raw backend error detail from UI:', detail)
        return fallback
      }
      return detail
    }
  }
  if (err instanceof Error && err.message) {
    if (looksLikeRawServerError(err.message)) {
      console.error('Suppressed raw error message from UI:', err.message)
      return fallback
    }
    return err.message
  }
  return fallback
}

// Create axios instance with default config
export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle token expiration
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/auth'
    }
    return Promise.reject(error)
  }
)

// Auth endpoints
export const auth = {
  register: (data: { email: string; username: string; password: string; full_name: string }) =>
    api.post('/auth/register', data),
  
  login: (data: { username: string; password: string }) =>
    api.post('/auth/login', { email: data.username, password: data.password }),
  
  getProfile: () => api.get('/auth/me'),
  
  // PUT /users/me (not /auth/me -- there is no PUT under the /auth prefix,
  // only GET /auth/me; profile updates are handled by users.py).
  updateProfile: (data: Record<string, unknown>) => api.put('/users/me', data),
}

// League endpoints
export const leagues = {
  getAll: () => api.get('/leagues/'),
  
  getYahooAuthUrl: () => api.get('/leagues/yahoo/auth-url'),
  
  connectYahoo: (authorizationCode: string) => 
    api.post('/leagues/yahoo/connect', { authorization_code: authorizationCode }),
  
  testEspnConnection: (leagueId: string, season?: number, swid?: string, espnS2?: string) =>
    api.get('/leagues/espn/test-connection', { 
      params: { league_id: leagueId, season, swid, espn_s2: espnS2 } 
    }),
  
  connectEspn: (leagueId: string, season?: number, swid?: string, espnS2?: string, teamId?: string) =>
    api.post('/leagues/espn/connect', {
      league_id: leagueId,
      season: season || 2024,
      swid,
      espn_s2: espnS2,
      team_id: teamId,
    }),

  getEspnTeams: (leagueId: string, season?: number, swid?: string, espnS2?: string) =>
    api.get('/leagues/espn/teams', {
      params: { league_id: leagueId, season, swid, espn_s2: espnS2 }
    }),

  getSleeperTeams: (leagueId: string, username?: string) =>
    api.get('/leagues/sleeper/teams', {
      params: { league_id: leagueId, username: username || undefined }
    }),

  connectSleeper: (leagueId: string, teamId?: string, username?: string) =>
    api.post('/leagues/sleeper/connect', {
      league_id: leagueId,
      team_id: teamId,
      username: username || undefined,
    }),

  getStandings: (leagueId: number) => api.get(`/leagues/${leagueId}/standings`),

  updateSettings: (leagueId: number, settings: Record<string, unknown>) =>
    api.put(`/leagues/${leagueId}/settings`, settings),

  disconnect: (leagueId: number) => api.delete(`/leagues/${leagueId}`),
}

// Players endpoints
export const players = {
  getAll: (params?: { position?: string; team?: string; sort?: 'rank' | 'bye_week' | 'consensus'; page?: number; page_size?: number }) =>
    api.get('/players/', { params }),
  
  getFromDatabase: (params?: { 
    position?: string; 
    team?: string; 
    injury_status?: string;
    min_projected_points?: number;
    max_risk_level?: string;
    page?: number; 
    page_size?: number;
  }) =>
    api.get('/players/database', { params }),
  
  getById: (id: number) => api.get(`/players/${id}`),
  
  search: (query: string) => api.get(`/players/search/${encodeURIComponent(query)}`),
  
  addFromSleeper: (sleeperId: string) => api.post('/players/add-from-sleeper', { sleeper_id: sleeperId }),
  
  generateAnalysis: (playerId: string) => api.post(`/players/${playerId}/analysis`),
  
  getQuickAnalysis: (playerId: string, includeAI: boolean = false) => 
    api.get(`/players/${playerId}/quick-analysis?include_ai=${includeAI}`),
}

// Draft endpoints
export const draft = {
  // Direct draft recommendations (non-session based)
  getDraftRecommendations: (data: {
    available_players: unknown[];
    team_needs: string[];
    draft_position: number;
    scoring_format?: string;
    league_size?: number;
  }) => api.post('/draft/recommendations', data),

  getTrendingCandidates: (params?: { hours?: number; limit?: number }) =>
    api.get('/draft/trending-candidates', { params }),

  getPositionalRankings: (position: string, params?: { limit?: number }) =>
    api.get(`/draft/positional-rankings/${position}`, { params }),

  getLeagueAnalysis: (leagueId: string) =>
    api.get(`/draft/league-analysis/${leagueId}`),

  getWaiverCandidates: (leagueId: string) =>
    api.get(`/draft/waiver-candidates/${leagueId}`),

  getProjections: (week: number, params?: { season?: string }) =>
    api.get(`/draft/projections/week/${week}`, { params }),
}

// Historical data endpoints
export const historical = {
  sync: (data: { seasons?: number[]; force_refresh?: boolean }) =>
    api.post('/historical/sync', data),
  
  getOverview: () => api.get('/historical/stats/overview'),
  
  getPlayerSummary: (playerId: number, seasons?: number) =>
    api.get(`/historical/players/${playerId}/summary`, { params: { seasons } }),
  
  getPlayerTrends: (playerId: number) =>
    api.get(`/historical/players/${playerId}/trends`),
  
  getWeeklyPerformance: (playerId: number, season: number) =>
    api.get(`/historical/players/${playerId}/weekly-performance/${season}`),
  
  getPositionAnalysis: (position: string, seasons?: number) =>
    api.get(`/historical/positions/${position}/analysis`, { params: { seasons } }),
  
  comparePlayers: (data: { player_ids: number[]; seasons?: number }) =>
    api.post('/historical/players/compare', data),
  
  getSeasonSummaries: (playerId: number) =>
    api.get(`/historical/players/${playerId}/season-summaries`),
  
  getConsistencyAnalysis: (playerId: number, seasons?: number) =>
    api.get(`/historical/players/${playerId}/consistency-analysis`, { params: { seasons } }),
  
  getLeagueTrends: (params?: { position?: string; trend_type?: string; limit?: number }) =>
    api.get('/historical/trends/league-wide', { params }),
}

// Waiver wire endpoints
export const waiverWire = {
  getRecommendations: (params: { week: number; season?: number; position?: string; priority?: string; limit?: number }) =>
    api.get('/waiver-wire/recommendations', { params }),
  
  getRecommendationsByPriority: (priority: string, params: { week: number; season?: number; limit?: number }) =>
    api.get(`/waiver-wire/recommendations/priority/${priority}`, { params }),
  
  analyzeRoster: (data: { roster_player_ids: number[]; week?: number; season?: number }) =>
    api.post('/waiver-wire/analyze-roster', data),
  
  // Real-time snapshot from Sleeper's live trending add/drop feed (see
  // backend/app/services/waiver_wire_service.py::get_live_trending_players).
  // NOT a historical trend line -- WaiverWireTrend, the table this used to
  // (always-emptily) query, has no real ingestion pipeline behind it.
  getTrending: (params: { week: number; season?: number; position?: string; trend_direction?: string; limit?: number }) =>
    api.get('/waiver-wire/trending', { params }),

  generateRecommendations: (params: { week: number; season?: number; force_refresh?: boolean }) =>
    api.post('/waiver-wire/generate-recommendations', null, { params }),

  getPlayerEvaluation: (playerId: number, params: { week: number; season?: number }) =>
    api.get(`/waiver-wire/player/${playerId}/evaluation`, { params }),

  getWeeklyInsights: (params: { week: number; season?: number }) =>
    api.get('/waiver-wire/insights/weekly-summary', { params }),

  // NOTE: getAlerts/subscribeToAlerts (GET/POST /waiver-wire/alerts*) were
  // removed -- both queried/wrote a table nothing in the backend ever
  // populated. The Alerts tab now reads the real in-app notification center
  // via the `notifications` export below instead.
}

// Matchup analysis endpoints (backend/app/api/v1/endpoints/matchup_analysis.py)
// -- defensive-streaming targets and position-vs-defense outlook, driven by
// live NFL schedule + defensive-ranking data rather than a static heuristic.
export const matchupAnalysis = {
  getDefenseStreaming: (week: number, currentDefense?: string) =>
    api.get(`/matchup-analysis/defense-streaming/${week}`, {
      params: currentDefense ? { current_defense: currentDefense } : undefined,
    }),

  getPositionOutlook: (position: string, weeksAhead?: number) =>
    api.get(`/matchup-analysis/position-outlook/${position}`, {
      params: weeksAhead ? { weeks_ahead: weeksAhead } : undefined,
    }),

  getCurrentWeek: () => api.get('/matchup-analysis/current-week'),
}

// Trade analyzer endpoints
export const trade = {
  searchPlayers: (q: string, limit?: number) =>
    api.get('/trade/player-search', { params: { q, limit } }),

  analyze: (data: { side_a_gives: string[]; side_b_gives: string[] }) =>
    api.post('/trade/analysis', data),
}

// Manual league scoring override endpoints (backend/app/api/v1/endpoints/
// league_scoring.py). A real, hand-entered scoring configuration that takes
// priority over auto-detected platform scoring rules for the draft
// assistant (see draft_assistant_service.py's _apply_manual_scoring_override)
// -- useful for modeling a hypothetical scoring change, a platform without
// real settings access, or correcting an auto-detected value. `leagueId`
// throughout is the app's own UserLeague row id (the same id used by the
// `leagues` endpoints above), not the platform's external league id.
export interface LeagueScoringConfig {
  user_league_id: number
  scoring_type?: 'PPR' | 'Half_PPR' | 'Standard' | 'Custom'
  reception_points?: number
  passing_yards_per_point?: number
  passing_td_points?: number
  passing_int_points?: number
  completion_points?: number
  incompletion_points?: number
  rushing_yards_per_point?: number
  rushing_td_points?: number
  receiving_yards_per_point?: number
  receiving_td_points?: number
  target_points?: number
  fumble_lost_points?: number
}

export const leagueScoring = {
  get: (leagueId: number) => api.get(`/league-scoring/league/${leagueId}`),

  configure: (data: LeagueScoringConfig) => api.post('/league-scoring/configure', data),

  getPresets: () => api.get('/league-scoring/presets'),
}

// In-app notification center endpoints (not device/browser push -- see
// backend/app/models/notification.py for the scoping rationale)
export const notifications = {
  list: (params?: { page?: number; page_size?: number; unread_only?: boolean }) =>
    api.get('/notifications/', { params }),

  getUnreadCount: () => api.get('/notifications/unread-count'),

  markRead: (notificationId: number) => api.post(`/notifications/${notificationId}/read`),

  markAllRead: () => api.post('/notifications/read-all'),
}

export default api
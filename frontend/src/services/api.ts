import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api/v1'

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
      window.location.href = '/login'
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
  
  updateProfile: (data: any) => api.put('/auth/me', data),
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
  
  connectEspn: (leagueId: string, season?: number, swid?: string, espnS2?: string) =>
    api.post('/leagues/espn/connect', { 
      league_id: leagueId, 
      season: season || 2024, 
      swid, 
      espn_s2: espnS2 
    }),
  
  getAnalysis: (leagueId: number) => api.get(`/leagues/${leagueId}/analysis`),
  
  getMatchups: (leagueId: number, week?: number) => 
    api.get(`/leagues/${leagueId}/matchups${week ? `?week=${week}` : ''}`),
  
  getStandings: (leagueId: number) => api.get(`/leagues/${leagueId}/standings`),
  
  disconnect: (leagueId: number) => api.delete(`/leagues/${leagueId}`),
}

// Players endpoints
export const players = {
  getAll: (params?: { position?: string; team?: string; page?: number; page_size?: number }) =>
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
  startSession: (data: { platform: string; league_id: string; settings?: any }) =>
    api.post('/draft/start', data),
  
  getRecommendations: (sessionId: string, params?: any) =>
    api.get(`/draft/${sessionId}/recommendations`, { params }),
  
  recordPick: (sessionId: string, data: { player_id: number; team_id: string; round: number; pick: number }) =>
    api.post(`/draft/${sessionId}/picks`, data),
  
  getSession: (sessionId: string) => api.get(`/draft/${sessionId}`),
  
  endSession: (sessionId: string) => api.post(`/draft/${sessionId}/end`),

  // Direct draft recommendations (non-session based)
  getDraftRecommendations: (data: {
    available_players: any[];
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

// Content endpoints
export const content = {
  getBlogPosts: (params?: { category?: string; page?: number }) =>
    api.get('/content/blog-posts/', { params }),
  
  getBlogPost: (slug: string) => api.get(`/content/blog-posts/${slug}`),
  
  generateContent: (data: { topic: string; content_type: string; settings?: any }) =>
    api.post('/content/generate', data),
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
  getRecommendations: (params: { week: number; season?: number; position?: string; limit?: number }) =>
    api.get('/waiver-wire/recommendations', { params }),
  
  getRecommendationsByPriority: (priority: string, params: { week: number; season?: number; limit?: number }) =>
    api.get(`/waiver-wire/recommendations/priority/${priority}`, { params }),
  
  analyzeRoster: (data: { roster_player_ids: number[]; week?: number; season?: number }) =>
    api.post('/waiver-wire/analyze-roster', data),
  
  getTrending: (params: { week: number; season?: number; position?: string; trend_direction?: string; limit?: number }) =>
    api.get('/waiver-wire/trending', { params }),
  
  getAlerts: (params?: { active_only?: boolean; priority?: string; limit?: number }) =>
    api.get('/waiver-wire/alerts', { params }),
  
  generateRecommendations: (params: { week: number; season?: number; force_refresh?: boolean }) =>
    api.post('/waiver-wire/generate-recommendations', null, { params }),
  
  getPlayerEvaluation: (playerId: number, params: { week: number; season?: number }) =>
    api.get(`/waiver-wire/player/${playerId}/evaluation`, { params }),
  
  getWeeklyInsights: (params: { week: number; season?: number }) =>
    api.get('/waiver-wire/insights/weekly-summary', { params }),
  
  subscribeToAlerts: (data: { position?: string; min_ownership?: number; max_ownership?: number; priority_levels?: string[] }) =>
    api.post('/waiver-wire/alerts/subscribe', data),
}

export default api
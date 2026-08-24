import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PlusIcon, StarIcon, XMarkIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { draft, getErrorMessage, type MockDraftResult } from '../services/api'
import { DraftPickLog, type PickLogEntry } from '../components/draft'
import { DataConfidenceBadge } from '../components/common/DataConfidenceBadge'
import { positionColors } from '../components/players/playerDisplay'

interface DraftSettings {
  scoringFormat: 'PPR' | 'Half PPR' | 'Standard'
  teamCount: number
  draftPosition: number
  totalRounds: number
}

interface Player {
  sleeper_id: string
  full_name: string
  position: string
  team: string
  projected_points?: number
  adp?: number
  trending_count?: number
  search_rank?: number
}

interface DraftedPlayer extends Player {
  round: number
  pick: number
}

interface Recommendation {
  player_name: string
  position: string
  reasoning: string
  confidence: number
}

type DraftStatus = 'setup' | 'drafting' | 'complete'

// Roster construction a team is trying to fill before it starts taking best
// player available. Shared by the user's own "Team Needs" panel and the bot
// pick logic below, so both use one real definition of "need" rather than
// two that could drift apart.
const IDEAL_POSITION_COUNTS: Record<string, number> = { RB: 2, WR: 2, QB: 1, TE: 1 }

function getPositionNeeds(roster: { position: string }[]): string[] {
  const positionCounts = roster.reduce((acc, player) => {
    acc[player.position] = (acc[player.position] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const needs = Object.entries(IDEAL_POSITION_COUNTS)
    .filter(([pos, ideal]) => (positionCounts[pos] || 0) < ideal)
    .map(([pos]) => pos)

  return needs.length > 0 ? needs : ['RB', 'WR']
}

const GRADE_BADGE_COLORS: Record<string, string> = {
  A: 'bg-success-100 text-success-800',
  B: 'bg-accent-100 text-accent-800',
  C: 'bg-warning-100 text-warning-800',
  D: 'bg-orange-100 text-orange-800',
  F: 'bg-danger-100 text-danger-800',
}

// Keys off the base letter so grade modifiers (A-, B+, ...) still resolve to
// a color rather than falling through to the "unknown" default.
function getGradeBadgeColor(grade: string): string {
  const base = grade.trim().charAt(0).toUpperCase()
  return GRADE_BADGE_COLORS[base] || 'bg-ink-100 text-ink-700'
}

// Sleeper's own sentinel for "unranked" -- mirrors the backend's
// _UNRANKED_SENTINEL in draft.py so bots sort unranked players last, not
// first, exactly like the real positional-rankings endpoint already does.
const UNRANKED_SENTINEL = 9999999

function turnTeamForPick(overallPick: number, teamCount: number): number {
  const round = Math.floor((overallPick - 1) / teamCount) + 1
  const posInRound = ((overallPick - 1) % teamCount) + 1
  // Standard snake draft: odd rounds go 1..N, even rounds go N..1.
  return round % 2 === 1 ? posInRound : teamCount - posInRound + 1
}

// Bots draft the highest real-search_rank player at a position they still
// need, falling back to best-player-available once their needs are filled.
// No fabricated "bot intelligence" -- same ranking data and the same
// active-roster-filtered pool the real recommendations endpoint uses.
function pickBotPlayer(
  team: number,
  log: PickLogEntry[],
  pool: Player[]
): { player: Player; reason: string } | undefined {
  if (pool.length === 0) return undefined

  const roster = log.filter((entry) => entry.team === team).map((entry) => entry.player)
  const needs = getPositionNeeds(roster)
  const needPool = pool.filter((p) => needs.includes(p.position))
  const usingNeedPool = needPool.length > 0
  const candidates = usingNeedPool ? needPool : pool

  const ranked = [...candidates].sort(
    (a, b) => (a.search_rank ?? UNRANKED_SENTINEL) - (b.search_rank ?? UNRANKED_SENTINEL)
  )
  const player = ranked[0]
  const rankLabel = player.search_rank ? `#${player.search_rank} overall` : 'unranked'
  const reason = usingNeedPool
    ? `Highest-ranked available ${player.position} (${rankLabel}) -- filling a roster need`
    : `Best player available (${rankLabel})`

  return { player, reason }
}

interface SimStepResult {
  log: PickLogEntry[]
  changed: boolean
  ranOut: boolean
}

// Advances the draft log by exactly one pick if (and only if) it is
// currently a bot's turn. Returns changed: false untouched once it's the
// user's turn or the draft is over, so it's safe to call repeatedly/eagerly
// from both the auto-advance timer and the "simulate to my pick" button
// without ever double-picking.
function simulateOneBotPickIfNeeded(
  log: PickLogEntry[],
  settings: DraftSettings,
  availablePlayers: Player[]
): SimStepResult {
  const totalPicks = settings.teamCount * settings.totalRounds
  const pickNum = log.length + 1
  if (pickNum > totalPicks) return { log, changed: false, ranOut: false }

  const team = turnTeamForPick(pickNum, settings.teamCount)
  if (team === settings.draftPosition) return { log, changed: false, ranOut: false }

  const draftedIds = new Set(log.map((entry) => entry.player.sleeper_id))
  const pool = availablePlayers.filter((p) => !draftedIds.has(p.sleeper_id))
  const botPick = pickBotPlayer(team, log, pool)
  if (!botPick) return { log, changed: false, ranOut: true }

  const round = Math.floor((pickNum - 1) / settings.teamCount) + 1
  const pickInRound = ((pickNum - 1) % settings.teamCount) + 1
  const entry: PickLogEntry = {
    overallPick: pickNum,
    round,
    pickInRound,
    team,
    player: botPick.player,
    reason: botPick.reason,
    isUser: false,
  }
  return { log: [...log, entry], changed: true, ranOut: false }
}

export function DraftPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  // Set by AuthPage right after a brand-new user registers and is
  // auto-signed-in -- a one-time welcome, not a persistent state. Dismissing
  // it (or navigating away and back) clears the query param for good.
  const [showWelcome, setShowWelcome] = useState(searchParams.get('welcome') === '1')

  const dismissWelcome = useCallback(() => {
    setShowWelcome(false)
    const next = new URLSearchParams(searchParams)
    next.delete('welcome')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  const [settings, setSettings] = useState<DraftSettings>({
    scoringFormat: 'PPR',
    teamCount: 12,
    draftPosition: 6,
    totalRounds: 15
  })

  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  // Backend falls back to a real, deterministic ranking (source:
  // "algorithmic") when the AI provider(s) are unavailable -- never
  // fabricates AI-style reasoning, so the UI must say honestly which one
  // actually produced the current recommendations.
  const [recommendationsSource, setRecommendationsSource] = useState<'ai' | 'algorithmic' | null>(null)
  const [availablePlayers, setAvailablePlayers] = useState<Player[]>([])
  const [trendingPlayers, setTrendingPlayers] = useState<Player[]>([])
  const [loading, setLoading] = useState(false)
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null)
  const [selectedPosition, setSelectedPosition] = useState<string>('ALL')

  // The entire draft, in overall-pick order -- both the user's picks and
  // every simulated bot pick. This is the single source of truth for whose
  // turn it is, what's still available, and what the pick-by-pick board
  // shows; there's no separate "current round" counter to fall out of sync.
  const [pickLog, setPickLog] = useState<PickLogEntry[]>([])
  const [draftStatus, setDraftStatus] = useState<DraftStatus>('setup')
  const [botSimError, setBotSimError] = useState<string | null>(null)

  // Grading the finished mock draft: a real network call (POST
  // /draft/mock-draft-results), not an instant local computation, so it
  // gets its own loading/error/result state rather than piggybacking on
  // `loading` above (which gates the whole page's initial data load).
  // `hasSubmittedDraftRef` guards against re-submitting the same finished
  // draft on every re-render once `draftFinished` flips true -- it's reset
  // whenever a fresh draft starts.
  const [gradeResult, setGradeResult] = useState<MockDraftResult | null>(null)
  const [gradeSaving, setGradeSaving] = useState(false)
  const [gradeError, setGradeError] = useState<string | null>(null)
  const hasSubmittedDraftRef = useRef(false)

  const positions = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DEF']

  const totalPicks = settings.teamCount * settings.totalRounds
  const currentPick = Math.min(pickLog.length + 1, totalPicks)
  const currentRound = Math.min(
    Math.floor((currentPick - 1) / settings.teamCount) + 1,
    settings.totalRounds
  )
  const currentTurnTeam = turnTeamForPick(currentPick, settings.teamCount)
  const draftFinished = draftStatus === 'complete' || pickLog.length >= totalPicks
  const isUsersTurnNow =
    draftStatus === 'drafting' && !draftFinished && currentTurnTeam === settings.draftPosition
  const canDraftNow = draftStatus === 'drafting' && isUsersTurnNow
  const showRecommendationsPanel = draftStatus === 'setup' || isUsersTurnNow

  // Memoized against pickLog specifically (not recreated on every render) --
  // getTeamNeeds/generateRecommendations below depend on this array's
  // identity, and an unmemoized derive-from-pickLog-every-render here would
  // give them a new identity every render regardless of whether pickLog
  // actually changed, retriggering the recommendations effect in a loop.
  const draftedPlayers: DraftedPlayer[] = useMemo(
    () =>
      pickLog
        .filter((entry) => entry.isUser)
        .map((entry) => ({ ...entry.player, round: entry.round, pick: entry.overallPick })),
    [pickLog]
  )

  const draftedIds = useMemo(
    () => new Set(pickLog.map((entry) => entry.player.sleeper_id)),
    [pickLog]
  )

  // Calculate team needs based on drafted players
  const getTeamNeeds = useCallback((): string[] => {
    return getPositionNeeds(draftedPlayers)
  }, [draftedPlayers])

  // Persists the finished mock draft and fetches back its grade. Builds
  // user_roster from `draftedPlayers` -- the same user-only, round/pick-
  // annotated derivation from pickLog already used for the "Your Team"
  // sidebar (entry.pick there is entry.overallPick, matching the shape the
  // backend expects). search_rank/adp/projected_points are sent as null
  // when the ranking pool didn't have them for a given player, rather than
  // omitted, so the backend sees an explicit "unknown" instead of a missing
  // key.
  const saveMockDraftResult = useCallback(async () => {
    setGradeSaving(true)
    setGradeError(null)
    try {
      const response = await draft.saveMockDraftResults({
        draft_settings: {
          scoring_format: settings.scoringFormat,
          team_count: settings.teamCount,
          draft_position: settings.draftPosition,
          total_rounds: settings.totalRounds,
        },
        user_roster: draftedPlayers.map((player) => ({
          sleeper_id: player.sleeper_id,
          full_name: player.full_name,
          position: player.position,
          team: player.team,
          round: player.round,
          pick: player.pick,
          search_rank: player.search_rank ?? null,
          adp: player.adp ?? null,
          projected_points: player.projected_points ?? null,
        })),
      })
      setGradeResult(response.data)
    } catch (error) {
      // Don't silently pretend the draft saved when it didn't -- an honest
      // error here matters because the user has no other way to get this
      // grade back (there's no "retry saving" outside this page yet).
      console.error('Error saving mock draft results:', error)
      setGradeError(getErrorMessage(error, "Couldn't save your draft results, so a grade isn't available right now."))
    } finally {
      setGradeSaving(false)
    }
  }, [settings, draftedPlayers])

  // Fires exactly once per completed draft, the moment draftFinished flips
  // true -- not on every render while it stays true, and not for the
  // draft-hasn't-started default state (draftFinished is false until
  // draftStatus becomes 'complete' or pickLog fills up).
  useEffect(() => {
    if (!draftFinished || hasSubmittedDraftRef.current) return
    hasSubmittedDraftRef.current = true
    saveMockDraftResult()
  }, [draftFinished, saveMockDraftResult])

  // Called out separately from the full value_analysis list below --
  // matched by keyword against value_category rather than a fixed enum,
  // since the exact category vocabulary is the backend's to define. If
  // nothing in the response happens to read as a "value" or "reach", these
  // are simply omitted rather than guessing.
  const bestValuePick = useMemo(
    () => gradeResult?.value_analysis.find((entry) => /value/i.test(entry.value_category)) ?? null,
    [gradeResult]
  )
  const biggestReachPick = useMemo(
    () => gradeResult?.value_analysis.find((entry) => /reach/i.test(entry.value_category)) ?? null,
    [gradeResult]
  )

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      setLoading(true)
      try {
        // Get trending players for draft insights
        const trending = await draft.getTrendingCandidates({ hours: 48, limit: 25 })
        setTrendingPlayers(trending.data.candidates || [])

        // Get positional rankings to populate available players. Limits are
        // sized generously (well beyond a single team's needs) because this
        // pool now has to sustain every team's picks for a full draft, not
        // just the user's -- e.g. 12 teams x 15 rounds needs ~180 real
        // players across these four positions. Each request reuses the
        // same active-roster-filtered, search_rank-sorted endpoint the real
        // recommendation engine relies on.
        const [rbRankings, wrRankings, qbRankings, teRankings] = await Promise.all([
          draft.getPositionalRankings('RB', { limit: 100 }),
          draft.getPositionalRankings('WR', { limit: 100 }),
          draft.getPositionalRankings('QB', { limit: 40 }),
          draft.getPositionalRankings('TE', { limit: 40 })
        ])

        const allPlayers = [
          ...(rbRankings.data.players || []),
          ...(wrRankings.data.players || []),
          ...(qbRankings.data.players || []),
          ...(teRankings.data.players || [])
        ]

        // Remove duplicates based on sleeper_id
        const uniquePlayers = allPlayers.reduce((acc: Player[], player) => {
          if (!acc.find(p => p.sleeper_id === player.sleeper_id)) {
            acc.push(player)
          }
          return acc
        }, [] as Player[])

        setAvailablePlayers(uniquePlayers)
      } catch (error) {
        console.error('Error loading draft data:', error)
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [])

  const generateRecommendations = useCallback(async () => {
    if (availablePlayers.length === 0) return

    setRecommendationsError(null)

    try {
      const teamNeeds = getTeamNeeds()

      // Filter out players already drafted by ANY team, not just the user.
      const available = availablePlayers
        .filter(p => !draftedIds.has(p.sleeper_id))
        .slice(0, 20) // Top 20 available

      const result = await draft.getDraftRecommendations({
        available_players: available,
        team_needs: teamNeeds,
        draft_position: currentPick,
        scoring_format: settings.scoringFormat,
        league_size: settings.teamCount
      })

      setRecommendations(result.data.recommendations || [])
      setRecommendationsSource(result.data.source === 'algorithmic' ? 'algorithmic' : 'ai')
    } catch (error) {
      // Don't fabricate recommendations when the real call fails -- a made-up
      // confidence score and templated reasoning would look identical to a
      // genuine AI recommendation. Surface the failure instead.
      console.error('Error generating recommendations:', error)
      setRecommendations([])
      setRecommendationsSource(null)
      setRecommendationsError("Couldn't load recommendations. Try refreshing.")
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availablePlayers, pickLog, settings, getTeamNeeds, currentPick])

  // Get recommendations whenever it's actually relevant to see them: before
  // the draft starts (a live preview) or when it's the user's turn to pick.
  // While bots are picking there's nothing to recommend against yet, so we
  // skip the network call entirely rather than fetching and discarding it.
  useEffect(() => {
    if (availablePlayers.length > 0 && showRecommendationsPanel) {
      generateRecommendations()
    } else if (!showRecommendationsPanel) {
      setRecommendations([])
      setRecommendationsSource(null)
    }
  }, [availablePlayers, showRecommendationsPanel, generateRecommendations])

  // Auto-advance bot picks one at a time with a short pause between each,
  // so the board visibly fills in rather than jumping straight to the
  // user's next turn. Recomputes from the latest pickLog on every run and
  // only ever commits if that snapshot is still current at fire time, so a
  // "Simulate to my next pick" click can't race with a pending timer and
  // double up a pick.
  useEffect(() => {
    if (draftStatus !== 'drafting' || availablePlayers.length === 0) return

    const result = simulateOneBotPickIfNeeded(pickLog, settings, availablePlayers)

    if (result.ranOut) {
      setBotSimError('Ran out of available players to simulate the rest of the draft.')
      return
    }

    if (!result.changed) {
      if (pickLog.length >= totalPicks) {
        setDraftStatus('complete')
      }
      return
    }

    const timer = setTimeout(() => {
      setPickLog(prev => (prev === pickLog ? result.log : prev))
    }, 550)
    return () => clearTimeout(timer)
  }, [draftStatus, pickLog, availablePlayers, settings, totalPicks])

  const startDraft = () => {
    setPickLog([])
    setBotSimError(null)
    setRecommendationsError(null)
    setDraftStatus('drafting')
    hasSubmittedDraftRef.current = false
    setGradeResult(null)
    setGradeError(null)
  }

  const resetDraft = () => {
    setPickLog([])
    setBotSimError(null)
    setDraftStatus('setup')
    hasSubmittedDraftRef.current = false
    setGradeResult(null)
    setGradeError(null)
  }

  // Fast-forwards synchronously through consecutive bot picks until it's
  // the user's turn (or the draft ends), for anyone who doesn't want to
  // wait out the animated delay. Reuses the exact same per-pick function as
  // the auto-advance effect above -- this is not a second, different bot.
  const simulateToMyPick = () => {
    let log = pickLog
    let iterations = 0
    while (iterations < 1000) {
      const result = simulateOneBotPickIfNeeded(log, settings, availablePlayers)
      if (result.ranOut) {
        setBotSimError('Ran out of available players to simulate the rest of the draft.')
        break
      }
      if (!result.changed) break
      log = result.log
      iterations++
    }
    if (log !== pickLog) setPickLog(log)
    if (log.length >= totalPicks) setDraftStatus('complete')
  }

  const draftPlayer = (player: Player) => {
    if (!canDraftNow) return

    const pickNum = pickLog.length + 1
    const round = Math.floor((pickNum - 1) / settings.teamCount) + 1
    const pickInRound = ((pickNum - 1) % settings.teamCount) + 1
    const entry: PickLogEntry = {
      overallPick: pickNum,
      round,
      pickInRound,
      team: settings.draftPosition,
      player,
      isUser: true
    }

    setPickLog(prev => [...prev, entry])
  }

  const filteredPlayers = useMemo(() => {
    // When viewing ALL positions, present a single global ranking rather than
    // the positional concatenation order (which biased the list toward RBs).
    // Prefer an explicit overall rank (search_rank) when present, fall back to
    // ADP, and finally the UNRANKED_SENTINEL so unranked players sort last.
    if (selectedPosition === 'ALL') {
      return [...availablePlayers].sort((a, b) => {
        const aRank = (a.search_rank ?? a.adp ?? UNRANKED_SENTINEL)
        const bRank = (b.search_rank ?? b.adp ?? UNRANKED_SENTINEL)
        return aRank - bRank
      })
    }

    return [...availablePlayers]
      .filter((p) => p.position === selectedPosition)
      .sort((a, b) => {
        const aRank = (a.search_rank ?? a.adp ?? UNRANKED_SENTINEL)
        const bRank = (b.search_rank ?? b.adp ?? UNRANKED_SENTINEL)
        return aRank - bRank
      })
  }, [availablePlayers, selectedPosition])

  const availableFilteredPlayers = filteredPlayers.filter((p) => !draftedIds.has(p.sleeper_id))

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mx-auto"></div>
          <p className="mt-2 text-ink-600">Loading draft data...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {showWelcome && (
        <div className="bg-accent-50 border border-accent-200 rounded-lg p-4 flex items-start justify-between gap-4">
          <p className="text-sm text-accent-900">
            <span className="font-semibold">Welcome!</span> Here's a live look at AI draft
            recommendations below, built from real player data -- try adjusting the settings
            on the right to see them change. These aren't tied to a specific league yet;{' '}
            <Link to="/leagues" className="font-medium underline hover:text-accent-700">
              connect your league
            </Link>{' '}
            to get advice based on your actual roster and draft slot.
          </p>
          <button
            type="button"
            onClick={dismissWelcome}
            className="text-accent-400 hover:text-accent-600 shrink-0"
            aria-label="Dismiss welcome message"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      )}

      <div>
        <h1 className="font-display font-black uppercase tracking-tight text-3xl text-ink-900">Draft Assistant</h1>
        <p className="text-ink-600 mt-2">
          AI-powered draft recommendations optimized for {settings.scoringFormat} scoring
        </p>
      </div>

      {draftStatus === 'drafting' && !isUsersTurnNow && !draftFinished && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-amber-600"></div>
            <p className="text-sm text-amber-900">
              Team {currentTurnTeam} is picking (Round {currentRound}, overall pick {currentPick})...
            </p>
          </div>
          <button
            onClick={simulateToMyPick}
            className="px-3 py-1.5 bg-amber-600 text-white text-xs font-medium rounded hover:bg-amber-700 shrink-0"
          >
            Simulate to my next pick
          </button>
        </div>
      )}

      {botSimError && (
        <div className="bg-danger-50 border border-danger-200 rounded-lg p-4 text-sm text-danger-800">
          {botSimError}
        </div>
      )}

      {draftFinished && (
        <div className="space-y-4">
          <div className="bg-success-50 border border-success-200 rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">
            <p className="text-sm text-success-900">
              <span className="font-semibold">Draft complete!</span> You drafted {draftedPlayers.length}{' '}
              players across {settings.totalRounds} rounds.
            </p>
            <Link
              to="/draft-history"
              className="px-3 py-1.5 bg-white border border-success-300 text-success-800 text-xs font-medium rounded hover:bg-success-100 shrink-0"
            >
              View draft history
            </Link>
          </div>

          {gradeSaving && (
            <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6 flex items-center gap-3">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-accent-500"></div>
              <p className="text-sm text-ink-600">Saving your draft and calculating your grade...</p>
            </div>
          )}

          {gradeError && (
            <div className="bg-danger-50 border border-danger-200 rounded-lg p-4 flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-start gap-2">
                <ExclamationTriangleIcon className="w-5 h-5 text-danger-500 shrink-0 mt-0.5" />
                <p className="text-sm text-danger-800">{gradeError}</p>
              </div>
              <button
                onClick={saveMockDraftResult}
                className="px-3 py-1.5 bg-danger-600 text-white text-xs font-medium rounded hover:bg-danger-700 shrink-0"
              >
                Retry
              </button>
            </div>
          )}

          {gradeResult && (
            <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6 space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                <div
                  className={`flex items-center justify-center w-16 h-16 rounded-full text-2xl font-bold shrink-0 ${getGradeBadgeColor(gradeResult.draft_grade)}`}
                >
                  {gradeResult.draft_grade}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-ink-900">Your Draft Grade</h2>
                  <p className="text-sm text-ink-600">Composition score: {gradeResult.composition_score}/100</p>
                </div>
              </div>

              {gradeResult.final_analysis && (
                <p className="text-sm text-ink-700 bg-ink-50 rounded-md p-4 border border-ink-100">
                  {gradeResult.final_analysis}
                </p>
              )}

              {Object.keys(gradeResult.position_breakdown ?? {}).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-ink-900 mb-2">Position Breakdown</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    {Object.entries(gradeResult.position_breakdown).map(([position, breakdown]) => (
                      <div
                        key={position}
                        className={`rounded-md border p-3 text-center ${
                          breakdown.needs_attention
                            ? 'border-danger-200 bg-danger-50'
                            : breakdown.overstocked
                            ? 'border-warning-200 bg-warning-50'
                            : 'border-ink-200 bg-ink-50'
                        }`}
                      >
                        <div className="text-xs font-semibold text-ink-900">{position}</div>
                        <div className="text-lg font-bold text-ink-900">{breakdown.players_drafted}</div>
                        <div className="text-[11px] text-ink-500">min {breakdown.recommended_minimum}</div>
                        <div className="text-[11px] text-ink-500 mt-1">Depth {breakdown.depth_score}</div>
                        {breakdown.needs_attention && (
                          <div className="text-[11px] text-danger-700 font-medium mt-1">Needs attention</div>
                        )}
                        {breakdown.overstocked && (
                          <div className="text-[11px] text-warning-700 font-medium mt-1">Overstocked</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(bestValuePick || biggestReachPick) && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {bestValuePick && (
                    <div className="rounded-md border border-success-200 bg-success-50 p-4">
                      <div className="text-xs font-semibold text-success-800 uppercase tracking-wide mb-1">
                        Best Value
                      </div>
                      <div className="font-medium text-ink-900">{bestValuePick.player_name}</div>
                      <div className="text-xs text-ink-600">
                        {bestValuePick.position} &middot; Round {bestValuePick.round}, Pick {bestValuePick.pick} overall
                        &middot; {bestValuePick.value_category}
                      </div>
                    </div>
                  )}
                  {biggestReachPick && (
                    <div className="rounded-md border border-warning-200 bg-warning-50 p-4">
                      <div className="text-xs font-semibold text-warning-800 uppercase tracking-wide mb-1">
                        Biggest Reach
                      </div>
                      <div className="font-medium text-ink-900">{biggestReachPick.player_name}</div>
                      <div className="text-xs text-ink-600">
                        {biggestReachPick.position} &middot; Round {biggestReachPick.round}, Pick {biggestReachPick.pick}{' '}
                        overall &middot; {biggestReachPick.value_category}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {gradeResult.value_analysis.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-ink-900 mb-2">Pick-by-Pick Value</h3>
                  <div className="max-h-64 overflow-y-auto space-y-1.5">
                    {gradeResult.value_analysis.map((entry, index) => (
                      <div
                        key={`${entry.player_name}-${entry.pick}-${index}`}
                        className="flex items-center justify-between gap-2 p-2 bg-ink-50 rounded text-sm"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-xs text-ink-500 shrink-0 w-20">
                            Rd {entry.round} &middot; #{entry.pick}
                          </span>
                          <span className="font-medium text-ink-900 truncate">{entry.player_name}</span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${
                              positionColors[entry.position as keyof typeof positionColors] || 'bg-ink-100 text-ink-800'
                            }`}
                          >
                            {entry.position}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs text-ink-500">{entry.value_category}</span>
                          <span className={`px-2 py-0.5 rounded font-stat text-xs font-bold ${getGradeBadgeColor(entry.value_grade)}`}>
                            {entry.value_grade}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-2 border-t border-ink-100">
                <Link to="/draft-history" className="text-sm font-medium text-accent-600 hover:text-accent-700">
                  View all your mock drafts &rarr;
                </Link>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">

          {/* AI Recommendations */}
          <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-semibold text-ink-900">
                  {recommendationsSource === 'algorithmic' ? 'Draft Recommendations' : 'AI Recommendations'}
                </h2>
                {recommendationsSource === 'algorithmic' && (
                  <DataConfidenceBadge level="heuristic" label="Algorithmic (AI unavailable)" />
                )}
              </div>
              <span className="text-sm text-ink-500">
                {draftStatus === 'setup' ? 'Preview' : `Round ${currentRound}`}, Pick {currentPick} overall
                {draftStatus === 'drafting' && isUsersTurnNow && (
                  <span className="ml-2 font-medium text-accent-600">Your turn!</span>
                )}
              </span>
            </div>

            <div className="space-y-3">
              {draftFinished ? (
                <div className="text-center py-8 text-ink-500">
                  <p>Draft complete -- see your final roster in the sidebar.</p>
                </div>
              ) : !showRecommendationsPanel ? (
                <div className="text-center py-8 text-ink-500">
                  <p>Waiting for the other teams to pick...</p>
                </div>
              ) : recommendations.length > 0 ? recommendations.map((rec, index) => (
                <div key={`rec-${rec.player_name}-${index}`} className="flex items-center justify-between p-4 bg-accent-50 rounded-lg border border-accent-200">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-ink-900">{rec.player_name}</span>
                      <span className="text-sm text-ink-500">{rec.position}</span>
                      <StarIcon className="w-4 h-4 text-accent-500" />
                    </div>
                    <p className="text-sm text-ink-700">{rec.reasoning}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-success-700">
                      {rec.confidence}% confidence
                    </div>
                    <button
                      onClick={() => {
                        const player = availablePlayers.find(p =>
                          p.full_name === rec.player_name ||
                          p.full_name.includes(rec.player_name)
                        )
                        if (player) draftPlayer(player)
                      }}
                      disabled={!canDraftNow}
                      className="mt-2 px-3 py-1 bg-accent-500 text-white text-xs rounded hover:bg-accent-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Draft
                    </button>
                  </div>
                </div>
              )) : recommendationsError ? (
                <div className="text-center py-8 text-danger-600">
                  <p>{recommendationsError}</p>
                </div>
              ) : (
                <div className="text-center py-8 text-ink-500">
                  <p>Configure your draft settings to get AI recommendations</p>
                </div>
              )}
            </div>
          </div>

          {/* Draft Board / pick-by-pick log */}
          <DraftPickLog picks={pickLog} />

          {/* Available Players */}
          <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-ink-900">Available Players</h2>
              <select
                value={selectedPosition}
                onChange={(e) => setSelectedPosition(e.target.value)}
                className="rounded-md border-ink-300 text-sm focus:border-accent-500 focus:ring-accent-500"
              >
                {positions.map(pos => (
                  <option key={pos} value={pos}>{pos}</option>
                ))}
              </select>
            </div>

            <div className="max-h-96 overflow-y-auto">
              <div className="space-y-2">
                {availableFilteredPlayers.slice(0, 50).map((player) => (
                  <div key={player.sleeper_id} className="flex items-center justify-between p-3 bg-ink-50 rounded-md hover:bg-ink-100 transition-colors">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-ink-900">{player.full_name}</span>
                        <span className="text-sm text-ink-500">{player.position} - {player.team}</span>
                        {trendingPlayers.some(tp => tp.sleeper_id === player.sleeper_id) && (
                          <span className="text-xs bg-success-100 text-success-800 px-2 py-1 rounded">
                            Trending
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {player.projected_points && (
                        <div className="text-right">
                          <div className="text-sm font-medium text-ink-900">Proj: {player.projected_points}</div>
                        </div>
                      )}
                      <button
                        onClick={() => draftPlayer(player)}
                        disabled={!canDraftNow}
                        className="p-1 text-accent-600 hover:text-accent-800 disabled:opacity-30 disabled:cursor-not-allowed"
                        title={canDraftNow ? 'Draft player' : 'Not your turn'}
                      >
                        <PlusIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">

          {/* Draft Settings */}
          <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-4 text-ink-900">Draft Settings</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">
                  Scoring Format
                </label>
                <select
                  value={settings.scoringFormat}
                  onChange={(e) => setSettings({...settings, scoringFormat: e.target.value as DraftSettings['scoringFormat']})}
                  disabled={draftStatus === 'drafting'}
                  className="w-full rounded-md border-ink-300 focus:border-accent-500 focus:ring-accent-500 disabled:bg-ink-100 disabled:text-ink-500"
                >
                  <option value="PPR">PPR</option>
                  <option value="Half PPR">Half PPR</option>
                  <option value="Standard">Standard</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">
                  Team Count
                </label>
                <select
                  value={settings.teamCount}
                  onChange={(e) => setSettings({...settings, teamCount: Number(e.target.value)})}
                  disabled={draftStatus === 'drafting'}
                  className="w-full rounded-md border-ink-300 focus:border-accent-500 focus:ring-accent-500 disabled:bg-ink-100 disabled:text-ink-500"
                >
                  <option value={8}>8 Teams</option>
                  <option value={10}>10 Teams</option>
                  <option value={12}>12 Teams</option>
                  <option value={14}>14 Teams</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">
                  Your Draft Position
                </label>
                <select
                  value={settings.draftPosition}
                  onChange={(e) => setSettings({...settings, draftPosition: Number(e.target.value)})}
                  disabled={draftStatus === 'drafting'}
                  className="w-full rounded-md border-ink-300 focus:border-accent-500 focus:ring-accent-500 disabled:bg-ink-100 disabled:text-ink-500"
                >
                  {Array.from({length: settings.teamCount}, (_, i) => (
                    <option key={i + 1} value={i + 1}>Position {i + 1}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-ink-700 mb-1">
                  Total Rounds
                </label>
                <select
                  value={settings.totalRounds}
                  onChange={(e) => setSettings({...settings, totalRounds: Number(e.target.value)})}
                  disabled={draftStatus === 'drafting'}
                  className="w-full rounded-md border-ink-300 focus:border-accent-500 focus:ring-accent-500 disabled:bg-ink-100 disabled:text-ink-500"
                >
                  <option value={10}>10 Rounds</option>
                  <option value={12}>12 Rounds</option>
                  <option value={15}>15 Rounds</option>
                </select>
              </div>

              {draftStatus === 'setup' && (
                <button
                  onClick={startDraft}
                  className="w-full bg-success-600 text-white py-2 px-4 rounded-md hover:bg-success-700 font-medium"
                >
                  Start Mock Draft
                </button>
              )}

              <button
                onClick={generateRecommendations}
                disabled={!showRecommendationsPanel}
                className="w-full bg-accent-500 text-white py-2 px-4 rounded-md hover:bg-accent-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Refresh Recommendations
              </button>
            </div>
          </div>

          {/* Your Team */}
          <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-4 text-ink-900">
              Your Team ({draftedPlayers.length})
            </h2>

            {draftedPlayers.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {draftedPlayers.map((player) => (
                  <div key={`drafted-${player.sleeper_id}-${player.round}-${player.pick}`} className="p-2 bg-success-50 rounded border border-success-200">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-medium text-sm text-ink-900">{player.full_name}</span>
                        <span className="text-xs text-ink-500 ml-2">{player.position}</span>
                      </div>
                      <span className="text-xs text-ink-600">
                        R{player.round}P{player.pick}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-ink-500 text-sm">
                  Your drafted players will appear here
                </p>
                <p className="text-xs text-ink-400 mt-1">
                  {draftStatus === 'setup'
                    ? 'Start the mock draft to begin picking'
                    : 'Click the + button next to players to draft them'}
                </p>
              </div>
            )}

            {pickLog.length > 0 && (
              <button
                onClick={resetDraft}
                className="w-full mt-4 text-sm text-ink-600 hover:text-ink-800"
              >
                Reset Draft
              </button>
            )}
          </div>

          {/* Team Needs */}
          {draftedPlayers.length > 0 && (
            <div className="bg-white rounded-lg border border-ink-200 shadow-sm p-6">
              <h2 className="text-lg font-semibold mb-2 text-ink-900">Team Needs</h2>
              <div className="flex flex-wrap gap-2">
                {getTeamNeeds().map(need => (
                  <span key={need} className="px-2 py-1 bg-warning-100 text-warning-800 text-xs rounded">
                    {need}
                  </span>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

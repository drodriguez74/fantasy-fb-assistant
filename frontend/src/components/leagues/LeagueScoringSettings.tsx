import { useState, useEffect, useCallback } from 'react'
import {
  AdjustmentsHorizontalIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import { leagueScoring, getErrorMessage } from '../../services/api'

interface LeagueScoringSettingsProps {
  leagueId: number
}

interface DetectedScoringRules {
  passing: { completion: number; incompletion: number; attempt: number; yard: number; td: number; interception: number }
  rushing: { attempt: number; yard: number; td: number }
  receiving: { reception: number; yard: number; td: number; target: number }
  fumbles: { lost: number }
  source: string
}

interface RosterSettings {
  starters?: Record<string, number> | null
  bench?: number | null
  roster_size?: number | null
  points_per_reception?: number | null
  scoring_type?: string | null
  source?: string | null
}

interface CustomScoringConfig {
  scoring_type: string
  passing_settings: {
    yards_per_point: number
    td_points: number
    int_points?: number
    completion_points?: number
    incompletion_points?: number
    bonuses?: { '300_yards'?: number; '400_yards'?: number }
  }
  rushing_settings: {
    yards_per_point: number
    td_points: number
    bonuses?: { '100_yards'?: number; '200_yards'?: number }
  }
  receiving_settings: {
    yards_per_point: number
    td_points: number
    reception_points?: number
    target_points?: number
    bonuses?: { '100_yards'?: number; '200_yards'?: number }
  }
  fumble_lost_points?: number
}

interface LeagueScoringGetResponse {
  has_custom_scoring: boolean
  default_scoring?: string
  detected_scoring?: DetectedScoringRules | null
  detected_scoring_description?: string | null
  roster_settings?: RosterSettings | null
  scoring_config?: CustomScoringConfig
}

// A points-per-yard value (what the platform/override actually stores) is
// awkward to read as a raw decimal (e.g. 0.04) -- flip it to "yards per
// point" (e.g. 25) for display, the way commissioners actually talk about
// scoring ("25 yards per point"), and treat 0 honestly as "not scored" (a
// real league setting, not a divide-by-zero to hide).
function yardsPerPointLabel(pointsPerYard: number | undefined | null): string {
  if (!pointsPerYard) return 'Not scored'
  return `${Math.round(1 / pointsPerYard)} yds / pt`
}

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-ink-50 last:border-0">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-sm font-medium text-body tabular-nums">{value}</span>
    </div>
  )
}

function ScoringGroupCard({
  title,
  rows,
}: {
  title: string
  rows: { label: string; value: string | number }[]
}) {
  return (
    <div className="bg-surface-2/50 rounded-lg p-4">
      <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">{title}</h4>
      {rows.map((row) => (
        <StatRow key={row.label} label={row.label} value={row.value} />
      ))}
    </div>
  )
}

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'K', 'DEF', 'D/ST']

/**
 * Read-only view of this league's real scoring rules and roster
 * construction -- pulled from whatever this league's real source of truth
 * is: a saved manual override (`LeagueScoring`, when one exists for this
 * league -- see `backend/app/models/league_scoring.py`) if present,
 * otherwise the platform's own live-detected settings
 * (`espn_service_enhanced.get_scoring_and_roster_settings` /
 * `sleeper_service.parse_league_settings`). No editing surface here by
 * design -- configuring or overriding scoring is a backend/API capability
 * only now, not something this tab exposes.
 */
export function LeagueScoringSettings({ leagueId }: LeagueScoringSettingsProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<LeagueScoringGetResponse | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const res = await leagueScoring.get(leagueId)
      setData(res.data as LeagueScoringGetResponse)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load scoring configuration'))
    } finally {
      setLoading(false)
    }
  }, [leagueId])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="bg-surface rounded-lg border border-hairline p-6">
        <div className="flex items-center space-x-3">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-accent-ink" />
          <span className="text-sm text-muted">Loading scoring settings...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-danger-50 border border-danger-200 text-danger-700 rounded-md p-4 text-sm flex items-start gap-2">
        <ExclamationTriangleIcon className="h-4 w-4 mt-0.5 flex-shrink-0" />
        <span>{error}</span>
      </div>
    )
  }

  if (!data) return null

  const custom = data.has_custom_scoring ? data.scoring_config : undefined
  const detected = !data.has_custom_scoring ? data.detected_scoring : undefined
  const rosterSettings = data.roster_settings

  // Normalize both real sources (a saved manual override vs. live-detected
  // platform rules) into one shape for rendering, so the groups below don't
  // need to branch on which source is active.
  const passing = custom
    ? {
        yard: custom.passing_settings.yards_per_point ? 1 / custom.passing_settings.yards_per_point : 0,
        td: custom.passing_settings.td_points,
        interception: custom.passing_settings.int_points ?? 0,
        completion: custom.passing_settings.completion_points ?? 0,
        incompletion: custom.passing_settings.incompletion_points ?? 0,
      }
    : detected?.passing

  const rushing = custom
    ? {
        yard: custom.rushing_settings.yards_per_point ? 1 / custom.rushing_settings.yards_per_point : 0,
        td: custom.rushing_settings.td_points,
      }
    : detected?.rushing

  const receiving = custom
    ? {
        reception: custom.receiving_settings.reception_points ?? 0,
        yard: custom.receiving_settings.yards_per_point ? 1 / custom.receiving_settings.yards_per_point : 0,
        td: custom.receiving_settings.td_points,
        target: custom.receiving_settings.target_points ?? 0,
      }
    : detected?.receiving

  const fumbleLost = custom ? custom.fumble_lost_points ?? 0 : detected?.fumbles.lost

  const hasAnyScoring = Boolean(passing || rushing || receiving)

  return (
    <div className="space-y-6">
      <div className="bg-surface rounded-lg border border-hairline p-6 space-y-4">
        <div className="flex items-start gap-3">
          <AdjustmentsHorizontalIcon className="h-5 w-5 text-accent-ink mt-0.5 shrink-0" />
          <div>
            <h3 className="text-lg font-semibold text-body">League Scoring</h3>
            <p className="text-sm text-muted mt-1 max-w-2xl">
              {data.has_custom_scoring
                ? "This league has a manual scoring override on file -- the values below are what's actually used, not the platform's defaults."
                : hasAnyScoring
                  ? `Real scoring rules, detected live from this league's connected platform${detected?.source ? ` (${detected.source})` : ''}.`
                  : `No real scoring rules could be detected for this league -- showing the ${data.default_scoring || 'PPR'} default.`}
            </p>
          </div>
        </div>

        {hasAnyScoring && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
            {passing && (
              <ScoringGroupCard
                title="Passing"
                rows={[
                  { label: 'Per yard', value: yardsPerPointLabel(passing.yard) },
                  { label: 'Per TD', value: passing.td },
                  { label: 'Per interception', value: passing.interception },
                  ...(passing.completion ? [{ label: 'Per completion', value: passing.completion }] : []),
                  ...(passing.incompletion ? [{ label: 'Per incompletion', value: passing.incompletion }] : []),
                ]}
              />
            )}
            {rushing && (
              <ScoringGroupCard
                title="Rushing"
                rows={[
                  { label: 'Per yard', value: yardsPerPointLabel(rushing.yard) },
                  { label: 'Per TD', value: rushing.td },
                ]}
              />
            )}
            {receiving && (
              <ScoringGroupCard
                title="Receiving"
                rows={[
                  { label: 'Per reception (PPR)', value: receiving.reception },
                  { label: 'Per yard', value: yardsPerPointLabel(receiving.yard) },
                  { label: 'Per TD', value: receiving.td },
                  ...(receiving.target ? [{ label: 'Per target', value: receiving.target }] : []),
                ]}
              />
            )}
            <ScoringGroupCard
              title="Other"
              rows={[{ label: 'Per fumble lost', value: fumbleLost ?? 0 }]}
            />
          </div>
        )}

        {data.detected_scoring_description && !data.has_custom_scoring && (
          <p className="text-xs text-muted italic pt-1">{data.detected_scoring_description}</p>
        )}
      </div>

      {rosterSettings && rosterSettings.starters && (
        <div className="bg-surface rounded-lg border border-hairline p-6 space-y-4">
          <div>
            <h3 className="text-lg font-semibold text-body">Roster Construction</h3>
            <p className="text-sm text-muted mt-1">
              This league's real starting lineup requirements
              {rosterSettings.source ? `, from ${rosterSettings.source}` : ''}.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            {POSITION_ORDER.filter((pos) => rosterSettings.starters?.[pos]).map((pos) => (
              <div
                key={pos}
                className="bg-highlight border border-accent-100 rounded-lg px-3 py-2 text-center min-w-[64px]"
              >
                <div className="text-xs text-accent-ink font-medium">{pos}</div>
                <div className="text-lg font-stat tabular-nums font-semibold text-body">
                  {rosterSettings.starters?.[pos]}
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2 border-t border-hairline">
            <div>
              <div className="text-xs text-muted uppercase tracking-wide">Bench spots</div>
              <div className="text-sm font-medium text-body">{rosterSettings.bench ?? 'N/A'}</div>
            </div>
            <div>
              <div className="text-xs text-muted uppercase tracking-wide">Roster size</div>
              <div className="text-sm font-medium text-body">{rosterSettings.roster_size ?? 'N/A'}</div>
            </div>
            <div>
              <div className="text-xs text-muted uppercase tracking-wide">Points per reception</div>
              <div className="text-sm font-medium text-body">{rosterSettings.points_per_reception ?? 'N/A'}</div>
            </div>
            <div>
              <div className="text-xs text-muted uppercase tracking-wide">Format</div>
              <div className="text-sm font-medium text-body">{rosterSettings.scoring_type ?? 'N/A'}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

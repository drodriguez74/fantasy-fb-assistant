import { useState, useEffect, useCallback } from 'react'
import {
  AdjustmentsHorizontalIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import { leagueScoring, getErrorMessage, type LeagueScoringConfig } from '../../services/api'

interface LeagueScoringSettingsProps {
  leagueId: number
}

// Keys line up 1:1 with LeagueScoringConfig's numeric fields (services/api.ts)
// -- kept as strings in form state so a field can sit empty/partial while
// the user is typing without fighting NaN on every keystroke.
type ScoringFormState = Record<
  | 'reception_points'
  | 'passing_yards_per_point'
  | 'passing_td_points'
  | 'passing_int_points'
  | 'completion_points'
  | 'incompletion_points'
  | 'rushing_yards_per_point'
  | 'rushing_td_points'
  | 'receiving_yards_per_point'
  | 'receiving_td_points'
  | 'target_points'
  | 'fumble_lost_points',
  string
>

const DEFAULT_FORM: ScoringFormState = {
  reception_points: '1',
  passing_yards_per_point: '25',
  passing_td_points: '4',
  passing_int_points: '-1',
  completion_points: '0',
  incompletion_points: '0',
  rushing_yards_per_point: '10',
  rushing_td_points: '6',
  receiving_yards_per_point: '10',
  receiving_td_points: '6',
  target_points: '0',
  fumble_lost_points: '-2',
}

// Grouped to mirror how a real commissioner reads a scoring sheet (by
// category), and to mirror app.services.scoring_rules's own passing/
// rushing/receiving grouping -- the same shape the draft assistant's
// override actually reads (see draft_assistant_service.
// _apply_manual_scoring_override / scoring_rules_from_league_scoring).
const FIELD_GROUPS: { title: string; fields: { key: keyof ScoringFormState; label: string }[] }[] = [
  {
    title: 'Passing',
    fields: [
      { key: 'passing_yards_per_point', label: 'Yards per point' },
      { key: 'passing_td_points', label: 'Points per TD' },
      { key: 'passing_int_points', label: 'Points per interception' },
      { key: 'completion_points', label: 'Points per completion' },
      { key: 'incompletion_points', label: 'Points per incompletion' },
    ],
  },
  {
    title: 'Rushing',
    fields: [
      { key: 'rushing_yards_per_point', label: 'Yards per point' },
      { key: 'rushing_td_points', label: 'Points per TD' },
    ],
  },
  {
    title: 'Receiving',
    fields: [
      { key: 'reception_points', label: 'Points per reception (PPR)' },
      { key: 'receiving_yards_per_point', label: 'Yards per point' },
      { key: 'receiving_td_points', label: 'Points per TD' },
      { key: 'target_points', label: 'Points per target' },
    ],
  },
  {
    title: 'Other',
    fields: [{ key: 'fumble_lost_points', label: 'Points per fumble lost' }],
  },
]

interface ScoringSettingsResponse {
  yards_per_point: number
  td_points: number
  int_points?: number
  completion_points?: number
  incompletion_points?: number
  reception_points?: number
  target_points?: number
}

interface DetectedScoringRules {
  passing: { completion: number; incompletion: number; attempt: number; yard: number; td: number; interception: number }
  rushing: { attempt: number; yard: number; td: number }
  receiving: { reception: number; yard: number; td: number; target: number }
  fumbles: { lost: number }
  source: string
}

interface LeagueScoringGetResponse {
  has_custom_scoring: boolean
  default_scoring?: string
  detected_scoring?: DetectedScoringRules | null
  detected_scoring_description?: string | null
  scoring_config?: {
    passing_settings: ScoringSettingsResponse
    rushing_settings: ScoringSettingsResponse
    receiving_settings: ScoringSettingsResponse
    fumble_lost_points?: number
  }
}

function configToForm(config: NonNullable<LeagueScoringGetResponse['scoring_config']>): ScoringFormState {
  return {
    reception_points: String(config.receiving_settings.reception_points ?? 1),
    passing_yards_per_point: String(config.passing_settings.yards_per_point),
    passing_td_points: String(config.passing_settings.td_points),
    passing_int_points: String(config.passing_settings.int_points ?? -1),
    completion_points: String(config.passing_settings.completion_points ?? 0),
    incompletion_points: String(config.passing_settings.incompletion_points ?? 0),
    rushing_yards_per_point: String(config.rushing_settings.yards_per_point),
    rushing_td_points: String(config.rushing_settings.td_points),
    receiving_yards_per_point: String(config.receiving_settings.yards_per_point),
    receiving_td_points: String(config.receiving_settings.td_points),
    target_points: String(config.receiving_settings.target_points ?? 0),
    fumble_lost_points: String(config.fumble_lost_points ?? -2),
  }
}

/**
 * Manual scoring override for this league (backend/app/api/v1/endpoints/
 * league_scoring.py, backend/app/models/league_scoring.py::LeagueScoring).
 * The draft assistant auto-detects a connected league's real scoring rules
 * from Sleeper/ESPN's live APIs already (see draft_assistant_service.py) --
 * this is a deliberate, explicit override on top of that, for modeling a
 * hypothetical scoring change, a platform this app doesn't extract real
 * settings from yet, or correcting something auto-detection got wrong. See
 * DraftAssistantService._apply_manual_scoring_override for how a saved
 * value here takes priority over auto-detected settings.
 */
export function LeagueScoringSettings({ leagueId }: LeagueScoringSettingsProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [hasCustomScoring, setHasCustomScoring] = useState(false)
  const [defaultScoring, setDefaultScoring] = useState('PPR')
  const [detectedScoring, setDetectedScoring] = useState<DetectedScoringRules | null>(null)
  const [detectedDescription, setDetectedDescription] = useState('')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<ScoringFormState>(DEFAULT_FORM)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const res = await leagueScoring.get(leagueId)
      const data = res.data as LeagueScoringGetResponse
      if (data.has_custom_scoring && data.scoring_config) {
        setHasCustomScoring(true)
        setForm(configToForm(data.scoring_config))
      } else {
        setHasCustomScoring(false)
        setDefaultScoring(data.default_scoring || 'PPR')
        setDetectedScoring(data.detected_scoring ?? null)
        setDetectedDescription(data.detected_scoring_description ?? '')
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load scoring configuration'))
    } finally {
      setLoading(false)
    }
  }, [leagueId])

  useEffect(() => {
    load()
  }, [load])

  const handleChange = (key: keyof ScoringFormState, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const payload: LeagueScoringConfig = { user_league_id: leagueId, scoring_type: 'Custom' }
      for (const group of FIELD_GROUPS) {
        for (const { key } of group.fields) {
          const parsed = Number(form[key])
          if (Number.isNaN(parsed)) {
            throw new Error(`"${key.replace(/_/g, ' ')}" must be a number`)
          }
          payload[key] = parsed
        }
      }
      await leagueScoring.configure(payload)
      setSuccess('Custom scoring saved — the draft assistant will use these values instead of auto-detected settings.')
      setEditing(false)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save scoring configuration'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6">
        <div className="flex items-center space-x-3">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-accent-500" />
          <span className="text-sm text-ink-500">Loading scoring configuration...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-ink-200 p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-ink-900 flex items-center gap-2">
            <AdjustmentsHorizontalIcon className="h-5 w-5 text-accent-500" />
            Custom Scoring Override
          </h3>
          <p className="text-sm text-ink-500 mt-1 max-w-2xl">
            {hasCustomScoring
              ? 'A manual scoring override is active for this league. The draft assistant uses these values instead of what it auto-detects from the platform.'
              : detectedScoring
                ? "No manual override — showing this league's real scoring rules, detected live from the connected platform."
                : `No custom scoring configured — the draft assistant auto-detects this league's real scoring rules from the connected platform (falling back to ${defaultScoring} if that fails). Set a custom override here to replace that, e.g. to model a hypothetical rule change.`}
          </p>
        </div>
        {!editing && (
          <button
            onClick={() => {
              setEditing(true)
              setSuccess('')
            }}
            className="shrink-0 bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors focus:outline-none focus:ring-2 focus:ring-accent-500 text-sm font-medium"
          >
            {hasCustomScoring ? 'Edit Scoring' : 'Configure Custom Scoring'}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-danger-50 border border-danger-200 text-danger-700 rounded-md p-3 text-sm flex items-start gap-2">
          <ExclamationTriangleIcon className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {success && !editing && (
        <div className="bg-success-50 border border-success-200 text-success-700 rounded-md p-3 text-sm flex items-start gap-2">
          <CheckCircleIcon className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {!hasCustomScoring && !editing && detectedScoring && (
        <div className="pt-3 border-t border-ink-100 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-xs text-ink-500 uppercase tracking-wide">Per reception</div>
              <div className="font-medium text-ink-900">{detectedScoring.receiving.reception}</div>
            </div>
            <div>
              <div className="text-xs text-ink-500 uppercase tracking-wide">Passing TD</div>
              <div className="font-medium text-ink-900">{detectedScoring.passing.td}</div>
            </div>
            <div>
              <div className="text-xs text-ink-500 uppercase tracking-wide">Rushing / Receiving TD</div>
              <div className="font-medium text-ink-900">{detectedScoring.rushing.td}</div>
            </div>
            <div>
              <div className="text-xs text-ink-500 uppercase tracking-wide">Interception</div>
              <div className="font-medium text-ink-900">{detectedScoring.passing.interception}</div>
            </div>
            <div>
              <div className="text-xs text-ink-500 uppercase tracking-wide">Fumble lost</div>
              <div className="font-medium text-ink-900">{detectedScoring.fumbles.lost}</div>
            </div>
            {!!detectedScoring.passing.completion && (
              <div>
                <div className="text-xs text-ink-500 uppercase tracking-wide">Per completion</div>
                <div className="font-medium text-ink-900">{detectedScoring.passing.completion}</div>
              </div>
            )}
            {!!detectedScoring.passing.incompletion && (
              <div>
                <div className="text-xs text-ink-500 uppercase tracking-wide">Per incompletion</div>
                <div className="font-medium text-ink-900">{detectedScoring.passing.incompletion}</div>
              </div>
            )}
          </div>
          {detectedDescription && (
            <p className="text-xs text-ink-500 italic">{detectedDescription}</p>
          )}
        </div>
      )}

      {editing && (
        <div className="space-y-5 pt-3 border-t border-ink-100">
          {FIELD_GROUPS.map((group) => (
            <div key={group.title}>
              <h4 className="text-xs font-semibold text-ink-500 uppercase tracking-wide mb-2">
                {group.title}
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {group.fields.map(({ key, label }) => (
                  <label key={key} className="block">
                    <span className="text-xs text-ink-500">{label}</span>
                    <input
                      type="number"
                      step="0.01"
                      value={form[key]}
                      onChange={(e) => handleChange(key, e.target.value)}
                      className="mt-1 block w-full border border-ink-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
                    />
                  </label>
                ))}
              </div>
            </div>
          ))}

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors disabled:bg-ink-200 disabled:text-ink-400 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-accent-500 text-sm font-medium"
            >
              {saving ? 'Saving...' : 'Save Custom Scoring'}
            </button>
            <button
              onClick={() => {
                setEditing(false)
                setError('')
                load()
              }}
              disabled={saving}
              className="text-ink-500 hover:text-ink-700 text-sm font-medium disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

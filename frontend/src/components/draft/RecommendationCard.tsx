import { StarIcon, TrophyIcon } from '@heroicons/react/24/outline'
import { DraftRecommendation } from '../../types'
import { getPositionColor } from '../players/playerDisplay'

interface RecommendationCardProps {
  recommendation: DraftRecommendation
  onDraftPlayer: (player: DraftRecommendation['player']) => void
  rank: number
}

export function RecommendationCard({ recommendation, onDraftPlayer, rank }: RecommendationCardProps) {
  const getConfidenceColor = (score: number): string => {
    if (score >= 80) return 'text-success-700'
    if (score >= 60) return 'text-warning-700'
    return 'text-danger-700'
  }

  const getRiskColor = (risk: string): string => {
    const colors: Record<string, string> = {
      LOW: 'bg-success-100 text-success-800',
      MEDIUM: 'bg-warning-100 text-warning-800',
      HIGH: 'bg-danger-100 text-danger-800'
    }
    return colors[risk] || 'bg-ink-100 text-ink-800'
  }

  return (
    <div className="bg-accent-50 rounded-lg border border-accent-200 p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-6 h-6 bg-accent-500 text-white text-xs font-bold rounded-full">
            {rank}
          </div>
          <StarIcon className="h-5 w-5 text-accent-500" />
          <span className="text-sm text-accent-700 font-medium">AI Recommendation</span>
        </div>
        <div className={`text-sm font-medium ${getConfidenceColor(recommendation.score)}`}>
          {recommendation.score.toFixed(0)}% confidence
        </div>
      </div>

      <div className="mb-3">
        <div className="flex items-center gap-2 mb-1">
          <h3 className="font-semibold text-ink-900">{recommendation.player.name}</h3>
          <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPositionColor(recommendation.player.position)}`}>
            {recommendation.player.position}
          </span>
          <span className="text-sm text-ink-500">{recommendation.player.team}</span>
        </div>

        <div className="flex items-center gap-3 text-xs text-ink-500">
          <span>Tier {recommendation.tier}</span>
          <span>Pos Rank: #{recommendation.position_rank}</span>
          {recommendation.player.projected_points && (
            <span>Proj: {recommendation.player.projected_points.toFixed(1)}</span>
          )}
          {recommendation.player.adp && (
            <span>ADP: {recommendation.player.adp.toFixed(1)}</span>
          )}
        </div>
      </div>

      <p className="text-sm text-ink-700 mb-3 leading-relaxed">
        {recommendation.reasoning}
      </p>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {recommendation.value_over_replacement > 0 && (
            <span className="px-2 py-1 bg-success-100 text-success-800 text-xs rounded">
              <TrophyIcon className="h-3 w-3 inline mr-1" />
              Value: +{recommendation.value_over_replacement.toFixed(1)}
            </span>
          )}
          {recommendation.player.risk_level && (
            <span className={`px-2 py-1 text-xs rounded ${getRiskColor(recommendation.player.risk_level)}`}>
              Risk: {recommendation.player.risk_level}
            </span>
          )}
          {recommendation.bye_week_impact > 0 && (
            <span className="px-2 py-1 bg-warning-100 text-warning-800 text-xs rounded">
              Bye: Week {recommendation.player.bye_week}
            </span>
          )}
        </div>

        <button
          onClick={() => onDraftPlayer(recommendation.player)}
          className="bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors text-sm font-medium"
        >
          Draft Player
        </button>
      </div>
    </div>
  )
}
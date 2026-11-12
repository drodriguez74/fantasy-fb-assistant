import { DataConfidenceBadge } from '../../common/DataConfidenceBadge'
import { TeamNeedsStrip } from '../../waivers/LineupWaivers'
import { type TradeRecommendation } from './types'

interface TradesTabProps {
  tradeRecs: TradeRecommendation
}

export function TradesTab({ tradeRecs }: TradesTabProps) {
  return (
      <div className="space-y-6">
        {tradeRecs.team_needs && tradeRecs.team_needs.length > 0 && <TeamNeedsStrip needs={tradeRecs.team_needs} />}
        <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
          <div className="flex items-start justify-between gap-3 mb-4">
            <h3 className="text-lg font-medium text-body">Trade Suggestions</h3>
            <DataConfidenceBadge
              level={tradeRecs.basis ? 'computed' : 'heuristic'}
              label={tradeRecs.basis ? 'Real rosters' : 'AI-generated'}
            />
          </div>
          <p className="text-sm text-muted mb-6">
            {tradeRecs.basis || 'Trade recommendations based on roster analysis.'} Trade deadline: {tradeRecs.trade_deadline}
          </p>

          {tradeRecs.suggestions.length === 0 && (
            <p className="text-sm text-muted">No trade right now improves both your lineup and a partner's enough to be worth proposing.</p>
          )}

          <div className="space-y-4">
            {tradeRecs.suggestions.map((suggestion, index: number) =>
              suggestion.you_receive && suggestion.you_send ? (
                <div key={`trade-suggestion-${index}-${suggestion.team_id}`} className="border border-hairline rounded-lg p-4">
                  <div className="stat-nums text-[10px] tracking-wider text-faint mb-2">
                    WITH {(suggestion.team_name || 'ANOTHER TEAM').toUpperCase()}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <h4 className="font-medium text-danger-700">You Send</h4>
                      {(suggestion.you_send_players ?? [suggestion.you_send]).map((p) => (
                        <div key={p.name}>
                          <p className="text-body">{p.name} ({p.position})</p>
                          <p className="stat-nums text-xs text-muted">{p.projected_points?.toFixed(1)} proj</p>
                        </div>
                      ))}
                    </div>
                    <div>
                      <h4 className="font-medium text-success-700">You Receive</h4>
                      <p className="text-body">{suggestion.you_receive.name} ({suggestion.you_receive.position})</p>
                      <p className="stat-nums text-xs text-muted">{suggestion.you_receive.projected_points?.toFixed(1)} proj</p>
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t border-hairline">
                    {suggestion.my_gain != null && suggestion.their_gain != null && (
                      <p className="stat-nums text-xs mb-1">
                        <span className="text-success-700 font-semibold">You +{suggestion.my_gain.toFixed(0)}</span>
                        <span className="text-faint"> · </span>
                        <span className="text-body">Them +{suggestion.their_gain.toFixed(0)}</span>
                        <span className="text-faint"> projected season points</span>
                      </p>
                    )}
                    <p className="text-sm text-muted">{suggestion.reasoning}</p>
                  </div>
                </div>
              ) : (
                <div key={`trade-suggestion-${index}`} className="border border-hairline rounded-lg p-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <h4 className="font-medium text-success-700">Target</h4>
                      <p className="text-body">{suggestion.target_player}</p>
                    </div>
                    <div>
                      <h4 className="font-medium text-accent-ink">Offer</h4>
                      <p className="text-body">{(suggestion.offer_players ?? []).join(', ')}</p>
                    </div>
                    <div>
                      <h4 className="font-medium text-body">Likelihood</h4>
                      <p className="text-body">{suggestion.likelihood}</p>
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t border-hairline">
                    <p className="text-sm text-muted">{suggestion.reasoning}</p>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      </div>
  )
}

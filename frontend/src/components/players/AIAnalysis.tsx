import { useState } from 'react'
import { players, getErrorMessage } from '../../services/api'
import type { Player } from '../../types'

interface AIAnalysisProps {
  player: Player
  showButton?: boolean
}

export function AIAnalysis({ player, showButton = true }: AIAnalysisProps) {
  const [analysis, setAnalysis] = useState<string | null>(player.ai_analysis || null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generateAnalysis = async () => {
    try {
      setLoading(true)
      setError('')
      
      const response = await players.generateAnalysis(player.sleeper_id || player.id.toString())
      setAnalysis(response.data.ai_analysis)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to generate analysis'))
    } finally {
      setLoading(false)
    }
  }

  if (!analysis && !showButton) return null

  return (
    <div className="mt-3 p-3 bg-highlight rounded-lg border border-highlight-line">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <span className="text-sm font-semibold text-accent-ink">AI Analysis</span>
          {player.risk_level && (
            <span className={`px-2 py-1 text-xs font-medium rounded-full ${
              player.risk_level === 'LOW' ? 'bg-success-100 text-success-800' :
              player.risk_level === 'MEDIUM' ? 'bg-warning-100 text-warning-800' :
              'bg-danger-100 text-danger-800'
            }`}>
              {player.risk_level} Risk
            </span>
          )}
        </div>
        
        {showButton && !analysis && (
          <button
            onClick={generateAnalysis}
            disabled={loading}
            className="px-3 py-1 text-xs bg-volt text-volt-ink rounded hover:bg-volt-dark disabled:opacity-50"
          >
            {loading ? 'Analyzing...' : 'Get AI Insights'}
          </button>
        )}
      </div>

      {error && (
        <div className="text-xs text-danger-700 mb-2">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center space-x-2">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent-ink"></div>
          <span className="text-sm text-accent-ink">Generating AI analysis...</span>
        </div>
      )}

      {analysis && !loading && (
        <div className="text-sm text-muted leading-relaxed">
          <p className="whitespace-pre-wrap">{analysis}</p>
          
          {showButton && (
            <button
              onClick={generateAnalysis}
              disabled={loading}
              className="mt-2 px-2 py-1 text-xs text-accent-ink hover:text-accent-ink hover:bg-highlight rounded"
            >
              Refresh Analysis
            </button>
          )}
        </div>
      )}
    </div>
  )
}
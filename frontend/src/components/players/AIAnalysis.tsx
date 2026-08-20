import { useState } from 'react'
import { players } from '../../services/api'
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate analysis')
    } finally {
      setLoading(false)
    }
  }

  if (!analysis && !showButton) return null

  return (
    <div className="mt-3 p-3 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <span className="text-sm font-semibold text-blue-800">🤖 AI Analysis</span>
          {player.risk_level && (
            <span className={`px-2 py-1 text-xs font-medium rounded-full ${
              player.risk_level === 'LOW' ? 'bg-green-100 text-green-800' :
              player.risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' :
              'bg-red-100 text-red-800'
            }`}>
              {player.risk_level} Risk
            </span>
          )}
        </div>
        
        {showButton && !analysis && (
          <button
            onClick={generateAnalysis}
            disabled={loading}
            className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Analyzing...' : 'Get AI Insights'}
          </button>
        )}
      </div>

      {error && (
        <div className="text-xs text-red-600 mb-2">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center space-x-2">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
          <span className="text-sm text-blue-600">Generating AI analysis...</span>
        </div>
      )}

      {analysis && !loading && (
        <div className="text-sm text-gray-700 leading-relaxed">
          <p className="whitespace-pre-wrap">{analysis}</p>
          
          {showButton && (
            <button
              onClick={generateAnalysis}
              disabled={loading}
              className="mt-2 px-2 py-1 text-xs text-blue-600 hover:text-blue-800 hover:bg-blue-100 rounded"
            >
              🔄 Refresh Analysis
            </button>
          )}
        </div>
      )}
    </div>
  )
}
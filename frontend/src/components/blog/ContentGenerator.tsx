import { useState } from 'react'
import { PlusIcon, SparklesIcon } from '@heroicons/react/24/outline'
import { api, getErrorMessage } from '../../services/api'

interface ContentTemplate {
  name: string
  description: string
  parameters: Record<string, unknown>
}

interface ContentGeneratorProps {
  templates: Record<string, ContentTemplate>
  onContentGenerated: () => void
}

export function ContentGenerator({ templates, onContentGenerated }: ContentGeneratorProps) {
  const [generatingContent, setGeneratingContent] = useState<string | null>(null)
  const [error, setError] = useState('')

  const generateContent = async (templateKey: string, templateName: string) => {
    try {
      setGeneratingContent(templateKey)
      setError('')
      
      const requestData = {
        content_type: templateKey,
        topic: `Generated ${templateName}`,
        parameters: getDefaultParameters(templateKey)
      }
      
      await api.post('/content/generate-and-save', requestData)
      onContentGenerated()
      
    } catch (err) {
      setError(getErrorMessage(err, `Failed to generate ${templateName}`))
    } finally {
      setGeneratingContent(null)
    }
  }

  const getDefaultParameters = (templateKey: string) => {
    switch (templateKey) {
      case 'weekly_rankings':
        return { week: 1, position: 'ALL' }
      case 'waiver_wire':
        return { week: 1 }
      case 'start_sit':
        return { week: 1, position: 'ALL' }
      case 'breakout_candidates':
        return { timeframe: 'weekly' }
      case 'draft_strategy':
        return { draft_type: 'redraft', league_size: 12 }
      case 'player_analysis':
        return { player_name: 'Sample Player Analysis' }
      case 'injury_report':
        return {}
      default:
        return {}
    }
  }

  if (Object.keys(templates).length === 0) {
    return null
  }

  return (
    <div className="bg-blue-50 rounded-lg p-6">
      <div className="flex items-center mb-4">
        <SparklesIcon className="h-6 w-6 text-blue-600 mr-2" />
        <h2 className="text-lg font-semibold text-gray-900">Generate New Content</h2>
      </div>
      
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-md p-3">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(templates).map(([key, template]) => (
          <button
            key={key}
            onClick={() => generateContent(key, template.name)}
            disabled={generatingContent === key}
            className="text-left p-4 bg-white rounded-lg border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-gray-900">{template.name}</h3>
              {generatingContent === key ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
              ) : (
                <PlusIcon className="h-4 w-4 text-gray-400" />
              )}
            </div>
            <p className="text-sm text-gray-600">{template.description}</p>
          </button>
        ))}
      </div>
    </div>
  )
}
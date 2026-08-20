interface DraftSettings {
  scoringFormat: 'PPR' | 'Half PPR' | 'Standard'
  teamCount: number
  draftPosition: number
}

interface DraftSettingsProps {
  settings: DraftSettings
  onSettingsChange: (settings: DraftSettings) => void
  onRefreshRecommendations: () => void
  isLoading?: boolean
}

export function DraftSettings({ 
  settings, 
  onSettingsChange, 
  onRefreshRecommendations, 
  isLoading = false 
}: DraftSettingsProps) {
  const updateSettings = (updates: Partial<DraftSettings>) => {
    onSettingsChange({ ...settings, ...updates })
  }

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 p-6">
      <h2 className="text-lg font-semibold mb-4">Draft Settings</h2>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Scoring Format
          </label>
          <select 
            value={settings.scoringFormat}
            onChange={(e) => updateSettings({ scoringFormat: e.target.value as any })}
            className="w-full rounded-md border-gray-300 focus:border-blue-500 focus:ring-blue-500"
          >
            <option value="PPR">PPR (Point Per Reception)</option>
            <option value="Half PPR">Half PPR (0.5 Per Reception)</option>
            <option value="Standard">Standard (No PPR)</option>
          </select>
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            League Size
          </label>
          <select 
            value={settings.teamCount}
            onChange={(e) => updateSettings({ teamCount: Number(e.target.value) })}
            className="w-full rounded-md border-gray-300 focus:border-blue-500 focus:ring-blue-500"
          >
            <option value={8}>8 Teams</option>
            <option value={10}>10 Teams</option>
            <option value={12}>12 Teams</option>
            <option value={14}>14 Teams</option>
            <option value={16}>16 Teams</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Your Draft Position
          </label>
          <select 
            value={settings.draftPosition}
            onChange={(e) => updateSettings({ draftPosition: Number(e.target.value) })}
            className="w-full rounded-md border-gray-300 focus:border-blue-500 focus:ring-blue-500"
          >
            {Array.from({length: settings.teamCount}, (_, i) => (
              <option key={i + 1} value={i + 1}>
                Position {i + 1} {i === 0 ? '(First)' : i === settings.teamCount - 1 ? '(Last)' : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={onRefreshRecommendations}
            disabled={isLoading}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Generating...' : 'Refresh Recommendations'}
          </button>
        </div>

        <div className="bg-blue-50 rounded-md p-3">
          <h4 className="text-sm font-medium text-blue-900 mb-1">Current Setup</h4>
          <div className="text-xs text-blue-700 space-y-1">
            <p>Format: {settings.scoringFormat}</p>
            <p>League: {settings.teamCount} teams</p>
            <p>Position: {settings.draftPosition} of {settings.teamCount}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend, Tooltip } from 'recharts'
import { PlayerComparisonData, CHART_COLORS } from './ChartTypes'

interface PlayerComparisonChartProps {
  data: PlayerComparisonData[]
  height?: number
  showLegend?: boolean
}

interface ComparisonTooltipEntry {
  dataKey: string
  color: string
  value: number
}

interface ComparisonTooltipProps {
  active?: boolean
  payload?: ComparisonTooltipEntry[]
  label?: string | number
}

export function PlayerComparisonChart({ data, height = 400, showLegend = true }: PlayerComparisonChartProps) {
  // Transform data for radar chart
  const radarData = [
    {
      metric: 'Projected Points',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: Math.min(player.projectedPoints * 5, 100) // Scale to 0-100
      }), {})
    },
    {
      metric: 'Consistency',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: player.consistency * 10 // Scale to 0-100
      }), {})
    },
    {
      metric: 'Ceiling',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: Math.min(player.ceiling * 4, 100) // Scale to 0-100
      }), {})
    },
    {
      metric: 'Floor',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: Math.min(player.floor * 8, 100) // Scale to 0-100
      }), {})
    },
    {
      metric: 'Target Share',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: player.targetShare || 0
      }), {})
    },
    {
      metric: 'Snap Count %',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: player.snapCount || 0
      }), {})
    },
    {
      metric: 'Value Score',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: player.valueScore || 50
      }), {})
    },
    {
      metric: 'Upside Rating',
      ...data.reduce((acc, player) => ({
        ...acc,
        [player.player]: player.upsideRating * 10 // Scale to 0-100
      }), {})
    }
  ]

  // Generate colors for each player
  const playerColors = data.map((_, index) => {
    const colors = [CHART_COLORS.primary, CHART_COLORS.success, CHART_COLORS.warning, CHART_COLORS.danger, CHART_COLORS.info]
    return colors[index % colors.length]
  })

  const CustomTooltip = ({ active, payload, label }: ComparisonTooltipProps) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-semibold text-gray-900">{label}</p>
          {payload.map((entry, index: number) => (
            <p key={`tooltip-${entry.dataKey}-${index}`} style={{ color: entry.color }} className="text-sm">
              {entry.dataKey}: {entry.value.toFixed(1)}
            </p>
          ))}
        </div>
      )
    }
    return null
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={radarData} margin={{ top: 20, right: 30, bottom: 20, left: 30 }}>
          <PolarGrid stroke="#E5E7EB" />
          <PolarAngleAxis 
            dataKey="metric" 
            tick={{ fontSize: 12, fill: '#6B7280' }}
            className="text-xs"
          />
          <PolarRadiusAxis 
            angle={90} 
            domain={[0, 100]} 
            tick={{ fontSize: 10, fill: '#9CA3AF' }}
            tickCount={5}
          />
          {data.map((player, index) => (
            <Radar
              key={player.player}
              name={player.player}
              dataKey={player.player}
              stroke={playerColors[index]}
              fill={playerColors[index]}
              fillOpacity={0.1}
              strokeWidth={2}
              dot={{ fill: playerColors[index], strokeWidth: 1, r: 4 }}
            />
          ))}
          <Tooltip content={<CustomTooltip />} />
          {showLegend && (
            <Legend 
              wrapperStyle={{ paddingTop: '20px' }}
              iconType="line"
            />
          )}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

// Bar chart for side-by-side comparison
export function PlayerComparisonBarChart({ data }: PlayerComparisonChartProps) {
  // Transform data for bar chart comparison
  const metrics: Array<{
    key: 'projectedPoints' | 'consistency' | 'valueScore' | 'upsideRating'
    name: string
    color: string
  }> = [
    { key: 'projectedPoints', name: 'Projected Points', color: CHART_COLORS.primary },
    { key: 'consistency', name: 'Consistency (x10)', color: CHART_COLORS.success },
    { key: 'valueScore', name: 'Value Score', color: CHART_COLORS.warning },
    { key: 'upsideRating', name: 'Upside (x10)', color: CHART_COLORS.info }
  ]

  return (
    <div className="space-y-6">
      {metrics.map((metric) => (
        <div key={metric.key} className="bg-gray-50 p-4 rounded-lg">
          <h4 className="text-sm font-medium text-gray-900 mb-3">{metric.name}</h4>
          <div className="space-y-2">
            {data.map((player) => {
              let value = player[metric.key] || 0
              if (metric.key === 'consistency' || metric.key === 'upsideRating') {
                value *= 10 // Scale for display
              }
              const maxValue = Math.max(...data.map(p => {
                let v = p[metric.key] || 0
                if (metric.key === 'consistency' || metric.key === 'upsideRating') {
                  v *= 10
                }
                return v
              }))
              const percentage = maxValue > 0 ? (value / maxValue) * 100 : 0

              return (
                <div key={player.player} className="flex items-center space-x-3">
                  <div className="w-24 text-sm text-gray-700 truncate">{player.player}</div>
                  <div className="flex-1 bg-gray-200 rounded-full h-4 relative">
                    <div
                      className="h-4 rounded-full transition-all duration-300"
                      style={{
                        width: `${percentage}%`,
                        backgroundColor: metric.color
                      }}
                    />
                    <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-gray-900">
                      {value.toFixed(1)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
import { ResponsiveContainer, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Line, ComposedChart } from 'recharts'
import { ScheduleDifficultyData, CHART_COLORS } from './ChartTypes'

interface ScheduleDifficultyChartProps {
  data: ScheduleDifficultyData[]
  height?: number
  showAverage?: boolean
}

interface ScheduleTooltipEntry {
  dataKey: string
  color: string
  value: number
  payload: Record<string, string | number>
}

interface ScheduleTooltipProps {
  active?: boolean
  payload?: ScheduleTooltipEntry[]
  label?: string | number
}

export function ScheduleDifficultyChart({ data, height = 300, showAverage = true }: ScheduleDifficultyChartProps) {
  // Group data by player
  const playerData = data.reduce((acc, item) => {
    if (!acc[item.player]) {
      acc[item.player] = []
    }
    acc[item.player].push(item)
    return acc
  }, {} as Record<string, ScheduleDifficultyData[]>)

  // Transform for chart display
  const chartData = Array.from(new Set(data.map(d => d.week)))
    .sort((a, b) => a - b)
    .map(week => {
      const weekData: Record<string, string | number> = { week: `Week ${week}` }
      
      Object.keys(playerData).forEach(player => {
        const playerWeekData = playerData[player].find(d => d.week === week)
        if (playerWeekData) {
          weekData[player] = playerWeekData.difficulty
          weekData[`${player}_opponent`] = playerWeekData.opponent
          weekData[`${player}_rating`] = playerWeekData.rating
        }
      })

      // Calculate average difficulty for the week
      if (showAverage) {
        const weekDifficulties = Object.keys(playerData)
          .map(player => playerData[player].find(d => d.week === week)?.difficulty)
          .filter(Boolean) as number[]
        
        if (weekDifficulties.length > 0) {
          weekData.average = weekDifficulties.reduce((sum, val) => sum + val, 0) / weekDifficulties.length
        }
      }

      return weekData
    })

  const playerColors = Object.keys(playerData).map((_, index) => {
    const colors = [CHART_COLORS.primary, CHART_COLORS.success, CHART_COLORS.warning, CHART_COLORS.danger, CHART_COLORS.info]
    return colors[index % colors.length]
  })

  const CustomTooltip = ({ active, payload, label }: ScheduleTooltipProps) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-surface p-3 border border-hairline rounded-lg max-w-xs">
          <p className="font-semibold text-body mb-2">{label}</p>
          {payload.map((entry, index: number) => {
            if (entry.dataKey === 'average') {
              return (
                <p key={`tooltip-avg-${index}`} style={{ color: entry.color }} className="text-sm">
                  Average Difficulty: {entry.value.toFixed(1)}/10
                </p>
              )
            }
            
            const opponent = entry.payload[`${entry.dataKey}_opponent`]
            const rating = entry.payload[`${entry.dataKey}_rating`]
            
            return (
              <div key={`tooltip-${entry.dataKey}-${index}`} className="text-sm mb-1">
                <p style={{ color: entry.color }} className="font-medium">
                  {entry.dataKey}: {entry.value.toFixed(1)}/10
                </p>
                {opponent && (
                  <p className="text-muted text-xs">
                    vs {opponent} ({rating})
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )
    }
    return null
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            dataKey="week" 
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
          />
          <YAxis 
            domain={[0, 10]}
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: 'Difficulty (1-10)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
          />
          
          {/* Player difficulty bars */}
          {Object.keys(playerData).map((player, index) => (
            <Bar
              key={player}
              dataKey={player}
              fill={playerColors[index]}
              opacity={0.8}
              name={player}
            />
          ))}
          
          {/* Average line */}
          {showAverage && (
            <Line
              type="monotone"
              dataKey="average"
              stroke="#6B7280"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={{ fill: '#6B7280', strokeWidth: 2, r: 4 }}
              name="Average"
            />
          )}
          
          <Tooltip content={<CustomTooltip />} />
          <Legend />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

// Heatmap version for easier comparison
export function ScheduleDifficultyHeatmap({ data }: ScheduleDifficultyChartProps) {
  const players = Array.from(new Set(data.map(d => d.player)))
  const weeks = Array.from(new Set(data.map(d => d.week))).sort((a, b) => a - b)

  const getDifficultyColor = (difficulty: number) => {
    if (difficulty <= 3.5) return 'bg-green-200 text-green-800'
    if (difficulty <= 6.5) return 'bg-yellow-200 text-yellow-800'
    return 'bg-red-200 text-red-800'
  }

  return (
    <div className="w-full overflow-x-auto">
      <div className="min-w-max">
        <div className="grid grid-cols-1 gap-2">
          {/* Header */}
          <div className="grid grid-cols-[120px_repeat(8,80px)] gap-1 text-xs font-medium text-muted">
            <div></div>
            {weeks.map(week => (
              <div key={week} className="text-center">Week {week}</div>
            ))}
          </div>
          
          {/* Data rows */}
          {players.map(player => (
            <div key={player} className="grid grid-cols-[120px_repeat(8,80px)] gap-1">
              <div className="text-sm font-medium text-body truncate">{player}</div>
              {weeks.map(week => {
                const playerWeek = data.find(d => d.player === player && d.week === week)
                if (!playerWeek) {
                  return <div key={week} className="h-12 bg-surface-2 rounded flex items-center justify-center text-xs text-faint">-</div>
                }
                
                return (
                  <div
                    key={week}
                    className={`h-12 rounded flex flex-col items-center justify-center text-xs font-medium ${getDifficultyColor(playerWeek.difficulty)}`}
                    title={`${player} vs ${playerWeek.opponent}: ${playerWeek.difficulty}/10 (${playerWeek.rating})`}
                  >
                    <div>{playerWeek.difficulty.toFixed(1)}</div>
                    <div className="text-xs opacity-75">{playerWeek.opponent}</div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
        
        {/* Legend */}
        <div className="mt-4 flex items-center justify-center space-x-6 text-xs">
          <div className="flex items-center space-x-1">
            <div className="w-3 h-3 bg-green-200 rounded"></div>
            <span>Easy (1-3.5)</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-3 h-3 bg-yellow-200 rounded"></div>
            <span>Moderate (3.5-6.5)</span>
          </div>
          <div className="flex items-center space-x-1">
            <div className="w-3 h-3 bg-red-200 rounded"></div>
            <span>Difficult (6.5-10)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
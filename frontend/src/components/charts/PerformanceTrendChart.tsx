import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, AreaChart, Area, ComposedChart, Bar } from 'recharts'
import { TrendData, CHART_COLORS } from './ChartTypes'

interface PerformanceTrendChartProps {
  data: TrendData[]
  height?: number
  showProjections?: boolean
  showAverage?: boolean
  chartType?: 'line' | 'area' | 'composed'
}

interface TrendTooltipEntry {
  dataKey: string
  color: string
  value: number
}

interface TrendTooltipProps {
  active?: boolean
  payload?: TrendTooltipEntry[]
  label?: string | number
}

export function PerformanceTrendChart({ 
  data, 
  height = 300, 
  showProjections = false, 
  showAverage = true,
  chartType = 'line'
}: PerformanceTrendChartProps) {
  
  // Group data by player and sort by week
  const playerData = data.reduce((acc, item) => {
    if (!acc[item.player]) {
      acc[item.player] = []
    }
    acc[item.player].push(item)
    return acc
  }, {} as Record<string, TrendData[]>)

  // Sort each player's data by week
  Object.keys(playerData).forEach(player => {
    playerData[player].sort((a, b) => a.week - b.week)
  })

  // Create chart data structure
  const weeks = Array.from(new Set(data.map(d => d.week))).sort((a, b) => a - b)
  const chartData = weeks.map(week => {
    const weekData: Record<string, number> = { week }
    
    Object.keys(playerData).forEach(player => {
      const playerWeekData = playerData[player].find(d => d.week === week)
      if (playerWeekData) {
        weekData[player] = playerWeekData.points
        if (showProjections && playerWeekData.projection) {
          weekData[`${player}_projection`] = playerWeekData.projection
        }
      }
    })

    // Calculate average for the week
    if (showAverage) {
      const weekPoints = Object.keys(playerData)
        .map(player => playerData[player].find(d => d.week === week)?.points)
        .filter(Boolean) as number[]
      
      if (weekPoints.length > 0) {
        weekData.average = weekPoints.reduce((sum, val) => sum + val, 0) / weekPoints.length
      }
    }

    return weekData
  })

  const players = Object.keys(playerData)
  const playerColors = players.map((_, index) => {
    const colors = [CHART_COLORS.primary, CHART_COLORS.success, CHART_COLORS.warning, CHART_COLORS.danger, CHART_COLORS.info]
    return colors[index % colors.length]
  })

  const CustomTooltip = ({ active, payload, label }: TrendTooltipProps) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-semibold text-gray-900 mb-2">Week {label}</p>
          {payload.map((entry, index: number) => {
            if (entry.dataKey === 'average') {
              return (
                <p key={`tooltip-avg-${index}`} style={{ color: entry.color }} className="text-sm">
                  Average: {entry.value.toFixed(1)} pts
                </p>
              )
            } else if (entry.dataKey.includes('_projection')) {
              return (
                <p key={`tooltip-proj-${entry.dataKey}-${index}`} style={{ color: entry.color }} className="text-sm italic">
                  {entry.dataKey.replace('_projection', '')} (proj): {entry.value.toFixed(1)} pts
                </p>
              )
            } else {
              return (
                <p key={`tooltip-${entry.dataKey}-${index}`} style={{ color: entry.color }} className="text-sm">
                  {entry.dataKey}: {entry.value.toFixed(1)} pts
                </p>
              )
            }
          })}
        </div>
      )
    }
    return null
  }

  if (chartType === 'area') {
    return (
      <div className="w-full">
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis 
              dataKey="week" 
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#D1D5DB' }}
            />
            <YAxis 
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#D1D5DB' }}
              label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
            />
            
            {players.map((player, index) => (
              <Area
                key={player}
                type="monotone"
                dataKey={player}
                stackId="1"
                stroke={playerColors[index]}
                fill={playerColors[index]}
                fillOpacity={0.6}
                strokeWidth={2}
              />
            ))}
            
            <Tooltip content={<CustomTooltip />} />
            <Legend />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (chartType === 'composed') {
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
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#D1D5DB' }}
              label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
            />
            
            {/* Show first player as bars, rest as lines */}
            {players.slice(0, 1).map((player, index) => (
              <Bar
                key={player}
                dataKey={player}
                fill={playerColors[index]}
                opacity={0.8}
                name={player}
              />
            ))}
            
            {players.slice(1).map((player, index) => (
              <Line
                key={player}
                type="monotone"
                dataKey={player}
                stroke={playerColors[index + 1]}
                strokeWidth={2}
                dot={{ fill: playerColors[index + 1], strokeWidth: 2, r: 4 }}
                name={player}
              />
            ))}
            
            {/* Projections as dashed lines */}
            {showProjections && players.map((player, index) => (
              <Line
                key={`${player}_projection`}
                type="monotone"
                dataKey={`${player}_projection`}
                stroke={playerColors[index]}
                strokeWidth={1}
                strokeDasharray="5 5"
                dot={false}
                name={`${player} (proj)`}
              />
            ))}
            
            {/* Average line */}
            {showAverage && (
              <Line
                type="monotone"
                dataKey="average"
                stroke="#6B7280"
                strokeWidth={2}
                strokeDasharray="8 4"
                dot={{ fill: '#6B7280', strokeWidth: 2, r: 3 }}
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

  // Default line chart
  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            dataKey="week" 
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
          />
          <YAxis 
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
          />
          
          {players.map((player, index) => (
            <Line
              key={player}
              type="monotone"
              dataKey={player}
              stroke={playerColors[index]}
              strokeWidth={2}
              dot={{ fill: playerColors[index], strokeWidth: 2, r: 4 }}
              activeDot={{ r: 6 }}
              name={player}
            />
          ))}
          
          {/* Projections as dashed lines */}
          {showProjections && players.map((player, index) => (
            <Line
              key={`${player}_projection`}
              type="monotone"
              dataKey={`${player}_projection`}
              stroke={playerColors[index]}
              strokeWidth={1}
              strokeDasharray="5 5"
              dot={false}
              name={`${player} (proj)`}
            />
          ))}
          
          {/* Average line */}
          {showAverage && (
            <Line
              type="monotone"
              dataKey="average"
              stroke="#6B7280"
              strokeWidth={2}
              strokeDasharray="8 4"
              dot={{ fill: '#6B7280', strokeWidth: 2, r: 3 }}
              name="Average"
            />
          )}
          
          <Tooltip content={<CustomTooltip />} />
          <Legend />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// Mini sparkline version for compact display
export function PerformanceSparkline({ data, height = 60, width = 200 }: { data: TrendData[], height?: number, width?: number }) {
  const sortedData = [...data].sort((a, b) => a.week - b.week)
  
  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={sortedData}>
        <Line
          type="monotone"
          dataKey="points"
          stroke={CHART_COLORS.primary}
          strokeWidth={2}
          dot={false}
          activeDot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
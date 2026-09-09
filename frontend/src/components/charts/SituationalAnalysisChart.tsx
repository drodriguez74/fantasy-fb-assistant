import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, RadialBarChart, RadialBar, PieChart, Pie, Cell } from 'recharts'
import { SituationalData } from './ChartTypes'
import { useChartColors, seriesColor, type ChartColors } from '../../hooks/useChartColors'

interface SituationalAnalysisChartProps {
  data: SituationalData[]
  height?: number
  chartType?: 'bar' | 'radial' | 'comparison'
}

type SituationalChartDatum = SituationalData & {
  difference: number
  homeAdvantage: boolean
  total: number
}

interface SituationalTooltipProps {
  active?: boolean
  payload?: Array<{ payload: SituationalChartDatum }>
  label?: string | number
}

/** Shared Recharts tooltip chrome so the default box reads in dark mode. */
function tooltipStyle(colors: ChartColors) {
  return {
    contentStyle: {
      backgroundColor: colors.surface,
      border: `1px solid ${colors.grid}`,
      borderRadius: 8,
      color: colors.text,
    },
    labelStyle: { color: colors.text },
    itemStyle: { color: colors.textMuted },
  }
}

export function SituationalAnalysisChart({
  data,
  height = 300,
  chartType = 'bar'
}: SituationalAnalysisChartProps) {
  const colors = useChartColors()

  // Transform data for different chart types
  const chartData = data.map(item => ({
    ...item,
    difference: item.home - item.away,
    homeAdvantage: item.home > item.away,
    total: item.home + item.away
  }))

  const CustomTooltip = ({ active, payload, label }: SituationalTooltipProps) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-surface p-3 border border-hairline rounded-lg text-body">
          <p className="font-semibold text-body mb-2">{data.player}</p>
          <p className="text-sm">Situation: <span className="font-medium">{label}</span></p>
          <p className="text-sm">Home: <span className="font-medium">{data.home.toFixed(1)} pts</span></p>
          <p className="text-sm">Away: <span className="font-medium">{data.away.toFixed(1)} pts</span></p>
          <p className="text-sm">Difference: <span className="font-medium" style={{ color: data.difference > 0 ? colors.pos : colors.neg }}>
            {data.difference > 0 ? '+' : ''}{data.difference.toFixed(1)} pts
          </span></p>
        </div>
      )
    }
    return null
  }

  if (chartType === 'radial') {
    return (
      <div className="w-full">
        <ResponsiveContainer width="100%" height={height}>
          <RadialBarChart
            innerRadius="20%"
            outerRadius="80%"
            data={chartData}
            startAngle={90}
            endAngle={-270}
          >
            <RadialBar
              dataKey="home"
              cornerRadius={10}
              fill={seriesColor(colors, 0)}
              label={{ position: 'insideStart', fill: '#fff', fontSize: 12 }}
            />
            <RadialBar
              dataKey="away"
              cornerRadius={10}
              fill={seriesColor(colors, 4)}
              label={{ position: 'insideStart', fill: '#fff', fontSize: 12 }}
            />
            <Legend
              iconSize={8}
              wrapperStyle={{ fontSize: '12px', paddingTop: '20px', color: colors.textMuted }}
            />
            <Tooltip content={<CustomTooltip />} />
          </RadialBarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (chartType === 'comparison') {
    return (
      <div className="w-full space-y-4">
        {chartData.map((player) => (
          <div key={player.player} className="bg-surface-2 p-4 rounded-lg">
            <h4 className="text-sm font-medium text-body mb-3">{player.player}</h4>
            <div className="space-y-2">
              {/* Home performance */}
              <div className="flex items-center space-x-3">
                <div className="w-12 text-xs text-muted">Home</div>
                <div className="flex-1 bg-surface rounded-full h-6 relative border border-hairline">
                  <div
                    className="h-6 bg-accent-500 rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min((player.home / Math.max(player.home, player.away)) * 100, 100)}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-body">
                    {player.home.toFixed(1)} pts
                  </span>
                </div>
              </div>

              {/* Away performance */}
              <div className="flex items-center space-x-3">
                <div className="w-12 text-xs text-muted">Away</div>
                <div className="flex-1 bg-surface rounded-full h-6 relative border border-hairline">
                  <div
                    className="h-6 bg-faint rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min((player.away / Math.max(player.home, player.away)) * 100, 100)}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-body">
                    {player.away.toFixed(1)} pts
                  </span>
                </div>
              </div>

              {/* Difference indicator */}
              <div className="flex items-center justify-between text-xs mt-2">
                <span className="text-muted">Preference:</span>
                <span className={`font-medium ${player.homeAdvantage ? 'text-accent-ink' : 'text-muted'}`}>
                  {player.homeAdvantage ? 'Home' : 'Away'} ({Math.abs(player.difference).toFixed(1)} pts)
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  // Default bar chart
  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            dataKey="player"
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            angle={-45}
            textAnchor="end"
            height={80}
          />
          <YAxis
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: colors.textMuted } }}
          />
          <Bar dataKey="home" fill={seriesColor(colors, 0)} name="Home" />
          <Bar dataKey="away" fill={seriesColor(colors, 4)} name="Away" />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ color: colors.textMuted }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// Weather impact visualization
export function WeatherImpactChart({
  data,
  height = 250
}: {
  data: Array<{player: string, outdoor: number, dome: number, weatherSensitivity: string}>,
  height?: number
}) {
  const colors = useChartColors()

  const chartData = data.map(item => ({
    ...item,
    difference: item.dome - item.outdoor,
    domeAdvantage: item.dome > item.outdoor
  }))

  type WeatherChartDatum = (typeof chartData)[number]

  const getSensitivityColor = (sensitivity: string) => {
    switch (sensitivity.toUpperCase()) {
      case 'LOW': return colors.pos
      case 'MEDIUM': return colors.warn
      case 'HIGH': return colors.neg
      default: return colors.textMuted
    }
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            dataKey="player"
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            angle={-45}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: colors.textMuted } }}
          />
          <Bar dataKey="outdoor" fill={seriesColor(colors, 4)} name="Outdoor" />
          <Bar dataKey="dome" fill={seriesColor(colors, 0)} name="Dome" />
          <Tooltip
            cursor={{ fill: colors.grid, fillOpacity: 0.3 }}
            content={({ active, payload, label }: { active?: boolean; payload?: Array<{ payload: WeatherChartDatum }>; label?: string | number }) => {
              if (active && payload && payload.length) {
                const data = payload[0].payload
                return (
                  <div className="bg-surface p-3 border border-hairline rounded-lg text-body">
                    <p className="font-semibold text-body mb-2">{label}</p>
                    <p className="text-sm">Outdoor: <span className="font-medium">{data.outdoor.toFixed(1)} pts</span></p>
                    <p className="text-sm">Dome: <span className="font-medium">{data.dome.toFixed(1)} pts</span></p>
                    <p className="text-sm">Weather Sensitivity: <span
                      className="font-medium"
                      style={{ color: getSensitivityColor(data.weatherSensitivity) }}
                    >
                      {data.weatherSensitivity}
                    </span></p>
                  </div>
                )
              }
              return null
            }}
          />
          <Legend wrapperStyle={{ color: colors.textMuted }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// Game script analysis pie chart
export function GameScriptChart({
  data,
  height = 250
}: {
  data: Array<{player: string, leading: number, trailing: number, close: number}>,
  height?: number
}) {
  const colors = useChartColors()

  if (data.length === 0) return null

  // Use first player's data for pie chart (can be enhanced to show multiple players)
  const player = data[0]
  const pieData = [
    { name: 'Leading Games', value: player.leading, fill: colors.pos },
    { name: 'Trailing Games', value: player.trailing, fill: colors.neg },
    { name: 'Close Games', value: player.close, fill: colors.warn }
  ]

  return (
    <div className="w-full">
      <h4 className="text-sm font-medium text-body mb-2 text-center">{player.player} - Game Script Performance</h4>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={pieData}
            cx="50%"
            cy="50%"
            innerRadius={40}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
            stroke={colors.surface}
            label={({ name, value }) => `${name}: ${value?.toFixed(1) || 'N/A'}`}
            labelLine={false}
          >
            {pieData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip
            {...tooltipStyle(colors)}
            formatter={(value: number) => [`${value.toFixed(1)} pts`, '']}
          />
          <Legend wrapperStyle={{ color: colors.textMuted }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

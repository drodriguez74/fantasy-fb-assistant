import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, RadialBarChart, RadialBar, PieChart, Pie, Cell } from 'recharts'
import { SituationalData, CHART_COLORS } from './ChartTypes'

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

export function SituationalAnalysisChart({ 
  data, 
  height = 300,
  chartType = 'bar'
}: SituationalAnalysisChartProps) {
  
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
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-semibold text-gray-900 mb-2">{data.player}</p>
          <p className="text-sm">Situation: <span className="font-medium">{label}</span></p>
          <p className="text-sm">Home: <span className="font-medium">{data.home.toFixed(1)} pts</span></p>
          <p className="text-sm">Away: <span className="font-medium">{data.away.toFixed(1)} pts</span></p>
          <p className="text-sm">Difference: <span className={`font-medium ${data.difference > 0 ? 'text-green-600' : 'text-red-600'}`}>
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
              fill={CHART_COLORS.primary}
              label={{ position: 'insideStart', fill: 'white', fontSize: 12 }}
            />
            <RadialBar
              dataKey="away"
              cornerRadius={10}
              fill={CHART_COLORS.secondary}
              label={{ position: 'insideStart', fill: 'white', fontSize: 12 }}
            />
            <Legend 
              iconSize={8}
              wrapperStyle={{ fontSize: '12px', paddingTop: '20px' }}
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
          <div key={player.player} className="bg-gray-50 p-4 rounded-lg">
            <h4 className="text-sm font-medium text-gray-900 mb-3">{player.player}</h4>
            <div className="space-y-2">
              {/* Home performance */}
              <div className="flex items-center space-x-3">
                <div className="w-12 text-xs text-gray-600">Home</div>
                <div className="flex-1 bg-gray-200 rounded-full h-6 relative">
                  <div
                    className="h-6 bg-blue-500 rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min((player.home / Math.max(player.home, player.away)) * 100, 100)}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-gray-900">
                    {player.home.toFixed(1)} pts
                  </span>
                </div>
              </div>
              
              {/* Away performance */}
              <div className="flex items-center space-x-3">
                <div className="w-12 text-xs text-gray-600">Away</div>
                <div className="flex-1 bg-gray-200 rounded-full h-6 relative">
                  <div
                    className="h-6 bg-gray-500 rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.min((player.away / Math.max(player.home, player.away)) * 100, 100)}%`
                    }}
                  />
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-gray-900">
                    {player.away.toFixed(1)} pts
                  </span>
                </div>
              </div>
              
              {/* Difference indicator */}
              <div className="flex items-center justify-between text-xs mt-2">
                <span className="text-gray-600">Preference:</span>
                <span className={`font-medium ${player.homeAdvantage ? 'text-blue-600' : 'text-gray-600'}`}>
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
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            dataKey="player"
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            angle={-45}
            textAnchor="end"
            height={80}
          />
          <YAxis 
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
          />
          <Bar dataKey="home" fill={CHART_COLORS.primary} name="Home" />
          <Bar dataKey="away" fill={CHART_COLORS.secondary} name="Away" />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
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
  const chartData = data.map(item => ({
    ...item,
    difference: item.dome - item.outdoor,
    domeAdvantage: item.dome > item.outdoor
  }))

  type WeatherChartDatum = (typeof chartData)[number]

  const getSensitivityColor = (sensitivity: string) => {
    switch (sensitivity.toUpperCase()) {
      case 'LOW': return CHART_COLORS.success
      case 'MEDIUM': return CHART_COLORS.warning
      case 'HIGH': return CHART_COLORS.danger
      default: return CHART_COLORS.secondary
    }
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            dataKey="player"
            tick={{ fontSize: 12, fill: '#6B7280' }}
            angle={-45}
            textAnchor="end"
            height={60}
          />
          <YAxis 
            tick={{ fontSize: 12, fill: '#6B7280' }}
            label={{ value: 'Fantasy Points', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
          />
          <Bar dataKey="outdoor" fill="#94A3B8" name="Outdoor" />
          <Bar dataKey="dome" fill="#3B82F6" name="Dome" />
          <Tooltip
            content={({ active, payload, label }: { active?: boolean; payload?: Array<{ payload: WeatherChartDatum }>; label?: string | number }) => {
              if (active && payload && payload.length) {
                const data = payload[0].payload
                return (
                  <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
                    <p className="font-semibold text-gray-900 mb-2">{label}</p>
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
          <Legend />
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
  if (data.length === 0) return null

  // Use first player's data for pie chart (can be enhanced to show multiple players)
  const player = data[0]
  const pieData = [
    { name: 'Leading Games', value: player.leading, fill: CHART_COLORS.success },
    { name: 'Trailing Games', value: player.trailing, fill: CHART_COLORS.danger },
    { name: 'Close Games', value: player.close, fill: CHART_COLORS.warning }
  ]

  return (
    <div className="w-full">
      <h4 className="text-sm font-medium text-gray-900 mb-2 text-center">{player.player} - Game Script Performance</h4>
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
            label={({ name, value }) => `${name}: ${value?.toFixed(1) || 'N/A'}`}
            labelLine={false}
          >
            {pieData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number) => [`${value.toFixed(1)} pts`, '']}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
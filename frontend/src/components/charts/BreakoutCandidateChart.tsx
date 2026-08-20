import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { BreakoutCandidateData, CHART_COLORS, RISK_COLORS } from './ChartTypes'

interface BreakoutCandidateChartProps {
  data: BreakoutCandidateData[]
  height?: number
  xAxis?: 'age' | 'ownership' | 'targetShare' | 'efficiency'
  yAxis?: 'probability' | 'snapCount' | 'targetShare'
}

export function BreakoutCandidateChart({ 
  data, 
  height = 400, 
  xAxis = 'ownership', 
  yAxis = 'probability' 
}: BreakoutCandidateChartProps) {
  
  // Transform data for scatter plot
  const chartData = data.map((candidate, index) => ({
    ...candidate,
    x: (candidate as any)[xAxis],
    y: (candidate as any)[yAxis],
    z: candidate.targetShare || 10, // Size for bubble chart
    index
  }))

  const getAxisLabel = (axis: string) => {
    switch (axis) {
      case 'age': return 'Age'
      case 'ownership': return 'Ownership %'
      case 'targetShare': return 'Target Share %'
      case 'efficiency': return 'Efficiency Score'
      case 'probability': return 'Breakout Probability'
      case 'snapCount': return 'Snap Count %'
      default: return axis
    }
  }

  const getProbabilityColor = (probability: number) => {
    if (probability >= 0.7) return RISK_COLORS.LOW    // High probability = green
    if (probability >= 0.5) return RISK_COLORS.MEDIUM // Medium probability = yellow
    return RISK_COLORS.HIGH                           // Low probability = red
  }

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-semibold text-gray-900 mb-2">{data.player}</p>
          <div className="space-y-1 text-sm">
            <p>Breakout Probability: <span className="font-medium">{(data.probability * 100).toFixed(1)}%</span></p>
            <p>Age: <span className="font-medium">{data.age || 'N/A'}</span></p>
            <p>Ownership: <span className="font-medium">{data.ownership?.toFixed(1) || '0'}%</span></p>
            <p>Target Share: <span className="font-medium">{data.targetShare?.toFixed(1) || '0'}%</span></p>
            <p>Snap Count: <span className="font-medium">{data.snapCount?.toFixed(1) || '0'}%</span></p>
            <p>Efficiency: <span className="font-medium">{data.efficiency?.toFixed(2) || 'N/A'}</span></p>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart
          data={chartData}
          margin={{ top: 20, right: 30, bottom: 40, left: 40 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            type="number"
            dataKey="x"
            name={getAxisLabel(xAxis)}
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: getAxisLabel(xAxis), position: 'insideBottom', offset: -20, style: { textAnchor: 'middle' } }}
          />
          <YAxis 
            type="number"
            dataKey="y"
            name={getAxisLabel(yAxis)}
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: getAxisLabel(yAxis), angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
            domain={yAxis === 'probability' ? [0, 1] : undefined}
          />
          <Tooltip content={<CustomTooltip />} />
          <Scatter
            dataKey="y"
            fill={CHART_COLORS.primary}
          >
            {chartData.map((entry, index) => (
              <Cell 
                key={`cell-${index}`} 
                fill={getProbabilityColor(entry.probability)}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

// Bubble chart version with three dimensions
export function BreakoutCandidateBubbleChart({ data, height = 400 }: BreakoutCandidateChartProps) {
  const chartData = data.map((candidate, index) => ({
    ...candidate,
    x: candidate.ownership || 0,
    y: candidate.probability,
    z: (candidate.targetShare || 5) * 2, // Size multiplier for visibility
    index
  }))

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-semibold text-gray-900 mb-2">{data.player}</p>
          <div className="space-y-1 text-sm">
            <p>Breakout Probability: <span className="font-medium">{(data.probability * 100).toFixed(1)}%</span></p>
            <p>Ownership: <span className="font-medium">{data.ownership?.toFixed(1) || '0'}%</span></p>
            <p>Target Share: <span className="font-medium">{data.targetShare?.toFixed(1) || '0'}%</span> (bubble size)</p>
            <p>Age: <span className="font-medium">{data.age || 'N/A'}</span></p>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="w-full">
      <div className="mb-4 text-sm text-gray-600">
        <p>X-axis: Ownership %, Y-axis: Breakout Probability, Bubble size: Target Share</p>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart
          data={chartData}
          margin={{ top: 20, right: 30, bottom: 40, left: 40 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            type="number"
            dataKey="x"
            name="Ownership %"
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: 'Ownership %', position: 'insideBottom', offset: -20, style: { textAnchor: 'middle' } }}
          />
          <YAxis 
            type="number"
            dataKey="y"
            name="Breakout Probability"
            domain={[0, 1]}
            tick={{ fontSize: 12, fill: '#6B7280' }}
            axisLine={{ stroke: '#D1D5DB' }}
            label={{ value: 'Breakout Probability', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Scatter dataKey="y">
            {chartData.map((entry, index) => (
              <Cell 
                key={`cell-${index}`} 
                fill={getProbabilityColor(entry.probability)}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      
      {/* Legend */}
      <div className="mt-4 flex items-center justify-center space-x-6 text-xs">
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 bg-green-500 rounded-full"></div>
          <span>High Probability (70%+)</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <span>Medium Probability (50-70%)</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 bg-red-500 rounded-full"></div>
          <span>Low Probability (&lt;50%)</span>
        </div>
      </div>
    </div>
  )
}

// Helper function to get color based on probability
function getProbabilityColor(probability: number): string {
  if (probability >= 0.7) return RISK_COLORS.LOW
  if (probability >= 0.5) return RISK_COLORS.MEDIUM
  return RISK_COLORS.HIGH
}
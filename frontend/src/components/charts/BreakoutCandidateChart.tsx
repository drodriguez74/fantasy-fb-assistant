import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { BreakoutCandidateData } from './ChartTypes'
import { useChartColors, seriesColor, probabilityColor } from '../../hooks/useChartColors'

interface BreakoutCandidateChartProps {
  data: BreakoutCandidateData[]
  height?: number
  xAxis?: 'age' | 'ownership' | 'targetShare' | 'efficiency'
  yAxis?: 'probability' | 'snapCount' | 'targetShare'
}

interface BreakoutTooltipProps {
  active?: boolean
  payload?: Array<{ payload: BreakoutCandidateData & { x: number; y: number; z: number; index: number } }>
}

export function BreakoutCandidateChart({
  data,
  height = 400,
  xAxis = 'ownership',
  yAxis = 'probability'
}: BreakoutCandidateChartProps) {
  const colors = useChartColors()

  // Transform data for scatter plot
  const chartData = data.map((candidate, index) => ({
    ...candidate,
    x: candidate[xAxis],
    y: candidate[yAxis],
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

  const CustomTooltip = ({ active, payload }: BreakoutTooltipProps) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-surface p-3 border border-hairline rounded-lg">
          <p className="font-semibold text-body mb-2">{data.player}</p>
          <div className="space-y-1 text-sm text-body">
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
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            type="number"
            dataKey="x"
            name={getAxisLabel(xAxis)}
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            label={{ value: getAxisLabel(xAxis), position: 'insideBottom', offset: -20, style: { textAnchor: 'middle', fill: colors.textMuted } }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={getAxisLabel(yAxis)}
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            label={{ value: getAxisLabel(yAxis), angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: colors.textMuted } }}
            domain={yAxis === 'probability' ? [0, 1] : undefined}
          />
          <Tooltip content={<CustomTooltip />} />
          <Scatter
            dataKey="y"
            fill={seriesColor(colors, 0)}
          >
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={probabilityColor(colors, entry.probability)}
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
  const colors = useChartColors()

  const chartData = data.map((candidate, index) => ({
    ...candidate,
    x: candidate.ownership || 0,
    y: candidate.probability,
    z: (candidate.targetShare || 5) * 2, // Size multiplier for visibility
    index
  }))

  const CustomTooltip = ({ active, payload }: BreakoutTooltipProps) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-surface p-3 border border-hairline rounded-lg">
          <p className="font-semibold text-body mb-2">{data.player}</p>
          <div className="space-y-1 text-sm text-body">
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
      <div className="mb-4 text-sm text-muted">
        <p>X-axis: Ownership %, Y-axis: Breakout Probability, Bubble size: Target Share</p>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart
          data={chartData}
          margin={{ top: 20, right: 30, bottom: 40, left: 40 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            type="number"
            dataKey="x"
            name="Ownership %"
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            label={{ value: 'Ownership %', position: 'insideBottom', offset: -20, style: { textAnchor: 'middle', fill: colors.textMuted } }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Breakout Probability"
            domain={[0, 1]}
            tick={{ fontSize: 12, fill: colors.textMuted }}
            axisLine={{ stroke: colors.axis }}
            label={{ value: 'Breakout Probability', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: colors.textMuted } }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Scatter dataKey="y">
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={probabilityColor(colors, entry.probability)}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="mt-4 flex items-center justify-center space-x-6 text-xs text-muted">
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors.pos }}></div>
          <span>High Probability (70%+)</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors.warn }}></div>
          <span>Medium Probability (50-70%)</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors.neg }}></div>
          <span>Low Probability (&lt;50%)</span>
        </div>
      </div>
    </div>
  )
}

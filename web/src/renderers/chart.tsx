/**
 * Built-in chart renderer — bar and line charts as inline SVG.
 *
 * Content part schema:
 *
 *     {
 *       type: "chart",
 *       chart_type: "bar" | "line",
 *       title: "Optional title",
 *       data: [{ label: "Q1", value: 45 }, ...]
 *     }
 */

import type { RendererProps } from './registry'

const COLORS = {
  bar: 'hsl(var(--primary))',
  line: 'hsl(var(--primary))',
  axis: 'hsl(var(--muted-foreground))',
  label: 'hsl(var(--muted-foreground))',
  title: 'hsl(var(--foreground))',
  grid: 'hsl(var(--border))',
  dot: 'hsl(var(--primary))',
}

interface DataPoint {
  label: string
  value: number
}

export function ChartRenderer({ data }: RendererProps) {
  const chartType = (data.chart_type as string) || 'bar'
  const items = (data.data as DataPoint[]) || []
  const title = data.title as string | undefined

  if (!items.length) {
    return <div className="text-xs text-muted-foreground italic">(no chart data)</div>
  }

  return (
    <div className="my-2">
      {title && (
        <div className="text-xs font-medium mb-1.5" style={{ color: COLORS.title }}>
          {title}
        </div>
      )}
      {chartType === 'line' ? (
        <LineChart items={items} />
      ) : (
        <BarChart items={items} />
      )}
    </div>
  )
}

function BarChart({ items }: { items: DataPoint[] }) {
  const maxVal = Math.max(...items.map((d) => d.value), 1)
  const barHeight = 20
  const gap = 4
  const labelWidth = 60
  const valueWidth = 40
  const chartWidth = 200
  const svgWidth = labelWidth + chartWidth + valueWidth
  const svgHeight = items.length * (barHeight + gap) - gap

  return (
    <svg
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      width="100%"
      style={{ maxWidth: svgWidth }}
      role="img"
    >
      {items.map((d, i) => {
        const y = i * (barHeight + gap)
        const barW = (d.value / maxVal) * chartWidth

        return (
          <g key={i}>
            {/* Label */}
            <text
              x={labelWidth - 6}
              y={y + barHeight / 2}
              textAnchor="end"
              dominantBaseline="central"
              fontSize="10"
              fill={COLORS.label}
            >
              {d.label}
            </text>
            {/* Bar */}
            <rect
              x={labelWidth}
              y={y}
              width={barW}
              height={barHeight}
              rx={3}
              fill={COLORS.bar}
              opacity={0.8}
            />
            {/* Value */}
            <text
              x={labelWidth + barW + 6}
              y={y + barHeight / 2}
              dominantBaseline="central"
              fontSize="10"
              fill={COLORS.label}
            >
              {d.value}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function LineChart({ items }: { items: DataPoint[] }) {
  const values = items.map((d) => d.value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const span = maxVal - minVal || 1

  const padding = { top: 10, right: 10, bottom: 28, left: 10 }
  const chartW = Math.max(items.length * 32, 200)
  const chartH = 100
  const svgW = padding.left + chartW + padding.right
  const svgH = padding.top + chartH + padding.bottom

  const points = items.map((d, i) => ({
    x: padding.left + (i / Math.max(items.length - 1, 1)) * chartW,
    y: padding.top + chartH - ((d.value - minVal) / span) * chartH,
  }))

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
    .join(' ')

  // Area fill path
  const areaD = `${pathD} L ${points[points.length - 1].x} ${padding.top + chartH} L ${points[0].x} ${padding.top + chartH} Z`

  return (
    <svg viewBox={`0 0 ${svgW} ${svgH}`} width="100%" style={{ maxWidth: svgW }} role="img">
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
        const y = padding.top + chartH - frac * chartH
        return (
          <line
            key={frac}
            x1={padding.left}
            y1={y}
            x2={padding.left + chartW}
            y2={y}
            stroke={COLORS.grid}
            strokeWidth={0.5}
          />
        )
      })}

      {/* Area */}
      <path d={areaD} fill={COLORS.line} opacity={0.1} />

      {/* Line */}
      <path d={pathD} fill="none" stroke={COLORS.line} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

      {/* Dots */}
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill={COLORS.dot} />
      ))}

      {/* X-axis labels */}
      {items.map((d, i) => {
        // Skip some labels if too many
        const skip = items.length > 10 ? Math.ceil(items.length / 10) : 1
        if (i % skip !== 0 && i !== items.length - 1) return null
        return (
          <text
            key={i}
            x={points[i].x}
            y={svgH - 4}
            textAnchor="middle"
            fontSize="9"
            fill={COLORS.label}
          >
            {d.label}
          </text>
        )
      })}
    </svg>
  )
}

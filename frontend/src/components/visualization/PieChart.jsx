import React from 'react'
import {
  ResponsiveContainer,
  PieChart as RechartsPie,
  Pie,
  Cell,
  Tooltip,
  Legend
} from 'recharts'
import { CHART_COLORS, formatValue, truncateLabel, formatColumnHeader } from './formatters'

const CustomTooltip = ({ active, payload, format, totalSum }) => {
  if (active && payload && payload.length) {
    const item = payload[0]
    const val = item.value
    const pct = totalSum > 0 ? ((val / totalSum) * 100).toFixed(1) : 0

    return (
      <div className="vis-tooltip-card">
        <div className="vis-tooltip-label">{item.name}</div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: item.payload?.fill || '#6366F1' }} />
          <span className="vis-tooltip-name">Value:</span>
          <span className="vis-tooltip-val">{formatValue(val, format)}</span>
        </div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-name" style={{ marginLeft: 16 }}>Share:</span>
          <span className="vis-tooltip-val">{pct}%</span>
        </div>
      </div>
    )
  }
  return null
}

export default function PieChartComponent({
  title,
  label_key,
  value_key,
  x_key,
  y_key,
  data = [],
  format = 'number',
  description
}) {
  const lKey = label_key || x_key
  const vKey = value_key || y_key

  if (!data || data.length === 0 || !lKey || !vKey) {
    return null
  }

  const totalSum = data.reduce((acc, curr) => acc + (Number(curr[vKey]) || 0), 0)

  return (
    <div className="vis-chart-card animate-fade-in">
      {title && (
        <div className="vis-chart-header">
          <div className="vis-chart-title">{title}</div>
          {description && <div className="vis-chart-desc">{description}</div>}
        </div>
      )}

      <div className="vis-chart-body" style={{ width: '100%', height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RechartsPie>
            <Pie
              data={data}
              dataKey={vKey}
              nameKey={lKey}
              cx="50%"
              cy="48%"
              innerRadius={55}
              outerRadius={88}
              paddingAngle={4}
            >
              {data.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  stroke="#fff"
                  strokeWidth={2}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip format={format} totalSum={totalSum} />} />
            <Legend
              verticalAlign="bottom"
              height={36}
              formatter={(value) => (
                <span style={{ color: '#4B5563', fontSize: '12px', fontWeight: 500 }}>
                  {truncateLabel(value, 15)}
                </span>
              )}
            />
          </RechartsPie>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

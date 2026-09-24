import { useId } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from 'recharts'
import { PRIMARY_SERIES, AXIS_TICK, AXIS_LINE, GRID_STROKE, formatValue, formatAxisNumber, truncateLabel, formatColumnHeader } from './formatters'

const CustomTooltip = ({ active, payload, label, format, yKey }) => {
  if (active && payload && payload.length) {
    const item = payload[0]
    return (
      <div className="vis-tooltip-card">
        <div className="vis-tooltip-label">{label}</div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: PRIMARY_SERIES }} />
          <span className="vis-tooltip-name">{formatColumnHeader(yKey)}:</span>
          <span className="vis-tooltip-val">{formatValue(item.value, format)}</span>
        </div>
      </div>
    )
  }
  return null
}

export default function LineChartComponent({
  title,
  x_key,
  y_key,
  data = [],
  format = 'number',
  description
}) {
  const gradId = `lineGrad-${useId().replace(/:/g, '')}`
  if (!data || data.length === 0 || !x_key || !y_key) {
    return null
  }

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
          <AreaChart data={data} margin={{ top: 12, right: 16, left: -10, bottom: 20 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={PRIMARY_SERIES} stopOpacity={0.18} />
                <stop offset="95%" stopColor={PRIMARY_SERIES} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={GRID_STROKE} />
            <XAxis
              dataKey={x_key}
              tickFormatter={(val) => truncateLabel(val, 12)}
              tick={AXIS_TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              interval={data.length > 8 ? 'preserveStartEnd' : 0}
              angle={data.length > 6 ? -25 : 0}
              textAnchor={data.length > 6 ? 'end' : 'middle'}
              height={data.length > 6 ? 35 : 25}
            />
            <YAxis
              tickFormatter={formatAxisNumber}
              tick={AXIS_TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
            />
            <Tooltip
              cursor={{ stroke: '#C4DFDD', strokeWidth: 1 }}
              content={<CustomTooltip format={format} yKey={y_key} />}
            />
            <Area
              type="monotone"
              dataKey={y_key}
              stroke={PRIMARY_SERIES}
              strokeWidth={2}
              fillOpacity={1}
              fill={`url(#${gradId})`}
              activeDot={{ r: 5, fill: PRIMARY_SERIES, stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

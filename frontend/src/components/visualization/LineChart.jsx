import React from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from 'recharts'
import { formatValue, formatAxisNumber, truncateLabel, formatColumnHeader } from './formatters'

const CustomTooltip = ({ active, payload, label, format, yKey }) => {
  if (active && payload && payload.length) {
    const item = payload[0]
    return (
      <div className="vis-tooltip-card">
        <div className="vis-tooltip-label">{label}</div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: '#6366F1' }} />
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
              <linearGradient id="lineColorGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366F1" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#6366F1" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(229, 231, 235, 0.6)" />
            <XAxis
              dataKey={x_key}
              tickFormatter={(val) => truncateLabel(val, 12)}
              tick={{ fill: '#6B7280', fontSize: 12 }}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={false}
              interval={data.length > 8 ? 'preserveStartEnd' : 0}
              angle={data.length > 6 ? -25 : 0}
              textAnchor={data.length > 6 ? 'end' : 'middle'}
              height={data.length > 6 ? 35 : 25}
            />
            <YAxis
              tickFormatter={formatAxisNumber}
              tick={{ fill: '#6B7280', fontSize: 12 }}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={false}
            />
            <Tooltip
              content={<CustomTooltip format={format} yKey={y_key} />}
            />
            <Area
              type="monotone"
              dataKey={y_key}
              stroke="#6366F1"
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#lineColorGrad)"
              activeDot={{ r: 6, fill: '#4F46E5', stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

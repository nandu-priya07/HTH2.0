import React from 'react'
import {
  ResponsiveContainer,
  BarChart as RechartsBar,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell
} from 'recharts'
import { CHART_COLORS, formatValue, formatAxisNumber, truncateLabel, formatColumnHeader } from './formatters'

const CustomTooltip = ({ active, payload, label, format, xKey, yKey, isHorizontal }) => {
  if (active && payload && payload.length) {
    const item = payload[0]
    const titleLabel = isHorizontal ? item.payload?.[xKey] : label
    const val = item.value

    return (
      <div className="vis-tooltip-card">
        <div className="vis-tooltip-label">{titleLabel}</div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: item.color || '#6366F1' }} />
          <span className="vis-tooltip-name">{formatColumnHeader(yKey)}:</span>
          <span className="vis-tooltip-val">{formatValue(val, format)}</span>
        </div>
      </div>
    )
  }
  return null
}

export default function BarChartComponent({
  title,
  x_key,
  y_key,
  data = [],
  orientation = 'vertical',
  format = 'number',
  description
}) {
  if (!data || data.length === 0 || !x_key || !y_key) {
    return null
  }

  const isHorizontal = orientation === 'horizontal'
  const chartHeight = isHorizontal ? Math.max(240, Math.min(400, data.length * 40 + 60)) : 280

  return (
    <div className="vis-chart-card animate-fade-in">
      {title && (
        <div className="vis-chart-header">
          <div className="vis-chart-title">{title}</div>
          {description && <div className="vis-chart-desc">{description}</div>}
        </div>
      )}

      <div className="vis-chart-body" style={{ width: '100%', height: chartHeight }}>
        <ResponsiveContainer width="100%" height="100%">
          {isHorizontal ? (
            <RechartsBar
              data={data}
              layout="vertical"
              margin={{ top: 10, right: 24, left: 10, bottom: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(229, 231, 235, 0.6)" />
              <XAxis
                type="number"
                tickFormatter={formatAxisNumber}
                tick={{ fill: '#6B7280', fontSize: 12 }}
                axisLine={{ stroke: '#E5E7EB' }}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey={x_key}
                tickFormatter={(val) => truncateLabel(val, 16)}
                tick={{ fill: '#4B5563', fontSize: 12, fontWeight: 500 }}
                axisLine={{ stroke: '#E5E7EB' }}
                tickLine={false}
                width={110}
              />
              <Tooltip
                content={<CustomTooltip format={format} xKey={x_key} yKey={y_key} isHorizontal={true} />}
              />
              <Bar dataKey={y_key} radius={[0, 6, 6, 0]} maxBarSize={28}>
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={CHART_COLORS[index % CHART_COLORS.length]}
                  />
                ))}
              </Bar>
            </RechartsBar>
          ) : (
            <RechartsBar
              data={data}
              layout="horizontal"
              margin={{ top: 10, right: 16, left: -10, bottom: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(229, 231, 235, 0.6)" />
              <XAxis
                dataKey={x_key}
                tickFormatter={(val) => truncateLabel(val, 14)}
                tick={{ fill: '#6B7280', fontSize: 12 }}
                axisLine={{ stroke: '#E5E7EB' }}
                tickLine={false}
                interval={0}
                angle={data.length > 5 ? -25 : 0}
                textAnchor={data.length > 5 ? 'end' : 'middle'}
                height={data.length > 5 ? 40 : 25}
              />
              <YAxis
                tickFormatter={formatAxisNumber}
                tick={{ fill: '#6B7280', fontSize: 12 }}
                axisLine={{ stroke: '#E5E7EB' }}
                tickLine={false}
              />
              <Tooltip
                content={<CustomTooltip format={format} xKey={x_key} yKey={y_key} isHorizontal={false} />}
              />
              <Bar dataKey={y_key} radius={[6, 6, 0, 0]} maxBarSize={42}>
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={CHART_COLORS[index % CHART_COLORS.length]}
                  />
                ))}
              </Bar>
            </RechartsBar>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}

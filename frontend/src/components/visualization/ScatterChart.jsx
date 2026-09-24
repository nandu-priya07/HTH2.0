import React from 'react'
import {
  ResponsiveContainer,
  ScatterChart as RechartsScatter,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from 'recharts'
import { formatValue, formatAxisNumber, formatColumnHeader } from './formatters'

const CustomTooltip = ({ active, payload, xKey, yKey, format }) => {
  if (active && payload && payload.length) {
    const dataPoint = payload[0].payload
    return (
      <div className="vis-tooltip-card">
        <div className="vis-tooltip-label">Point Data</div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: '#6366F1' }} />
          <span className="vis-tooltip-name">{formatColumnHeader(xKey)}:</span>
          <span className="vis-tooltip-val">{formatValue(dataPoint[xKey], 'number')}</span>
        </div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: '#3B82F6' }} />
          <span className="vis-tooltip-name">{formatColumnHeader(yKey)}:</span>
          <span className="vis-tooltip-val">{formatValue(dataPoint[yKey], format)}</span>
        </div>
      </div>
    )
  }
  return null
}

export default function ScatterChartComponent({
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
          <RechartsScatter margin={{ top: 12, right: 16, left: -10, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(229, 231, 235, 0.6)" />
            <XAxis
              type="number"
              dataKey={x_key}
              name={x_key}
              tickFormatter={formatAxisNumber}
              tick={{ fill: '#6B7280', fontSize: 12 }}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={false}
            />
            <YAxis
              type="number"
              dataKey={y_key}
              name={y_key}
              tickFormatter={formatAxisNumber}
              tick={{ fill: '#6B7280', fontSize: 12 }}
              axisLine={{ stroke: '#E5E7EB' }}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip xKey={x_key} yKey={y_key} format={format} />} />
            <Scatter
              name={title || 'Distribution'}
              data={data}
              fill="#6366F1"
              line={false}
            />
          </RechartsScatter>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

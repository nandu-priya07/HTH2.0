import {
  ResponsiveContainer,
  BarChart as RechartsBar,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  LabelList
} from 'recharts'
import { PRIMARY_SERIES, AXIS_TICK, AXIS_LINE, GRID_STROKE, formatValue, formatAxisNumber, truncateLabel, formatColumnHeader } from './formatters'

const CustomTooltip = ({ active, payload, label, format, xKey, yKey, isHorizontal }) => {
  if (active && payload && payload.length) {
    const item = payload[0]
    const titleLabel = isHorizontal ? item.payload?.[xKey] : label
    const val = item.value

    return (
      <div className="vis-tooltip-card">
        <div className="vis-tooltip-label">{titleLabel}</div>
        <div className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: PRIMARY_SERIES }} />
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
              margin={{ top: 10, right: 64, left: 10, bottom: 10 }}
            >
              <CartesianGrid horizontal={false} stroke={GRID_STROKE} />
              <XAxis
                type="number"
                tickFormatter={formatAxisNumber}
                tick={AXIS_TICK}
                axisLine={AXIS_LINE}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey={x_key}
                tickFormatter={(val) => truncateLabel(val, 16)}
                tick={{ ...AXIS_TICK, fill: '#102F35', fontWeight: 500 }}
                axisLine={AXIS_LINE}
                tickLine={false}
                width={110}
              />
              <Tooltip
                cursor={{ fill: 'rgba(9, 124, 135, 0.06)' }}
                content={<CustomTooltip format={format} xKey={x_key} yKey={y_key} isHorizontal={true} />}
              />
              <Bar dataKey={y_key} fill={PRIMARY_SERIES} radius={[0, 4, 4, 0]} maxBarSize={24}>
                {data.length <= 12 && (
                  <LabelList dataKey={y_key} position="right" formatter={(v) => formatValue(v, format)} style={{ fill: '#557177', fontSize: 11.5 }} />
                )}
              </Bar>
            </RechartsBar>
          ) : (
            <RechartsBar
              data={data}
              layout="horizontal"
              margin={{ top: 10, right: 16, left: -10, bottom: 20 }}
            >
              <CartesianGrid vertical={false} stroke={GRID_STROKE} />
              <XAxis
                dataKey={x_key}
                tickFormatter={(val) => truncateLabel(val, 14)}
                tick={AXIS_TICK}
                axisLine={AXIS_LINE}
                tickLine={false}
                interval={0}
                angle={data.length > 5 ? -25 : 0}
                textAnchor={data.length > 5 ? 'end' : 'middle'}
                height={data.length > 5 ? 40 : 25}
              />
              <YAxis
                tickFormatter={formatAxisNumber}
                tick={AXIS_TICK}
                axisLine={AXIS_LINE}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: 'rgba(9, 124, 135, 0.06)' }}
                content={<CustomTooltip format={format} xKey={x_key} yKey={y_key} isHorizontal={false} />}
              />
              <Bar dataKey={y_key} fill={PRIMARY_SERIES} radius={[4, 4, 0, 0]} maxBarSize={40} />
            </RechartsBar>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}

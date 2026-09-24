import React from 'react'
import { formatValue } from './formatters'
import { SparklesIcon } from '../Icons'

export default function MetricCard({
  title,
  value,
  format = 'number',
  description,
  aggregation,
  value_key
}) {
  const displayVal = formatValue(value, format)
  const isCurrency = format === 'currency'

  return (
    <div className="vis-kpi-card animate-fade-in">
      <div className="vis-kpi-top">
        <div className="vis-kpi-title-group">
          <div className="vis-kpi-icon-pill">
            <SparklesIcon size={14} />
          </div>
          <span className="vis-kpi-title">{title || 'Calculated Metric'}</span>
        </div>
        {aggregation && (
          <span className="vis-kpi-badge">{String(aggregation).toUpperCase()}</span>
        )}
      </div>

      <div className="vis-kpi-value-row">
        <span className="vis-kpi-number">{displayVal}</span>
        {isCurrency && <span className="vis-kpi-unit">USD</span>}
      </div>

      {description && (
        <div className="vis-kpi-footer">
          <span className="vis-kpi-dot"></span>
          <span>{description}</span>
        </div>
      )}
    </div>
  )
}

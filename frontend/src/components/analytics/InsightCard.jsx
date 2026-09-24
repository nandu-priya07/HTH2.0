import { useState } from 'react'
import { Sparkline, MiniBars } from './MiniCharts'
import EvidencePanel from './EvidencePanel'
import { TrendingUpIcon, AlertTriangleIcon, ChevronDownIcon, CheckCircleIcon } from '../ui/Icons'

const DIRECTION = {
  up: { cls: 'status-good', icon: TrendingUpIcon },
  alert: { cls: 'status-bad', icon: AlertTriangleIcon },
  warn: { cls: 'status-warn', icon: AlertTriangleIcon },
  good: { cls: 'status-good', icon: CheckCircleIcon },
  flat: { cls: 'status-info', icon: null }
}

export default function InsightCard({ insight }) {
  const [showEvidence, setShowEvidence] = useState(false)
  if (!insight) return null

  const d = DIRECTION[insight.direction] || DIRECTION.flat
  const Icon = d.icon
  const hasData = Array.isArray(insight.data) && insight.data.length > 0
  const maxIdx = hasData ? insight.data.indexOf(Math.max(...insight.data)) : undefined

  return (
    <article className="card card-hover insight-card">
      <div className="insight-top">
        <h3 className="insight-title">{insight.title}</h3>
        {insight.change && (
          <span className={`status ${d.cls}`}>
            {Icon && <Icon size={12} />}
            {insight.change}
          </span>
        )}
      </div>

      <div className="insight-metric">
        {typeof insight.metric === 'number'
          ? insight.metric.toLocaleString(undefined, { maximumFractionDigits: 2 })
          : insight.metric}
      </div>

      {insight.explanation && (
        <p className="insight-explanation">{insight.explanation}</p>
      )}

      {hasData && (
        <div className="insight-visual">
          {insight.visual === 'bars' ? (
            <MiniBars
              data={insight.data}
              labels={insight.labels}
              height={56}
              highlight={maxIdx}
            />
          ) : (
            <Sparkline
              data={insight.data}
              height={56}
              label={insight.title}
              highlightIndex={insight.direction === 'alert' ? maxIdx : undefined}
            />
          )}
        </div>
      )}

      {insight.evidence && (
        <>
          <button
            type="button"
            className="insight-evidence-btn"
            aria-expanded={showEvidence}
            onClick={() => setShowEvidence((v) => !v)}
          >
            Evidence <ChevronDownIcon size={14} className={showEvidence ? 'rot-180' : ''} />
          </button>
          {showEvidence && <EvidencePanel compact evidence={insight.evidence} />}
        </>
      )}
    </article>
  )
}

import { useState } from 'react'
import { MiniBars } from './MiniCharts'
import EvidencePanel from './EvidencePanel'
import { TrendingUpIcon, AlertTriangleIcon, ChevronDownIcon } from '../ui/Icons'

const DIRECTION = {
  up: { cls: 'status-good', icon: TrendingUpIcon },
  alert: { cls: 'status-bad', icon: AlertTriangleIcon },
  flat: { cls: 'status-info', icon: null }
}

export default function ComparisonInsightCard({
  title,
  metric,
  change,
  direction = 'up',
  explanation,
  data = [],
  labels = [],
  evidence
}) {
  const [showEvidence, setShowEvidence] = useState(false)
  const d = DIRECTION[direction] || DIRECTION.flat
  const Icon = d.icon

  return (
    <article className="card card-hover insight-card">
      <div className="insight-top">
        <h3 className="insight-title">{title}</h3>
        {change && (
          <span className={`status ${d.cls}`}>
            {Icon && <Icon size={12} />}
            {change}
          </span>
        )}
      </div>
      <div className="insight-metric">{metric}</div>
      <p className="insight-explanation">{explanation}</p>

      {data.length > 0 && (
        <div className="insight-visual">
          <MiniBars
            data={data}
            labels={labels.map((l) => String(l).slice(0, 10))}
            height={56}
            highlight={0}
          />
        </div>
      )}

      {evidence && (
        <>
          <button
            type="button"
            className="insight-evidence-btn"
            aria-expanded={showEvidence}
            onClick={() => setShowEvidence((v) => !v)}
          >
            Evidence <ChevronDownIcon size={14} className={showEvidence ? 'rot-180' : ''} />
          </button>
          {showEvidence && <EvidencePanel compact evidence={evidence} />}
        </>
      )}
    </article>
  )
}

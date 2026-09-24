import { useState } from 'react'
import { Sparkline } from './MiniCharts'
import EvidencePanel from './EvidencePanel'
import { AlertTriangleIcon, ChevronDownIcon } from '../ui/Icons'

export default function AnomalyInsightCard({
  title = 'Potential Anomaly',
  metric,
  change = 'Review',
  explanation,
  data = [],
  evidence
}) {
  const [showEvidence, setShowEvidence] = useState(false)

  return (
    <article className="card card-hover insight-card">
      <div className="insight-top">
        <h3 className="insight-title">{title}</h3>
        <span className="status status-bad">
          <AlertTriangleIcon size={12} />
          {change}
        </span>
      </div>
      <div className="insight-metric">{metric}</div>
      <p className="insight-explanation">{explanation}</p>

      {data.length > 0 && (
        <div className="insight-visual">
          <Sparkline
            data={data}
            height={56}
            label={title}
            highlightIndex={data.indexOf(Math.max(...data))}
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

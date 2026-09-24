import { useState } from 'react'
import { MiniBars } from './MiniCharts'
import EvidencePanel from './EvidencePanel'
import { ChevronDownIcon } from '../ui/Icons'

export default function DistributionInsightCard({
  title,
  metric,
  change,
  explanation,
  data = [],
  labels = [],
  evidence
}) {
  const [showEvidence, setShowEvidence] = useState(false)

  return (
    <article className="card card-hover insight-card">
      <div className="insight-top">
        <h3 className="insight-title">{title}</h3>
        {change && <span className="status status-info">{change}</span>}
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

import { useState } from 'react'
import EvidencePanel from './EvidencePanel'
import { ChevronDownIcon, TrendingUpIcon } from '../ui/Icons'

const fmt = (v) => {
  if (v === null || v === undefined) return '—'
  const num = Number(v)
  if (!Number.isFinite(num)) return String(v)
  if (Math.abs(num) >= 1_000_000) return `${(num / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 })}M`
  if (Math.abs(num) >= 1_000) return num.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return num.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function MetricInsightCard({
  title,
  value,
  mean,
  median,
  min,
  max,
  std,
  count,
  explanation,
  evidence
}) {
  const [showEvidence, setShowEvidence] = useState(false)

  return (
    <article className="card card-hover card-pad insight-card">
      <div className="section-label">{title}</div>
      <div className="insight-metric">{fmt(value)}</div>
      <p className="insight-explanation">
        {explanation || `Mean ${fmt(mean)} · range ${fmt(min)} – ${fmt(max)}`}
      </p>

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

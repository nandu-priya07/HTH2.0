import { useState } from 'react'
import { MiniBars } from './MiniCharts'
import EvidencePanel from './EvidencePanel'
import { ChevronDownIcon } from '../ui/Icons'

export default function CategoryInsightCard({
  title,
  value,
  count,
  totalRows,
  percentage,
  distribution = [],
  labels = [],
  explanation,
  evidence
}) {
  const [showEvidence, setShowEvidence] = useState(false)

  const chartData = distribution.map((d) => (typeof d === 'number' ? d : d.value))
  const chartLabels = labels.length ? labels : distribution.map((d) => (typeof d === 'object' ? String(d.label) : ''))

  return (
    <article className="card card-hover card-pad insight-card">
      <div className="section-label">{title}</div>
      <div className="insight-metric">{String(value)}</div>
      <p className="insight-explanation">
        {explanation || (count && totalRows ? `${Number(count).toLocaleString()} of ${Number(totalRows).toLocaleString()} rows (${percentage}%)` : '')}
      </p>

      {chartData.length > 0 && (
        <div className="insight-visual">
          <MiniBars
            data={chartData}
            labels={chartLabels.map((l) => l.slice(0, 10))}
            height={44}
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

import { useState } from 'react'
import { Sparkline, MiniBars } from './MiniCharts'
import EvidencePanel from './EvidencePanel'
import { TrendingUpIcon, AlertTriangleIcon, ChevronDownIcon } from '../ui/Icons'

const DIRECTION = {
  up: { cls: 'status-good', icon: TrendingUpIcon },
  alert: { cls: 'status-bad', icon: AlertTriangleIcon },
  flat: { cls: 'status-info', icon: null }
}

export default function InsightCard({ insight }) {
  const [showEvidence, setShowEvidence] = useState(false)
  const d = DIRECTION[insight.direction] || DIRECTION.flat
  const Icon = d.icon
  return (
    <article className="card card-hover insight-card">
      <div className="insight-top">
        <h3 className="insight-title">{insight.title}</h3>
        <span className={`status ${d.cls}`}>{Icon && <Icon size={12} />}{insight.change}</span>
      </div>
      <div className="insight-metric">{insight.metric}</div>
      <p className="insight-explanation">{insight.explanation}</p>
      <div className="insight-visual">
        {insight.visual === 'bars'
          ? <MiniBars data={insight.data} labels={insight.labels} height={56} highlight={insight.data.indexOf(Math.max(...insight.data))} />
          : <Sparkline data={insight.data} height={56} label={insight.title} highlightIndex={insight.direction === 'alert' ? insight.data.indexOf(Math.max(...insight.data)) : undefined} />}
      </div>
      <button type="button" className="insight-evidence-btn" aria-expanded={showEvidence} onClick={() => setShowEvidence((v) => !v)}>
        Evidence <ChevronDownIcon size={14} className={showEvidence ? 'rot-180' : ''} />
      </button>
      {showEvidence && <EvidencePanel compact evidence={insight.evidence} />}
    </article>
  )
}

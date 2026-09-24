import { CheckCircleIcon, AlertCircleIcon, AlertTriangleIcon } from '../ui/Icons'

const tier = (score) => (score >= 0.95 ? 'good' : score >= 0.8 ? 'warn' : 'bad')
const TIER_ICON = { good: CheckCircleIcon, warn: AlertCircleIcon, bad: AlertTriangleIcon }
const TIER_LABEL = { good: 'Good', warn: 'Review', bad: 'Poor' }

/** quality: result of lib/dataset.computeDataQuality() */
export default function DataQualityPanel({ quality }) {
  if (!quality) {
    return (
      <section className="card card-pad">
        <h3 className="card-title">Data Quality</h3>
        <p className="card-subtitle" style={{ marginTop: 8 }}>Quality metrics will appear once a dataset profile is available.</p>
      </section>
    )
  }
  const overall = tier(quality.score / 100)
  return (
    <section className="card card-pad quality-card" aria-labelledby="quality-title">
      <div className="quality-head">
        <div className="quality-ring" style={{ '--pct': quality.score }} role="img" aria-label={`Data quality score ${quality.score}%`}>
          <span>{quality.score}%</span>
        </div>
        <div>
          <h3 id="quality-title" className="card-title">Data Quality</h3>
          <p className="card-subtitle">Computed from the backend profile and cleaning report.</p>
          <span className={`status status-${overall}`} style={{ marginTop: 8 }}>
            {(() => { const I = TIER_ICON[overall]; return <I size={12} /> })()}
            {TIER_LABEL[overall]}
          </span>
        </div>
      </div>
      <ul className="quality-list">
        {quality.metrics.map((m) => {
          const t = tier(m.score)
          const Icon = TIER_ICON[t]
          return (
            <li key={m.key}>
              <div className="quality-row">
                <span className="quality-name"><Icon size={14} className={`tone-${t}`} />{m.label}</span>
                <span className="quality-score">{Math.round(m.score * 100)}%</span>
              </div>
              <div className="quality-bar"><span className={`tone-bg-${t}`} style={{ width: `${m.score * 100}%` }} /></div>
              <div className="quality-detail">{m.detail}</div>
            </li>
          )
        })}
      </ul>
      {quality.warnings?.length > 0 && (
        <details className="quality-warnings">
          <summary>{quality.warnings.length} cleaning warning{quality.warnings.length > 1 ? 's' : ''}</summary>
          <ul>
            {quality.warnings.map((w, i) => <li key={i}><span className="mono">{w.column}</span> — {w.issue}</li>)}
          </ul>
        </details>
      )}
    </section>
  )
}

import { useState } from 'react'
import { AlertTriangleIcon, AlertCircleIcon, CheckCircleIcon, ShieldCheckIcon, ChevronDownIcon } from '../ui/Icons'
import EvidencePanel from './EvidencePanel'

const SEVERITY = {
  High: { cls: 'status-bad', icon: AlertTriangleIcon },
  Medium: { cls: 'status-warn', icon: AlertCircleIcon },
  Low: { cls: 'status-info', icon: CheckCircleIcon }
}

/**
 * Dynamic Anomaly Table.
 * Renders real outlier records from the uploaded dataset or an intentional
 * clean state if no statistical anomalies were detected.
 */
export default function AnomalyTable({
  anomalies = [],
  total,
  badge,
  evidence,
  metricName
}) {
  const [showEvidence, setShowEvidence] = useState(false)
  const count = total ?? anomalies.length

  if (!anomalies || anomalies.length === 0) {
    return (
      <section className="card anomaly-card" aria-labelledby="anomaly-title" style={{ padding: '24px' }}>
        <header className="card-header" style={{ padding: 0, marginBottom: '16px' }}>
          <div>
            <h3 id="anomaly-title" className="card-title">Anomalies & Outliers</h3>
            <p className="card-subtitle">
              Statistical outlier analysis across numeric measures
            </p>
          </div>
          {badge}
        </header>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '14px',
          padding: '16px 20px',
          borderRadius: 'var(--radius-md)',
          background: 'var(--color-surface-2)',
          border: '1px solid var(--color-border)'
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: 'var(--teal-50)',
            color: 'var(--color-primary)',
            flexShrink: 0
          }}>
            <CheckCircleIcon size={20} />
          </div>
          <div>
            <div style={{ fontWeight: 'var(--weight-semibold)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
              No statistical anomalies detected
            </div>
            <div style={{ fontSize: '13px', color: 'var(--color-text-2)', marginTop: '2px' }}>
              All analyzed values fall within expected standard distribution boundaries (1.5 × IQR fences). No extreme outliers found.
            </div>
          </div>
        </div>

        {evidence && (
          <div style={{ marginTop: '14px' }}>
            <button
              type="button"
              className="insight-evidence-btn"
              aria-expanded={showEvidence}
              onClick={() => setShowEvidence((v) => !v)}
            >
              Evidence <ChevronDownIcon size={14} className={showEvidence ? 'rot-180' : ''} />
            </button>
            {showEvidence && <EvidencePanel compact evidence={evidence} />}
          </div>
        )}
      </section>
    )
  }

  return (
    <section className="card anomaly-card" aria-labelledby="anomaly-title">
      <header className="card-header" style={{ padding: '20px 24px 0' }}>
        <div>
          <h3 id="anomaly-title" className="card-title">Anomalies Detected</h3>
          <p className="card-subtitle">
            {count.toLocaleString()} unusual record{count === 1 ? '' : 's'} flagged for review{metricName ? ` in ${metricName}` : ''}
          </p>
        </div>
        {badge}
      </header>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Record</th>
              <th>Reason</th>
              <th>Severity</th>
              <th className="num">Value</th>
            </tr>
          </thead>
          <tbody>
            {anomalies.map((a, idx) => {
              const s = SEVERITY[a.severity] || SEVERITY.Low
              const Icon = s.icon
              const key = a.record ? `${a.record}-${idx}` : `row-${idx}`
              return (
                <tr key={key}>
                  <td className="mono" style={{ whiteSpace: 'nowrap' }}>{a.record}</td>
                  <td>{a.reason}</td>
                  <td>
                    <span className={`status ${s.cls}`}>
                      <Icon size={12} />
                      {a.severity}
                    </span>
                  </td>
                  <td className="num mono">{typeof a.value === 'number' ? a.value.toLocaleString() : a.value}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {evidence && (
        <div style={{ padding: '12px 24px 20px' }}>
          <button
            type="button"
            className="insight-evidence-btn"
            aria-expanded={showEvidence}
            onClick={() => setShowEvidence((v) => !v)}
          >
            Evidence <ChevronDownIcon size={14} className={showEvidence ? 'rot-180' : ''} />
          </button>
          {showEvidence && <EvidencePanel compact evidence={evidence} />}
        </div>
      )}
    </section>
  )
}

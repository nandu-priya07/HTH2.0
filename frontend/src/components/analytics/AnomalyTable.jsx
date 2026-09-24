import { AlertTriangleIcon, AlertCircleIcon, CheckCircleIcon } from '../ui/Icons'

const SEVERITY = {
  High: { cls: 'status-bad', icon: AlertTriangleIcon },
  Medium: { cls: 'status-warn', icon: AlertCircleIcon },
  Low: { cls: 'status-info', icon: CheckCircleIcon }
}

/** Anomaly list. `anomalies`: [{ record, reason, severity: 'High'|'Medium'|'Low', value }] */
export default function AnomalyTable({ anomalies = [], total, badge }) {
  return (
    <section className="card anomaly-card" aria-labelledby="anomaly-title">
      <header className="card-header" style={{ padding: '20px 24px 0' }}>
        <div>
          <h3 id="anomaly-title" className="card-title">Anomalies Detected</h3>
          <p className="card-subtitle">{(total ?? anomalies.length).toLocaleString()} unusual records flagged for review</p>
        </div>
        {badge}
      </header>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>Record</th><th>Reason</th><th>Severity</th><th className="num">Value</th></tr>
          </thead>
          <tbody>
            {anomalies.map((a) => {
              const s = SEVERITY[a.severity] || SEVERITY.Low
              const Icon = s.icon
              return (
                <tr key={a.record}>
                  <td className="mono">{a.record}</td>
                  <td>{a.reason}</td>
                  <td><span className={`status ${s.cls}`}><Icon size={12} />{a.severity}</span></td>
                  <td className="num mono">{a.value}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

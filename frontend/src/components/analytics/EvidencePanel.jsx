import { ShieldCheckIcon } from '../ui/Icons'

/**
 * Evidence summary. Accepts the `evidence` object from lib/explain or any
 * object with the same keys — backends can populate it directly later.
 */
export default function EvidencePanel({ evidence, compact = false }) {
  if (!evidence) return null
  const rows = [
    ['Metric', evidence.metric],
    ['Fields Used', evidence.fields?.length ? evidence.fields.join(', ') : null],
    ['Rows', evidence.rows !== undefined && evidence.rows !== null
      ? `${Number(evidence.rows).toLocaleString()}${evidence.filteredRows !== undefined && evidence.filteredRows !== evidence.rows ? ` → ${Number(evidence.filteredRows).toLocaleString()} after filters` : ''}`
      : null],
    ['Filters', evidence.filters?.length ? evidence.filters.join(' · ') : 'None'],
    ['Transformation', evidence.transformation],
    ['Aggregation', evidence.aggregation],
    ['Sort', evidence.sort],
    ['Limit', evidence.limit]
  ].filter(([, v]) => v !== null && v !== undefined && v !== '')

  return (
    <section className={`evidence${compact ? ' is-compact' : ''}`} aria-label="Evidence">
      <div className="evidence-head">
        <ShieldCheckIcon size={14} />
        <span>Evidence</span>
      </div>
      <dl className="evidence-grid">
        {rows.map(([k, v]) => (
          <div key={k} className="evidence-item">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

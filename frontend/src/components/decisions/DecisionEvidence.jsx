import { ShieldCheckIcon } from '../ui/Icons'

/**
 * Reusable Decision Evidence Component.
 * Displays calculation, row counts, filters, and field aggregations.
 */
export default function DecisionEvidence({ evidence = [] }) {
  if (!evidence || evidence.length === 0) return null

  return (
    <div className="decision-evidence-wrap">
      <div className="section-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
        <ShieldCheckIcon size={12} /> Evidence
      </div>
      <ul className="decision-evidence" style={{ margin: '8px 0 0', padding: 0, listStyle: 'none' }}>
        {evidence.map((item, idx) => (
          <li
            key={idx}
            className="mono"
            style={{
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
              fontSize: '12px',
              padding: '6px 10px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-surface)',
              border: 'var(--border)',
              marginBottom: '6px'
            }}
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

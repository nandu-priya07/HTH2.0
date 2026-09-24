import { TargetIcon } from '../ui/Icons'
import DecisionMetric from './DecisionMetric'
import DecisionEvidence from './DecisionEvidence'
import SupportingAnalysis from './SupportingAnalysis'

/**
 * Reusable Decision Finding Card.
 * Desktop: 2-column layout (Finding + Metrics on left, Evidence + Analysis on right).
 * Tablet/Mobile: Stacks cleanly without horizontal scrollbars or fixed-width blowout.
 */
export default function DecisionFindingCard({
  finding,
  metrics = [],
  evidence = [],
  analysis,
  type,
  badge
}) {
  return (
    <article className="card decision-entry" style={{ width: '100%', maxWidth: '100%' }}>
      {/* Left Column: Finding Statement & Supporting Metric Tiles */}
      <div className="decision-entry-main" style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div className="section-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <TargetIcon size={12} /> Finding
          </div>
          {badge}
        </div>

        <p
          className="decision-finding"
          style={{
            overflowWrap: 'anywhere',
            wordBreak: 'break-word',
            margin: '10px 0 0',
            fontSize: 'var(--text-xl)',
            fontWeight: 'var(--weight-bold)',
            lineHeight: 1.35
          }}
        >
          {finding}
        </p>

        {metrics && metrics.length > 0 && (
          <div
            className="decision-metrics"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              gap: 'var(--space-3)',
              marginTop: 'var(--space-5)'
            }}
          >
            {metrics.map((m, idx) => (
              <DecisionMetric
                key={`${m.label}-${idx}`}
                label={m.label}
                value={m.value}
                hint={m.hint}
                tone={m.tone}
              />
            ))}
          </div>
        )}
      </div>

      {/* Right Column: Evidence & Supporting Analysis */}
      <aside className="decision-entry-side" style={{ minWidth: 0 }}>
        <DecisionEvidence evidence={evidence} />
        <SupportingAnalysis analysis={analysis} />
      </aside>
    </article>
  )
}

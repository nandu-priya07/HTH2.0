/**
 * Reusable Decision Metric Tile.
 * Displays primary comparison, baseline, or variance metrics.
 */
export default function DecisionMetric({ label, value, hint, tone }) {
  return (
    <div className={`stat-tile${tone ? ` tone-${tone}` : ''}`}>
      <div className="stat-tile-label" style={{ overflowWrap: 'anywhere' }}>{label}</div>
      <div className="stat-tile-value" style={{ overflowWrap: 'anywhere' }}>{value}</div>
      {hint && <div className="stat-tile-hint">{hint}</div>}
    </div>
  )
}

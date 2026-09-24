/**
 * Reusable Supporting Analysis Component.
 * Displays the analytical methodology behind the decision finding.
 */
export default function SupportingAnalysis({ analysis }) {
  if (!analysis) return null

  return (
    <div className="decision-analysis-wrap" style={{ marginTop: '16px' }}>
      <div className="section-label" style={{ marginBottom: '6px' }}>Supporting analysis</div>
      <p className="muted" style={{ margin: 0, fontSize: '13px', lineHeight: 1.5, overflowWrap: 'anywhere' }}>
        {analysis}
      </p>
    </div>
  )
}

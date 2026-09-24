import { useAnalyst } from '../state/analystContext'
import useDatasetDecisions from '../state/useDatasetDecisions'
import DecisionFindingCard from '../components/decisions/DecisionFindingCard'
import { Link, EmptyState } from '../components/ui/primitives'
import { DatabaseIcon, UploadIcon, ArrowRightIcon, SparklesIcon, AlertCircleIcon } from '../components/ui/Icons'

export default function DecisionsPage() {
  const { activeDataset } = useAnalyst()
  const {
    loading,
    decisions,
    stats,
    profile,
    hasDecisions
  } = useDatasetDecisions(activeDataset)

  // Empty State: No active dataset uploaded
  if (!activeDataset) {
    return (
      <div className="page">
        <div className="container">
          <header className="page-header">
            <div>
              <div className="eyebrow">Decisions</div>
              <h1>Findings you can act on</h1>
              <p>
                A decision log built from analyses. Each entry pairs a finding with its evidence and supporting metrics —
                no recommendation is shown without the analysis behind it.
              </p>
            </div>
          </header>

          <div className="card" style={{ padding: '60px 24px', textAlign: 'center' }}>
            <EmptyState
              icon={<DatabaseIcon size={24} />}
              title="No dataset connected"
              actions={
                <Link to="/upload" className="btn btn-primary btn-sm">
                  <UploadIcon size={14} /> Upload dataset
                </Link>
              }
            >
              Upload a dataset to evaluate group comparisons, contribution concentration, and evidence-backed decision findings.
            </EmptyState>
          </div>
        </div>
      </div>
    )
  }

  // Loading State: Calculating decision findings
  if (loading) {
    return (
      <div className="page">
        <div className="container">
          <header className="page-header">
            <div>
              <div className="eyebrow">Decisions</div>
              <h1>Findings you can act on</h1>
              <p>Evaluating dataset structure, cross-tabulations, and performance benchmarks...</p>
            </div>
            {stats && (
              <span className="tag tag-teal">
                <DatabaseIcon size={12} /> {stats.name}
              </span>
            )}
          </header>

          <div className="card" style={{ padding: '64px 24px', textAlign: 'center' }}>
            <div className="pulse-dots" style={{ marginBottom: '16px' }}>
              <span /><span /><span />
            </div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--color-text)' }}>
              Evaluating decision findings for {stats?.name || 'dataset'}...
            </h3>
            <p className="muted" style={{ marginTop: '8px', maxWidth: '480px', marginInline: 'auto', fontSize: '13.5px' }}>
              Discovering significant group divergences, volume concentrations, time patterns, and distribution anomalies.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="container">
        {/* Page Header */}
        <header className="page-header">
          <div>
            <div className="eyebrow">Decisions</div>
            <h1>Findings you can act on</h1>
            <p>
              A decision log built from analyses. Each entry pairs a finding with its evidence and supporting metrics —
              no recommendation is shown without the analysis behind it.
            </p>
          </div>
          {stats && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span className="tag tag-teal">
                <DatabaseIcon size={12} /> {stats.name}
              </span>
              <span className="tag tag-neutral">
                {Number(profile?.rowCount || stats.rows).toLocaleString()} rows · {profile?.columnCount || stats.cols} columns
              </span>
            </div>
          )}
        </header>

        {/* Dynamic Decision Entries List */}
        {hasDecisions ? (
          <div className="decision-list" style={{ display: 'grid', gap: 'var(--space-5)' }}>
            {decisions.map((d) => (
              <DecisionFindingCard
                key={d.id}
                finding={d.finding}
                metrics={d.metrics}
                evidence={d.evidence}
                analysis={d.analysis}
                type={d.type}
                badge={
                  <span className="tag tag-teal" style={{ fontSize: '11px' }}>
                    <SparklesIcon size={11} /> Evidence-backed
                  </span>
                }
              />
            ))}
          </div>
        ) : (
          <div className="card" style={{ padding: '48px 24px', textAlign: 'center' }}>
            <div style={{ display: 'inline-flex', padding: '12px', borderRadius: '50%', background: 'var(--color-surface-2)', marginBottom: '12px' }}>
              <AlertCircleIcon size={22} className="muted" />
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>No decision-level findings detected yet</h3>
            <p className="muted" style={{ fontSize: '13.5px', marginTop: '6px', maxWidth: '480px', marginInline: 'auto' }}>
              Your dataset does not currently contain enough variation, grouping, or time-based evidence to generate a supported decision finding.
            </p>
          </div>
        )}

        {/* Contextual Bottom CTA to Ask AI */}
        <div className="card card-pad decision-cta" style={{ marginTop: 'var(--space-8)' }}>
          <div>
            <h3 className="card-title">Run a decision analysis on your own data</h3>
            <p className="card-subtitle">
              Ask a “should we…” or “how much would…” question in Ask AI. When the query processor detects a decision intent on {stats?.name || 'your dataset'}, it models factors, scenarios, boundaries, and counter-tests.
            </p>
          </div>
          <Link to="/ask-ai" className="btn btn-primary" style={{ whiteSpace: 'nowrap' }}>
            Open Ask AI <ArrowRightIcon size={16} />
          </Link>
        </div>
      </div>
    </div>
  )
}

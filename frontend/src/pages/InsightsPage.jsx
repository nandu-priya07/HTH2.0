import { useAnalyst } from '../state/analystContext'
import useDatasetAnalysis from '../state/useDatasetAnalysis'
import MetricInsightCard from '../components/analytics/MetricInsightCard'
import CategoryInsightCard from '../components/analytics/CategoryInsightCard'
import ComparisonInsightCard from '../components/analytics/ComparisonInsightCard'
import TrendInsightCard from '../components/analytics/TrendInsightCard'
import AnomalyInsightCard from '../components/analytics/AnomalyInsightCard'
import DistributionInsightCard from '../components/analytics/DistributionInsightCard'
import InsightCard from '../components/analytics/InsightCard'
import AnomalyTable from '../components/analytics/AnomalyTable'
import { Link, EmptyState } from '../components/ui/primitives'
import { DatabaseIcon, UploadIcon, SparklesIcon, AlertCircleIcon } from '../components/ui/Icons'

export default function InsightsPage() {
  const { activeDataset } = useAnalyst()
  const {
    loading,
    error,
    profile,
    metrics,
    categories,
    automatedInsights,
    anomalies,
    anomalyEvidence,
    stats,
    hasData
  } = useDatasetAnalysis(activeDataset)

  // Empty state: no dataset uploaded or active
  if (!activeDataset) {
    return (
      <div className="page">
        <div className="container">
          <header className="page-header">
            <div>
              <div className="eyebrow">Insights</div>
              <h1>What stands out in your data</h1>
              <p>Upload a CSV, Excel, or tabular document to discover dynamic metrics, trends, and anomalies.</p>
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
              Upload a file to automatically profile its schema and generate real-time analytical insights.
            </EmptyState>
          </div>
        </div>
      </div>
    )
  }

  // Loading state when dataset changes or initial analysis runs
  if (loading) {
    return (
      <div className="page">
        <div className="container">
          <header className="page-header">
            <div>
              <div className="eyebrow">Insights</div>
              <h1>What stands out in your data</h1>
              <p>Analyzing dataset structure, calculating distributions, and detecting patterns...</p>
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
              Profiling {stats?.name || 'dataset'}...
            </h3>
            <p className="muted" style={{ marginTop: '8px', maxWidth: '460px', marginInline: 'auto', fontSize: '13.5px' }}>
              Computing summary statistics, category distributions, time trends, and outlier boundaries directly from your uploaded data.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Determine column availability for intentional messaging
  const hasNumeric = profile?.hasNumeric
  const hasCategorical = profile?.hasCategorical
  const hasDate = profile?.hasDate
  const totalRows = profile?.rowCount || stats?.rows || 0

  return (
    <div className="page">
      <div className="container">
        {/* Page Header */}
        <header className="page-header">
          <div>
            <div className="eyebrow">Insights</div>
            <h1>What stands out in your data</h1>
            <p>Each insight states the metric, the change, why it matters, and the evidence behind it.</p>
          </div>
          {stats && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span className="tag tag-teal">
                <DatabaseIcon size={12} /> {stats.name}
              </span>
              <span className="tag tag-neutral">
                {Number(totalRows).toLocaleString()} rows · {profile?.columnCount || stats.cols} columns
              </span>
            </div>
          )}
        </header>

        {/* Section 1: Measures & Dimensions From Your Dataset */}
        <section className="page-section" aria-labelledby="profile-title">
          <div className="page-section-head">
            <div>
              <h2 id="profile-title" className="card-title">From your dataset</h2>
              <p className="card-subtitle" style={{ marginTop: '2px' }}>
                Summary metrics and distributions calculated directly from {stats?.name || 'uploaded file'}
              </p>
            </div>
          </div>

          {/* Cards Grid */}
          {hasData ? (
            <div className="grid grid-4" style={{ gap: '16px' }}>
              {/* Numeric Metric Cards */}
              {metrics.slice(0, 4).map((m) => (
                <MetricInsightCard
                  key={`metric-${m.name}`}
                  title={`Total · ${m.label}`}
                  value={m.sum}
                  mean={m.mean}
                  min={m.min}
                  max={m.max}
                  count={m.count}
                  metricName={m.label}
                  evidence={m.evidence}
                />
              ))}

              {/* Categorical Distribution Cards */}
              {categories.slice(0, 4).map((c) => (
                <CategoryInsightCard
                  key={`cat-${c.name}`}
                  columnName={c.label}
                  mostFrequent={c.mostFrequent}
                  mostFrequentCount={c.mostFrequentCount}
                  totalRows={totalRows}
                  share={c.share}
                  topValues={c.topValues}
                  evidence={c.evidence}
                />
              ))}
            </div>
          ) : (
            <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
              <p className="muted">The profile for this dataset has no numeric or categorical summaries to display.</p>
            </div>
          )}

          {/* Empty / Limited Data Notes for Section 1 */}
          {!hasNumeric && hasCategorical && (
            <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--color-text-2)' }}>
              Note: No numeric measures detected in this dataset. Displaying categorical distributions only.
            </div>
          )}
          {hasNumeric && !hasCategorical && (
            <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--color-text-2)' }}>
              Note: No categorical dimensions detected in this dataset. Displaying numerical metrics only.
            </div>
          )}
        </section>

        {/* Section 2: Automated Insights */}
        <section className="page-section" aria-labelledby="auto-title">
          <div className="page-section-head">
            <div>
              <h2 id="auto-title" className="card-title">Automated insights</h2>
              <p className="card-subtitle" style={{ marginTop: '2px' }}>
                Cross-column comparisons, rankings, time trends, and concentration analysis
              </p>
            </div>
            <span className="tag tag-teal">
              <SparklesIcon size={12} /> Live Engine
            </span>
          </div>

          {automatedInsights.length > 0 ? (
            <div className="grid grid-3" style={{ gap: '16px' }}>
              {automatedInsights.map((insight) => {
                if (insight.type === 'trend') {
                  return (
                    <TrendInsightCard
                      key={insight.id}
                      title={insight.title}
                      metric={insight.metric}
                      change={insight.change}
                      direction={insight.direction}
                      explanation={insight.explanation}
                      data={insight.data}
                      labels={insight.labels}
                      peakPeriod={insight.peakPeriod}
                      evidence={insight.evidence}
                    />
                  )
                }

                if (insight.type === 'comparison') {
                  return (
                    <ComparisonInsightCard
                      key={insight.id}
                      title={insight.title}
                      metric={insight.metric}
                      change={insight.change}
                      direction={insight.direction}
                      explanation={insight.explanation}
                      categories={insight.categories || insight.labels}
                      values={insight.values || insight.data}
                      evidence={insight.evidence}
                    />
                  )
                }

                if (insight.type === 'distribution') {
                  return (
                    <DistributionInsightCard
                      key={insight.id}
                      title={insight.title}
                      columnName={insight.columnName || insight.title}
                      data={insight.data}
                      labels={insight.labels}
                      explanation={insight.explanation}
                      evidence={insight.evidence}
                    />
                  )
                }

                if (insight.type === 'anomaly') {
                  return (
                    <AnomalyInsightCard
                      key={insight.id}
                      title={insight.title}
                      count={insight.count}
                      metric={insight.metric}
                      change={insight.change}
                      explanation={insight.explanation}
                      anomalies={insight.anomalies}
                      data={insight.data}
                      evidence={insight.evidence}
                    />
                  )
                }

                // Default polymorphic InsightCard
                return <InsightCard key={insight.id} insight={insight} />
              })}
            </div>
          ) : (
            <div className="card" style={{ padding: '32px 24px', textAlign: 'center' }}>
              <div style={{ display: 'inline-flex', padding: '10px', borderRadius: '50%', background: 'var(--color-surface-2)', marginBottom: '8px' }}>
                <AlertCircleIcon size={20} className="muted" />
              </div>
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Limited multi-column relationships</h3>
              <p className="muted" style={{ fontSize: '13px', marginTop: '4px', maxWidth: '440px', marginInline: 'auto' }}>
                {!hasNumeric
                  ? 'No numeric measures available. Multi-column rankings and trend insights require quantitative values.'
                  : !hasCategorical && !hasDate
                  ? 'No categorical dimensions or date fields detected to correlate against numeric measures.'
                  : 'Automated insights require at least two compatible columns to discover patterns.'}
              </p>
            </div>
          )}
        </section>

        {/* Section 3: Anomalies & Outliers */}
        <section className="page-section">
          {hasNumeric ? (
            <AnomalyTable
              anomalies={anomalies}
              total={anomalies.length}
              evidence={anomalyEvidence}
              badge={
                <span className="tag tag-neutral">
                  IQR Statistical Scan
                </span>
              }
            />
          ) : (
            <div className="card" style={{ padding: '24px' }}>
              <h3 className="card-title">Anomalies & Outliers</h3>
              <p className="muted" style={{ fontSize: '13.5px', marginTop: '6px' }}>
                No numeric columns are present in this dataset to perform numerical outlier or anomaly detection.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

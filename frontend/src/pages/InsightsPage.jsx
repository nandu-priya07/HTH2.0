import InsightCard from '../components/analytics/InsightCard'
import AnomalyTable from '../components/analytics/AnomalyTable'
import { MiniBars } from '../components/analytics/MiniCharts'
import { PreviewBadge, Link, EmptyState } from '../components/ui/primitives'
import { useAnalyst } from '../state/analystContext'
import { getDatasetStats } from '../lib/dataset'
import { INSIGHTS, ANOMALIES } from '../mocks/previewData'
import { DatabaseIcon, UploadIcon } from '../components/ui/Icons'

const fmt = (v) => (typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v))

/** Highlights computed directly from the backend profile — real data, no inference. */
function ProfileHighlights({ dataset }) {
  const stats = getDatasetStats(dataset)
  const cols = dataset?.profile?.columns || []
  const numeric = cols.filter((c) => c.semantic_type === 'numeric' && c.statistics).slice(0, 2)
  const categorical = cols.filter((c) => c.top_values?.length > 1).slice(0, 2)

  if (!numeric.length && !categorical.length) {
    return <p className="muted">The profile for this dataset has no numeric or categorical summaries to highlight.</p>
  }

  return (
    <div className="grid grid-4">
      {numeric.map((c) => (
        <article key={c.name} className="card card-pad profile-card">
          <div className="section-label">Total · <span className="mono">{c.name}</span></div>
          <div className="insight-metric">{fmt(c.statistics.sum)}</div>
          <p className="insight-explanation">Mean {fmt(c.statistics.mean)} · range {fmt(c.statistics.min)} – {fmt(c.statistics.max)}</p>
        </article>
      ))}
      {categorical.map((c) => (
        <article key={c.name} className="card card-pad profile-card">
          <div className="section-label">Most frequent · <span className="mono">{c.name}</span></div>
          <div className="insight-metric">{String(c.top_values[0].value)}</div>
          <p className="insight-explanation">{c.top_values[0].count.toLocaleString()} of {Number(stats.rows).toLocaleString()} rows</p>
          <MiniBars data={c.top_values.map((t) => t.count)} labels={c.top_values.map((t) => String(t.value).slice(0, 8))} height={44} />
        </article>
      ))}
    </div>
  )
}

export default function InsightsPage() {
  const { activeDataset } = useAnalyst()
  const stats = getDatasetStats(activeDataset)

  return (
    <div className="page">
      <div className="container">
        <header className="page-header">
          <div>
            <div className="eyebrow">Insights</div>
            <h1>What stands out in your data</h1>
            <p>Each insight states the metric, the change, why it matters, and the evidence behind it.</p>
          </div>
        </header>

        <section className="page-section" aria-labelledby="profile-title">
          <div className="page-section-head">
            <h2 id="profile-title" className="card-title">From your dataset</h2>
            {stats && <span className="tag tag-teal"><DatabaseIcon size={12} /> {stats.name}</span>}
          </div>
          {activeDataset?.profile ? (
            <ProfileHighlights dataset={activeDataset} />
          ) : (
            <div className="card">
              <EmptyState
                icon={<DatabaseIcon size={22} />}
                title="No dataset connected"
                actions={<Link to="/upload" className="btn btn-primary btn-sm"><UploadIcon size={14} /> Upload dataset</Link>}
              >
                Upload a file to see highlights computed from its profile.
              </EmptyState>
            </div>
          )}
        </section>

        <section className="page-section" aria-labelledby="auto-title">
          <div className="page-section-head">
            <h2 id="auto-title" className="card-title">Automated insights</h2>
            <PreviewBadge />
          </div>
          <div className="grid grid-3">
            {INSIGHTS.map((i) => <InsightCard key={i.id} insight={i} />)}
          </div>
        </section>

        <section className="page-section">
          <AnomalyTable anomalies={ANOMALIES} total={12} badge={<PreviewBadge />} />
        </section>
      </div>
    </div>
  )
}

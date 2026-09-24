import { StatTile } from '../ui/primitives'
import { formatCount } from '../../lib/dataset'

export default function DatasetOverview({ stats }) {
  if (!stats) return null
  return (
    <section className="card card-pad" aria-labelledby="overview-title">
      <div className="card-header">
        <div>
          <h3 id="overview-title" className="card-title">Dataset Overview</h3>
          <p className="card-subtitle">Counts come from the inferred schema.</p>
        </div>
      </div>
      <div className="overview-grid">
        <StatTile label="Rows" value={formatCount(stats.rows)} />
        <StatTile label="Columns" value={formatCount(stats.columns)} />
        <StatTile label="Numeric Fields" value={formatCount(stats.numeric)} tone="teal" />
        <StatTile label="Categorical Fields" value={formatCount(stats.categorical)} tone="sage" />
        <StatTile label="Date Fields" value={formatCount(stats.date)} tone="yellow" />
      </div>
    </section>
  )
}

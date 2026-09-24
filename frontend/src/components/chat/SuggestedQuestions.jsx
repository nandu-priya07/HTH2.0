import { SparklesIcon, BarChartIcon, TrendingUpIcon, ListIcon, AlertTriangleIcon, ArrowRightIcon, UploadIcon, DatabaseIcon } from '../ui/Icons'
import { Link } from '../ui/primitives'
import { getDatasetStats, formatCount } from '../../lib/dataset'

/* Default question templates. When the backend returns dataset-specific
   suggestions (GET /api/dataset/:id/suggestions) they replace these in order. */
const CARD_CONFIGS = [
  { icon: BarChartIcon, category: 'Ranking', defaultText: 'Which region generated the highest revenue?' },
  { icon: TrendingUpIcon, category: 'Trend', defaultText: 'Show monthly sales trends.' },
  { icon: ListIcon, category: 'Top-N', defaultText: 'What are the top 5 products?' },
  { icon: SparklesIcon, category: 'Comparison', defaultText: 'Compare revenue across regions.' },
  { icon: AlertTriangleIcon, category: 'Anomaly', defaultText: 'Are there unusual transactions?' }
]

export default function SuggestedQuestions({ onSelectSuggestion, activeDataset, suggestions = [] }) {
  const stats = getDatasetStats(activeDataset)
  const fromDataset = suggestions.length > 0

  const cards = CARD_CONFIGS.map((cfg, i) => ({ ...cfg, text: suggestions[i] || cfg.defaultText }))

  return (
    <div className="ask-empty animate-fade-in">
      <div className="ask-empty-badge" aria-hidden="true"><SparklesIcon size={24} /></div>
      <h1 className="ask-empty-title">
        {stats ? <>Ask anything about <span className="text-accent">{stats.name}</span></> : <>Ask your data <span className="text-accent">anything</span></>}
      </h1>
      <p className="ask-empty-sub">
        Get an answer, a chart chosen for the question, and a step-by-step explanation of how it was calculated.
      </p>

      {stats ? (
        <div className="ask-empty-dataset">
          <DatabaseIcon size={14} />
          <span className="mono">{stats.name}</span>
          <span>· {formatCount(stats.rows)} rows · {formatCount(stats.columns)} columns</span>
          <span className="status status-good">Ready</span>
        </div>
      ) : (
        <div className="ask-empty-nodata">
          <span>No dataset connected yet.</span>
          <Link to="/upload" className="btn btn-primary btn-sm"><UploadIcon size={14} /> Upload dataset</Link>
          <span className="muted">or attach one with <strong>+</strong> below</span>
        </div>
      )}

      <div className="suggestions">
        <div className="suggestions-head">
          <span className="section-label">Try asking</span>
          <span className="suggestions-source">{fromDataset ? 'Generated from your schema' : 'Example questions'}</span>
        </div>
        <ul className="suggestions-list">
          {cards.map(({ icon: Icon, category, text }) => (
            <li key={category}>
              <button className="suggestion" onClick={() => onSelectSuggestion(text)}>
                <span className="suggestion-icon"><Icon size={16} /></span>
                <span className="suggestion-body">
                  <span className="suggestion-cat">{category}</span>
                  <span className="suggestion-text">{text}</span>
                </span>
                <ArrowRightIcon size={16} className="suggestion-arrow" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

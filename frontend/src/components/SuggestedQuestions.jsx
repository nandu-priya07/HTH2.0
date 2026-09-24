import { SparklesIcon, BarChartIcon, TrendingUpIcon, TableIcon, DatabaseIcon } from './Icons'

export default function SuggestedQuestions({ onSelectSuggestion, activeDataset, suggestions = [] }) {
  const defaultSuggestions = [
    { text: 'What is the total sales by region?', category: 'Breakdown', icon: <TableIcon size={14} /> },
    { text: 'What is the average profit by category?', category: 'Aggregation', icon: <BarChartIcon size={14} /> },
    { text: 'Show sales trend by month', category: 'Trend', icon: <TrendingUpIcon size={14} /> },
    { text: 'What are the top 5 products by sales?', category: 'Ranking', icon: <SparklesIcon size={14} /> }
  ]

  const activeSuggestions = suggestions.length > 0
    ? suggestions.map((text, i) => ({
        text,
        category: i % 2 === 0 ? 'Analysis' : 'Breakdown',
        icon: <BarChartIcon size={14} />
      }))
    : defaultSuggestions

  const datasetName = activeDataset?.filename || activeDataset?.result?.metadata?.filename
  const rowCount = activeDataset?.metadata?.rows || activeDataset?.result?.metadata?.rows || activeDataset?.rows

  return (
    <div className="empty-chat-container animate-fade-in">
      {/* Central Glowing Hero Icon */}
      <div className="empty-brand-badge">
        <div className="brand-glow-ring"></div>
        <SparklesIcon size={28} className="brand-hero-spark" />
      </div>

      <h1 className="empty-title">
        HTH2.0 <span className="title-gradient">AI Data Analyst</span>
      </h1>

      <p className="empty-subtitle">
        Natural-language data intelligence. Ingests your dataset, parses intent, and executes precision analytics without hallucination.
      </p>

      {/* Dataset Active Pill or Prompt */}
      {activeDataset ? (
        <div className="active-dataset-hero-pill">
          <DatabaseIcon size={15} />
          <span className="dataset-hero-name">{datasetName}</span>
          {rowCount && (
            <span className="dataset-hero-meta">• {rowCount.toLocaleString()} rows</span>
          )}
          <span className="dataset-status-badge">Ready for Queries</span>
        </div>
      ) : (
        <div className="no-dataset-hero-pill">
          <DatabaseIcon size={14} />
          <span>No dataset loaded • Attach a CSV or Excel file below to begin</span>
        </div>
      )}

      {/* Feature Pills */}
      <div className="features-ribbon">
        <div className="feature-pill">
          <span className="feature-dot emerald"></span>
          <span>Zero Hallucinations</span>
        </div>
        <div className="feature-pill">
          <span className="feature-dot indigo"></span>
          <span>Schema-Agnostic</span>
        </div>
        <div className="feature-pill">
          <span className="feature-dot cyan"></span>
          <span>Instant Aggregations</span>
        </div>
      </div>

      {/* Suggestions Section */}
      <div className="suggestions-section">
        <div className="suggestions-header">
          <span className="suggestions-title">Recommended Questions</span>
          <span className="suggestions-hint">Click any prompt to analyze</span>
        </div>

        <div className="suggestions-grid">
          {activeSuggestions.map((item, idx) => (
            <button
              key={idx}
              className="suggestion-card"
              onClick={() => onSelectSuggestion(item.text)}
            >
              <div className="suggestion-card-top">
                <span className="suggestion-cat-badge">{item.category}</span>
                <span className="suggestion-icon">{item.icon}</span>
              </div>
              <div className="suggestion-text">{item.text}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

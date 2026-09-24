import { SparklesIcon, BarChartIcon, TrendingUpIcon, TableIcon, DatabaseIcon } from './Icons'

/* Arrow icon inline — simple chevron right */
function ArrowRight() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
    </svg>
  )
}

/* Card configurations — each has a color variant and icon color */
const CARD_CONFIGS = [
  {
    variant: 'variant-purple',
    iconColor: 'purple',
    icon: <BarChartIcon size={18} />,
    category: 'Ranking',
    defaultTitle: 'Top products',
    defaultText: 'What are the top 5 products by revenue?'
  },
  {
    variant: 'variant-blue',
    iconColor: 'blue',
    icon: <TrendingUpIcon size={18} />,
    category: 'Trend',
    defaultTitle: 'Sales trends',
    defaultText: 'Show me the monthly sales trend'
  },
  {
    variant: 'variant-cyan',
    iconColor: 'cyan',
    icon: <TableIcon size={18} />,
    category: 'Breakdown',
    defaultTitle: 'Regional breakdown',
    defaultText: 'What is the total sales by region?'
  },
  {
    variant: 'variant-pink',
    iconColor: 'pink',
    icon: <SparklesIcon size={18} />,
    category: 'Analysis',
    defaultTitle: 'Profit analysis',
    defaultText: 'What is the average profit by category?'
  }
]

export default function SuggestedQuestions({ onSelectSuggestion, activeDataset, suggestions = [] }) {
  const datasetName = activeDataset?.filename || activeDataset?.result?.metadata?.filename
  const rowCount    = activeDataset?.metadata?.rows || activeDataset?.result?.metadata?.rows || activeDataset?.rows

  /* Build final cards — use backend suggestions text if available */
  const cards = CARD_CONFIGS.map((cfg, i) => ({
    ...cfg,
    text: suggestions[i] || cfg.defaultText
  }))

  return (
    <div className="empty-chat-container animate-fade-in">

      {/* Floating brand orb */}
      <div className="empty-brand-badge" aria-hidden="true">
        <div className="brand-glow-ring" />
        <SparklesIcon size={30} />
      </div>

      {/* Eyebrow */}
      <div className="empty-eyebrow">
        <span className="eyebrow-dot" />
        AI Data Analyst
        <span className="eyebrow-dot" />
      </div>

      {/* Main heading */}
      <h1 className="empty-title">
        Turn data into <span className="title-gradient">intelligence</span>
      </h1>

      <p className="empty-subtitle">
        Ask questions about your data in plain English. HTH2.0 analyzes it,
        finds patterns, and delivers precise insights — instantly.
      </p>

      {/* Dataset status pill */}
      {activeDataset ? (
        <div className="active-dataset-hero-pill">
          <DatabaseIcon size={15} />
          <span className="dataset-hero-name">{datasetName}</span>
          {rowCount && <span className="dataset-hero-meta">· {rowCount.toLocaleString()} rows</span>}
          <span className="dataset-status-badge">● Ready</span>
        </div>
      ) : (
        <div className="no-dataset-hero-pill">
          <DatabaseIcon size={15} />
          <span>No dataset loaded · Upload a CSV or Excel file below to begin</span>
        </div>
      )}

      {/* Feature capability badges */}
      <div className="features-ribbon">
        <div className="feature-pill">
          <span className="feature-dot emerald" />
          Reliable Analysis
        </div>
        <div className="feature-pill">
          <span className="feature-dot indigo" />
          Schema-Agnostic
        </div>
        <div className="feature-pill">
          <span className="feature-dot cyan" />
          Instant Aggregations
        </div>
      </div>

      {/* Suggestion cards grid */}
      <div className="suggestions-section">
        <div className="suggestions-header">
          <span className="suggestions-title">Try asking</span>
          <span className="suggestions-hint">Click any card to analyze</span>
        </div>

        <div className="suggestions-grid">
          {cards.map((card, idx) => (
            <button
              key={idx}
              className={`suggestion-card ${card.variant}`}
              onClick={() => onSelectSuggestion(card.text)}
              title={card.text}
            >
              <div className="suggestion-card-top">
                <div className={`suggestion-icon-wrap ${card.iconColor}`}>
                  {card.icon}
                </div>
                <span className="suggestion-cat-badge">{card.category}</span>
              </div>

              <div className="suggestion-body">
                <div className="suggestion-card-title">{card.defaultTitle}</div>
                <div className="suggestion-text">{card.text}</div>
              </div>

              <div className="suggestion-arrow">
                <ArrowRight />
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

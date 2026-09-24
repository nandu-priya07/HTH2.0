export default function SuggestedQuestions({ onSelectSuggestion }) {
  const suggestions = [
    'What are the top 5 products by revenue?',
    'Show me the monthly sales trend',
    'Which region has the highest sales?',
    'Which products have the highest profit?',
    'Give me a summary of the dataset'
  ]

  return (
    <div className="empty-chat-container">
      <div className="empty-brand-icon">⚡</div>
      <h1 className="empty-title">HTH2.0 AI Data Analyst</h1>
      <p className="empty-subtitle">
        Ask questions about your dataset. Analyze sales, customers, products, regions, trends and more.
      </p>

      <div className="suggestions-title">Try asking:</div>

      <div className="suggestions-grid">
        {suggestions.map((text, idx) => (
          <div
            key={idx}
            className="suggestion-card"
            onClick={() => onSelectSuggestion(text)}
          >
            {text}
          </div>
        ))}
      </div>
    </div>
  )
}

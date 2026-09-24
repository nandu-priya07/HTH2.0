import { useState } from 'react'
import {
  SparklesIcon,
  PaperclipIcon,
  CodeIcon,
  AlertCircleIcon,
  BarChartIcon
} from './Icons'
import VisualizationRenderer from './visualization/VisualizationRenderer'

export default function ChatMessage({ message, onSelectOption }) {
  const {
    sender,
    text,
    table,
    scalar,
    status,
    options,
    query_spec,
    metadata,
    attachment,
    visualization,
    visualizations,
    isLoading,
    error
  } = message

  const [showSpec, setShowSpec] = useState(false)

  const formatFileSize = (bytes) => {
    if (!bytes) return ''
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  if (sender === 'user') {
    return (
      <div className="message-row user animate-slide-up">
        <div className="message-bubble-wrapper">
          <div className="user-message-content">
            {attachment && (
              <div className="user-message-attachment">
                <div className="attachment-icon-pill">
                  <PaperclipIcon size={16} />
                </div>
                <div className="attachment-meta">
                  <div className="attachment-title">{attachment.filename}</div>
                  {attachment.file_size && (
                    <div className="attachment-subtext">
                      {formatFileSize(attachment.file_size)} • {attachment.file_type?.toUpperCase() || 'FILE'}
                    </div>
                  )}
                </div>
              </div>
            )}
            {text && <div className="user-text">{text}</div>}
          </div>
        </div>
      </div>
    )
  }

  // AI Assistant Message
  return (
    <div className="message-row ai animate-slide-up">
      <div className="message-bubble-wrapper">
        {/* AI Brand Avatar Pill */}
        <div className="ai-avatar-pill">
          <SparklesIcon size={16} />
        </div>

        <div className="ai-message-content">
          {isLoading ? (
            <div className="ai-loading-container">
              <div className="pulse-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <span className="loading-label">Analyzing dataset & executing query...</span>
            </div>
          ) : (
            <>
              {/* Text Summary */}
              {text && (
                <div className="ai-text-summary">
                  {text.split('\n').map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
                </div>
              )}

              {/* DYNAMIC VISUALIZATION LAYER (Chart / KPI / Table / Multi-section) */}
              {(visualization || (visualizations && visualizations.length > 0) || table || scalar) && (
                <VisualizationRenderer
                  visualization={visualization}
                  visualizations={visualizations}
                  table={table}
                  scalar={scalar}
                />
              )}

              {/* CLARIFICATION PILL OPTIONS */}
              {status === 'NEEDS_CLARIFICATION' && options && options.length > 0 && (
                <div className="clarification-options-card">
                  <div className="clarification-title">
                    <AlertCircleIcon size={15} />
                    <span>Select an option to clarify:</span>
                  </div>
                  <div className="options-pills-grid">
                    {options.map((opt, idx) => (
                      <button
                        key={idx}
                        className="option-pill-btn"
                        onClick={() => onSelectOption && onSelectOption(opt)}
                      >
                        <BarChartIcon size={13} />
                        <span>{opt}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* ERROR CARD */}
              {error && (
                <div className="ai-error-card">
                  <AlertCircleIcon size={16} />
                  <span>{error}</span>
                </div>
              )}

              {/* QUERY SPEC TRANSPARENCY ACCORDION */}
              {query_spec && (
                <div className="query-spec-accordion">
                  <button
                    className="spec-toggle-btn"
                    onClick={() => setShowSpec(!showSpec)}
                    title="Toggle Query Execution Details"
                  >
                    <CodeIcon size={12} />
                    <span>
                      Query Spec: {query_spec.operation || 'analysis'}
                      {query_spec.metric || query_spec.column ? ` • ${query_spec.metric || query_spec.column}` : ''}
                      {query_spec.aggregation ? ` (${query_spec.aggregation})` : ''}
                    </span>
                    <span className="spec-caret">{showSpec ? '▲' : '▼'}</span>
                  </button>
                  {showSpec && (
                    <pre className="spec-code-block">
                      {JSON.stringify(query_spec, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

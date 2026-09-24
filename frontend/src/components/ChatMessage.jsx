import { useState } from 'react'
import {
  SparklesIcon,
  PaperclipIcon,
  TableIcon,
  CopyIcon,
  CodeIcon,
  AlertCircleIcon,
  BarChartIcon
} from './Icons'

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
    isLoading,
    error
  } = message

  const [showSpec, setShowSpec] = useState(false)
  const [copied, setCopied] = useState(false)

  const formatFileSize = (bytes) => {
    if (!bytes) return ''
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  const handleCopyTable = () => {
    if (!table || !table.headers || !table.rows) return
    const csvContent = [
      table.headers.join(','),
      ...table.rows.map((row) => row.join(','))
    ].join('\n')
    navigator.clipboard.writeText(csvContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Calculate maximum numeric value in table for proportional bar indicators
  const getColumnMax = (colIndex) => {
    if (!table || !table.rows) return 0
    let maxVal = 0
    table.rows.forEach((r) => {
      const val = parseFloat(r[colIndex])
      if (!isNaN(val) && val > maxVal) {
        maxVal = val
      }
    })
    return maxVal
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

              {/* 1. SCALAR KPI METRIC CARD */}
              {scalar && (
                <div className="scalar-kpi-card">
                  <div className="kpi-header">
                    <span className="kpi-label">{scalar.metric || 'Calculated Metric'}</span>
                    {scalar.aggregation && (
                      <span className="kpi-badge">
                        {scalar.aggregation.toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div className="kpi-value-row">
                    <div className="kpi-number">
                      {typeof scalar.value === 'number'
                        ? scalar.value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                        : scalar.value}
                    </div>
                  </div>
                  {metadata && metadata.rows_analyzed && (
                    <div className="kpi-footer">
                      <span className="kpi-meta-dot"></span>
                      <span>Analyzed across {metadata.rows_analyzed.toLocaleString()} records</span>
                    </div>
                  )}
                </div>
              )}

              {/* 2. GROUPED / DETAIL DATA TABLE */}
              {table && table.headers && table.rows && (
                <div className="ai-table-card">
                  <div className="table-card-header">
                    <div className="table-card-title">
                      <TableIcon size={15} />
                      <span>Data Results ({table.rows.length} rows)</span>
                    </div>
                    <button className="table-action-btn" onClick={handleCopyTable} title="Copy table as CSV">
                      <CopyIcon size={13} />
                      <span>{copied ? 'Copied!' : 'Copy CSV'}</span>
                    </button>
                  </div>

                  <div className="table-wrapper">
                    <table className="analytics-table">
                      <thead>
                        <tr>
                          {table.headers.map((h, i) => (
                            <th key={i} className={i > 0 && typeof table.rows[0]?.[i] === 'number' ? 'text-right' : ''}>
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {table.rows.map((row, rIdx) => (
                          <tr key={rIdx}>
                            {row.map((cell, cIdx) => {
                              const isNum = typeof cell === 'number'
                              const maxVal = isNum ? getColumnMax(cIdx) : 0
                              const pct = maxVal > 0 ? Math.min((cell / maxVal) * 100, 100) : 0

                              return (
                                <td key={cIdx} className={isNum ? 'text-right cell-numeric' : ''}>
                                  <div className="cell-content-wrapper">
                                    <span>
                                      {isNum ? cell.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(cell ?? '-')}
                                    </span>
                                    {isNum && maxVal > 0 && (
                                      <div className="mini-progress-bar">
                                        <div className="mini-progress-fill" style={{ width: `${pct}%` }}></div>
                                      </div>
                                    )}
                                  </div>
                                </td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* 3. CLARIFICATION PILL OPTIONS */}
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

              {/* 4. ERROR CARD */}
              {error && (
                <div className="ai-error-card">
                  <AlertCircleIcon size={16} />
                  <span>{error}</span>
                </div>
              )}

              {/* 5. QUERY SPEC TRANSPARENCY ACCORDION */}
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
                      {query_spec.metric ? ` • ${query_spec.metric}` : ''}
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

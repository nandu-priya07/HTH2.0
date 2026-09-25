import { useState } from 'react'
import { ZapIcon, ChevronDownIcon, ClockIcon } from '../ui/Icons'

export default function ResponseTiming({ timing }) {
  const [isOpen, setIsOpen] = useState(false)

  if (!timing || typeof timing.total_ms !== 'number') return null

  const {
    total_ms = 0,
    chat_ms = 0,
    context_ms = 0,
    runtime_ms = 0,
    llm_ms = 0,
    exec_ms = 0,
    format_ms = 0,
    cache_status = 'MISS',
    prompt_metrics = {}
  } = timing

  const isHit = cache_status === 'HIT'
  const totalFormatted = total_ms >= 1000 ? `${(total_ms / 1000).toFixed(2)}s` : `${Math.round(total_ms)}ms`
  const llmFormatted = llm_ms >= 1000 ? `${(llm_ms / 1000).toFixed(2)}s` : `${llm_ms.toFixed(1)}ms`
  const execFormatted = exec_ms < 1 ? `${exec_ms.toFixed(2)}ms` : `${exec_ms.toFixed(1)}ms`
  const contextTotalMs = chat_ms + context_ms

  // Percentage calculations for visual bar
  const total = Math.max(total_ms, 1)
  const llmPct = Math.min(100, Math.max(2, (llm_ms / total) * 100))
  const execPct = Math.min(100, Math.max(1, (exec_ms / total) * 100))
  const otherPct = Math.max(0, 100 - llmPct - execPct)

  return (
    <div className="msg-timing-wrap">
      <div className="msg-timing-bar">
        <button
          type="button"
          className="msg-timing-badge-btn"
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
          title="Click to view detailed query response timing breakdown"
        >
          <span className="timing-icon"><ZapIcon size={13} /></span>
          <span className="timing-total"><strong>{totalFormatted}</strong></span>
          <span className="timing-divider">·</span>

          <span className={`timing-cache-pill ${isHit ? 'hit' : 'miss'}`}>
            {isHit ? '⚡ Cache HIT' : 'Cache MISS'}
          </span>

          <span className="timing-divider">·</span>
          <span className="timing-pill">LLM {llmFormatted}</span>
          <span className="timing-pill">DuckDB {execFormatted}</span>

          <span className={`timing-chevron ${isOpen ? 'open' : ''}`}>
            <ChevronDownIcon size={12} />
          </span>
        </button>
      </div>

      {isOpen && (
        <div className="msg-timing-details animate-slide-up">
          <div className="timing-details-head">
            <span className="section-label"><ClockIcon size={12} /> Response Latency Breakdown</span>
            <span className="timing-total-raw">{total_ms.toFixed(1)} ms total</span>
          </div>

          {/* Visual Percentage Stacked Bar */}
          <div className="timing-progress-bar-wrap">
            <div className="timing-progress-bar">
              <div
                className="bar-seg seg-llm"
                style={{ width: `${llmPct}%` }}
                title={`LLM Query Understanding: ${llmFormatted} (${llmPct.toFixed(1)}%)`}
              />
              <div
                className="bar-seg seg-exec"
                style={{ width: `${execPct}%` }}
                title={`DuckDB Analytics: ${execFormatted} (${execPct.toFixed(1)}%)`}
              />
              <div
                className="bar-seg seg-other"
                style={{ width: `${otherPct}%` }}
                title={`System & Preprocessing: ${(total_ms - llm_ms - exec_ms).toFixed(1)}ms (${otherPct.toFixed(1)}%)`}
              />
            </div>
            <div className="timing-bar-legend">
              <span className="legend-item"><span className="legend-dot dot-llm" /> LLM ({llmPct.toFixed(0)}%)</span>
              <span className="legend-item"><span className="legend-dot dot-exec" /> DuckDB ({execPct.toFixed(0)}%)</span>
              <span className="legend-item"><span className="legend-dot dot-other" /> System ({(total_ms - llm_ms - exec_ms).toFixed(1)}ms)</span>
            </div>
          </div>

          {/* Step-by-Step Breakdown Grid */}
          <div className="timing-grid">
            <div className="timing-grid-item">
              <span className="grid-label">Dataset Cache Lookup</span>
              <span className="grid-val mono">
                {runtime_ms.toFixed(2)} ms
                <span className={`grid-tag ${isHit ? 'tag-hit' : 'tag-miss'}`}>{cache_status}</span>
              </span>
            </div>

            <div className="timing-grid-item">
              <span className="grid-label">Context & Session</span>
              <span className="grid-val mono">{contextTotalMs.toFixed(1)} ms</span>
            </div>

            <div className="timing-grid-item">
              <span className="grid-label">LLM Intent Understanding</span>
              <span className="grid-val mono">{llm_ms.toFixed(1)} ms</span>
            </div>

            <div className="timing-grid-item">
              <span className="grid-label">DuckDB Analytics Execution</span>
              <span className="grid-val mono">{exec_ms.toFixed(2)} ms</span>
            </div>

            {format_ms > 0 && (
              <div className="timing-grid-item">
                <span className="grid-label">Response Formatting</span>
                <span className="grid-val mono">{format_ms.toFixed(1)} ms</span>
              </div>
            )}
          </div>

          {/* Prompt footprint metrics if available */}
          {prompt_metrics && (prompt_metrics.estimated_token_count != null || prompt_metrics.dataset_rows != null) && (
            <div className="timing-footprint">
              {prompt_metrics.estimated_token_count != null && (
                <span className="footprint-pill">
                  LLM Prompt: ~{prompt_metrics.estimated_token_count} tokens ({prompt_metrics.char_count?.toLocaleString()} chars)
                </span>
              )}
              {prompt_metrics.dataset_rows != null && (
                <span className="footprint-pill">
                  Runtime Dataset: {prompt_metrics.dataset_rows?.toLocaleString()} rows × {prompt_metrics.dataset_columns} cols (DuckDB)
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

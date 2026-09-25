import { useRef, useState, useEffect } from 'react'
import {
  SparklesIcon,
  PaperclipIcon,
  AlertCircleIcon,
  AlertTriangleIcon,
  BarChartIcon,
  TableIcon,
  CornerDownRightIcon,
  UploadIcon,
  CheckCircleIcon,
  TargetIcon,
  EditIcon,
  SendIcon
} from '../ui/Icons'
import { Link } from '../ui/primitives'
import VisualizationRenderer from '../visualization/VisualizationRenderer'
import ExplanationTrace from '../analytics/ExplanationTrace'
import EvidencePanel from '../analytics/EvidencePanel'
import { buildExplanation } from '../../lib/explain'
import { formatBytes } from '../../lib/dataset'
import GeoDecisionExplorer from '../analytics/GeoDecisionExplorer'
import ResponseTiming from '../analytics/ResponseTiming'


/* Renders plain text with **bold** spans and paragraph breaks. */
function RichText({ text }) {
  return text.split('\n').filter((p, i, arr) => p.trim() || (i > 0 && arr[i - 1].trim())).map((para, i) => (
    <p key={i}>
      {para.split(/(\*\*[^*]+\*\*)/g).map((chunk, j) =>
        chunk.startsWith('**') && chunk.endsWith('**') ? <strong key={j}>{chunk.slice(2, -2)}</strong> : chunk
      )}
    </p>
  ))
}

/* Follow-up prompts derived from what was just executed + the inferred schema. */
function buildFollowUps(spec, schemaHints = {}) {
  if (!spec) return []
  const out = []
  const groupBy = spec.group_by || []
  if (groupBy.length && (spec.sort?.length || spec.limit)) out.push('What about the second highest?')
  if (groupBy.length && !spec.sort?.length) out.push('Which one is the highest?')
  const cat = (schemaHints.categorical || []).find((c) => !groupBy.includes(c))
  if (cat) out.push(`Break this down by ${cat}`)
  const date = (schemaHints.date || [])[0]
  if (date && !groupBy.includes(date)) out.push(`Show its trend over ${date}`)
  return out.slice(0, 3)
}

function AnalyzingState() {
  return (
    <div className="ai-analyzing" role="status" aria-live="polite">
      <div className="pulse-dots"><span /><span /><span /></div>
      <ol className="ai-analyzing-steps">
        <li>Understanding intent</li>
        <li>Generating query</li>
        <li>Analyzing data</li>
      </ol>
      <span className="sr-only">Analyzing your question…</span>
    </div>
  )
}

function ClarificationCard({ message, measureOptions, onSelectOption }) {
  const hasBackendOptions = message.options?.length > 0
  const choices = hasBackendOptions ? message.options : measureOptions.slice(0, 6)
  return (
    <div className="state-card state-clarify">
      <div className="state-card-head">
        <span className="state-card-icon"><TargetIcon size={16} /></span>
        <div>
          <div className="state-card-title">I can answer this, but I need one detail first</div>
          <div className="state-card-sub">Rather than guess, pick what you mean:</div>
        </div>
      </div>
      {message.text && <div className="state-card-text"><RichText text={message.text} /></div>}
      {choices.length > 0 && (
        <div className="state-card-options" role="group" aria-label="Clarification options">
          {choices.map((opt) => (
            <button
              key={opt}
              className="option-btn"
              onClick={() => onSelectOption?.(hasBackendOptions || !message.question ? opt : `${message.question} (measured by ${opt})`)}
            >
              <BarChartIcon size={13} />
              <span>{opt}</span>
            </button>
          ))}
        </div>
      )}
      {!choices.length && <div className="state-card-sub">Reply below with the field you meant.</div>}
    </div>
  )
}

const UNANSWERED_TITLES = {
  not_available: "This isn't available in the current dataset",
  no_data: 'No matching records'
}

function UnanswerableCard({ message, onViewFields, onAskAnother }) {
  const title = UNANSWERED_TITLES[message.status] || "I couldn't answer this from the current dataset."
  return (
    <div className="state-card state-unanswerable" role="alert">
      <div className="state-card-head">
        <span className="state-card-icon"><AlertTriangleIcon size={16} /></span>
        <div>
          <div className="state-card-title">{title}</div>
          {message.error && <div className="state-card-sub">{message.error}</div>}
        </div>
      </div>
      {message.text && message.text !== message.error && <div className="state-card-text"><RichText text={message.text} /></div>}
      <div className="state-card-options">
        {onViewFields && (
          <button className="btn btn-secondary btn-sm" onClick={onViewFields}><TableIcon size={14} /> View available fields</button>
        )}
        {onAskAnother && (
          <button className="btn btn-ghost btn-sm" onClick={onAskAnother}>Ask another question</button>
        )}
      </div>
    </div>
  )
}

function DecisionAnalysis({ decision_analysis }) {
  return (
    <section className="decision-card" aria-label="Decision analysis">
      <div className="answer-label"><TargetIcon size={13} /> Decision analysis</div>
      <p className="decision-question">{decision_analysis.user_question}</p>

      <div className="decision-cols">
        <div>
          <h4>Relevant factors</h4>
          <ul className="decision-factors">
            {(decision_analysis.factor_discovery?.factors || []).slice(0, 6).map((factor) => (
              <li key={factor.name}>
                <strong className="mono">{factor.name}</strong>
                <span>{factor.relationship}</span>
                <span className="decision-strength">strength {Number(factor.strength).toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Decision boundary</h4>
          <p>{decision_analysis.boundary?.boundary_value == null ? decision_analysis.boundary?.reason : `${decision_analysis.boundary.boundary_value}% — ${decision_analysis.boundary.reason}`}</p>
        </div>
      </div>

      <h4>Scenario analysis</h4>
      <div className="decision-scenarios">
        {(decision_analysis.scenario_analysis?.scenarios || []).map((scenario) => (
          <div key={scenario.increase_percent} className={`decision-scenario${scenario.target_reached ? ' boundary' : ''}`}>
            <strong>+{scenario.increase_percent}%</strong>
            <span>{Number(scenario.projected_value).toLocaleString()}</span>
            {scenario.target_reached && <span className="status status-warn">Boundary</span>}
            <small>Incremental benefit: {Number(scenario.incremental_benefit).toLocaleString()}</small>
          </div>
        ))}
      </div>

      <h4>Counter-tests</h4>
      {decision_analysis.counter_tests?.length
        ? <ul className="decision-tests">{decision_analysis.counter_tests.map((test, index) => <li key={`${test.test}-${index}`}>{test.factor || test.test}: {test.result}</li>)}</ul>
        : <p className="muted">No eligible counter-test was supported by the available columns and sample sizes.</p>}

      <details className="decision-trace">
        <summary>Evidence and calculation trace</summary>
        <p>{decision_analysis.evidence?.interpretation}</p>
        <p>Method: {decision_analysis.scenario_analysis?.method}</p>
        <pre>{JSON.stringify(decision_analysis.trace, null, 2)}</pre>
      </details>
    </section>
  )
}

function UserMessageItem({
  message,
  isFollowUp,
  isEditing,
  onStartEdit,
  onCancelEdit,
  onSubmitEdit,
  isLoadingSession
}) {
  const { text, attachment } = message
  const [draftText, setDraftText] = useState(text || '')
  const textareaRef = useRef(null)

  // Keep draft in sync if edit mode toggles or original text changes
  useEffect(() => {
    if (isEditing) {
      setDraftText(text || '')
    }
  }, [isEditing, text])

  // Auto-focus and place cursor at the end
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      const el = textareaRef.current
      el.focus()
      const len = el.value.length
      el.setSelectionRange(len, len)
    }
  }, [isEditing])

  const handleCancel = () => {
    setDraftText(text || '')
    onCancelEdit?.()
  }

  const handleSend = () => {
    const clean = draftText.trim()
    if (!clean || isLoadingSession) return
    if (clean === (text || '').trim()) {
      onCancelEdit?.()
      return
    }
    onSubmitEdit?.(clean)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      handleCancel()
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className={`msg msg-user animate-slide-up${isEditing ? ' is-editing' : ''}`}>
      {isFollowUp && !isEditing && (
        <span className="msg-followup-tag"><CornerDownRightIcon size={12} /> Follow-up</span>
      )}

      {isEditing ? (
        <div className="msg-user-edit-card" role="region" aria-label="Edit message">
          <textarea
            ref={textareaRef}
            className="msg-user-edit-textarea"
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your data…"
            disabled={isLoadingSession}
            aria-label="Edit message text"
          />
          <div className="msg-user-edit-actions">
            <span className="msg-user-edit-hint">
              <kbd>Esc</kbd> cancel · <kbd>↵</kbd> send
            </span>
            <div className="msg-user-edit-btns">
              <button
                type="button"
                className="btn-edit-cancel"
                onClick={handleCancel}
                disabled={isLoadingSession}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-edit-send"
                onClick={handleSend}
                disabled={isLoadingSession || !draftText.trim()}
              >
                <span>Send</span>
                <SendIcon size={12} />
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="msg-user-row">
          <button
            type="button"
            className="msg-user-edit-btn"
            onClick={onStartEdit}
            title="Edit message"
            aria-label="Edit message"
            disabled={isLoadingSession}
          >
            <EditIcon size={13} />
          </button>

          <div className="msg-user-bubble">
            {attachment && (
              <div className="msg-attachment">
                <span className="msg-attachment-icon"><PaperclipIcon size={15} /></span>
                <span>
                  <span className="msg-attachment-name">{attachment.filename}</span>
                  {attachment.file_size && (
                    <span className="msg-attachment-meta">{formatBytes(attachment.file_size)} · {attachment.file_type?.toUpperCase() || 'FILE'}</span>
                  )}
                </span>
              </div>
            )}
            {text && <div className="msg-user-text">{text}</div>}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ChatMessage({
  message,
  messageIndex,
  onSelectOption,
  onViewFields,
  onAskAnother,
  isFollowUp = false,
  isEditing = false,
  onStartEdit,
  onCancelEdit,
  onSubmitEdit,
  measureOptions = [],
  schemaHints,
  isLoadingSession = false
}) {
  const {
    sender,
    text,
    table,
    scalar,
    status,
    query_spec,
    attachment,
    visualization,
    visualizations,
    isLoading,
    error,
    errorKind,
    decision_analysis,
    geo,
    geo_result,
    geo_evidence,
    kind,
    timing
  } = message

  if (sender === 'user') {
    return (
      <UserMessageItem
        message={message}
        isFollowUp={isFollowUp}
        isEditing={isEditing}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        onSubmitEdit={onSubmitEdit}
        isLoadingSession={isLoadingSession}
      />
    )
  }

  const isClarification = status === 'clarification' || status === 'NEEDS_CLARIFICATION'
  const isUnanswerable = !isClarification && !errorKind &&
    (status === 'error' || status === 'not_available' || status === 'no_data' || (error && !text))
  // A single number is already stated in the answer; only show a KPI card when one was asked for.
  const visList = visualizations?.length ? visualizations : visualization ? [visualization] : []
  const isPlainScalar = Boolean(scalar) && !table && text &&
    visList.every((v) => (v.visualization_type || v.type) === 'kpi' && !v.visualization_required)
  const hasVis = !isPlainScalar && (visList.length > 0 || table || scalar)
  const trace = !isClarification && !isUnanswerable ? buildExplanation(message) : null
  const followUps = trace ? buildFollowUps(query_spec, schemaHints) : []

  return (
    <div className="msg msg-ai animate-slide-up">
      <div className="msg-ai-avatar" aria-hidden="true"><SparklesIcon size={15} /></div>
      <div className="msg-ai-body">
        {isLoading ? (
          <AnalyzingState />
        ) : errorKind === 'connection' || errorKind === 'server' ? (
          <div className="state-card state-connection" role="alert">
            <div className="state-card-head">
              <span className="state-card-icon"><AlertCircleIcon size={16} /></span>
              <div>
                <div className="state-card-title">{errorKind === 'server' ? 'The analysis engine returned an error' : 'Connection problem'}</div>
                <div className="state-card-sub">{error}</div>
              </div>
            </div>
          </div>
        ) : isClarification ? (
          <ClarificationCard message={message} measureOptions={measureOptions} onSelectOption={onSelectOption} />
        ) : isUnanswerable ? (
          <UnanswerableCard message={message} onViewFields={onViewFields} onAskAnother={onAskAnother} />
        ) : kind === 'dataset_ready' ? (
          <div className="state-card state-ready">
            <div className="state-card-head">
              <span className="state-card-icon"><CheckCircleIcon size={16} /></span>
              <div className="state-card-title">Dataset Ready</div>
            </div>
            <div className="state-card-text"><RichText text={text} /></div>
            {onViewFields && (
              <div className="state-card-options">
                <button className="btn btn-secondary btn-sm" onClick={onViewFields}><TableIcon size={14} /> View detected schema</button>
              </div>
            )}
          </div>
        ) : (
          <article className="answer-card">
            {text && (
              <div className="answer-block">
                <div className="answer-label"><SparklesIcon size={13} /> Answer</div>
                <div className="answer-text"><RichText text={text} /></div>
                {status === 'no_dataset' && (
                  <Link to="/upload" className="btn btn-primary btn-sm" style={{ marginTop: 12 }}>
                    <UploadIcon size={14} /> Upload a dataset
                  </Link>
                )}
              </div>
            )}

            {decision_analysis && <DecisionAnalysis decision_analysis={decision_analysis} />}

            {geo && <GeoDecisionExplorer geo={geo} result={geo_result} evidence={geo_evidence} />}

            {hasVis && (
              <div className="answer-block answer-chart">
                <div className="answer-label"><BarChartIcon size={13} /> Chart</div>
                <VisualizationRenderer visualization={visualization} visualizations={visualizations} table={table} scalar={scalar} />
              </div>
            )}

            {trace && (
              <>
                <ExplanationTrace trace={trace} rawSpec={query_spec} />
                <EvidencePanel evidence={trace.evidence} />
              </>
            )}

            {timing && <ResponseTiming timing={timing} />}

            {error && <div className="answer-warning" role="alert"><AlertCircleIcon size={14} /> {error}</div>}


            {followUps.length > 0 && onSelectOption && (
              <div className="followups">
                <span className="section-label">Follow-up</span>
                <div className="followups-list">
                  {followUps.map((f) => (
                    <button key={f} className="followup-chip" onClick={() => onSelectOption(f)}>
                      <CornerDownRightIcon size={12} /> {f}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </article>
        )}
      </div>
    </div>
  )
}

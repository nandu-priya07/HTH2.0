import { useId, useState } from 'react'
import { ChevronDownIcon, CodeIcon } from '../ui/Icons'

/**
 * "How we got this answer" — Question → Intent → Fields → Operation → Result,
 * plus optional plain-language steps. Driven by lib/explain.buildExplanation().
 */
export default function ExplanationTrace({ trace, defaultOpen = false, rawSpec }) {
  const [open, setOpen] = useState(defaultOpen)
  const [showRaw, setShowRaw] = useState(false)
  const bodyId = useId()
  if (!trace) return null

  const stages = [
    trace.question && { label: 'Question', content: <span className="trace-question">“{trace.question}”</span> },
    trace.intent?.length && { label: 'Detected Intent', content: <span className="trace-chips">{trace.intent.map((t) => <span key={t} className="tag tag-teal mono">{t}</span>)}</span> },
    trace.fields?.length && { label: 'Fields Used', content: <span className="trace-chips">{trace.fields.map((f) => <span key={f} className="tag mono">{f}</span>)}</span> },
    trace.expression && { label: 'Operation', content: <code className="trace-code">{trace.expression}</code> },
    trace.result && { label: 'Result', content: <strong className="trace-result">{trace.result}</strong> }
  ].filter(Boolean)

  return (
    <section className={`trace${open ? ' is-open' : ''}`} aria-label="How we got this answer">
      <button
        type="button"
        className="trace-toggle"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="trace-toggle-icon" aria-hidden="true"><CodeIcon size={14} /></span>
        <span className="trace-toggle-text">How we got this answer</span>
        <span className="trace-toggle-hint">{stages.length} stages{trace.steps?.length ? ` · ${trace.steps.length} steps` : ''}</span>
        <ChevronDownIcon size={16} className="trace-caret" />
      </button>

      {open && (
        <div id={bodyId} className="trace-body animate-fade-in">
          <ol className="trace-flow">
            {stages.map((s, i) => (
              <li key={s.label} className="trace-stage" style={{ animationDelay: `${i * 60}ms` }}>
                <span className="trace-stage-label">{s.label}</span>
                <span className="trace-stage-content">{s.content}</span>
              </li>
            ))}
          </ol>

          {trace.steps?.length > 0 && (
            <div className="trace-steps">
              <div className="section-label">How this was calculated</div>
              <ol>
                {trace.steps.map((step, i) => <li key={i}>{step}</li>)}
              </ol>
            </div>
          )}

          {rawSpec && (
            <div className="trace-raw">
              <button type="button" className="trace-raw-toggle" aria-expanded={showRaw} onClick={() => setShowRaw((v) => !v)}>
                {showRaw ? 'Hide' : 'Show'} executed query spec (JSON)
              </button>
              {showRaw && <pre className="trace-raw-code">{JSON.stringify(rawSpec, null, 2)}</pre>}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

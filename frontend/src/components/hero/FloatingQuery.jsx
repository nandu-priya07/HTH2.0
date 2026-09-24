import { useState, useEffect } from 'react'
import { SparklesIcon, CheckCircleIcon } from '../ui/Icons'

/**
 * Floating Card #4 — Live AI Query.
 * Demonstrates QueryLens actively answering a natural language question.
 * Transitions: Question → Analyzing... → Result
 */
export default function FloatingQuery({ style, isHighlighted = false }) {
  // Step: 0 = Question, 1 = Analyzing, 2 = Result
  const [step, setStep] = useState(0)

  useEffect(() => {
    // Check prefers-reduced-motion
    const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    if (prefersReduced) {
      setStep(2) // stay on result
      return
    }

    let isMounted = true

    const runSequence = () => {
      if (!isMounted) return

      // Step 0: Question (0s to 3s)
      setStep(0)

      const t1 = setTimeout(() => {
        if (!isMounted) return
        // Step 1: Analyzing (3s to 5.2s)
        setStep(1)
      }, 3200)

      const t2 = setTimeout(() => {
        if (!isMounted) return
        // Step 2: Answer (5.2s to 10s)
        setStep(2)
      }, 5200)

      const t3 = setTimeout(() => {
        if (!isMounted) return
        runSequence()
      }, 10500)

      return () => {
        clearTimeout(t1)
        clearTimeout(t2)
        clearTimeout(t3)
      }
    }

    const cleanup = runSequence()
    return () => {
      isMounted = false
      cleanup?.()
    }
  }, [])

  return (
    <div
      className={`float-card fc-live-query ${isHighlighted ? 'is-highlighted' : ''}`}
      style={style}
    >
      <div className="fc-stage-tag stage-insight">INSIGHT</div>

      <div className="fc-query-header">
        <span className="fc-label accent">
          <span className="fc-node-dot dot-cyan" aria-hidden="true" />
          <SparklesIcon size={12} />
          <span>Ask AI · Natural Query</span>
        </span>
        {step === 2 && (
          <span className="fc-confidence-badge">98% confidence</span>
        )}
      </div>

      <div className="fc-query-body">
        {step === 0 && (
          <div className="fc-query-question">
            “Which region is growing fastest?”
          </div>
        )}

        {step === 1 && (
          <div className="fc-query-analyzing">
            <div className="pulse-dots" aria-hidden="true">
              <span /><span /><span />
            </div>
            <span>Analyzing dataset patterns...</span>
          </div>
        )}

        {step === 2 && (
          <div className="fc-query-answer">
            <div className="fc-answer-main">
              <CheckCircleIcon size={14} className="fc-answer-icon" />
              <strong>West Region</strong>
              <span className="fc-badge-up">↑ 24.7%</span>
            </div>
            <p className="fc-answer-caption">
              Driven by technology and enterprise volume.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

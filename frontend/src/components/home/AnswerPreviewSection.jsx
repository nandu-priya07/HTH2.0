import { SectionHeading, PreviewBadge, Link } from '../ui/primitives'
import { HBarList } from '../analytics/MiniCharts'
import ExplanationTrace from '../analytics/ExplanationTrace'
import { EXAMPLE_ANSWER } from '../../mocks/previewData'
import { SparklesIcon, ArrowRightIcon } from '../ui/Icons'

const QUESTION_TYPES = [
  { type: 'Aggregation', q: 'What is total revenue?' },
  { type: 'Ranking', q: 'Which region has the highest revenue?' },
  { type: 'Comparison', q: 'Compare revenue across regions.' },
  { type: 'Trend', q: 'How did revenue change over time?' },
  { type: 'Filtering', q: 'What were sales in the West region?' },
  { type: 'Top-N', q: 'Show the top 5 products.' },
  { type: 'Distribution', q: 'How are sales distributed across categories?' }
]

export default function AnswerPreviewSection() {
  const ex = EXAMPLE_ANSWER
  return (
    <section className="home-section answer-section" aria-labelledby="answer-title">
      <div className="container answer-grid">
        <div>
          <SectionHeading
            eyebrow="Explanation-first"
            title={<span id="answer-title">An answer you can <span className="text-accent">verify</span></span>}
            description="Every response comes as a direct answer, a chart chosen for the question, and the exact calculation — so nobody has to take the number on faith."
          />
          <div className="qtype-list">
            <div className="section-label">7 question types, any schema</div>
            <ul>
              {QUESTION_TYPES.map((t) => (
                <li key={t.type}>
                  <span className="qtype-name">{t.type}</span>
                  <span className="qtype-q">“{t.q}”</span>
                </li>
              ))}
            </ul>
          </div>
          <Link to="/ask-ai" className="btn-3d btn-3d-primary" style={{ marginTop: 24 }}>
            Try it on your data <ArrowRightIcon size={16} />
          </Link>
        </div>

        <div className="card answer-preview">
          <div className="answer-preview-top">
            <span className="answer-preview-q">{ex.question}</span>
            <PreviewBadge>Example</PreviewBadge>
          </div>
          <div className="answer-block">
            <div className="answer-label"><SparklesIcon size={13} /> Answer</div>
            <p className="answer-text">{ex.answer}</p>
          </div>
          <div className="answer-block">
            <div className="answer-label">Chart · Revenue by Region</div>
            <HBarList items={ex.bars} format={(v) => `$${v.toFixed(2)}M`} />
          </div>
          <ExplanationTrace
            defaultOpen
            trace={{
              question: ex.question,
              intent: ex.intent,
              fields: ex.fields,
              expression: ex.expression,
              result: ex.result
            }}
          />
        </div>
      </div>
    </section>
  )
}

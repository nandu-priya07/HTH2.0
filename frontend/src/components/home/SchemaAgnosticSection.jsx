import { SectionHeading } from '../ui/primitives'
import { FileSpreadsheetIcon, ArrowDownIcon, CheckCircleIcon, SparklesIcon } from '../ui/Icons'

const DATASETS = [
  {
    name: 'SALES',
    fields: ['Revenue', 'Region', 'Product', 'Date'],
    tone: 'teal'
  },
  {
    name: 'RETAIL',
    fields: ['Amount', 'Store', 'Category', 'Timestamp'],
    tone: 'cyan'
  },
  {
    name: 'OPERATIONS',
    fields: ['Cost', 'Plant', 'Department', 'Month'],
    tone: 'sage'
  }
]

export default function SchemaAgnosticSection() {
  return (
    <section className="home-section schema-section" aria-labelledby="schema-title">
      <div className="container">
        <SectionHeading
          eyebrow="Schema-Agnostic"
          title={<span id="schema-title">Any dataset. <span className="text-accent">No fixed schema.</span></span>}
          description="QueryLens adapts to the structure of your data."
          align="center"
        />

        <div className="schema-system-flow">
          {/* Top: 3 compact dataset cards */}
          <div className="schema-compact-grid">
            {DATASETS.map((ds) => (
              <div key={ds.name} className={`schema-compact-card tone-${ds.tone}`}>
                <div className="schema-compact-head">
                  <span className="schema-compact-icon"><FileSpreadsheetIcon size={14} /></span>
                  <span className="schema-compact-name">{ds.name}</span>
                </div>
                <ul className="schema-compact-fields">
                  {ds.fields.map((field) => (
                    <li key={field} className="schema-compact-field">
                      <span className="schema-field-dot" />
                      <span>{field}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Convergence arrow */}
          <div className="schema-flow-arrow" aria-hidden="true">
            <span className="flow-vertical-line" />
            <span className="flow-arrow-head"><ArrowDownIcon size={18} /></span>
          </div>

          {/* Central QueryLens Hub */}
          <div className="schema-hub-card">
            <div className="schema-hub-mark" aria-hidden="true">
              <svg viewBox="0 0 32 32" width="26" height="26">
                <rect width="32" height="32" rx="8" fill="var(--teal-600)" />
                <rect x="8" y="17" width="4" height="7" rx="1.5" fill="#fff" />
                <rect x="14" y="12" width="4" height="12" rx="1.5" fill="#fff" opacity="0.85" />
                <rect x="20" y="8" width="4" height="16" rx="1.5" fill="var(--cyan-500)" />
              </svg>
            </div>
            <div className="schema-hub-info">
              <span className="schema-hub-title">QueryLens</span>
              <span className="schema-hub-sub">Universal Ingestion</span>
            </div>
          </div>

          {/* Arrow */}
          <div className="schema-flow-arrow sm" aria-hidden="true">
            <span className="flow-vertical-line sm" />
            <span className="flow-arrow-head"><ArrowDownIcon size={16} /></span>
          </div>

          {/* Step 2: Schema inferred */}
          <div className="schema-stage-pill">
            <CheckCircleIcon size={15} />
            <span>Schema inferred</span>
          </div>

          {/* Arrow */}
          <div className="schema-flow-arrow sm" aria-hidden="true">
            <span className="flow-vertical-line sm" />
            <span className="flow-arrow-head"><ArrowDownIcon size={16} /></span>
          </div>

          {/* Step 3: Ask naturally */}
          <div className="schema-outcome-card">
            <span className="schema-outcome-label">
              <SparklesIcon size={13} /> Ask naturally
            </span>
            <div className="schema-outcome-bubble">
              “What are our top performing categories by revenue?”
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}


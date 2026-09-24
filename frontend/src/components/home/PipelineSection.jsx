import { SectionHeading } from '../ui/primitives'
import { UploadIcon, TableIcon, MessageSquareIcon, CodeIcon, LightbulbIcon } from '../ui/Icons'

const STAGES = [
  { n: '01', title: 'Upload', label: 'CSV / Excel', icon: UploadIcon },
  { n: '02', title: 'Understand', label: 'Schema', icon: TableIcon },
  { n: '03', title: 'Ask', label: 'Natural language', icon: MessageSquareIcon },
  { n: '04', title: 'Analyze', label: 'Intent → Query', icon: CodeIcon },
  { n: '05', title: 'Explain', label: 'Answer + Evidence', icon: LightbulbIcon }
]

export default function PipelineSection() {
  return (
    <section className="home-section pipeline-section" aria-labelledby="pipeline-title">
      <div className="container">
        <SectionHeading
          eyebrow="Workflow"
          title={<span id="pipeline-title">From data to <span className="text-accent">insight.</span></span>}
          description="One simple flow."
          align="center"
        />
        <div className="pipeline-system">
          <ol className="pipeline-flow">
            {STAGES.map(({ n, title, label, icon: Icon }, i) => (
              <li key={n} className="pipeline-stage-item" style={{ '--stage-index': i }}>
                <div className="pipeline-card">
                  <div className="pipeline-card-top">
                    <span className="pipeline-num">{n}</span>
                    <span className="pipeline-icon"><Icon size={18} /></span>
                  </div>
                  <h3 className="pipeline-title">{title}</h3>
                  <div className="pipeline-label">{label}</div>
                </div>
                {i < STAGES.length - 1 && (
                  <div className="pipeline-arrow-track" aria-hidden="true">
                    <span className="pipeline-line" />
                    <span className="pipeline-arrow">→</span>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}


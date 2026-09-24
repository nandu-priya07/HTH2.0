import { PreviewBadge, Link } from '../components/ui/primitives'
import { DECISIONS } from '../mocks/previewData'
import { ShieldCheckIcon, TargetIcon, ArrowRightIcon } from '../components/ui/Icons'

export default function DecisionsPage() {
  return (
    <div className="page">
      <div className="container">
        <header className="page-header">
          <div>
            <div className="eyebrow">Decisions</div>
            <h1>Findings you can act on</h1>
            <p>
              A decision log built from analyses. Each entry pairs a finding with its evidence and supporting metrics —
              no recommendation is shown without the analysis behind it.
            </p>
          </div>
          <PreviewBadge />
        </header>

        <div className="decision-list">
          {DECISIONS.map((d) => (
            <article key={d.id} className="card decision-entry">
              <div className="decision-entry-main">
                <div className="section-label"><TargetIcon size={12} /> Finding</div>
                <p className="decision-finding">{d.finding}</p>
                <div className="decision-metrics">
                  {d.metrics.map((m) => (
                    <div key={m.label} className="stat-tile">
                      <div className="stat-tile-label">{m.label}</div>
                      <div className="stat-tile-value">{m.value}</div>
                    </div>
                  ))}
                </div>
              </div>
              <aside className="decision-entry-side">
                <div className="section-label"><ShieldCheckIcon size={12} /> Evidence</div>
                <ul className="decision-evidence">
                  {d.evidence.map((e) => <li key={e} className="mono">{e}</li>)}
                </ul>
                <div className="section-label" style={{ marginTop: 16 }}>Supporting analysis</div>
                <p className="muted">{d.analysis}</p>
              </aside>
            </article>
          ))}
        </div>

        <div className="card card-pad decision-cta">
          <div>
            <h3 className="card-title">Run a decision analysis on your own data</h3>
            <p className="card-subtitle">Ask a “should we…” or “how much would…” question in Ask AI. When the backend returns a decision analysis, it is shown with its factors, scenarios, boundary and counter-tests.</p>
          </div>
          <Link to="/ask-ai" className="btn btn-primary">Open Ask AI <ArrowRightIcon size={16} /></Link>
        </div>
      </div>
    </div>
  )
}

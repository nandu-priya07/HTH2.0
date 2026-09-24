import HeroVisualization from '../components/hero/HeroVisualization'
import PipelineSection from '../components/home/PipelineSection'
import SchemaAgnosticSection from '../components/home/SchemaAgnosticSection'
import AnswerPreviewSection from '../components/home/AnswerPreviewSection'
import { Link } from '../components/ui/primitives'
import { ArrowRightIcon, UploadIcon, CheckIcon } from '../components/ui/Icons'

export default function HomePage() {
  return (
    <div className="home">
      <section className="hero" aria-labelledby="hero-title">
        <div className="container hero-grid">
          <div className="hero-copy">
            <span className="eyebrow eyebrow-badge">
              <span className="eyebrow-dot" aria-hidden="true" />
              Natural Language Data Analyst
            </span>

            <h1 id="hero-title" className="hero-title">
              <span className="hero-title-line-1">Ask your data.</span>
              <span className="hero-title-line-2">
                <span className="hero-gradient-text">See what matters.</span>
              </span>
            </h1>

            <p className="hero-lead">
              Upload a dataset. Ask questions in plain language. Get clear answers.
            </p>

            <div className="hero-ctas">
              <Link to="/ask-ai" className="btn-3d btn-3d-primary">
                Explore your data <ArrowRightIcon size={16} />
              </Link>
              <Link to="/upload" className="btn-3d btn-3d-secondary">
                <UploadIcon size={16} /> Upload dataset
              </Link>
            </div>

            <div className="hero-feature-strip">
              <span className="hero-feature-item">
                <CheckIcon size={13} className="hero-feature-icon" /> Any dataset
              </span>
              <span className="hero-feature-item">
                <CheckIcon size={13} className="hero-feature-icon" /> No fixed schema
              </span>
              <span className="hero-feature-item">
                <CheckIcon size={13} className="hero-feature-icon" /> Explainable answers
              </span>
            </div>
          </div>

          <HeroVisualization />
        </div>

        <div className="container">
          <div className="hero-statement">
            <div className="hero-statement-main">Upload. Ask. Understand.</div>
            <div className="hero-statement-sub">Answers backed by your data.</div>
          </div>
        </div>
      </section>

      <PipelineSection />
      <SchemaAgnosticSection />
      <AnswerPreviewSection />

      <section className="home-section cta-band" aria-labelledby="cta-title">
        <div className="container cta-inner">
          <div>
            <h2 id="cta-title">Bring a spreadsheet you've never shown us.</h2>
            <p>Upload it and ask your first question in under a minute.</p>
          </div>
          <div className="row" style={{ flexWrap: 'wrap', gap: '14px' }}>
            <Link to="/upload" className="btn-3d btn-3d-cta-secondary">
              <UploadIcon size={16} /> Upload dataset
            </Link>
            <Link to="/ask-ai" className="btn-3d btn-3d-cta-primary">
              Explore your data <ArrowRightIcon size={16} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}

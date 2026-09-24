import { useState } from 'react'
import QueryLensHeroVisual from '../components/hero/QueryLensHeroVisual'
import PipelineSection from '../components/home/PipelineSection'
import SchemaAgnosticSection from '../components/home/SchemaAgnosticSection'
import AnswerPreviewSection from '../components/home/AnswerPreviewSection'
import { Link } from '../components/ui/primitives'
import { ArrowRightIcon, UploadIcon } from '../components/ui/Icons'

/* Product signals — each tone matches the part of the hero visual it lights up on hover:
   cyan = incoming data nodes, sage = data-quality card, coral = the located answer. */
const HERO_SIGNALS = [
  { id: 'signal-data', label: 'Any dataset', tone: 'analysis', mark: 'ring' },
  { id: 'signal-schema', label: 'No fixed schema', tone: 'valid', mark: 'diamond' },
  { id: 'signal-explain', label: 'Explainable answers', tone: 'geo', mark: 'arrow' }
]

export default function HomePage() {
  const [hoveredCta, setHoveredCta] = useState(null)

  return (
    <div className="home">
      <section className="hero" aria-labelledby="hero-title">
        <div className="container hero-grid">
          <div className="hero-copy">
            {/* Coordinate ruler: the lat/long of the "West Region" marker on the globe */}
            <div className="hero-ruler" aria-hidden="true">
              <span className="hero-ruler-coord">37.77°N</span>
              <span className="hero-ruler-track">
                <span className="hero-ruler-tick is-discovery" />
              </span>
              <span className="hero-ruler-coord">122.42°W</span>
            </div>

            <span className="eyebrow hero-eyebrow">
              <span className="hero-eyebrow-signal" aria-hidden="true" />
              Natural Language Data Analyst
            </span>

            <h1 id="hero-title" className="hero-title">
              <span className="hero-title-line-1">Ask your data.</span>
              <span className="hero-title-line-2">
                See what <span className="hero-mark">matters.</span>
              </span>
            </h1>

            <p className="hero-lead">
              Upload a dataset. Ask questions in plain language. Get clear answers.
            </p>

            <div className="hero-ctas">
              <Link
                to="/ask-ai"
                className="btn-3d btn-3d-primary"
                onMouseEnter={() => setHoveredCta('explore')}
                onMouseLeave={() => setHoveredCta(null)}
              >
                Explore your data <ArrowRightIcon size={16} />
              </Link>
              <Link
                to="/upload"
                className="btn-3d btn-3d-secondary"
                onMouseEnter={() => setHoveredCta('upload')}
                onMouseLeave={() => setHoveredCta(null)}
              >
                <UploadIcon size={16} /> Upload dataset
              </Link>
            </div>

            <ul className="hero-signals" aria-label="What QueryLens handles">
              {HERO_SIGNALS.map((s) => (
                <li
                  key={s.id}
                  className={`hero-signal signal-${s.tone}`}
                  onMouseEnter={() => setHoveredCta(s.id)}
                  onMouseLeave={() => setHoveredCta(null)}
                >
                  <span className={`hero-signal-mark mark-${s.mark}`} aria-hidden="true" />
                  {s.label}
                </li>
              ))}
            </ul>
          </div>

          <QueryLensHeroVisual hoveredCta={hoveredCta} />
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

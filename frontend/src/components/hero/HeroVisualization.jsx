import WorldDotMap from './WorldDotMap'
import FloatingCards from './FloatingCards'
import { HERO_NODES, HERO_MARKER, HERO_ARCS } from '../../mocks/previewData'

/**
 * Hero visual for the Home page.
 *
 * To swap in the looping Google Flow video later, pass `videoSrc`
 * (and optionally `poster`). The floating cards stay layered on top:
 *
 *   <HeroVisualization videoSrc="/media/hero-loop.mp4" poster="/media/hero.jpg" />
 */
export default function HeroVisualization({ videoSrc, poster, showCards = true }) {
  return (
    <div className="hero-visual" aria-label="Illustration: global data connected into AI insights">
      <div className="hero-visual-stage">
        {videoSrc ? (
          <video
            className="hero-video"
            src={videoSrc}
            poster={poster}
            autoPlay
            muted
            loop
            playsInline
            aria-hidden="true"
          />
        ) : (
          <WorldDotMap
            nodes={HERO_NODES}
            marker={HERO_MARKER}
            arcs={HERO_ARCS}
            title="Global analytics map with connected data nodes"
          />
        )}
      </div>
      {showCards && <FloatingCards />}
    </div>
  )
}

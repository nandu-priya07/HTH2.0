import QueryLensHeroVisual from './QueryLensHeroVisual'

/**
 * Hero visual for the Home page.
 * Wraps the unified QueryLensHeroVisual component.
 */
export default function HeroVisualization({ hoveredCta = null }) {
  return <QueryLensHeroVisual hoveredCta={hoveredCta} />
}

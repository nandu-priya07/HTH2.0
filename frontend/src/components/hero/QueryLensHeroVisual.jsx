import { useState, useEffect, useRef } from 'react'
import HeroVideo from './HeroVideo'
import GlobeGlow from './GlobeGlow'
import GlobeMarker from './GlobeMarker'
import DataConnections from './DataConnections'
import DataNode from './DataNode'
import AmbientParticles from './AmbientParticles'
import FloatingRevenue from './FloatingRevenue'
import FloatingRegion from './FloatingRegion'
import FloatingQuality from './FloatingQuality'
import FloatingQuery from './FloatingQuery'
import heroVideoAsset from '../../assets/Analytics_homepage_hero_animatio…_1080p_20260924184427.mp4'

/**
 * QueryLensHeroVisual Component.
 * The core visual engine for the QueryLens homepage.
 *
 * Integrates:
 * Layer 1 (Atmosphere): Breathing radial globe glow + ambient data particles
 * Layer 2 (Video): Looping 1080p geospatial data globe with vignette blending
 * Layer 3 (Data Infrastructure): Live location marker, connection paths, and data nodes
 * Layer 4 (UI Floating Ecosystem): Revenue pulse, regional insight, live query, and data quality gauge
 *
 * Includes subtle multi-layer mouse parallax with prefers-reduced-motion support.
 */
export default function QueryLensHeroVisual({ hoveredCta = null }) {
  const containerRef = useRef(null)
  const [offsets, setOffsets] = useState({ x: 0, y: 0 })
  const targetOffsets = useRef({ x: 0, y: 0 })
  const rafId = useRef(null)

  useEffect(() => {
    // Check prefers-reduced-motion
    const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    if (prefersReduced) return

    const container = containerRef.current
    if (!container) return

    const handleMouseMove = (e) => {
      const rect = container.getBoundingClientRect()
      const centerX = rect.left + rect.width / 2
      const centerY = rect.top + rect.height / 2
      const deltaX = (e.clientX - centerX) / (rect.width / 2)
      const deltaY = (e.clientY - centerY) / (rect.height / 2)

      // Clamp between -1 and 1
      targetOffsets.current = {
        x: Math.max(-1, Math.min(1, deltaX)),
        y: Math.max(-1, Math.min(1, deltaY))
      }
    }

    const handleMouseLeave = () => {
      targetOffsets.current = { x: 0, y: 0 }
    }

    // Smooth lerp loop
    const lerp = (a, b, n) => (1 - n) * a + n * b
    let currentX = 0
    let currentY = 0

    const updateParallax = () => {
      currentX = lerp(currentX, targetOffsets.current.x, 0.08)
      currentY = lerp(currentY, targetOffsets.current.y, 0.08)
      setOffsets({
        x: Math.round(currentX * 100) / 100,
        y: Math.round(currentY * 100) / 100
      })
      rafId.current = requestAnimationFrame(updateParallax)
    }

    window.addEventListener('mousemove', handleMouseMove, { passive: true })
    container.addEventListener('mouseleave', handleMouseLeave)
    rafId.current = requestAnimationFrame(updateParallax)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      container.removeEventListener('mouseleave', handleMouseLeave)
      if (rafId.current) cancelAnimationFrame(rafId.current)
    }
  }, [])

  // Depth transforms
  const atmosphereTransform = `translate3d(${offsets.x * 2}px, ${offsets.y * 2}px, 0)`
  const videoTransform = `translate3d(${offsets.x * 3.5}px, ${offsets.y * 3.5}px, 0)`
  const cardsTransform = `translate3d(${offsets.x * 6.5}px, ${offsets.y * 6.5}px, 0)`
  const nodesTransform = `translate3d(${offsets.x * 8.5}px, ${offsets.y * 8.5}px, 0)`

  return (
    <div
      ref={containerRef}
      className={`querylens-hero-visual ${hoveredCta ? `hover-${hoveredCta}` : ''}`}
      aria-label="Interactive QueryLens analytical visual engine"
    >
      {/* LAYER 1: ATMOSPHERE */}
      <div className="hero-depth-layer layer-atmosphere" style={{ transform: atmosphereTransform }}>
        <GlobeGlow isHighlighted={hoveredCta === 'explore'} />
        <AmbientParticles />
      </div>

      {/* LAYER 2: VIDEO ENGINE */}
      <div className="hero-depth-layer layer-video" style={{ transform: videoTransform }}>
        <HeroVideo
          src={heroVideoAsset}
          isHighlighted={hoveredCta === 'explore'}
        />
      </div>

      {/* LAYER 3: LIVE GEOSPATIAL INFRASTRUCTURE */}
      <div className="hero-depth-layer layer-nodes" style={{ transform: nodesTransform }}>
        <DataConnections />
        <GlobeMarker x="40%" y="46%" label="West Region" />
        {/* Video data nodes: cyan = analytical streams, blue = continent nodes, pin = geographic marker, ice = white-hot burst */}
        <DataNode x="22%" y="38%" tone="cyan" delay="0.4s" />
        <DataNode x="72%" y="34%" tone="blue" delay="1.1s" />
        <DataNode x="64%" y="62%" tone="pin" delay="1.8s" />
        <DataNode x="30%" y="68%" tone="cyan" delay="1.5s" />
      </div>

      {/* LAYER 4: FLOATING ANALYTICAL COMPONENTS */}
      <div className="hero-depth-layer layer-cards" style={{ transform: cardsTransform }}>
        {/* Card 1: Revenue Pulse (Top Left) */}
        <FloatingRevenue
          isHighlighted={hoveredCta === 'explore'}
        />

        {/* Card 2: Regional Insight (Bottom Left) — the located, explainable answer */}
        <FloatingRegion
          isHighlighted={hoveredCta === 'explore' || hoveredCta === 'signal-explain'}
        />

        {/* Card 3: Data Quality (Top Right) — schema inference on upload */}
        <FloatingQuality
          isHighlighted={hoveredCta === 'upload' || hoveredCta === 'signal-schema'}
        />

        {/* Card 4: Live Query (Bottom Right) */}
        <FloatingQuery
          isHighlighted={hoveredCta === 'explore'}
        />
      </div>
    </div>
  )
}

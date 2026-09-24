import { useRef, useEffect, useState } from 'react'
import WorldDotMap from './WorldDotMap'
import { HERO_NODES, HERO_MARKER, HERO_ARCS } from '../../mocks/previewData'

/**
 * HeroVideo Component.
 * Plays the looping globe visualization with atmospheric framing,
 * soft boundary blending, and reduced-motion handling.
 */
export default function HeroVideo({ src, poster, isHighlighted = false }) {
  const videoRef = useRef(null)
  const [hasError, setHasError] = useState(false)
  const [isLoaded, setIsLoaded] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    // Check prefers-reduced-motion
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handleMotionChange = (e) => {
      if (e.matches) {
        video.pause()
      } else {
        video.play().catch(() => {})
      }
    }

    if (mediaQuery.matches) {
      video.pause()
    } else {
      video.play().catch(() => {
        // Autoplay may be deferred until user interaction in some strict browsers
      })
    }

    mediaQuery.addEventListener?.('change', handleMotionChange)
    return () => {
      mediaQuery.removeEventListener?.('change', handleMotionChange)
    }
  }, [])

  if (hasError) {
    return (
      <WorldDotMap
        nodes={HERO_NODES}
        marker={HERO_MARKER}
        arcs={HERO_ARCS}
        title="Global analytics map with connected data nodes"
      />
    )
  }

  return (
    <div className={`hero-video-frame ${isHighlighted ? 'is-highlighted' : ''}`}>
      {/* Soft atmospheric radial vignette mask */}
      <div className="hero-video-vignette" />

      {/* Actual video element */}
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        autoPlay
        muted
        loop
        playsInline
        aria-hidden="true"
        className={`hero-video-element ${isLoaded ? 'is-loaded' : ''}`}
        onLoadedData={() => setIsLoaded(true)}
        onError={() => setHasError(true)}
      />

      {/* Ambient glass border highlight */}
      <div className="hero-video-border-shine" />
    </div>
  )
}

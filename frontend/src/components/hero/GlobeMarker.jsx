/**
 * Primary Geographic Location Marker.
 * Positioned on the active region of the globe visual.
 * Coral #FCA47C with subtle pulsing halo and radial glow.
 */
export default function GlobeMarker({ x = '42%', y = '48%', label = 'West Region' }) {
  return (
    <div
      className="hero-globe-marker"
      style={{
        position: 'absolute',
        left: x,
        top: y,
        transform: 'translate(-50%, -50%)',
        zIndex: 5,
        pointerEvents: 'none'
      }}
      aria-hidden="true"
    >
      {/* Outer ambient glow */}
      <div className="marker-radial-glow" />

      {/* Pulsing ring */}
      <div className="marker-pulse-ring" />

      {/* Core point */}
      <div className="marker-core-point" />

      {/* Optional micro label */}
      {label && (
        <div className="marker-micro-label">
          <span className="marker-micro-dot" />
          {label}
        </div>
      )}
    </div>
  )
}

/**
 * Atmospheric GlobeGlow component.
 * Creates a soft breathing cyan/teal glow centered on the globe visual.
 */
export default function GlobeGlow({ isHighlighted = false }) {
  return (
    <div
      className={`hero-globe-glow ${isHighlighted ? 'is-highlighted' : ''}`}
      aria-hidden="true"
    >
      {/* Primary cyan luminous halo */}
      <div className="glow-cyan-layer" />
      {/* Secondary deep-teal ambient depth */}
      <div className="glow-blue-depth" />
    </div>
  )
}

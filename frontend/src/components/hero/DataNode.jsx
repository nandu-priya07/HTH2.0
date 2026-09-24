/**
 * DataNode component.
 * Small analytical node dot with core and pulsing halo around the globe.
 */
export default function DataNode({ x, y, tone = 'cyan', delay = '0s', label }) {
  return (
    <div
      className={`hero-data-node tone-${tone}`}
      style={{
        left: x,
        top: y,
        animationDelay: delay
      }}
      aria-hidden="true"
    >
      <div className="data-node-halo" />
      <div className="data-node-core" />
      {label && <span className="data-node-label">{label}</span>}
    </div>
  )
}

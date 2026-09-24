import { memo } from 'react'
import { LAND_CELLS, MASK_COLS, MASK_ROWS, project } from '../../lib/worldMask'

const CELL = 10
const W = MASK_COLS * CELL
const H = MASK_ROWS * CELL

const toXY = ({ lon, lat }) => {
  const { col, row } = project(lon, lat)
  return { x: col * CELL, y: row * CELL }
}

function arcPath(a, b) {
  const p1 = toXY(a)
  const p2 = toXY(b)
  const mx = (p1.x + p2.x) / 2
  const my = (p1.y + p2.y) / 2 - Math.min(90, Math.hypot(p2.x - p1.x, p2.y - p1.y) * 0.32)
  return `M${p1.x},${p1.y} Q${mx},${my} ${p2.x},${p2.y}`
}

/**
 * Dot-matrix world map.
 *  - nodes:   [{ lon, lat, tone: 'cyan'|'sage'|'yellow', r?, label? }]
 *  - marker:  { lon, lat, label }  — coral "you are here" pin
 *  - arcs:    [[nodeIndexA, nodeIndexB], …]
 *  - cellFill: optional (cell) => CSS color, for choropleth-style shading
 *  - heat:    optional [{ lon, lat, intensity 0..1 }] soft density blobs
 */
function WorldDotMap({ nodes = [], marker, arcs = [], cellFill, heat = [], animated = true, className = '', title = 'World map' }) {
  return (
    <svg
      className={`world-map${animated ? ' is-animated' : ''} ${className}`}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={title}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <radialGradient id="wm-heat" r="0.5">
          <stop offset="0%" stopColor="var(--cyan-500)" stopOpacity="0.55" />
          <stop offset="60%" stopColor="var(--teal-600)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--teal-600)" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="wm-glow" r="0.5">
          <stop offset="0%" stopColor="var(--coral-500)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--coral-500)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Land dots */}
      <g className="wm-land">
        {LAND_CELLS.map((cell) => (
          <circle
            key={`${cell.col}-${cell.row}`}
            cx={cell.col * CELL + CELL / 2}
            cy={cell.row * CELL + CELL / 2}
            r={2.6}
            style={cellFill ? { fill: cellFill(cell) } : undefined}
          />
        ))}
      </g>

      {/* Density blobs */}
      {heat.length > 0 && (
        <g className="wm-heat">
          {heat.map((h, i) => {
            const { x, y } = toXY(h)
            const r = 26 + 46 * (h.intensity ?? 0.5)
            return <circle key={i} cx={x} cy={y} r={r} fill="url(#wm-heat)" style={{ animationDelay: `${i * 0.6}s` }} />
          })}
        </g>
      )}

      {/* Connection arcs */}
      <g className="wm-arcs">
        {arcs.map(([a, b], i) =>
          nodes[a] && nodes[b] ? (
            <path key={i} d={arcPath(nodes[a], nodes[b])} style={{ animationDelay: `${i * 0.7}s` }} />
          ) : null
        )}
      </g>

      {/* Data nodes */}
      <g className="wm-nodes">
        {nodes.map((n, i) => {
          const { x, y } = toXY(n)
          const r = n.r ?? 4
          return (
            <g key={i} className={`wm-node tone-${n.tone || 'cyan'}`} style={{ animationDelay: `${(i % 5) * 0.5}s` }}>
              <circle className="wm-node-halo" cx={x} cy={y} r={r * 2.4} />
              <circle className="wm-node-core" cx={x} cy={y} r={r} />
              {n.label && <title>{n.label}</title>}
            </g>
          )
        })}
      </g>

      {/* Location marker */}
      {marker && (() => {
        const { x, y } = toXY(marker)
        return (
          <g className="wm-marker" transform={`translate(${x} ${y})`}>
            <circle r="26" fill="url(#wm-glow)" className="wm-marker-glow" />
            <g className="wm-marker-pin">
              <circle r="7" className="wm-marker-ring" />
              <circle r="4" className="wm-marker-core" />
            </g>
            {marker.label && <title>{marker.label}</title>}
          </g>
        )
      })()}
    </svg>
  )
}

export default memo(WorldDotMap)

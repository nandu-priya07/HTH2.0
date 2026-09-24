/**
 * Lightweight SVG micro-charts for cards (no axes). Single-series by design:
 * the card title names the series, so no legend is needed.
 * Each mark carries a <title> so values are reachable on hover / by AT.
 */

export function Sparkline({ data = [], width = 160, height = 44, area = true, label = 'Trend', highlightIndex }) {
  if (!data.length) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const pad = 4
  const step = (width - pad * 2) / Math.max(1, data.length - 1)
  const pts = data.map((v, i) => [pad + i * step, pad + (1 - (v - min) / span) * (height - pad * 2)])
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const last = pts[pts.length - 1]
  const hi = highlightIndex !== undefined ? pts[highlightIndex] : null

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label={`${label}: ${data.join(', ')}`} preserveAspectRatio="none">
      {area && <path d={`${line} L${last[0]},${height} L${pts[0][0]},${height} Z`} className="sparkline-area" />}
      <path d={line} className="sparkline-line" vectorEffect="non-scaling-stroke" />
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="6" className="sparkline-hit"><title>{data[i]}</title></circle>
      ))}
      <circle cx={last[0]} cy={last[1]} r="3" className="sparkline-end" />
      {hi && <circle cx={hi[0]} cy={hi[1]} r="4" className="sparkline-alert" />}
    </svg>
  )
}

export function MiniBars({ data = [], labels = [], height = 64, highlight = 0, format = (v) => v, showLabels = true }) {
  if (!data.length) return null
  const max = Math.max(...data) || 1
  return (
    <div className="mini-bars" style={{ height: height + (showLabels ? 20 : 0) }} role="img" aria-label={labels.map((l, i) => `${l}: ${format(data[i])}`).join(', ')}>
      {data.map((v, i) => (
        <div key={i} className="mini-bar-col" title={`${labels[i] ?? ''} ${format(v)}`}>
          <div className="mini-bar-track" style={{ height }}>
            <div className={`mini-bar${i === highlight ? ' is-highlight' : ''}`} style={{ height: `${Math.max(4, (v / max) * 100)}%` }} />
          </div>
          {showLabels && <span className="mini-bar-label">{labels[i]}</span>}
        </div>
      ))}
    </div>
  )
}

/** Horizontal bars with direct value labels — used where values must read at a glance. */
export function HBarList({ items = [], format = (v) => v, highlight = 0 }) {
  const max = Math.max(...items.map((i) => i.value)) || 1
  return (
    <ul className="hbar-list">
      {items.map((it, i) => (
        <li key={it.label}>
          <span className="hbar-label">{it.label}</span>
          <span className="hbar-track">
            <span className={`hbar-fill${i === highlight ? ' is-highlight' : ''}`} style={{ width: `${(it.value / max) * 100}%` }} />
          </span>
          <span className="hbar-value">{format(it.value)}</span>
        </li>
      ))}
    </ul>
  )
}

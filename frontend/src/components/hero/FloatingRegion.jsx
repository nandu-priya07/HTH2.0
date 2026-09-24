import { GlobeIcon } from '../ui/Icons'

/**
 * Floating Card #2 — Regional Insight.
 * West Region $2.8M, +34.7% with mini distribution bars.
 */
export default function FloatingRegion({ style, isHighlighted = false }) {
  const bars = [
    { label: 'East', val: 42 },
    { label: 'Cent', val: 30 },
    { label: 'South', val: 55 },
    { label: 'West', val: 95, isTop: true }
  ]

  return (
    <div
      className={`float-card fc-region-insight ${isHighlighted ? 'is-highlighted' : ''}`}
      style={style}
    >
      <div className="fc-stage-tag stage-analysis">ANALYSIS</div>
      <div className="fc-label">
        <GlobeIcon size={12} />
        <span>Top Performing Region</span>
      </div>

      <div className="fc-region-split">
        <div>
          <div className="fc-value sm">West Region</div>
          <div className="fc-sub">$2.8M <span className="fc-badge-up">+34.7%</span></div>
        </div>

        {/* Mini distribution bars */}
        <div className="fc-mini-bars" aria-hidden="true">
          {bars.map((b) => (
            <div key={b.label} className="fc-mini-bar-col">
              <div
                className={`fc-mini-bar-fill ${b.isTop ? 'is-top' : ''}`}
                style={{ height: `${b.val}%` }}
              />
              <span className="fc-mini-bar-label">{b.label[0]}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

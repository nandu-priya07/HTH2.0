import { TrendingUpIcon } from '../ui/Icons'

/**
 * Floating Card #1 — Revenue Pulse.
 * Total Revenue $12.8M, ↑ 12.9% with animated SVG sparkline.
 */
export default function FloatingRevenue({ style, isHighlighted = false }) {
  // Smooth SVG sparkline coordinates
  const sparklinePoints = "4,28 18,24 32,26 46,18 60,20 74,12 88,14 102,6 116,8 130,3"

  return (
    <div
      className={`float-card fc-revenue-pulse ${isHighlighted ? 'is-highlighted' : ''}`}
      style={style}
    >
      <div className="fc-stage-tag stage-analysis">ANALYSIS</div>
      <div className="fc-label">Total Revenue</div>
      <div className="fc-value">$12.8M</div>
      <div className="fc-delta up">
        <TrendingUpIcon size={12} />
        <span>12.9% vs last period</span>
      </div>

      {/* Animated SVG Sparkline */}
      <div className="fc-sparkline-wrap" aria-hidden="true">
        <svg viewBox="0 0 134 32" className="fc-sparkline-svg">
          <defs>
            <linearGradient id="revAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#23CED9" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#23CED9" stopOpacity="0.0" />
            </linearGradient>
            {/* Analysis accent: teal into cyan */}
            <linearGradient id="revStrokeGrad" x1="0" y1="0" x2="100%" y2="0">
              <stop offset="0%" stopColor="#097C87" />
              <stop offset="100%" stopColor="#23CED9" />
            </linearGradient>
          </defs>
          {/* Shaded area */}
          <polygon
            points={`4,30 ${sparklinePoints} 130,30`}
            fill="url(#revAreaGrad)"
          />
          {/* Stroke path */}
          <polyline
            points={sparklinePoints}
            fill="none"
            stroke="url(#revStrokeGrad)"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="fc-sparkline-line"
          />
          {/* Latest value = the discovery point (warm yellow) */}
          <circle cx="130" cy="3" r="3.5" fill="#F9D779" stroke="#FFFFFF" strokeWidth="1.5" className="fc-spark-point" />
        </svg>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { ShieldCheckIcon } from '../ui/Icons'

/**
 * Floating Card #3 — Data Quality.
 * 96% circular gauge with schema inference and interactive micro expansion.
 */
export default function FloatingQuality({ style, isHighlighted = false }) {
  const [isHovered, setIsHovered] = useState(false)
  const pct = 96
  const radius = 18
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (pct / 100) * circumference

  return (
    <div
      className={`float-card fc-quality-pulse ${isHighlighted ? 'is-highlighted' : ''}`}
      style={style}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      tabIndex={0}
      role="region"
      aria-label="Dataset Quality: 96%"
    >
      <div className="fc-stage-tag stage-data">DATA</div>

      <div className="fc-quality-content">
        {/* Animated circular gauge */}
        <div className="fc-circular-gauge" aria-hidden="true">
          <svg width="44" height="44" viewBox="0 0 44 44">
            {/* Gradient definition */}
            <defs>
              {/* Validation accent: emerald into deep green */}
              <linearGradient id="qualityGaugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#34d399" />
                <stop offset="100%" stopColor="#059669" />
              </linearGradient>
            </defs>
            {/* Background track */}
            <circle
              cx="22"
              cy="22"
              r={radius}
              fill="none"
              stroke="#e2edf8"
              strokeWidth="3.5"
            />
            {/* Animated progress circle */}
            <circle
              cx="22"
              cy="22"
              r={radius}
              fill="none"
              stroke="url(#qualityGaugeGrad)"
              strokeWidth="3.5"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              className="fc-gauge-progress"
              transform="rotate(-90 22 22)"
            />
          </svg>
          <span className="fc-gauge-text">{pct}%</span>
        </div>

        <div>
          <div className="fc-label">
            <ShieldCheckIcon size={12} />
            <span>Data Quality</span>
          </div>
          <div className="fc-sub">Schema inferred · 28 fields</div>
        </div>
      </div>

      {/* Interactive Micro Detail Tooltip */}
      {isHovered && (
        <div className="fc-quality-tooltip" role="tooltip">
          <span>28 valid fields</span>
          <span className="dot-sep">·</span>
          <span>3 missing imputed</span>
          <span className="dot-sep">·</span>
          <span>0 type errors</span>
        </div>
      )}
    </div>
  )
}

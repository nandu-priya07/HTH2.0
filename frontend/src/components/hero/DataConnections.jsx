/**
 * SVG Connection Paths with animated data pulses.
 * Connects the active globe node to the floating regional insight card.
 */
export default function DataConnections() {
  return (
    <svg
      className="hero-data-connections"
      viewBox="0 0 600 480"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 4
      }}
    >
      <defs>
        {/* Video data arcs: glowing cyan fading into continent cobalt / orchid */}
        <linearGradient id="connGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.85" />
          <stop offset="100%" stopColor="#2563eb" stopOpacity="0.35" />
        </linearGradient>

        <linearGradient id="connGrad2" x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#a052e5" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.25" />
        </linearGradient>

        {/* Glow filter for traveling data pulses */}
        <filter id="pulseGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Path 1: From Regional Card (bottom left) to Globe Marker (~250, 230) */}
      <path
        id="path-card-to-globe"
        d="M 140 370 C 180 340, 210 280, 252 230"
        stroke="url(#connGrad)"
        strokeWidth="1.5"
        strokeDasharray="4 4"
        className="conn-path-dash"
      />

      {/* Path 2: Cross-connection from Globe Marker to East node */}
      <path
        id="path-globe-to-node"
        d="M 252 230 C 320 200, 390 220, 440 260"
        stroke="url(#connGrad2)"
        strokeWidth="1.2"
        strokeDasharray="3 3"
        opacity="0.5"
      />

      {/* Path 3: Upward subtle link towards Revenue pulse */}
      <path
        d="M 252 230 C 220 170, 180 130, 150 90"
        stroke="#38bdf8"
        strokeWidth="1"
        strokeDasharray="2 3"
        opacity="0.35"
      />

      {/* Traveling Data Pulse Dot along Path 1 */}
      <circle r="3.5" fill="#38bdf8" filter="url(#pulseGlow)">
        <animateMotion
          dur="3.6s"
          repeatCount="indefinite"
          path="M 140 370 C 180 340, 210 280, 252 230"
          keyPoints="0;1"
          keyTimes="0;1"
        />
      </circle>

      {/* Secondary Traveling Pulse Dot along Path 2 */}
      <circle r="2.5" fill="#FFFFFF" opacity="0.9" filter="url(#pulseGlow)">
        <animateMotion
          dur="4.8s"
          repeatCount="indefinite"
          path="M 252 230 C 320 200, 390 220, 440 260"
          keyPoints="0;1"
          keyTimes="0;1"
        />
      </circle>
    </svg>
  )
}

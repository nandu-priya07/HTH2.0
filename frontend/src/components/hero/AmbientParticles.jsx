/**
 * Ambient Particles.
 * 16 lightweight drifting particle dots with varying delays and low opacities.
 */
export default function AmbientParticles() {
  const particles = [
    { x: '18%', y: '22%', size: 3, delay: '0s', dur: '8s', tone: 'cyan' },
    { x: '28%', y: '14%', size: 2.5, delay: '2s', dur: '10s', tone: 'blue' },
    { x: '72%', y: '18%', size: 3.5, delay: '1s', dur: '7s', tone: 'ice' },
    { x: '82%', y: '28%', size: 2, delay: '3.5s', dur: '9s', tone: 'cyan' },
    { x: '88%', y: '45%', size: 3, delay: '0.8s', dur: '8.5s', tone: 'blue' },
    { x: '78%', y: '68%', size: 2.5, delay: '2.4s', dur: '11s', tone: 'pin' },
    { x: '68%', y: '82%', size: 3, delay: '4s', dur: '7.5s', tone: 'blue' },
    { x: '35%', y: '85%', size: 2, delay: '1.2s', dur: '9.2s', tone: 'ice' },
    { x: '14%', y: '74%', size: 3.5, delay: '3s', dur: '8s', tone: 'cyan' },
    { x: '10%', y: '48%', size: 2.5, delay: '0.5s', dur: '10.5s', tone: 'blue' },
    { x: '24%', y: '36%', size: 2, delay: '2.8s', dur: '8.8s', tone: 'ice' },
    { x: '62%', y: '26%', size: 3, delay: '1.6s', dur: '7.8s', tone: 'cyan' },
    { x: '58%', y: '72%', size: 2.5, delay: '4.2s', dur: '9.6s', tone: 'pin' },
    { x: '42%', y: '18%', size: 2, delay: '0.2s', dur: '11.2s', tone: 'ice' },
    { x: '85%', y: '58%', size: 2.5, delay: '3.1s', dur: '8.2s', tone: 'cyan' },
    { x: '16%', y: '62%', size: 2, delay: '1.9s', dur: '9.8s', tone: 'blue' }
  ]

  return (
    <div className="hero-ambient-particles" aria-hidden="true">
      {particles.map((p, idx) => (
        <span
          key={idx}
          className={`ambient-particle tone-${p.tone}`}
          style={{
            left: p.x,
            top: p.y,
            width: `${p.size}px`,
            height: `${p.size}px`,
            animationDelay: p.delay,
            animationDuration: p.dur
          }}
        />
      ))}
    </div>
  )
}

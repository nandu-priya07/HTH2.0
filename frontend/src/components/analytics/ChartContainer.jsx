/**
 * Generic frame for any visualization (bar, line, area, donut, scatter,
 * table, map…). Keeps header / legend / actions consistent across pages.
 */
export default function ChartContainer({ title, subtitle, badge, actions, legend, children, footer, className = '' }) {
  return (
    <section className={`chart-container card ${className}`} aria-label={typeof title === 'string' ? title : undefined}>
      {(title || actions || badge) && (
        <header className="chart-container-head">
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          <div className="row" style={{ flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {badge}
            {actions}
          </div>
        </header>
      )}
      {legend && (
        <ul className="chart-legend">
          {legend.map((l) => (
            <li key={l.label}><span className="chart-legend-swatch" style={{ background: l.color }} />{l.label}</li>
          ))}
        </ul>
      )}
      <div className="chart-container-body">{children}</div>
      {footer && <footer className="chart-container-foot">{footer}</footer>}
    </section>
  )
}

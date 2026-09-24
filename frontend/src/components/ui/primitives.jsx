import { navigate } from '../../lib/router'
import { SEMANTIC_TYPE_META } from '../../lib/dataset'
import { AlertCircleIcon } from './Icons'

/** Client-side link: keeps a real <a href> for accessibility / new-tab. */
export function Link({ to, children, className = '', onClick, ...rest }) {
  const handleClick = (e) => {
    onClick?.(e)
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    navigate(to)
  }
  return (
    <a href={to} className={className} onClick={handleClick} {...rest}>
      {children}
    </a>
  )
}

/** Discloses that a section shows illustrative data, not backend output. */
export function PreviewBadge({ children = 'Sample data · UI preview' }) {
  return (
    <span className="preview-badge" title="This section shows illustrative data. It will be populated by the backend in a later phase.">
      <AlertCircleIcon size={12} />
      {children}
    </span>
  )
}

export function SectionHeading({ eyebrow, title, description, align = 'left', actions }) {
  return (
    <div className={`section-heading align-${align}`}>
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="section-heading-actions">{actions}</div>}
    </div>
  )
}

export function TypeBadge({ type }) {
  const meta = SEMANTIC_TYPE_META[type] || SEMANTIC_TYPE_META.unknown
  return <span className={`tag tag-${meta.tone}`}>{meta.label}</span>
}

export function EmptyState({ icon, title, children, actions }) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {actions && <div className="row" style={{ marginTop: 8, flexWrap: 'wrap', justifyContent: 'center' }}>{actions}</div>}
    </div>
  )
}

export function StatTile({ label, value, hint, tone }) {
  return (
    <div className={`stat-tile${tone ? ` tone-${tone}` : ''}`}>
      <div className="stat-tile-label">{label}</div>
      <div className="stat-tile-value">{value}</div>
      {hint && <div className="stat-tile-hint">{hint}</div>}
    </div>
  )
}

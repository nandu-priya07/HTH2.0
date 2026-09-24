import { useEffect, useRef, useState } from 'react'
import { Link } from '../ui/primitives'
import { usePath } from '../../lib/router'
import { useAnalyst } from '../../state/analystContext'
import { getDatasetStats, formatCount } from '../../lib/dataset'
import { BellIcon, HelpCircleIcon, DatabaseIcon, MenuIcon, CloseIcon, UploadIcon } from '../ui/Icons'

const NAV_ITEMS = [
  { to: '/', label: 'Home', match: ['/', '/home'] },
  { to: '/ask-ai', label: 'Ask AI' },
  { to: '/insights', label: 'Insights' },
  { to: '/explorer', label: 'Explorer' },
  { to: '/scenarios', label: 'Scenarios' },
  { to: '/decisions', label: 'Decisions' },
  { to: '/history', label: 'History' }
]

const isActive = (item, path) => (item.match || [item.to]).includes(path)

function useDismiss(open, setOpen) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, setOpen])
  return ref
}

function Popover({ label, icon, children, align = 'right' }) {
  const [open, setOpen] = useState(false)
  const ref = useDismiss(open, setOpen)
  return (
    <div className="popover" ref={ref}>
      <button
        type="button"
        className="icon-btn"
        aria-label={label}
        aria-expanded={open}
        title={label}
        onClick={() => setOpen((o) => !o)}
      >
        {icon}
      </button>
      {open && (
        <div className={`popover-panel align-${align}`} role="dialog" aria-label={label}>
          {children}
        </div>
      )}
    </div>
  )
}

function DatasetStatus() {
  const { activeDataset, isLoading } = useAnalyst()
  const stats = getDatasetStats(activeDataset)
  if (!stats) {
    return (
      <Link to="/upload" className="dataset-status is-empty" title="Upload a dataset">
        <UploadIcon size={14} />
        <span className="dataset-status-text">No dataset</span>
      </Link>
    )
  }
  return (
    <Link to="/upload" className="dataset-status" title={`${stats.name} · ${formatCount(stats.rows)} rows`}>
      <span className={`dataset-status-dot${isLoading ? ' busy' : ''}`} aria-hidden="true" />
      <DatabaseIcon size={14} />
      <span className="dataset-status-text">{stats.name}</span>
      <span className="sr-only">Dataset ready</span>
    </Link>
  )
}

export default function TopNav() {
  const path = usePath()
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

  return (
    <header className="topnav">
      <div className="topnav-inner">
        <Link to="/" className="brand" aria-label="QueryLens home">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="32" height="32">
              <rect width="32" height="32" rx="9" fill="var(--video-primary)" />
              <rect x="8" y="17" width="4" height="7" rx="1.5" fill="#fff" />
              <rect x="14" y="12" width="4" height="12" rx="1.5" fill="#fff" opacity="0.85" />
              <rect x="20" y="8" width="4" height="16" rx="1.5" fill="var(--video-cool)" />
            </svg>
          </span>
          <span className="brand-text">
            <span className="brand-name">QueryLens</span>
            <span className="brand-sub">Natural Language Data Analyst</span>
          </span>
        </Link>

        <nav className="topnav-links" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`topnav-link${isActive(item, path) ? ' active' : ''}`}
              aria-current={isActive(item, path) ? 'page' : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="topnav-actions">
          <DatasetStatus />
          <Popover label="Notifications" icon={<BellIcon size={18} />}>
            <div className="popover-title">Notifications</div>
            <p className="popover-empty">You're all caught up. Dataset and analysis alerts will appear here.</p>
          </Popover>
          <Popover label="Help" icon={<HelpCircleIcon size={18} />}>
            <div className="popover-title">How it works</div>
            <ol className="popover-steps">
              <li><strong>Upload</strong> any CSV or Excel file.</li>
              <li>We <strong>infer its schema</strong> — no fixed column names.</li>
              <li><strong>Ask</strong> a question in plain language.</li>
              <li>Get an <strong>answer, a chart and the calculation</strong>.</li>
            </ol>
          </Popover>
          <button type="button" className="avatar" aria-label="Profile" title="Profile">U</button>
          <button
            type="button"
            className="icon-btn topnav-menu-btn"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav id="mobile-nav" className="mobile-nav animate-fade-in" aria-label="Primary mobile">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`mobile-nav-link${isActive(item, path) ? ' active' : ''}`}
              aria-current={isActive(item, path) ? 'page' : undefined}
              onClick={closeMenu}
            >
              {item.label}
            </Link>
          ))}
          <Link to="/upload" className="btn btn-primary" style={{ marginTop: 8 }} onClick={closeMenu}>
            <UploadIcon size={16} /> Upload dataset
          </Link>
        </nav>
      )}
    </header>
  )
}

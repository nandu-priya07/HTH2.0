import TopNav from './TopNav'
import { Link } from '../ui/primitives'

export default function AppShell({ children, fullBleed = false }) {
  return (
    <div className={`app-shell${fullBleed ? ' is-full-bleed' : ''}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <TopNav />
      <main id="main" className="app-main" tabIndex={-1}>
        {children}
      </main>
      {!fullBleed && (
        <footer className="app-footer">
          <div className="container app-footer-inner">
            <span>
              <strong>QueryLens</strong> · Natural Language Data Analyst
            </span>
            <nav className="row" aria-label="Footer">
              <Link to="/upload">Upload</Link>
              <Link to="/ask-ai">Ask AI</Link>
              <Link to="/history">History</Link>
            </nav>
          </div>
        </footer>
      )}
    </div>
  )
}

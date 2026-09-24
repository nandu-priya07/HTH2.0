import { EmptyState, Link } from '../components/ui/primitives'
import { GlobeIcon } from '../components/ui/Icons'

export default function NotFoundPage() {
  return (
    <div className="page">
      <div className="container">
        <div className="card">
          <EmptyState
            icon={<GlobeIcon size={22} />}
            title="Page not found"
            actions={<><Link to="/" className="btn btn-primary btn-sm">Go home</Link><Link to="/ask-ai" className="btn btn-ghost btn-sm">Ask AI</Link></>}
          >
            That route doesn't exist. Use the navigation above to continue.
          </EmptyState>
        </div>
      </div>
    </div>
  )
}

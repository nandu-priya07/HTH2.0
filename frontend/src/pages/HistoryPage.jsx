import { useEffect, useState } from 'react'
import { EmptyState, Link } from '../components/ui/primitives'
import { useAnalyst } from '../state/analystContext'
import { navigate } from '../lib/router'
import { formatCount } from '../lib/dataset'
import { ClockIcon, DatabaseIcon, MessageSquareIcon, ArrowRightIcon, UploadIcon, PaperclipIcon } from '../components/ui/Icons'

const TABS = [
  { id: 'analyses', label: 'Previous analyses' },
  { id: 'questions', label: 'Previous questions' },
  { id: 'datasets', label: 'Previous datasets' }
]

const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')

function Skeletons() {
  return (
    <div className="history-skeletons" aria-label="Loading">
      {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 56 }} />)}
    </div>
  )
}

/* GET /api/datasets — existing endpoint, read-only. */
function useDatasets(enabled) {
  const [state, setState] = useState({ error: null, items: null })
  const done = state.items !== null || state.error !== null
  useEffect(() => {
    if (!enabled || done) return
    let cancelled = false
    fetch('/api/datasets')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Status ${r.status}`))))
      .then((d) => { if (!cancelled) setState({ error: null, items: d.datasets || [] }) })
      .catch((e) => { if (!cancelled) setState({ error: e.message, items: null }) })
    return () => { cancelled = true }
  }, [enabled, done])
  return { ...state, loading: enabled && !done }
}

/* Questions from the most recent conversations (GET /api/conversations/:id/messages). */
function useRecentQuestions(enabled, conversations) {
  const [state, setState] = useState({ items: null })
  const done = state.items !== null
  useEffect(() => {
    if (!enabled || done || !conversations.length) return
    let cancelled = false
    const recent = conversations.slice(0, 6)
    Promise.all(recent.map((c) =>
      fetch(`/api/conversations/${c.id}/messages`)
        .then((r) => (r.ok ? r.json() : []))
        .then((msgs) => (Array.isArray(msgs) ? msgs : []).filter((m) => m.role === 'user' && m.content).map((m) => ({ ...m, conv: c })))
        .catch(() => [])
    )).then((lists) => {
      if (cancelled) return
      const items = lists.flat().sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      setState({ items })
    })
    return () => { cancelled = true }
  }, [enabled, conversations, done])
  return { ...state, loading: enabled && !done && conversations.length > 0 }
}

export default function HistoryPage() {
  const { conversations, isLoadingConversations, conversationsError, fetchConversations, selectConversation } = useAnalyst()
  const [tab, setTab] = useState('analyses')
  const datasets = useDatasets(tab === 'datasets')
  const questions = useRecentQuestions(tab === 'questions', conversations)

  const open = (id) => { selectConversation(id); navigate('/ask-ai') }

  return (
    <div className="page">
      <div className="container">
        <header className="page-header">
          <div>
            <div className="eyebrow">History</div>
            <h1>Your analytical history</h1>
            <p>Every dataset you uploaded, every question you asked, and every analysis you ran.</p>
          </div>
        </header>

        <div className="segmented history-tabs" role="tablist" aria-label="History sections">
          {TABS.map((t) => (
            <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </div>

        <section className="card history-panel" role="tabpanel" aria-label={TABS.find((t) => t.id === tab).label}>
          {tab === 'analyses' && (
            isLoadingConversations && !conversations.length ? <Skeletons />
              : conversationsError ? (
                <EmptyState icon={<ClockIcon size={22} />} title="Couldn't load history" actions={<button className="btn btn-ghost btn-sm" onClick={fetchConversations}>Retry</button>}>
                  The backend didn't respond. Make sure it's running on port 8000.
                </EmptyState>
              ) : !conversations.length ? (
                <EmptyState icon={<MessageSquareIcon size={22} />} title="No analyses yet" actions={<Link to="/upload" className="btn btn-primary btn-sm"><UploadIcon size={14} /> Upload a dataset</Link>}>
                  Upload a dataset and ask a question — the conversation will be saved here.
                </EmptyState>
              ) : (
                <ul className="history-rows">
                  {conversations.map((c) => (
                    <li key={c.id}>
                      <button className="history-row" onClick={() => open(c.id)}>
                        <span className="history-row-icon"><MessageSquareIcon size={16} /></span>
                        <span className="history-row-main">
                          <span className="history-row-title">{c.title}</span>
                          <span className="history-row-meta">
                            {when(c.updated_at || c.created_at)}
                            {c.files?.length ? <> · <PaperclipIcon size={11} /> {c.files.map((f) => f.filename).join(', ')}</> : c.dataset_id ? ' · dataset attached' : ''}
                          </span>
                        </span>
                        <ArrowRightIcon size={16} className="history-row-arrow" />
                      </button>
                    </li>
                  ))}
                </ul>
              )
          )}

          {tab === 'questions' && (
            !conversations.length ? (
              <EmptyState icon={<MessageSquareIcon size={22} />} title="No questions yet">Questions you ask in Ask AI will be listed here.</EmptyState>
            ) : questions.loading || !questions.items ? <Skeletons />
              : !questions.items.length ? (
                <EmptyState icon={<MessageSquareIcon size={22} />} title="No questions yet">Your recent conversations don't contain any questions.</EmptyState>
              ) : (
                <ul className="history-rows">
                  {questions.items.map((q) => (
                    <li key={q.id}>
                      <button className="history-row" onClick={() => open(q.conv.id)}>
                        <span className="history-row-icon"><MessageSquareIcon size={16} /></span>
                        <span className="history-row-main">
                          <span className="history-row-title">“{q.content}”</span>
                          <span className="history-row-meta">{when(q.created_at)} · in {q.conv.title}</span>
                        </span>
                        <ArrowRightIcon size={16} className="history-row-arrow" />
                      </button>
                    </li>
                  ))}
                </ul>
              )
          )}

          {tab === 'datasets' && (
            datasets.loading || (!datasets.items && !datasets.error) ? <Skeletons />
              : datasets.error ? (
                <EmptyState icon={<DatabaseIcon size={22} />} title="Couldn't load datasets">{datasets.error}</EmptyState>
              ) : !datasets.items.length ? (
                <EmptyState icon={<DatabaseIcon size={22} />} title="No datasets yet" actions={<Link to="/upload" className="btn btn-primary btn-sm"><UploadIcon size={14} /> Upload a dataset</Link>}>
                  Uploaded files will appear here.
                </EmptyState>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>Dataset</th><th className="num">Rows</th><th className="num">Columns</th><th>Uploaded</th></tr></thead>
                    <tbody>
                      {datasets.items.map((d, i) => {
                        const meta = d.metadata || {}
                        return (
                          <tr key={d.dataset_id || d.file_id || i}>
                            <td><span className="row"><DatabaseIcon size={14} /><span className="mono">{d.filename || d.original_filename || meta.original_filename || d.dataset_id}</span></span></td>
                            <td className="num">{formatCount(meta.row_count ?? d.row_count)}</td>
                            <td className="num">{formatCount(meta.column_count ?? d.column_count)}</td>
                            <td>{when(d.created_at || d.uploaded_at)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )
          )}
        </section>
      </div>
    </div>
  )
}

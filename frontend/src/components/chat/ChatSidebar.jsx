import { useState } from 'react'
import {
  PlusIcon,
  DatabaseIcon,
  TableIcon,
  TrashIcon,
  CloseIcon,
  EditIcon,
  CheckIcon,
  MessageSquareIcon,
  PaperclipIcon,
  UploadIcon
} from '../ui/Icons'
import { Link } from '../ui/primitives'
import { getDatasetStats, formatCount } from '../../lib/dataset'

function formatRelativeTime(isoString) {
  if (!isoString) return ''
  try {
    const date = new Date(isoString)
    const now = new Date()
    const diffSec = Math.floor((now - date) / 1000)
    if (diffSec < 60) return 'Just now'
    const diffMin = Math.floor(diffSec / 60)
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHrs = Math.floor(diffMin / 60)
    if (diffHrs < 24) return `${diffHrs}h ago`
    const diffDays = Math.floor(diffHrs / 24)
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

function groupConversationsByDate(convList) {
  if (!convList || convList.length === 0) return []

  const groups = { Today: [], Yesterday: [], 'Previous 7 Days': [], Older: [] }
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const yesterdayStart = todayStart - 86400000
  const lastWeekStart = todayStart - 7 * 86400000

  convList.forEach((conv) => {
    const timeStr = conv.updated_at || conv.created_at
    const timestamp = timeStr ? new Date(timeStr).getTime() : 0
    if (timestamp >= todayStart) groups['Today'].push(conv)
    else if (timestamp >= yesterdayStart) groups['Yesterday'].push(conv)
    else if (timestamp >= lastWeekStart) groups['Previous 7 Days'].push(conv)
    else groups['Older'].push(conv)
  })

  return Object.entries(groups).filter(([, items]) => items.length > 0)
}

export default function ChatSidebar({
  conversations = [],
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onRenameConversation,
  isLoadingConversations = false,
  conversationsError = null,
  onRetryFetchConversations,
  activeDataset,
  onClearDataset,
  onInspectSchema,
  isOpen = true,
  onClose
}) {
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const stats = getDatasetStats(activeDataset)
  const schemaCount = activeDataset?.schema?.columns?.length || activeDataset?.result?.schema?.columns?.length || 0

  const handleStartRename = (e, conv) => {
    e.stopPropagation()
    setEditingId(conv.id)
    setEditTitle(conv.title)
  }

  const handleSaveRename = async (e, convId) => {
    e.stopPropagation()
    if (!editTitle || !editTitle.trim()) {
      setEditingId(null)
      return
    }
    if (onRenameConversation) await onRenameConversation(convId, editTitle.trim())
    setEditingId(null)
  }

  const handleCancelRename = (e) => {
    e.stopPropagation()
    setEditingId(null)
    setEditTitle('')
  }

  const handleDelete = async (e, convId) => {
    e.stopPropagation()
    setDeletingId(convId)
    try {
      if (onDeleteConversation) await onDeleteConversation(convId)
    } finally {
      setDeletingId(null)
    }
  }

  const grouped = groupConversationsByDate(conversations)

  return (
    <aside className={`chat-sidebar${isOpen ? ' open' : ' closed'}`} aria-label="Conversation history">
      <div className="sidebar-inner">
        <div className="sidebar-top">
          <button className="btn btn-primary sidebar-new" onClick={onNewChat} id="btn-new-chat">
            <PlusIcon size={16} />
            <span>New Analysis</span>
          </button>
          {onClose && (
            <button className="icon-btn sidebar-close" onClick={onClose} aria-label="Close history">
              <CloseIcon size={18} />
            </button>
          )}
        </div>

        {/* Active Dataset Card */}
        {stats ? (
          <div className="sidebar-dataset animate-fade-in">
            <div className="sidebar-dataset-head">
              <span className="section-label"><DatabaseIcon size={12} /> Active dataset</span>
              <button className="icon-btn icon-btn-sm" onClick={onClearDataset} title="Disconnect dataset" aria-label="Disconnect dataset">
                <TrashIcon size={13} />
              </button>
            </div>
            <div className="sidebar-dataset-name" title={stats.name}>{stats.name}</div>
            <div className="sidebar-dataset-stats">
              <span><strong>{formatCount(stats.rows)}</strong> rows</span>
              <span><strong>{formatCount(stats.columns)}</strong> columns</span>
            </div>
            {schemaCount > 0 && (
              <button className="sidebar-schema-btn" onClick={onInspectSchema}>
                <TableIcon size={13} />
                <span>Inspect schema ({schemaCount})</span>
              </button>
            )}
          </div>
        ) : (
          <Link to="/upload" className="sidebar-dataset is-empty">
            <UploadIcon size={16} />
            <span>
              <strong>No dataset connected</strong>
              <small>Upload a CSV or Excel file</small>
            </span>
          </Link>
        )}

        {/* Conversations */}
        <div className="sidebar-history" id="sidebar-conversations-list">
          <div className="sidebar-section-head">
            <span className="section-label">Conversations</span>
            {conversations.length > 0 && <span className="sidebar-count">{conversations.length}</span>}
          </div>

          {isLoadingConversations && conversations.length === 0 && (
            <div className="sidebar-skeletons" aria-label="Loading conversations">
              {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 40 }} />)}
            </div>
          )}

          {conversationsError && (
            <div className="sidebar-error">
              <p>Couldn't load conversations.</p>
              {onRetryFetchConversations && (
                <button className="btn btn-ghost btn-sm" onClick={onRetryFetchConversations}>Retry</button>
              )}
            </div>
          )}

          {!isLoadingConversations && !conversationsError && conversations.length === 0 && (
            <div className="sidebar-empty animate-fade-in">
              <MessageSquareIcon size={18} />
              <div>No conversations yet</div>
              <small>Your analyses will be listed here.</small>
            </div>
          )}

          {!conversationsError && grouped.map(([groupName, items]) => (
            <div key={groupName} className="history-group">
              <div className="history-group-title">{groupName}</div>
              <ul className="history-list">
                {items.map((conv) => {
                  const isActive = activeConversationId === conv.id
                  const isEditing = editingId === conv.id
                  const isDeleting = deletingId === conv.id

                  return (
                    <li key={conv.id} className={`history-item${isActive ? ' active' : ''}${isDeleting ? ' deleting' : ''}`}>
                      {isEditing ? (
                        <div className="history-edit-row">
                          <input
                            type="text"
                            className="input history-edit-input"
                            value={editTitle}
                            aria-label="Conversation title"
                            onChange={(e) => setEditTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveRename(e, conv.id)
                              if (e.key === 'Escape') handleCancelRename(e)
                            }}
                            autoFocus
                          />
                          <button className="icon-btn icon-btn-sm" onClick={(e) => handleSaveRename(e, conv.id)} aria-label="Save title">
                            <CheckIcon size={14} />
                          </button>
                          <button className="icon-btn icon-btn-sm" onClick={handleCancelRename} aria-label="Cancel rename">
                            <CloseIcon size={14} />
                          </button>
                        </div>
                      ) : (
                        <>
                          <button
                            className="history-item-btn"
                            onClick={() => onSelectConversation(conv.id)}
                            title={conv.title}
                            aria-current={isActive ? 'true' : undefined}
                          >
                            <span className="history-item-text">{conv.title}</span>
                            <span className="history-item-meta">
                              <span>{formatRelativeTime(conv.updated_at || conv.created_at)}</span>
                              {conv.dataset_id && (
                                <span className="history-dataset-badge" title="Dataset attached">
                                  <PaperclipIcon size={10} /> Dataset
                                </span>
                              )}
                            </span>
                          </button>
                          <div className="history-item-actions">
                            <button className="icon-btn icon-btn-sm" onClick={(e) => handleStartRename(e, conv)} aria-label={`Rename ${conv.title}`} title="Rename">
                              <EditIcon size={13} />
                            </button>
                            <button className="icon-btn icon-btn-sm danger" onClick={(e) => handleDelete(e, conv.id)} aria-label={`Delete ${conv.title}`} title="Delete">
                              <TrashIcon size={13} />
                            </button>
                          </div>
                        </>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          {conversationsError ? (
            <span className="status status-bad"><span className="live-dot" aria-hidden="true" /> Backend unreachable</span>
          ) : (
            <span className="status status-good"><span className="live-dot" aria-hidden="true" /> Backend connected</span>
          )}
          <span className="sidebar-version">Schema-agnostic core v2.0</span>
        </div>
      </div>
    </aside>
  )
}

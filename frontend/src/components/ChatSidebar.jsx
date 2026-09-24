import { useState } from 'react'
import {
  PlusIcon,
  DatabaseIcon,
  TableIcon,
  TrashIcon,
  CloseIcon,
  SettingsIcon,
  HelpCircleIcon,
  EditIcon,
  CheckIcon,
  MessageSquareIcon,
  SparklesIcon,
  PaperclipIcon
} from './Icons'

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
  } catch (e) {
    return ''
  }
}

function groupConversationsByDate(convList) {
  if (!convList || convList.length === 0) return []

  const groups = {
    Today: [],
    Yesterday: [],
    'Previous 7 Days': [],
    Older: []
  }

  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const yesterdayStart = todayStart - 86400000
  const lastWeekStart = todayStart - 7 * 86400000

  convList.forEach((conv) => {
    const timeStr = conv.updated_at || conv.created_at
    const timestamp = timeStr ? new Date(timeStr).getTime() : 0

    if (timestamp >= todayStart) {
      groups['Today'].push(conv)
    } else if (timestamp >= yesterdayStart) {
      groups['Yesterday'].push(conv)
    } else if (timestamp >= lastWeekStart) {
      groups['Previous 7 Days'].push(conv)
    } else {
      groups['Older'].push(conv)
    }
  })

  return Object.entries(groups).filter(([_, items]) => items.length > 0)
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
  isOpen = true
}) {
  const [showSchemaModal, setShowSchemaModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const schemaColumns =
    activeDataset?.schema?.columns ||
    activeDataset?.result?.schema?.columns ||
    []

  const datasetName =
    activeDataset?.filename ||
    activeDataset?.result?.metadata?.filename ||
    'Active Dataset'
  const rowCount =
    activeDataset?.metadata?.rows ||
    activeDataset?.result?.metadata?.rows ||
    activeDataset?.rows
  const colCount =
    activeDataset?.metadata?.columns ||
    activeDataset?.result?.metadata?.columns ||
    activeDataset?.columns_count ||
    schemaColumns.length

  const getSemanticTypeBadge = (type) => {
    switch (type) {
      case 'numeric':
        return <span className="type-badge numeric">NUM</span>
      case 'date':
        return <span className="type-badge date">DATE</span>
      case 'identifier':
        return <span className="type-badge identifier">ID</span>
      case 'boolean':
        return <span className="type-badge boolean">BOOL</span>
      default:
        return <span className="type-badge categorical">CAT</span>
    }
  }

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
    if (onRenameConversation) {
      await onRenameConversation(convId, editTitle.trim())
    }
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
      if (onDeleteConversation) {
        await onDeleteConversation(convId)
      }
    } finally {
      setDeletingId(null)
    }
  }

  const grouped = groupConversationsByDate(conversations)

  return (
    <>
      <aside
        className={`chat-sidebar${isOpen ? ' open' : ' closed'}`}
        aria-label="Chat history navigation"
      >
        <div className="sidebar-inner">
          {/* New Analysis Button */}
          <button
            className="new-chat-btn"
            onClick={onNewChat}
            aria-label="Start new analysis"
            id="btn-new-chat"
          >
            <PlusIcon size={16} />
            <span>New Analysis</span>
          </button>

          {/* Active Dataset Card */}
          {activeDataset && (
            <div className="sidebar-dataset-card animate-fade-in">
              <div className="dataset-card-header">
                <div className="dataset-card-title">
                  <DatabaseIcon size={13} />
                  <span>Active Dataset</span>
                </div>
                <button
                  className="dataset-clear-btn"
                  onClick={onClearDataset}
                  title="Disconnect dataset"
                  aria-label="Disconnect dataset"
                >
                  <TrashIcon size={13} />
                </button>
              </div>

              <div className="dataset-info-row">
                <span className="dataset-filename" title={datasetName}>
                  {datasetName}
                </span>
              </div>

              <div className="dataset-metrics-grid">
                <div className="dataset-stat">
                  <span className="stat-label">Rows</span>
                  <span className="stat-val">
                    {rowCount ? rowCount.toLocaleString() : '—'}
                  </span>
                </div>
                <div className="dataset-stat">
                  <span className="stat-label">Columns</span>
                  <span className="stat-val">{colCount || '—'}</span>
                </div>
              </div>

              {schemaColumns.length > 0 && (
                <button
                  className="view-schema-btn"
                  onClick={() => setShowSchemaModal(true)}
                >
                  <TableIcon size={13} />
                  <span>Inspect Schema ({schemaColumns.length})</span>
                </button>
              )}
            </div>
          )}

          {/* Real Backend-Backed Conversations History */}
          <div className="sidebar-history-section" id="sidebar-conversations-list">
            <div className="sidebar-section-header">
              <span className="section-header-title">Chat History</span>
              {conversations.length > 0 && (
                <span className="section-header-count">{conversations.length}</span>
              )}
            </div>

            {/* Loading State */}
            {isLoadingConversations && conversations.length === 0 && (
              <div className="sidebar-loading-state">
                <div className="pulse-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span className="loading-label">Loading conversations...</span>
              </div>
            )}

            {/* Error State */}
            {conversationsError && (
              <div className="sidebar-error-state">
                <p className="sidebar-error-text">Failed to load conversations</p>
                {onRetryFetchConversations && (
                  <button
                    className="sidebar-retry-btn"
                    onClick={onRetryFetchConversations}
                  >
                    Retry
                  </button>
                )}
              </div>
            )}

            {/* Empty State */}
            {!isLoadingConversations && !conversationsError && conversations.length === 0 && (
              <div className="sidebar-empty-state animate-fade-in">
                <div className="empty-icon-pill">
                  <MessageSquareIcon size={18} />
                </div>
                <div className="empty-title">No conversations yet</div>
                <div className="empty-subtitle">Start a new analysis</div>
              </div>
            )}

            {/* Grouped Conversations */}
            {!conversationsError && grouped.map(([groupName, items]) => (
              <div key={groupName} className="history-group animate-fade-in">
                <div className="history-group-title">{groupName}</div>
                <div className="history-list">
                  {items.map((conv) => {
                    const isActive = activeConversationId === conv.id
                    const isEditing = editingId === conv.id
                    const isDeleting = deletingId === conv.id

                    return (
                      <div
                        key={conv.id}
                        className={`history-item-container ${isActive ? 'active' : ''} ${isDeleting ? 'deleting' : ''}`}
                      >
                        {isEditing ? (
                          <div className="history-edit-row">
                            <input
                              type="text"
                              className="history-edit-input"
                              value={editTitle}
                              onChange={(e) => setEditTitle(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSaveRename(e, conv.id)
                                if (e.key === 'Escape') handleCancelRename(e)
                              }}
                              autoFocus
                              onClick={(e) => e.stopPropagation()}
                            />
                            <button
                              className="history-action-btn check"
                              onClick={(e) => handleSaveRename(e, conv.id)}
                              title="Save title"
                              aria-label="Save title"
                            >
                              <CheckIcon size={14} />
                            </button>
                            <button
                              className="history-action-btn cancel"
                              onClick={handleCancelRename}
                              title="Cancel"
                              aria-label="Cancel"
                            >
                              <CloseIcon size={14} />
                            </button>
                          </div>
                        ) : (
                          <button
                            className="history-item-btn"
                            onClick={() => onSelectConversation(conv.id)}
                            title={conv.title}
                          >
                            <span className="history-bullet" aria-hidden="true">•</span>
                            <div className="history-item-content">
                              <span className="history-item-text">{conv.title}</span>
                              <div className="history-item-meta-row">
                                <span className="history-item-time">
                                  {formatRelativeTime(conv.updated_at || conv.created_at)}
                                </span>
                                {conv.dataset_id && (
                                  <span className="history-dataset-badge" title="Dataset attached">
                                    <PaperclipIcon size={10} />
                                    <span>Dataset</span>
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Item Actions (Rename / Delete) */}
                            <div className="history-item-actions">
                              <button
                                className="history-action-btn edit"
                                onClick={(e) => handleStartRename(e, conv)}
                                title="Rename conversation"
                                aria-label="Rename conversation"
                              >
                                <EditIcon size={13} />
                              </button>
                              <button
                                className="history-action-btn delete"
                                onClick={(e) => handleDelete(e, conv.id)}
                                title="Delete conversation"
                                aria-label="Delete conversation"
                              >
                                <TrashIcon size={13} />
                              </button>
                            </div>
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Sidebar Footer */}
          <div className="sidebar-footer">
            <div className="engine-status-badge">
              <span className="pulse-indicator" aria-hidden="true" />
              <span>Analytics Engine Active</span>
            </div>

            <button className="sidebar-footer-btn" aria-label="Settings">
              <SettingsIcon size={15} />
              <span>Settings</span>
            </button>

            <button className="sidebar-footer-btn" aria-label="Help">
              <HelpCircleIcon size={15} />
              <span>Help & Support</span>
            </button>

            <div className="version-tag">Dataset-Agnostic Core v2.0</div>
          </div>
        </div>
      </aside>

      {/* Schema Inspector Modal */}
      {showSchemaModal && (
        <div
          className="modal-backdrop animate-fade-in"
          onClick={() => setShowSchemaModal(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Schema inspector"
        >
          <div className="schema-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-group">
                <TableIcon size={18} />
                <h3>Dataset Schema & Types</h3>
              </div>
              <button
                className="modal-close-btn"
                onClick={() => setShowSchemaModal(false)}
                aria-label="Close schema inspector"
              >
                <CloseIcon size={16} />
              </button>
            </div>

            <div className="modal-body">
              <p className="modal-desc">
                Inferred physical and semantic types for <strong>{datasetName}</strong>. The
                query processor uses these types for column resolution and aggregation safety.
              </p>

              <div className="schema-columns-list">
                {schemaColumns.map((col, idx) => (
                  <div key={idx} className="schema-column-row">
                    <div className="col-name-wrapper">
                      <span className="col-index">{idx + 1}.</span>
                      <span className="col-name">{col.name}</span>
                    </div>
                    <div className="col-type-badges">
                      {getSemanticTypeBadge(col.semantic_type)}
                      {col.dtype && <span className="dtype-badge">{col.dtype}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

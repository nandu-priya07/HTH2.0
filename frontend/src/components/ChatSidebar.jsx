import { useState } from 'react'
import {
  SparklesIcon,
  PlusIcon,
  DatabaseIcon,
  TableIcon,
  TrashIcon,
  CloseIcon,
  SettingsIcon,
  HelpCircleIcon
} from './Icons'

export default function ChatSidebar({
  onNewChat,
  activeDataset,
  onClearDataset,
  onSelectSavedQuery,
  isOpen
}) {
  const [selectedChatId, setSelectedChatId] = useState(1)
  const [showSchemaModal, setShowSchemaModal] = useState(false)

  const recentChatGroups = [
    {
      group: 'Today',
      items: [
        { id: 1, title: 'Sales & Revenue Analysis' },
        { id: 2, title: 'Regional Breakdown & Share' },
        { id: 3, title: 'Category Profitability' }
      ]
    },
    {
      group: 'Yesterday',
      items: [
        { id: 4, title: 'Monthly Growth & Trends' },
        { id: 5, title: 'Customer Segmentation' }
      ]
    },
    {
      group: 'Older',
      items: [
        { id: 6, title: 'Profit Margin Analysis' },
        { id: 7, title: 'Discount Impact Study' }
      ]
    }
  ]

  const schemaColumns = activeDataset?.schema?.columns ||
    activeDataset?.result?.schema?.columns ||
    []

  const datasetName = activeDataset?.filename || activeDataset?.result?.metadata?.filename || 'Active Dataset'
  const rowCount = activeDataset?.metadata?.rows || activeDataset?.result?.metadata?.rows || activeDataset?.rows
  const colCount = activeDataset?.metadata?.columns || activeDataset?.result?.metadata?.columns || activeDataset?.columns_count || schemaColumns.length

  const getSemanticTypeBadge = (type) => {
    switch (type) {
      case 'numeric':    return <span className="type-badge numeric">NUM</span>
      case 'date':       return <span className="type-badge date">DATE</span>
      case 'identifier': return <span className="type-badge identifier">ID</span>
      case 'boolean':    return <span className="type-badge boolean">BOOL</span>
      default:           return <span className="type-badge categorical">CAT</span>
    }
  }

  return (
    <>
      <aside
        className={`chat-sidebar${isOpen ? ' open' : ''}`}
        aria-label="Sidebar navigation"
      >
        <div className="sidebar-inner">
          {/* New Analysis Button */}
          <button
            className="new-chat-btn"
            onClick={onNewChat}
            aria-label="Start new analysis"
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
                <span className="dataset-filename" title={datasetName}>{datasetName}</span>
              </div>

              <div className="dataset-metrics-grid">
                <div className="dataset-stat">
                  <span className="stat-label">Rows</span>
                  <span className="stat-val">{rowCount ? rowCount.toLocaleString() : '—'}</span>
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

          {/* Recent Chats History */}
          <div className="sidebar-history-section">
            {recentChatGroups.map((group, gIdx) => (
              <div key={gIdx} className="history-group">
                <div className="history-group-title">{group.group}</div>
                <div className="history-list">
                  {group.items.map((item) => (
                    <button
                      key={item.id}
                      className={`history-item ${selectedChatId === item.id ? 'active' : ''}`}
                      onClick={() => {
                        setSelectedChatId(item.id)
                        if (onSelectSavedQuery) onSelectSavedQuery(item.title)
                      }}
                      title={item.title}
                    >
                      <span className="history-bullet" aria-hidden="true">•</span>
                      <span className="history-item-text">{item.title}</span>
                    </button>
                  ))}
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
                Inferred physical and semantic types for <strong>{datasetName}</strong>. The query processor uses these types for column resolution and aggregation safety.
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

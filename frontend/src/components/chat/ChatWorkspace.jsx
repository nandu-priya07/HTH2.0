import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import ChatSidebar from './ChatSidebar'
import ChatMessage from './ChatMessage'
import SuggestedQuestions from './SuggestedQuestions'
import ChatInput from './ChatInput'
import SchemaModal from '../dataset/SchemaModal'
import { useAnalyst } from '../../state/analystContext'
import { getDatasetStats, getNumericColumns, formatCount } from '../../lib/dataset'
import { DatabaseIcon, TrashIcon, LayoutSidebarIcon, TableIcon, UploadIcon } from '../ui/Icons'
import { Link } from '../ui/primitives'

/**
 * Ask AI workspace: conversation history (left) + analytical conversation (right).
 * All data and API behaviour comes from AnalystProvider (unchanged endpoints).
 */
export default function ChatWorkspace() {
  const {
    messages, input, setInput, isLoading, isLoadingMessages, uploadError, setUploadError,
    activeDataset, suggestions,
    conversations, activeConversationId, isLoadingConversations, conversationsError,
    fetchConversations, selectConversation, newChat, renameConversation, deleteConversation,
    sendMessage, editAndSendMessage, sendFile, clearDataset
  } = useAnalyst()

  const [editingMessageId, setEditingMessageId] = useState(null)
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => window.matchMedia('(min-width: 900px)').matches)
  const [showSchema, setShowSchema] = useState(false)
  const scrollEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    setEditingMessageId(null)
  }, [activeConversationId])

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isLoading, isLoadingMessages])

  const stats = getDatasetStats(activeDataset)
  const measureOptions = useMemo(() => getNumericColumns(activeDataset), [activeDataset])
  const schemaHints = useMemo(() => {
    const s = activeDataset?.schema || {}
    return { categorical: s.categorical_columns || [], date: s.date_columns || [], numeric: s.numeric_columns || [] }
  }, [activeDataset])

  const viewFields = activeDataset ? () => setShowSchema(true) : undefined
  const askAnother = useCallback(() => inputRef.current?.focus(), [])
  const closeSchema = useCallback(() => setShowSchema(false), [])
  const closeOnMobile = () => { if (!window.matchMedia('(min-width: 900px)').matches) setIsSidebarOpen(false) }

  // A user question counts as a follow-up once an earlier answer exists in the thread.
  let seenAnswer = false
  const rendered = messages.map((msg, i) => {
    const isFollowUp = msg.sender === 'user' && !msg.attachment && seenAnswer
    if (msg.sender === 'ai' && (msg.query_spec || msg.table || msg.scalar || msg.visualization)) seenAnswer = true
    const msgId = msg.id || `msg-${i}`
    const isEditing = editingMessageId === msgId

    return (
      <ChatMessage
        key={msgId}
        message={msg}
        messageIndex={i}
        isFollowUp={isFollowUp}
        isEditing={isEditing}
        onStartEdit={() => {
          if (!isLoading) setEditingMessageId(msgId)
        }}
        onCancelEdit={() => setEditingMessageId(null)}
        onSubmitEdit={(newText) => {
          setEditingMessageId(null)
          editAndSendMessage?.(i, newText)
        }}
        onSelectOption={(opt) => sendMessage(opt)}
        onViewFields={viewFields}
        onAskAnother={askAnother}
        measureOptions={measureOptions}
        schemaHints={schemaHints}
        isLoadingSession={isLoading}
      />
    )
  })

  return (
    <div className={`ask-layout${isSidebarOpen ? ' sidebar-open' : ''}`}>
      <ChatSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={(id) => { selectConversation(id); closeOnMobile() }}
        onNewChat={() => { newChat(); closeOnMobile() }}
        onDeleteConversation={deleteConversation}
        onRenameConversation={renameConversation}
        isLoadingConversations={isLoadingConversations}
        conversationsError={conversationsError}
        onRetryFetchConversations={fetchConversations}
        activeDataset={activeDataset}
        onClearDataset={clearDataset}
        onInspectSchema={() => setShowSchema(true)}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />
      {isSidebarOpen && <div className="ask-scrim" onClick={() => setIsSidebarOpen(false)} aria-hidden="true" />}

      <section className="ask-main" aria-label="Analytical conversation">
        <header className="ask-header">
          <button
            className="icon-btn"
            onClick={() => setIsSidebarOpen((o) => !o)}
            aria-label={isSidebarOpen ? 'Hide conversation history' : 'Show conversation history'}
            aria-expanded={isSidebarOpen}
            id="btn-sidebar-toggle"
          >
            <LayoutSidebarIcon size={18} />
          </button>

          {stats ? (
            <div className="ask-header-dataset">
              <span className="ask-header-icon"><DatabaseIcon size={15} /></span>
              <div className="ask-header-text">
                <span className="ask-header-name mono" title={stats.name}>{stats.name}</span>
                <span className="ask-header-meta">{formatCount(stats.rows)} rows · {formatCount(stats.columns)} columns</span>
              </div>
              <span className="status status-good"><span className="live-dot" aria-hidden="true" /> Dataset Ready</span>
            </div>
          ) : (
            <div className="ask-header-dataset is-empty">
              <span className="ask-header-meta">No dataset connected</span>
            </div>
          )}

          <div className="ask-header-actions">
            {stats ? (
              <>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowSchema(true)}>
                  <TableIcon size={14} /> <span className="hide-sm">Schema</span>
                </button>
                <button className="btn btn-ghost btn-sm" onClick={clearDataset} title="Disconnect dataset">
                  <TrashIcon size={14} /> <span className="hide-sm">Disconnect</span>
                </button>
              </>
            ) : (
              <Link to="/upload" className="btn btn-primary btn-sm"><UploadIcon size={14} /> Upload</Link>
            )}
          </div>
        </header>

        <div className="ask-scroll">
          <div className="ask-thread">
            {isLoadingMessages ? (
              <div className="ask-loading" role="status">
                <div className="pulse-dots"><span /><span /><span /></div>
                <span>Loading conversation…</span>
              </div>
            ) : messages.length === 0 ? (
              <SuggestedQuestions onSelectSuggestion={(t) => sendMessage(t)} activeDataset={activeDataset} suggestions={suggestions} />
            ) : (
              rendered
            )}
            {isLoading && <ChatMessage message={{ sender: 'ai', isLoading: true }} />}
            <div ref={scrollEndRef} />
          </div>
        </div>

        <div className="ask-composer">
          <ChatInput
            input={input}
            setInput={setInput}
            onSendMessage={sendMessage}
            onSendFile={sendFile}
            isLoading={isLoading}
            uploadError={uploadError}
            setUploadError={setUploadError}
            inputRef={inputRef}
            hasContext={messages.some((m) => m.sender === 'ai' && m.query_spec)}
          />
        </div>
      </section>

      {showSchema && activeDataset && <SchemaModal dataset={activeDataset} onClose={closeSchema} />}
    </div>
  )
}

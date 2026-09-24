import { useState, useRef, useEffect, useCallback } from 'react'
import ChatSidebar from './ChatSidebar'
import ChatMessage from './ChatMessage'
import SuggestedQuestions from './SuggestedQuestions'
import ChatInput from './ChatInput'
import {
  DatabaseIcon,
  TrashIcon,
  BellIcon,
  HelpCircleIcon,
  BarChartIcon,
  LayoutSidebarIcon,
  SparklesIcon
} from './Icons'

export default function ChatWorkspace() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [activeDataset, setActiveDataset] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [activeNav, setActiveNav] = useState('Analysis')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)

  // Persistent Chat History State
  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [isLoadingConversations, setIsLoadingConversations] = useState(false)
  const [conversationsError, setConversationsError] = useState(null)

  const scrollEndRef = useRef(null)

  // Auto scroll on new messages
  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, isLoadingMessages])

  // Load dataset suggestions helper
  const loadSuggestions = useCallback(async (datasetId) => {
    if (!datasetId) return
    try {
      const res = await fetch(`/api/dataset/${datasetId}/suggestions`)
      if (res.ok) {
        const data = await res.json()
        if (data.suggestions && data.suggestions.length > 0) {
          setSuggestions(data.suggestions)
        }
      }
    } catch (err) {
      console.warn('Could not fetch suggestions:', err)
    }
  }, [])

  // 1. Fetch Conversations from Backend API
  const fetchConversations = useCallback(async () => {
    setIsLoadingConversations(true)
    setConversationsError(null)
    try {
      const res = await fetch('/api/conversations')
      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`)
      }
      const data = await res.json()
      setConversations(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error('Failed to load conversations:', err)
      setConversationsError('Failed to load conversations')
    } finally {
      setIsLoadingConversations(false)
    }
  }, [])

  // 2. Initial application startup load
  useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  // Helper to format backend messages into ChatMessage props
  const formatApiMessage = (msg) => {
    const isAi = msg.role === 'assistant' || msg.role === 'system'
    const res = msg.result || {}
    const vis = msg.visualization

    return {
      id: msg.id,
      sender: isAi ? 'ai' : 'user',
      text: msg.content,
      result: msg.result,
      table: res.table || (res.tables && res.tables[0]),
      tables: res.tables,
      scalar: res.scalar || (res.scalars && res.scalars[0]),
      scalars: res.scalars,
      list: res.list,
      metadata: res.metadata,
      visualization: Array.isArray(vis) ? vis[0] : vis,
      visualizations: Array.isArray(vis) ? vis : (vis ? [vis] : []),
      created_at: msg.created_at
    }
  }

  // 3. Select & Load a Conversation
  const handleSelectConversation = async (conversationId) => {
    if (conversationId === activeConversationId && messages.length > 0) return

    setActiveConversationId(conversationId)
    setIsLoadingMessages(true)
    setUploadError(null)

    try {
      const res = await fetch(`/api/conversations/${conversationId}/messages`)
      if (!res.ok) {
        throw new Error('Failed to load conversation messages')
      }
      const data = await res.json()
      const formattedMessages = (Array.isArray(data) ? data : []).map(formatApiMessage)
      setMessages(formattedMessages)

      // Strictly resolve dataset from this conversation
      const convMeta = conversations.find((c) => c.id === conversationId)
      if (convMeta?.dataset_id) {
        if (convMeta.dataset_id !== activeDataset?.dataset_id) {
          try {
            const dsRes = await fetch(`/api/dataset/${convMeta.dataset_id}`)
            if (dsRes.ok) {
              const dsData = await dsRes.json()
              setActiveDataset(dsData)
              loadSuggestions(convMeta.dataset_id)
            }
          } catch (e) {
            console.warn('Could not load associated dataset info:', e)
          }
        }
      } else {
        // Conversation has no dataset
        setActiveDataset(null)
        setSuggestions([])
      }
    } catch (err) {
      console.error('Error loading conversation:', err)
      setMessages([
        {
          sender: 'ai',
          error: 'Failed to load conversation history. Please try clicking the conversation again.'
        }
      ])
    } finally {
      setIsLoadingMessages(false)
    }
  }

  // 4. Start New Chat / Reset
  const handleNewChat = () => {
    setActiveConversationId(null)
    setActiveDataset(null)
    setSuggestions([])
    setMessages([])
    setInput('')
    setUploadError(null)
  }

  // 5. Rename Conversation
  const handleRenameConversation = async (conversationId, newTitle) => {
    try {
      const res = await fetch(`/api/conversations/${conversationId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle })
      })
      if (res.ok) {
        const updated = await res.json()
        setConversations((prev) =>
          prev.map((c) => (c.id === conversationId ? { ...c, title: updated.title, updated_at: updated.updated_at } : c))
        )
      }
    } catch (err) {
      console.error('Failed to rename conversation:', err)
    }
  }

  // 6. Delete Conversation
  const handleDeleteConversation = async (conversationId) => {
    try {
      const res = await fetch(`/api/conversations/${conversationId}`, {
        method: 'DELETE'
      })
      if (res.ok) {
        setConversations((prev) => prev.filter((c) => c.id !== conversationId))
        if (activeConversationId === conversationId) {
          handleNewChat()
        }
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  }

  // 7. Send Message Flow
  const handleSendMessage = async (textToSend) => {
    const cleanText = textToSend ? textToSend.trim() : input.trim()
    if (!cleanText || isLoading) return

    const userMessage = { sender: 'user', text: cleanText }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    setUploadError(null)

    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: cleanText,
          dataset_id: activeDataset?.dataset_id || null,
          conversation_id: activeConversationId || null
        })
      })

      const data = await response.json()

      if (!response.ok) {
        setMessages((prev) => [
          ...prev,
          { sender: 'ai', error: data.error || 'Server returned an error processing your query.' }
        ])
        return
      }

      // Update active conversation ID if newly created or returned
      if (data.conversation_id) {
        setActiveConversationId(data.conversation_id)
        // Refresh conversations list so new title / timestamp appears in sidebar
        fetchConversations()
      }

      if (data.dataset_id && (!activeDataset || activeDataset.dataset_id !== data.dataset_id)) {
        try {
          const dsRes = await fetch(`/api/dataset/${data.dataset_id}`)
          if (dsRes.ok) {
            const dsData = await dsRes.json()
            setActiveDataset(dsData)
            loadSuggestions(data.dataset_id)
          }
        } catch (e) {
          console.warn('Could not load dataset info after query:', e)
        }
      }

      const aiMessage = {
        sender: 'ai',
        text: data.text,
        status: data.status,
        result_type: data.result_type || data.type,
        scalar: data.scalar,
        table: data.table,
        options: data.options,
        query_spec: data.query_spec || data.query,
        visualization: data.visualization,
        visualizations: data.visualizations,
        metadata: data.metadata,
        error: data.error
      }

      setMessages((prev) => [...prev, aiMessage])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          error:
            'Failed to connect to backend analytics engine. Please ensure the backend server is running on port 8000.'
        }
      ])
    } finally {
      setIsLoading(false)
    }
  }

  // 8. Send File Upload Flow
  const handleSendFile = async (file, optionalText) => {
    if (!file || isLoading) return
    setIsLoading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append('file', file)
    if (activeConversationId) {
      formData.append('conversation_id', activeConversationId)
    }

    try {
      const response = await fetch('/api/upload', { method: 'POST', body: formData })
      const data = await response.json()

      if (!response.ok || !data.success) {
        setUploadError(data.error || 'Upload failed. Only CSV and Excel files are allowed.')
        setIsLoading(false)
        return
      }

      const userMsg = {
        sender: 'user',
        text: optionalText || '',
        attachment: {
          filename: data.filename,
          file_size: data.file_size,
          dataset_id: data.dataset_id,
          file_type: data.file_type
        }
      }

      setActiveDataset(data)
      loadSuggestions(data.dataset_id)
      fetchConversations()

      const rowCount = data.metadata?.rows || data.row_count || '10,000+'
      const colCount = data.metadata?.columns || data.column_count || '20+'

      const aiMsg = {
        sender: 'ai',
        text: `Successfully ingested and cleaned **${data.filename}** (${rowCount.toLocaleString()} rows, ${colCount} columns).\n\nThe dataset schema and data types have been indexed. You can now ask questions, group by dimensions, or run filters.`
      }

      setMessages((prev) => [...prev, userMsg, aiMsg])
      setInput('')

      if (optionalText && optionalText.trim()) {
        setTimeout(() => {
          handleSendMessage(optionalText.trim())
        }, 300)
      }
    } catch (err) {
      setUploadError('Failed to connect to backend server. Make sure FastAPI is running on port 8000.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleClearDataset = () => {
    setActiveDataset(null)
    setSuggestions([])
    setMessages((prev) => [
      ...prev,
      {
        sender: 'ai',
        text: 'Active dataset disconnected. Upload a new CSV or Excel file to analyze a new dataset.'
      }
    ])
  }

  const datasetName =
    activeDataset?.filename || activeDataset?.result?.metadata?.filename || 'Active Dataset'
  const rowCount =
    activeDataset?.metadata?.rows || activeDataset?.result?.metadata?.rows || activeDataset?.rows

  const navItems = [
    { id: 'Dashboard', icon: <BarChartIcon size={15} /> },
    { id: 'Analysis', icon: <SparklesIcon size={15} /> },
    { id: 'Datasets', icon: <DatabaseIcon size={15} /> }
  ]

  return (
    <div className="chat-workspace-container">
      {/* ── TOP NAVIGATION BAR ── */}
      <nav className="top-navbar" role="navigation" aria-label="Main navigation">
        {/* Toggle Sidebar Button */}
        <button
          className="navbar-sidebar-toggle"
          onClick={() => setIsSidebarOpen((prev) => !prev)}
          title={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          aria-label={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          id="btn-sidebar-toggle"
        >
          <LayoutSidebarIcon size={18} />
        </button>

        {/* Brand */}
        <div
          className="navbar-brand"
          onClick={handleNewChat}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && handleNewChat()}
        >
          <div className="navbar-logo-mark" aria-hidden="true">
            H
          </div>
          <div className="navbar-brand-text">
            <span className="navbar-brand-name">HTH2.0</span>
            <span className="navbar-brand-sub">AI Data Analyst</span>
          </div>
        </div>

        {/* Center Nav */}
        <div className="navbar-nav" role="menubar">
          {navItems.map(({ id, icon }) => (
            <button
              key={id}
              className={`nav-item${activeNav === id ? ' active' : ''}`}
              onClick={() => setActiveNav(id)}
              role="menuitem"
              aria-current={activeNav === id ? 'page' : undefined}
            >
              {icon}
              {id}
            </button>
          ))}
        </div>

        {/* Right actions */}
        <div className="navbar-right">
          <button className="navbar-icon-btn" aria-label="Notifications" title="Notifications">
            <BellIcon size={17} />
          </button>
          <button className="navbar-icon-btn" aria-label="Help" title="Help">
            <HelpCircleIcon size={17} />
          </button>
          <div
            className="navbar-avatar"
            role="button"
            tabIndex={0}
            aria-label="User profile"
            title="User profile"
          >
            U
          </div>
        </div>
      </nav>

      {/* ── BODY: SIDEBAR + MAIN WORKSPACE ── */}
      <div className="chat-workspace-body">
        {/* Real Backend-Backed Chat History Sidebar */}
        <ChatSidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
          onDeleteConversation={handleDeleteConversation}
          onRenameConversation={handleRenameConversation}
          isLoadingConversations={isLoadingConversations}
          conversationsError={conversationsError}
          onRetryFetchConversations={fetchConversations}
          activeDataset={activeDataset}
          onClearDataset={handleClearDataset}
          isOpen={isSidebarOpen}
        />

        {/* ── MAIN CHAT AREA ── */}
        <main className="chat-main-area" role="main">
          {/* Active Dataset Bar */}
          {activeDataset && (
            <header className="workspace-top-bar animate-fade-in">
              <div className="top-bar-dataset-info">
                <DatabaseIcon size={14} className="top-bar-icon" />
                <span className="top-bar-title">{datasetName}</span>
                {rowCount && <span className="top-bar-meta">{rowCount.toLocaleString()} rows</span>}
                <span className="top-bar-badge">Engine Active</span>
              </div>
              <div className="top-bar-actions">
                <button
                  className="top-bar-btn"
                  onClick={handleClearDataset}
                  title="Disconnect Dataset"
                >
                  <TrashIcon size={13} />
                  <span>Disconnect</span>
                </button>
              </div>
            </header>
          )}

          {/* Messages or Welcome */}
          <div className="chat-scroll-container">
            {isLoadingMessages ? (
              <div className="messages-loading-state">
                <div className="pulse-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span className="loading-label">Loading messages...</span>
              </div>
            ) : messages.length === 0 ? (
              <SuggestedQuestions
                onSelectSuggestion={(text) => handleSendMessage(text)}
                activeDataset={activeDataset}
                suggestions={suggestions}
              />
            ) : (
              messages.map((msg, i) => (
                <ChatMessage
                  key={msg.id || i}
                  message={msg}
                  onSelectOption={(opt) => handleSendMessage(opt)}
                />
              ))
            )}

            {isLoading && <ChatMessage message={{ sender: 'ai', isLoading: true }} />}
            <div ref={scrollEndRef} />
          </div>

          {/* Chat Input */}
          <ChatInput
            input={input}
            setInput={setInput}
            onSendMessage={handleSendMessage}
            onSendFile={handleSendFile}
            isLoading={isLoading}
            uploadError={uploadError}
            setUploadError={setUploadError}
          />
        </main>
      </div>
    </div>
  )
}

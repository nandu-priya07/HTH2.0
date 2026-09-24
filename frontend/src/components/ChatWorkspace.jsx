import { useState, useRef, useEffect } from 'react'
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
  const [uploadError, setUploadError] = useState(null)
  const [activeDataset, setActiveDataset] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [activeNav, setActiveNav] = useState('Analysis')
  const scrollEndRef = useRef(null)

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  useEffect(() => {
    const fetchExistingDatasets = async () => {
      try {
        const res = await fetch('/api/datasets')
        if (res.ok) {
          const data = await res.json()
          if (data.datasets && data.datasets.length > 0) {
            const latest = data.datasets[0]
            setActiveDataset(latest)
            loadSuggestions(latest.dataset_id)
          }
        }
      } catch (err) {
        console.warn('Backend server not yet ready for datasets list:', err)
      }
    }
    fetchExistingDatasets()
  }, [])

  const loadSuggestions = async (datasetId) => {
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
  }

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
          dataset_id: activeDataset?.dataset_id || null
        })
      })

      const data = await response.json()

      if (!response.ok) {
        setMessages((prev) => [...prev, { sender: 'ai', error: data.error || 'Server returned an error processing your query.' }])
        return
      }

      if (data.dataset_id && (!activeDataset || activeDataset.dataset_id !== data.dataset_id)) {
        setActiveDataset((prev) => prev || { dataset_id: data.dataset_id, filename: 'Active Dataset' })
        loadSuggestions(data.dataset_id)
      }

      const aiMessage = {
        sender: 'ai',
        text: data.text,
        status: data.status,
        result_type: data.result_type,
        scalar: data.scalar,
        table: data.table,
        options: data.options,
        query_spec: data.query_spec,
        metadata: data.metadata,
        error: data.error
      }

      setMessages((prev) => [...prev, aiMessage])
    } catch (err) {
      setMessages((prev) => [...prev, {
        sender: 'ai',
        error: 'Failed to connect to backend analytics engine. Please ensure the backend server is running on port 8000.'
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSendFile = async (file, optionalText) => {
    if (!file || isLoading) return
    setIsLoading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append('file', file)

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

      const rowCount = data.metadata?.rows || data.row_count || '10,000+'
      const colCount = data.metadata?.columns || data.column_count || '20+'

      const aiMsg = {
        sender: 'ai',
        text: `Successfully ingested and cleaned **${data.filename}** (${rowCount.toLocaleString()} rows, ${colCount} columns).\n\nThe dataset schema and data types have been indexed. You can now ask questions, group by dimensions, or run filters.`
      }

      setMessages((prev) => [...prev, userMsg, aiMsg])
      setInput('')

      if (optionalText && optionalText.trim()) {
        setTimeout(() => { handleSendMessage(optionalText.trim()) }, 300)
      }
    } catch (err) {
      setUploadError('Failed to connect to backend server. Make sure FastAPI is running on port 8000.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setInput('')
    setUploadError(null)
  }

  const handleClearDataset = () => {
    setActiveDataset(null)
    setSuggestions([])
    setMessages((prev) => [...prev, {
      sender: 'ai',
      text: 'Active dataset disconnected. Upload a new CSV or Excel file to analyze a new dataset.'
    }])
  }

  const datasetName = activeDataset?.filename || activeDataset?.result?.metadata?.filename || 'Active Dataset'
  const rowCount = activeDataset?.metadata?.rows || activeDataset?.result?.metadata?.rows || activeDataset?.rows

  const navItems = [
    { id: 'Dashboard', icon: <BarChartIcon size={15} /> },
    { id: 'Analysis',  icon: <SparklesIcon size={15} /> },
    { id: 'Datasets',  icon: <DatabaseIcon size={15} /> },
  ]

  return (
    <div className="chat-workspace-container">

      {/* ── TOP NAVIGATION BAR ── */}
      <nav className="top-navbar" role="navigation" aria-label="Main navigation">
        {/* Brand */}
        <div className="navbar-brand" onClick={handleNewChat} role="button" tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && handleNewChat()}>
          <div className="navbar-logo-mark" aria-hidden="true">H</div>
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

      {/* ── MAIN CONTENT ── */}
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
              <button className="top-bar-btn" onClick={handleClearDataset} title="Disconnect Dataset">
                <TrashIcon size={13} />
                <span>Disconnect</span>
              </button>
            </div>
          </header>
        )}

        {/* Messages or Welcome */}
        <div className="chat-scroll-container">
          {messages.length === 0 ? (
            <SuggestedQuestions
              onSelectSuggestion={(text) => handleSendMessage(text)}
              activeDataset={activeDataset}
              suggestions={suggestions}
            />
          ) : (
            messages.map((msg, i) => (
              <ChatMessage
                key={i}
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
  )
}

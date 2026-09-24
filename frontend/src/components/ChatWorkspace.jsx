import { useState, useRef, useEffect } from 'react'
import ChatSidebar from './ChatSidebar'
import ChatMessage from './ChatMessage'
import SuggestedQuestions from './SuggestedQuestions'
import ChatInput from './ChatInput'
import { DatabaseIcon, SparklesIcon, TrashIcon } from './Icons'

export default function ChatWorkspace() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [activeDataset, setActiveDataset] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const scrollEndRef = useRef(null)

  // Auto-scroll chat view when messages change
  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // On mount: check for existing datasets in backend
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

  // 1. Send Question via Backend /api/query
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
        setMessages((prev) => [
          ...prev,
          {
            sender: 'ai',
            error: data.error || 'Server returned an error processing your query.'
          }
        ])
        return
      }

      // If backend auto-loaded a dataset that we didn't have in state
      if (data.dataset_id && (!activeDataset || activeDataset.dataset_id !== data.dataset_id)) {
        setActiveDataset((prev) => prev || { dataset_id: data.dataset_id, filename: 'Active Dataset' })
        loadSuggestions(data.dataset_id)
      }

      // Formulate AI Message
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
      setMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          error: 'Failed to connect to backend analytics engine. Please ensure the backend server is running on port 8000.'
        }
      ])
    } finally {
      setIsLoading(false)
    }
  }

  // 2. Upload File via Backend /api/upload
  const handleSendFile = async (file, optionalText) => {
    if (!file || isLoading) return

    setIsLoading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (!response.ok || !data.success) {
        setUploadError(data.error || 'Upload failed. Only CSV and Excel files are allowed.')
        setIsLoading(false)
        return
      }

      // Add user message showing the file attachment
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

      // Set active dataset and fetch context-tailored suggestions
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

      // If user provided a question alongside the file, automatically execute it
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

  const handleNewChat = () => {
    setMessages([])
    setInput('')
    setUploadError(null)
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

  const handleSelectOption = (option) => {
    handleSendMessage(option)
  }

  const handleSelectSuggestion = (suggestionText) => {
    handleSendMessage(suggestionText)
  }

  const datasetName = activeDataset?.filename || activeDataset?.result?.metadata?.filename || 'Active Dataset'
  const rowCount = activeDataset?.metadata?.rows || activeDataset?.result?.metadata?.rows || activeDataset?.rows

  return (
    <div className="chat-workspace-container">
      {/* 1. LEFT SIDEBAR */}
      <ChatSidebar
        onNewChat={handleNewChat}
        activeDataset={activeDataset}
        onClearDataset={handleClearDataset}
        onSelectSavedQuery={(q) => handleSendMessage(q)}
      />

      {/* 2. MAIN CHAT AREA */}
      <main className="chat-main-area">
        {/* Top Floating Active Dataset Bar */}
        {activeDataset && (
          <header className="workspace-top-bar animate-fade-in">
            <div className="top-bar-dataset-info">
              <DatabaseIcon size={15} className="top-bar-icon" />
              <span className="top-bar-title">{datasetName}</span>
              {rowCount && (
                <span className="top-bar-meta">{rowCount.toLocaleString()} rows</span>
              )}
              <span className="top-bar-badge">Engine Active</span>
            </div>
            <div className="top-bar-actions">
              <button
                className="top-bar-btn"
                onClick={handleClearDataset}
                title="Disconnect Dataset"
              >
                <TrashIcon size={14} />
                <span>Disconnect</span>
              </button>
            </div>
          </header>
        )}

        <div className="chat-scroll-container">
          {messages.length === 0 ? (
            <SuggestedQuestions
              onSelectSuggestion={handleSelectSuggestion}
              activeDataset={activeDataset}
              suggestions={suggestions}
            />
          ) : (
            messages.map((msg, index) => (
              <ChatMessage
                key={index}
                message={msg}
                onSelectOption={handleSelectOption}
              />
            ))
          )}

          {isLoading && (
            <ChatMessage
              message={{
                sender: 'ai',
                isLoading: true
              }}
            />
          )}

          <div ref={scrollEndRef} />
        </div>

        {/* Sticky Composer */}
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

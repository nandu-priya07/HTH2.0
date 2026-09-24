import { useState, useRef, useEffect } from 'react'

export default function ChatInput({
  input,
  setInput,
  onSendMessage,
  onSendFile,
  isLoading,
  uploadError,
  setUploadError
}) {
  const [selectedFile, setSelectedFile] = useState(null)
  const [showTooltip, setShowTooltip] = useState('')
  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '38px'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`
    }
  }, [input])

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  const handleFileClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setSelectedFile(file)
      if (setUploadError) setUploadError(null)
    }
    // Reset file input value so selecting the same file triggers onChange
    e.target.value = ''
  }

  const handleRemoveFile = () => {
    setSelectedFile(null)
    if (setUploadError) setUploadError(null)
  }

  const triggerTooltip = (msg) => {
    setShowTooltip(msg)
    setTimeout(() => setShowTooltip(''), 2500)
  }

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (isLoading) return

    if (selectedFile) {
      onSendFile(selectedFile, input.trim())
      setSelectedFile(null)
    } else if (input.trim()) {
      onSendMessage(input.trim())
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const isSendDisabled = (!input.trim() && !selectedFile) || isLoading

  return (
    <div className="chat-input-sticky">
      {/* Hidden File Input Picker */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv, .xlsx, .xls"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      <div className="input-box-card" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '8px' }}>
        {/* Tooltip Popup */}
        {showTooltip && <div className="tooltip-popup">{showTooltip}</div>}

        {/* Error Banner */}
        {uploadError && (
          <div className="upload-error-banner">
            <span>⚠️ {uploadError}</span>
            <button className="error-close-btn" onClick={() => setUploadError(null)}>✕</button>
          </div>
        )}

        {/* Selected File Attachment Card Preview */}
        {selectedFile && (
          <div className="file-attachment-preview">
            <div className="attachment-icon">📎</div>
            <div className="attachment-details">
              <div className="attachment-name">{selectedFile.name}</div>
              <div className="attachment-size">{formatFileSize(selectedFile.size)}</div>
            </div>
            <button
              type="button"
              className="remove-attachment-btn"
              onClick={handleRemoveFile}
              disabled={isLoading}
              title="Remove attachment"
            >
              ✕
            </button>
          </div>
        )}

        {/* Composer Controls Row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* LEFT: File Upload Button */}
          <button
            type="button"
            className={`input-action-btn ${selectedFile ? 'has-file' : ''}`}
            onClick={handleFileClick}
            disabled={isLoading}
            title="Attach file (.csv, .xlsx, .xls)"
          >
            ＋
          </button>

          {/* CENTER: Textarea Input */}
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedFile ? "Add a message about your dataset... (optional)" : "Ask anything about your dataset..."}
            rows={1}
            disabled={isLoading}
          />

          {/* RIGHT: Voice & Send Buttons */}
          <button
            type="button"
            className="input-action-btn"
            onClick={() => triggerTooltip('Voice input feature coming soon')}
            disabled={isLoading}
            title="Voice Input"
          >
            🎤
          </button>

          <button
            type="button"
            className="send-btn-primary"
            onClick={handleSubmit}
            disabled={isSendDisabled}
            title="Send Question"
          >
            {isLoading ? '...' : '➤'}
          </button>
        </div>
      </div>
    </div>
  )
}

import { useState, useRef, useEffect } from 'react'
import {
  PaperclipIcon,
  SendIcon,
  MicIcon,
  CloseIcon,
  AlertCircleIcon,
  PlusIcon
} from './Icons'

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
      textareaRef.current.style.height = '42px'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`
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
      {/* Hidden File Picker */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv, .xlsx, .xls"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      <div className="input-box-card">
        {/* Tooltip Popup */}
        {showTooltip && (
          <div className="tooltip-popup">
            <span>{showTooltip}</span>
          </div>
        )}

        {/* Error Banner */}
        {uploadError && (
          <div className="upload-error-banner animate-fade-in">
            <div className="error-banner-content">
              <AlertCircleIcon size={16} />
              <span>{uploadError}</span>
            </div>
            <button className="error-close-btn" onClick={() => setUploadError(null)}>
              <CloseIcon size={14} />
            </button>
          </div>
        )}

        {/* Selected File Attachment Card Preview */}
        {selectedFile && (
          <div className="file-attachment-preview animate-fade-in">
            <div className="attachment-icon-badge">
              <PaperclipIcon size={15} />
            </div>
            <div className="attachment-details">
              <div className="attachment-name">{selectedFile.name}</div>
              <div className="attachment-size">{formatFileSize(selectedFile.size)}</div>
            </div>
            <button
              type="button"
              className="remove-attachment-btn"
              onClick={handleRemoveFile}
              disabled={isLoading}
              title="Remove file"
            >
              <CloseIcon size={13} />
            </button>
          </div>
        )}

        {/* Composer Controls Row */}
        <div className="composer-row">
          {/* File Attach Button */}
          <button
            type="button"
            className={`input-action-btn ${selectedFile ? 'has-file' : ''}`}
            onClick={handleFileClick}
            disabled={isLoading}
            title="Attach CSV or Excel dataset"
          >
            <PlusIcon size={18} />
          </button>

          {/* Textarea Input */}
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              selectedFile
                ? "Attach this dataset and ask a question... (or send directly)"
                : "Ask anything about your data in plain English..."
            }
            rows={1}
            disabled={isLoading}
          />

          {/* Voice Input Button */}
          <button
            type="button"
            className="input-action-btn"
            onClick={() => triggerTooltip('Voice query input coming soon')}
            disabled={isLoading}
            title="Voice input"
          >
            <MicIcon size={17} />
          </button>

          {/* Send Button */}
          <button
            type="button"
            className="send-btn-primary"
            onClick={handleSubmit}
            disabled={isSendDisabled}
            title="Send query (Enter)"
          >
            {isLoading ? (
              <span className="btn-spinner"></span>
            ) : (
              <SendIcon size={16} />
            )}
          </button>
        </div>

        {/* Footer Shortcut Helper */}
        <div className="input-footer-hint">
          <span>Enter to submit • Shift + Enter for new line • CSV / Excel supported</span>
        </div>
      </div>
    </div>
  )
}

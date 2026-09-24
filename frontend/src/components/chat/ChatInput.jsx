import { useState, useRef, useEffect } from 'react'
import {
  PaperclipIcon,
  SendIcon,
  MicIcon,
  CloseIcon,
  AlertCircleIcon,
  PlusIcon
} from '../ui/Icons'
import { formatBytes } from '../../lib/dataset'

export default function ChatInput({
  input,
  setInput,
  onSendMessage,
  onSendFile,
  isLoading,
  uploadError,
  setUploadError,
  inputRef,
  hasContext = false
}) {
  const [selectedFile, setSelectedFile] = useState(null)
  const [showTooltip, setShowTooltip] = useState('')
  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)

  // Expose the textarea to parents (e.g. "Ask another question" focuses it)
  useEffect(() => {
    if (inputRef) inputRef.current = textareaRef.current
  }, [inputRef])

  // Auto-resize textarea height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '48px'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`
    }
  }, [input])

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0])
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
    <div className="composer-wrap">
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv, .xlsx, .xls"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={handleFileChange}
      />

      <form className="composer" onSubmit={handleSubmit}>
        {showTooltip && <div className="composer-tooltip" role="status">{showTooltip}</div>}

        {uploadError && (
          <div className="composer-error animate-fade-in" role="alert">
            <AlertCircleIcon size={16} />
            <span>{uploadError}</span>
            <button type="button" className="icon-btn icon-btn-sm" onClick={() => setUploadError(null)} aria-label="Dismiss error">
              <CloseIcon size={14} />
            </button>
          </div>
        )}

        {selectedFile && (
          <div className="composer-file animate-fade-in">
            <PaperclipIcon size={15} />
            <span className="composer-file-name">{selectedFile.name}</span>
            <span className="composer-file-size">{formatBytes(selectedFile.size)}</span>
            <button type="button" className="icon-btn icon-btn-sm" onClick={handleRemoveFile} disabled={isLoading} aria-label="Remove file">
              <CloseIcon size={13} />
            </button>
          </div>
        )}

        <div className="composer-row">
          <button
            type="button"
            className={`icon-btn composer-attach${selectedFile ? ' has-file' : ''}`}
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            title="Attach CSV or Excel dataset"
            aria-label="Attach CSV or Excel dataset"
          >
            <PlusIcon size={18} />
          </button>

          <label htmlFor="ask-input" className="sr-only">Ask a question about your dataset</label>
          <textarea
            id="ask-input"
            ref={textareaRef}
            className="composer-textarea"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              selectedFile
                ? 'Attach this dataset and ask a question… (or send directly)'
                : hasContext
                  ? 'Ask a follow-up — e.g. “What about the second highest?”'
                  : 'Ask anything about your dataset...'
            }
            rows={1}
            disabled={isLoading}
          />

          <button
            type="button"
            className="icon-btn"
            onClick={() => triggerTooltip('Voice query input coming soon')}
            disabled={isLoading}
            aria-label="Voice input (coming soon)"
            title="Voice input"
          >
            <MicIcon size={17} />
          </button>

          <button type="submit" className="composer-send" disabled={isSendDisabled} aria-label="Send question" title="Send (Enter)">
            {isLoading ? <span className="spinner" /> : <SendIcon size={16} />}
          </button>
        </div>
      </form>
      <div className="composer-hint">
        <span><kbd>Enter</kbd> to ask · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line</span>
        {hasContext && <span className="composer-context">Follow-up questions use this conversation's context</span>}
      </div>
    </div>
  )
}

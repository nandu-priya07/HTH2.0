import { useRef, useState } from 'react'
import { UploadIcon, AlertCircleIcon, CheckCircleIcon, FileSpreadsheetIcon } from '../ui/Icons'
import { formatBytes } from '../../lib/dataset'

const ACCEPT = ['.csv', '.xls', '.xlsx']
const isAccepted = (file) => ACCEPT.some((ext) => file.name.toLowerCase().endsWith(ext))

/**
 * Drag & drop zone. Visual states: empty · dragover · uploading · success · error.
 * `status` / `error` / `fileName` are driven by the parent (real upload result).
 */
export default function UploadDropzone({ status = 'empty', error, fileName, onFile, onReset }) {
  const [dragOver, setDragOver] = useState(false)
  const [localError, setLocalError] = useState(null)
  const [picked, setPicked] = useState(null)
  const inputRef = useRef(null)

  const handleFile = (file) => {
    if (!file) return
    if (!isAccepted(file)) {
      setLocalError(`“${file.name}” isn't supported. Please choose a CSV, XLS or XLSX file.`)
      return
    }
    setLocalError(null)
    setPicked(file)
    onFile(file)
  }

  const shownError = localError || (status === 'error' ? error : null)
  const state = dragOver ? 'dragover' : shownError ? 'error' : status
  const busy = status === 'uploading'

  return (
    <div
      className={`dropzone state-${state}`}
      onDragOver={(e) => { e.preventDefault(); if (!busy) setDragOver(true) }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false) }}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        if (!busy) handleFile(e.dataTransfer.files?.[0])
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => { handleFile(e.target.files?.[0]); e.target.value = '' }}
      />

      <div className="dropzone-icon" aria-hidden="true">
        {state === 'success' ? <CheckCircleIcon size={28} />
          : state === 'error' ? <AlertCircleIcon size={28} />
            : state === 'uploading' ? <span className="spinner spinner-teal" style={{ width: 26, height: 26 }} />
              : <UploadIcon size={28} />}
      </div>

      <div className="dropzone-copy" aria-live="polite">
        {state === 'dragover' && <><h3>Drop to upload</h3><p>Release to start schema inference.</p></>}
        {state === 'empty' && <><h3>Drag & drop your file here</h3><p>or browse from your computer</p></>}
        {state === 'uploading' && (
          <>
            <h3>Uploading {picked?.name || fileName}</h3>
            <p>Parsing, cleaning and inferring the schema…</p>
            <div className="dropzone-progress" role="progressbar" aria-label="Uploading" aria-busy="true"><span /></div>
          </>
        )}
        {state === 'success' && <><h3>Analyze a different file?</h3><p>Uploading a new file starts a fresh analysis.</p></>}
        {state === 'error' && <><h3>Upload failed</h3><p>{shownError}</p></>}
      </div>

      <div className="dropzone-actions">
        {(state === 'empty' || state === 'dragover') && (
          <button type="button" className="btn btn-primary" onClick={() => inputRef.current?.click()}>
            <UploadIcon size={16} /> Browse files
          </button>
        )}
        {state === 'error' && (
          <button type="button" className="btn btn-primary" onClick={() => { setLocalError(null); inputRef.current?.click() }}>
            Try another file
          </button>
        )}
        {state === 'success' && (
          <button type="button" className="btn btn-ghost" onClick={() => { setPicked(null); onReset?.(); inputRef.current?.click() }}>
            Upload a different file
          </button>
        )}
      </div>

      <div className="dropzone-formats">
        {['CSV', 'XLS', 'XLSX'].map((f) => (
          <span key={f} className="tag"><FileSpreadsheetIcon size={12} />{f}</span>
        ))}
        {picked && state !== 'success' && <span className="dropzone-size">{formatBytes(picked.size)}</span>}
      </div>
    </div>
  )
}

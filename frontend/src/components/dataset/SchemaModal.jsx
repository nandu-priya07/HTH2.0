import { useEffect, useRef } from 'react'
import SchemaTable from './SchemaTable'
import { CloseIcon } from '../ui/Icons'
import { getSchemaColumns, getDatasetStats } from '../../lib/dataset'

export default function SchemaModal({ dataset, onClose }) {
  const closeRef = useRef(null)
  const stats = getDatasetStats(dataset)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="schema-modal-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3 id="schema-modal-title">Available fields</h3>
            <p className="card-subtitle">Inferred types for <strong className="mono">{stats?.name}</strong> — used to resolve every question.</p>
          </div>
          <button ref={closeRef} className="icon-btn" onClick={onClose} aria-label="Close schema">
            <CloseIcon size={18} />
          </button>
        </div>
        <div className="modal-body" style={{ padding: 0 }}>
          <SchemaTable columns={getSchemaColumns(dataset)} profileColumns={dataset?.profile?.columns || []} rows={stats?.rows} />
        </div>
      </div>
    </div>
  )
}

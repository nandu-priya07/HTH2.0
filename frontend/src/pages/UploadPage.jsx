import { useState } from 'react'
import UploadDropzone from '../components/dataset/UploadDropzone'
import DatasetOverview from '../components/dataset/DatasetOverview'
import SchemaTable from '../components/dataset/SchemaTable'
import DataQualityPanel from '../components/dataset/DataQualityPanel'
import { Link } from '../components/ui/primitives'
import { useAnalyst } from '../state/analystContext'
import { getDatasetStats, getSchemaColumns, computeDataQuality, formatCount, formatBytes } from '../lib/dataset'
import { ArrowRightIcon, CheckCircleIcon, FileSpreadsheetIcon } from '../components/ui/Icons'

export default function UploadPage() {
  const { activeDataset, uploadDataset, isLoading, uploadError, setUploadError } = useAnalyst()
  const [phase, setPhase] = useState(activeDataset ? 'success' : 'empty')
  const [error, setError] = useState(null)

  const stats = getDatasetStats(activeDataset)
  const quality = computeDataQuality(activeDataset)
  const columns = getSchemaColumns(activeDataset)

  const handleFile = async (file) => {
    setError(null)
    setUploadError(null)
    setPhase('uploading')
    const result = await uploadDataset(file, { freshSession: true })
    if (result.ok) setPhase('success')
    else { setError(result.error || uploadError); setPhase('error') }
  }

  const status = isLoading && phase === 'uploading' ? 'uploading' : phase === 'success' && !stats ? 'empty' : phase

  return (
    <div className="page">
      <div className="container">
        <div className="upload-hero">
          <div className="eyebrow">Step 1 · Upload</div>
          <h1>Upload Your Dataset</h1>
          <p>Bring any CSV or Excel file. We'll understand its structure automatically.</p>
        </div>

        <UploadDropzone
          status={status}
          error={error}
          fileName={stats?.name}
          onFile={handleFile}
          onReset={() => { setPhase('empty'); setError(null) }}
        />

        {stats && status === 'success' && (
          <div className="upload-results animate-slide-up">
            <div className="ready-banner card">
              <span className="ready-icon"><CheckCircleIcon size={22} /></span>
              <div className="ready-text">
                <div className="ready-title">Dataset Ready</div>
                <div className="ready-file">
                  <FileSpreadsheetIcon size={14} />
                  <span className="mono">{stats.name}</span>
                  {stats.fileSize ? <span className="muted">· {formatBytes(stats.fileSize)}</span> : null}
                </div>
                <div className="ready-meta"><strong>{formatCount(stats.rows)}</strong> rows · <strong>{formatCount(stats.columns)}</strong> columns</div>
              </div>
              <Link to="/ask-ai" className="btn btn-primary">Ask a question <ArrowRightIcon size={16} /></Link>
            </div>

            <DatasetOverview stats={stats} />

            <div className="upload-detail-grid">
              {columns.length > 0
                ? <SchemaTable columns={columns} profileColumns={activeDataset?.profile?.columns || []} rows={stats.rows} />
                : <section className="card card-pad"><h3 className="card-title">Schema Detected</h3><p className="card-subtitle">No column metadata was returned for this dataset.</p></section>}
              <DataQualityPanel quality={quality} />
            </div>
          </div>
        )}

        {!stats && status !== 'uploading' && (
          <div className="upload-explainer">
            {[
              ['Schema inference', 'Every column is typed as numeric, categorical, date, identifier, boolean or text.'],
              ['Data profiling', 'Missing values, duplicates and value ranges are measured on upload.'],
              ['Cleaning report', 'Column names are standardized and conversions are logged — nothing silent.']
            ].map(([t, d]) => (
              <div key={t} className="upload-explainer-item">
                <CheckCircleIcon size={16} />
                <div><strong>{t}</strong><p>{d}</p></div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Read-only helpers over the dataset payload returned by
 * POST /api/upload and GET /api/dataset/:id. Nothing here assumes
 * any column name — it only reads the inferred schema/profile.
 */

export function getSchemaColumns(ds) {
  return ds?.schema?.columns || ds?.result?.schema?.columns || []
}

export function getDatasetStats(ds) {
  if (!ds) return null
  const schema = ds.schema || ds.result?.schema || {}
  const meta = ds.metadata || ds.result?.metadata || {}
  const columns = schema.columns || []
  const countType = (list, type) =>
    Array.isArray(list) ? list.length : columns.filter((c) => c.semantic_type === type).length

  return {
    name: ds.filename || meta.original_filename || meta.filename || 'Active dataset',
    rows: meta.row_count ?? meta.rows ?? schema.row_count ?? ds.row_count ?? ds.rows ?? null,
    columns: meta.column_count ?? meta.columns ?? schema.column_count ?? (columns.length || null),
    numeric: countType(schema.numeric_columns, 'numeric'),
    categorical: countType(schema.categorical_columns, 'categorical'),
    date: countType(schema.date_columns, 'date'),
    identifier: countType(schema.identifier_columns, 'identifier'),
    fileType: ds.file_type,
    fileSize: ds.file_size
  }
}

export function getNumericColumns(ds) {
  const schema = ds?.schema || ds?.result?.schema || {}
  if (Array.isArray(schema.numeric_columns)) return schema.numeric_columns
  return getSchemaColumns(ds).filter((c) => c.semantic_type === 'numeric').map((c) => c.name)
}

export function formatCount(n) {
  if (n === null || n === undefined || n === '') return '—'
  const num = Number(n)
  return Number.isFinite(num) ? num.toLocaleString() : String(n)
}

export function formatBytes(bytes) {
  if (!bytes) return ''
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

/** Example / range text for a schema column, taken from the real profile. */
export function describeColumnSample(profileCol) {
  if (!profileCol) return '—'
  const s = profileCol.statistics
  if (profileCol.top_values?.length) return String(profileCol.top_values[0].value)
  if (s && s.min !== undefined && s.max !== undefined) {
    return `${Number(s.min).toLocaleString()} – ${Number(s.max).toLocaleString()}`
  }
  if (s?.min_date) return `${String(s.min_date).slice(0, 10)} → ${String(s.max_date).slice(0, 10)}`
  return '—'
}

/**
 * Data-quality metrics derived from the backend profile + cleaning report.
 * Returns null when the payload has no profile (nothing is invented).
 */
export function computeDataQuality(ds) {
  const profile = ds?.profile
  if (!profile) return null
  const meta = ds.metadata || {}
  const cleaning = ds.cleaning_report || {}
  const schemaCols = getSchemaColumns(ds)

  const rows = profile.row_count || meta.row_count || 0
  const cols = profile.column_count || meta.column_count || 0
  const cells = rows * cols || 1

  const missing = profile.quality?.total_missing_values ?? 0
  const duplicates = cleaning.duplicate_rows_removed ?? meta.duplicate_rows_removed ?? profile.duplicate_row_count ?? 0
  const originalRows = meta.original_row_count || rows || 1

  const sumFailed = (obj) =>
    Object.values(obj || {}).reduce((acc, v) => acc + (Number(v?.failed) || 0), 0)
  const invalid = sumFailed(cleaning.numeric_conversions) + sumFailed(cleaning.date_conversions)

  const confidences = schemaCols.map((c) => c.inference_confidence).filter((v) => typeof v === 'number')
  const typeConsistency = confidences.length
    ? confidences.reduce((a, b) => a + b, 0) / confidences.length
    : 1

  const clamp = (v) => Math.max(0, Math.min(1, v))
  const metrics = [
    { key: 'missing', label: 'Missing Values', score: clamp(1 - missing / cells), detail: `${missing.toLocaleString()} empty cells` },
    { key: 'duplicates', label: 'Duplicates', score: clamp(1 - duplicates / originalRows), detail: `${duplicates.toLocaleString()} duplicate rows removed` },
    { key: 'invalid', label: 'Invalid Values', score: clamp(1 - invalid / cells), detail: `${invalid.toLocaleString()} values failed type conversion` },
    { key: 'types', label: 'Type Consistency', score: clamp(typeConsistency), detail: 'Average schema inference confidence' }
  ]
  const score = Math.round((metrics.reduce((a, m) => a + m.score, 0) / metrics.length) * 100)
  return { score, metrics, warnings: cleaning.warnings || [] }
}

export const SEMANTIC_TYPE_META = {
  numeric: { label: 'Numeric', short: 'NUM', tone: 'teal' },
  categorical: { label: 'Categorical', short: 'CAT', tone: 'sage' },
  date: { label: 'Date', short: 'DATE', tone: 'yellow' },
  identifier: { label: 'Identifier', short: 'ID', tone: 'cyan' },
  boolean: { label: 'Boolean', short: 'BOOL', tone: 'coral' },
  text: { label: 'Text', short: 'TEXT', tone: 'neutral' },
  unknown: { label: 'Unknown', short: '?', tone: 'neutral' }
}

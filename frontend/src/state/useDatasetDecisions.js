import { useState, useEffect, useMemo, useRef } from 'react'

/**
 * Custom hook to load or calculate dynamic dataset decision findings.
 *
 * Single source of truth:
 * 1. Fetches /api/dataset/{id}/decisions from backend.
 * 2. Gracefully falls back to deriving decision findings from activeDataset.profile and activeDataset.schema.
 * 3. Immediately clears previous decisions and enters loading state when the active dataset changes.
 */
export function useDatasetDecisions(activeDataset) {
  const [decisionsData, setDecisionsData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const lastLoadedIdRef = useRef(null)

  const datasetId = activeDataset?.dataset_id || activeDataset?.result?.dataset_id || null

  useEffect(() => {
    // If no dataset is active, clear immediately
    if (!activeDataset || !datasetId) {
      setDecisionsData(null)
      setIsLoading(false)
      setError(null)
      lastLoadedIdRef.current = null
      return
    }

    // If dataset changed, reset state immediately to prevent stale flashes
    if (lastLoadedIdRef.current !== datasetId) {
      setDecisionsData(null)
      lastLoadedIdRef.current = datasetId
    }

    let isCancelled = false
    setIsLoading(true)
    setError(null)

    async function fetchDecisions() {
      try {
        const res = await fetch(`/api/dataset/${datasetId}/decisions`)
        if (res.ok) {
          const data = await res.json()
          if (!isCancelled && data.success) {
            setDecisionsData(data)
            setIsLoading(false)
            return
          }
        }
      } catch (err) {
        console.warn('Failed to fetch backend decisions, using profile fallback:', err)
      }

      // Fallback: derive dynamically from activeDataset.profile & schema
      if (!isCancelled) {
        const derived = deriveDecisionsFromProfile(activeDataset)
        setDecisionsData(derived)
        setIsLoading(false)
      }
    }

    fetchDecisions()

    return () => {
      isCancelled = true
    }
  }, [datasetId, activeDataset])

  return useMemo(() => {
    const raw = decisionsData || {}
    const dsName = activeDataset?.name || activeDataset?.metadata?.filename || activeDataset?.result?.metadata?.filename || 'Dataset'
    const rowCount = raw.row_count ?? activeDataset?.metadata?.row_count ?? activeDataset?.result?.metadata?.row_count ?? 0
    const colCount = raw.column_count ?? activeDataset?.metadata?.column_count ?? activeDataset?.result?.metadata?.column_count ?? 0

    const decisions = raw.decisions || []

    const profile = {
      datasetName: dsName,
      rowCount,
      columnCount: colCount,
      hasNumeric: !!raw.has_numeric,
      hasCategorical: !!raw.has_categorical,
      hasDate: !!raw.has_date
    }

    const stats = {
      name: dsName,
      rows: rowCount,
      cols: colCount
    }

    return {
      loading: isLoading,
      isLoading,
      error,
      decisions,
      stats,
      profile,
      hasDecisions: decisions.length > 0,
      data: raw
    }
  }, [isLoading, error, decisionsData, activeDataset])
}

/**
 * Fallback decision generator using activeDataset profile statistics and top values.
 * Strictly calculates from actual metadata; never introduces sample or fake values.
 */
function deriveDecisionsFromProfile(dataset) {
  if (!dataset) return null

  const schema = dataset.schema || dataset.result?.schema || {}
  const profile = dataset.profile || dataset.result?.profile || {}
  const meta = dataset.metadata || dataset.result?.metadata || {}

  const totalRows = Number(meta.row_count ?? profile.row_count ?? schema.row_count ?? 0)
  const totalCols = Number(meta.column_count ?? profile.column_count ?? schema.column_count ?? 0)

  const numericCols = (schema.numeric_columns || []).filter(c => !isIdCol(c))
  const categoricalCols = (schema.categorical_columns || []).filter(c => !isIdCol(c))
  const dateCols = schema.date_columns || []

  const colProfiles = (profile.columns || []).reduce((acc, c) => {
    acc[c.name] = c
    return acc
  }, {})

  const decisions = []

  // 1. Dominant Categorical Share
  for (const cat of categoricalCols.slice(0, 3)) {
    const p = colProfiles[cat] || {}
    const topValues = p.top_values || []
    if (topValues.length >= 2 && totalRows > 0) {
      const top = topValues[0]
      const count = Number(top.count)
      const pct = (count / totalRows) * 100

      if (pct >= 30) {
        decisions.push({
          id: `dec_dist_${cat}`,
          type: 'distribution',
          finding: `'${top.value}' represents ${pct.toFixed(1)}% of all recorded observations in ${formatName(cat).toLowerCase()}.`,
          metrics: [
            { label: `'${top.value}' count`, value: count.toLocaleString() },
            { label: 'Total records', value: totalRows.toLocaleString() },
            { label: 'Share', value: `${pct.toFixed(1)}%` }
          ],
          evidence: [
            `FREQUENCY DISTRIBUTION GROUP BY ${cat}`,
            `${totalRows.toLocaleString()} rows analyzed`,
            `${topValues.length} distinct category values`
          ],
          analysis: `Categorical representation distribution across the ${formatName(cat)} field.`
        })
        break
      }
    }
  }

  // 2. Measure Scale & Dispersion
  if (numericCols.length > 0) {
    const num = numericCols[0]
    const p = colProfiles[num] || {}
    const stats = p.statistics || {}

    if (stats.sum !== undefined && stats.mean !== undefined) {
      const isCurr = isCurrencyCol(num)
      decisions.push({
        id: `dec_scale_${num}`,
        type: 'scale',
        finding: `${formatName(num)} aggregates to ${formatNum(stats.sum, isCurr)} with an average of ${formatNum(stats.mean, isCurr)} per record.`,
        metrics: [
          { label: `Total ${formatName(num).toLowerCase()}`, value: formatNum(stats.sum, isCurr) },
          { label: 'Average', value: formatNum(stats.mean, isCurr) },
          { label: 'Range', value: `${formatNum(stats.min, isCurr)} – ${formatNum(stats.max, isCurr)}` }
        ],
        evidence: [
          `SUM(${num}), AVG(${num})`,
          `${totalRows.toLocaleString()} rows analyzed`,
          'Descriptive distribution statistics'
        ],
        analysis: `Statistical scale and baseline central tendency across the ${formatName(num)} measure.`
      })
    }
  }

  return {
    dataset_id: dataset.dataset_id,
    row_count: totalRows,
    column_count: totalCols,
    numeric_columns: numericCols,
    categorical_columns: categoricalCols,
    date_columns: dateCols,
    decisions,
    has_numeric: numericCols.length > 0,
    has_categorical: categoricalCols.length > 0,
    has_date: dateCols.length > 0
  }
}

function isIdCol(colName) {
  const s = String(colName).toLowerCase().replace(/[-_]/g, '').trim()
  return s === 'id' || s === 'rowid' || s === 'orderid' || s === 'customerid' || s.endsWith('id')
}

function isCurrencyCol(colName) {
  const s = String(colName).toLowerCase()
  return ['sales', 'revenue', 'profit', 'cost', 'charge', 'price', 'fee', 'spend', 'budget', 'amount'].some(k => s.includes(k))
}

function formatName(col) {
  if (!col) return ''
  return String(col).replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatNum(v, isCurr = false) {
  if (v === null || v === undefined) return '—'
  const num = Number(v)
  if (!Number.isFinite(num)) return String(v)
  const prefix = isCurr ? '$' : ''
  if (Math.abs(num) >= 1_000_000) return `${prefix}${(num / 1_000_000).toFixed(2)}M`
  if (Math.abs(num) >= 1_000) return `${prefix}${(num / 1_000).toFixed(1)}K`
  return `${prefix}${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

export default useDatasetDecisions

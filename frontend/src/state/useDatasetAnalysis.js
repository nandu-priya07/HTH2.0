import { useState, useEffect, useMemo, useRef } from 'react'

/**
 * Custom hook to load or calculate dynamic dataset analysis,
 * metrics, distributions, comparisons, trends, and anomalies.
 *
 * Single source of truth:
 * 1. Fetches /api/dataset/{id}/insights from backend (which runs Pandas on the full dataset).
 * 2. Fallbacks gracefully to client-side derivation from activeDataset.profile and activeDataset.schema.
 * 3. Immediately clears stale insights and indicates loading when dataset changes.
 */
export function useDatasetAnalysis(activeDataset) {
  const [insightsData, setInsightsData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const lastLoadedIdRef = useRef(null)

  const datasetId = activeDataset?.dataset_id || activeDataset?.result?.dataset_id || null

  useEffect(() => {
    // If no dataset is active, clear immediately
    if (!activeDataset || !datasetId) {
      setInsightsData(null)
      setIsLoading(false)
      setError(null)
      lastLoadedIdRef.current = null
      return
    }

    // If dataset changed, reset data to avoid stale flashes
    if (lastLoadedIdRef.current !== datasetId) {
      setInsightsData(null)
      lastLoadedIdRef.current = datasetId
    }

    let isCancelled = false
    setIsLoading(true)
    setError(null)

    async function fetchInsights() {
      try {
        const res = await fetch(`/api/dataset/${datasetId}/insights`)
        if (res.ok) {
          const data = await res.json()
          if (!isCancelled && data.success) {
            setInsightsData(data)
            setIsLoading(false)
            return
          }
        }
      } catch (err) {
        console.warn('Failed to fetch backend insights, falling back to profile summary:', err)
      }

      // Fallback: derive dynamically from activeDataset.profile & schema
      if (!isCancelled) {
        const derived = deriveInsightsFromProfile(activeDataset)
        setInsightsData(derived)
        setIsLoading(false)
      }
    }

    fetchInsights()

    return () => {
      isCancelled = true
    }
  }, [datasetId, activeDataset])

  return useMemo(() => {
    const raw = insightsData || {}
    const dsName = activeDataset?.name || activeDataset?.metadata?.filename || activeDataset?.result?.metadata?.filename || 'Dataset'
    const rowCount = raw.row_count ?? activeDataset?.metadata?.row_count ?? activeDataset?.result?.metadata?.row_count ?? 0
    const colCount = raw.column_count ?? activeDataset?.metadata?.column_count ?? activeDataset?.result?.metadata?.column_count ?? 0

    const profile = {
      datasetName: dsName,
      rowCount,
      columnCount: colCount,
      numericColumns: raw.numeric_columns || [],
      categoricalColumns: raw.categorical_columns || [],
      dateColumns: raw.date_columns || [],
      identifierColumns: raw.identifier_columns || [],
      hasNumeric: !!raw.has_numeric || (raw.numeric_columns?.length > 0) || (raw.metrics?.length > 0),
      hasCategorical: !!raw.has_categorical || (raw.categorical_columns?.length > 0) || (raw.categoricals?.length > 0),
      hasDate: !!raw.has_date || (raw.date_columns?.length > 0)
    }

    const metrics = raw.metrics || []
    const categories = raw.categoricals || []
    const automatedInsights = raw.automated_insights || []
    const anomalies = raw.anomalies || []

    const anomalyEvidence = {
      fields: raw.numeric_columns?.length ? raw.numeric_columns.slice(0, 2) : ['Numeric Measures'],
      rows: rowCount,
      aggregation: 'Statistical IQR Fence (1.5 × IQR)',
      transformation: 'Evaluated Upper Fence (Q3 + 1.5×IQR) and Lower Fence (Q1 - 1.5×IQR) per measure',
      sort: 'Absolute deviation DESC'
    }

    const stats = {
      name: dsName,
      rows: rowCount,
      cols: colCount
    }

    const hasData = rowCount > 0 || metrics.length > 0 || categories.length > 0

    return {
      loading: isLoading,
      isLoading,
      error,
      profile,
      metrics,
      categories,
      automatedInsights,
      anomalies,
      anomalyEvidence,
      stats,
      hasData,
      data: raw
    }
  }, [isLoading, error, insightsData, activeDataset])
}

/**
 * Fallback insight generator using activeDataset's profile and schema directly.
 * Ensures zero dependency on sample data even if the insights endpoint is unreachable.
 */
function deriveInsightsFromProfile(dataset) {
  if (!dataset) return null

  const schema = dataset.schema || dataset.result?.schema || {}
  const profile = dataset.profile || dataset.result?.profile || {}
  const meta = dataset.metadata || dataset.result?.metadata || {}

  const totalRows = Number(meta.row_count ?? profile.row_count ?? schema.row_count ?? 0)
  const totalCols = Number(meta.column_count ?? profile.column_count ?? schema.column_count ?? 0)

  const numericCols = schema.numeric_columns || []
  const categoricalCols = schema.categorical_columns || []
  const dateCols = schema.date_columns || []
  const identifierCols = schema.identifier_columns || []

  const colProfiles = (profile.columns || []).reduce((acc, c) => {
    acc[c.name] = c
    return acc
  }, {})

  // Metrics
  const metrics = numericCols.slice(0, 4).map((col) => {
    const prof = colProfiles[col] || {}
    const stats = prof.statistics || {}
    const sumVal = stats.sum ?? 0
    return {
      id: `metric_${col}`,
      name: col,
      column: col,
      label: col,
      sum: sumVal,
      mean: stats.mean,
      median: stats.median,
      min: stats.min,
      max: stats.max,
      std: stats.std,
      count: stats.count || totalRows,
      explanation: `Mean ${formatNum(stats.mean)} · range ${formatNum(stats.min)} – ${formatNum(stats.max)}`,
      evidence: {
        fields: [col],
        rows: totalRows,
        filteredRows: stats.count || totalRows,
        aggregation: 'SUM',
        transformation: `Aggregated summary statistics over ${col}`
      }
    }
  })

  // Categoricals
  const categoricals = categoricalCols.slice(0, 4).map((col) => {
    const prof = colProfiles[col] || {}
    const topValues = prof.top_values || []
    const topItem = topValues[0] || { value: '—', count: 0 }
    const pct = totalRows > 0 ? Math.round((topItem.count / totalRows) * 1000) / 10 : 0
    return {
      id: `cat_${col}`,
      name: col,
      column: col,
      label: col,
      mostFrequent: String(topItem.value),
      mostFrequentCount: topItem.count,
      top_value: String(topItem.value),
      count: topItem.count,
      share: `${pct}%`,
      percentage: pct,
      topValues: topValues.map((t) => ({ value: String(t.value), count: Number(t.count) })),
      explanation: `${topItem.count.toLocaleString()} of ${totalRows.toLocaleString()} rows (${pct}%)`,
      distribution_labels: topValues.map((t) => String(t.value).slice(0, 12)),
      distribution_data: topValues.map((t) => Number(t.count)),
      evidence: {
        fields: [col],
        rows: totalRows,
        aggregation: 'FREQUENCY',
        transformation: `Count frequency distribution in ${col}`
      }
    }
  })

  // Automated Insights
  const automatedInsights = []

  // Top category dominance
  categoricals.forEach((cat) => {
    if (cat.percentage >= 35 && automatedInsights.length < 3) {
      automatedInsights.push({
        id: `dom_${cat.column}`,
        type: 'distribution',
        title: `${cat.column.replace(/_/g, ' ').toUpperCase()} Dominance`,
        metric: cat.top_value,
        change: `${cat.percentage}% share`,
        direction: 'flat',
        explanation: `'${cat.top_value}' accounts for ${cat.percentage}% of all records in ${cat.column}.`,
        visual: 'bars',
        data: cat.distribution_data,
        labels: cat.distribution_labels,
        evidence: cat.evidence
      })
    }
  })

  return {
    dataset_id: dataset.dataset_id,
    row_count: totalRows,
    column_count: totalCols,
    numeric_columns: numericCols,
    categorical_columns: categoricalCols,
    date_columns: dateCols,
    identifier_columns: identifierCols,
    metrics,
    categoricals,
    automated_insights: automatedInsights,
    anomalies: [],
    total_anomalies: 0,
    has_date: dateCols.length > 0,
    has_numeric: numericCols.length > 0,
    has_categorical: categoricalCols.length > 0
  }
}

function formatNum(v) {
  if (v === null || v === undefined) return '—'
  const num = Number(v)
  if (!Number.isFinite(num)) return String(v)
  if (Math.abs(num) >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`
  return num.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default useDatasetAnalysis

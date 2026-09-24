/**
 * Reusable formatting utilities for charts, metrics, and data tables.
 */

export const CHART_COLORS = [
  '#6366F1', // Indigo
  '#3B82F6', // Blue
  '#06B6D4', // Cyan
  '#10B981', // Emerald
  '#F59E0B', // Amber
  '#EC4899', // Pink
  '#8B5CF6', // Violet
  '#F43F5E'  // Rose
]

export function formatValue(val, format = 'number') {
  if (val === null || val === undefined || isNaN(val)) {
    return '-'
  }

  const num = typeof val === 'number' ? val : parseFloat(val)
  if (isNaN(num)) {
    return String(val)
  }

  const isInt = Number.isInteger(num)
  const maxDecimals = isInt ? 0 : 2

  if (format === 'currency') {
    return `$${num.toLocaleString(undefined, {
      minimumFractionDigits: isInt ? 0 : 2,
      maximumFractionDigits: maxDecimals
    })}`
  }

  if (format === 'percentage') {
    return `${num.toLocaleString(undefined, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 2
    })}%`
  }

  return num.toLocaleString(undefined, {
    minimumFractionDigits: isInt ? 0 : 0,
    maximumFractionDigits: maxDecimals
  })
}

export function formatAxisNumber(num) {
  if (typeof num !== 'number') return num
  const abs = Math.abs(num)
  if (abs >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  }
  if (abs >= 1_000) {
    return `${(num / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  }
  return num.toLocaleString()
}

export function truncateLabel(str, maxLen = 16) {
  if (!str) return ''
  const s = String(str)
  if (s.length <= maxLen) return s
  return s.substring(0, maxLen - 1) + '…'
}

export function formatColumnHeader(str) {
  if (!str) return ''
  return String(str)
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

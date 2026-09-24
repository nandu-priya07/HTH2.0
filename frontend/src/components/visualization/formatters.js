/**
 * Reusable formatting utilities for charts, metrics, and data tables.
 */

/* Categorical series — deeper steps of the brand hues (teal, coral, cyan,
   yellow, sage), validated for CVD + normal-vision separation in this order.
   Assigned in fixed order, never cycled: extra categories fold into "Other". */
export const CHART_COLORS = [
  '#008A9E', // teal
  '#E2682F', // coral
  '#1FB5C8', // cyan
  '#C28C00', // yellow
  '#2E7A3C'  // sage
]
export const OTHER_COLOR = '#A9BDC0'
export const PRIMARY_SERIES = CHART_COLORS[0]
export const AXIS_TICK = { fill: '#557177', fontSize: 12 }
export const AXIS_LINE = { stroke: '#DDEDEC' }
export const GRID_STROKE = '#E6F1F0'

/** Fold rows beyond the palette size into a single "Other" row (for part-to-whole charts). */
export function foldToOther(data, labelKey, valueKey, max = CHART_COLORS.length) {
  if (!Array.isArray(data) || data.length <= max) return data
  const sorted = [...data].sort((a, b) => (Number(b[valueKey]) || 0) - (Number(a[valueKey]) || 0))
  const head = sorted.slice(0, max - 1)
  const rest = sorted.slice(max - 1).reduce((acc, r) => acc + (Number(r[valueKey]) || 0), 0)
  return [...head, { [labelKey]: 'Other', [valueKey]: rest, __other: true }]
}

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

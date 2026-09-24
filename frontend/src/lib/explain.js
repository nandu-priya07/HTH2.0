/**
 * Builds the "How we got this answer" trace and evidence summary from the
 * query_spec / intent / metadata the backend already returns with /api/query.
 * It only restates what the backend executed — no inference happens here.
 */

const OP_LABEL = {
  sum: 'SUM',
  average: 'AVG',
  mean: 'AVG',
  count: 'COUNT',
  count_distinct: 'COUNT DISTINCT',
  distinct: 'DISTINCT',
  min: 'MIN',
  max: 'MAX',
  conditional_count: 'COUNT'
}

const OP_WORD = {
  sum: 'Summed',
  average: 'Averaged',
  mean: 'Averaged',
  count: 'Counted',
  count_distinct: 'Counted the distinct values of',
  distinct: 'Listed the distinct values of',
  min: 'Took the minimum of',
  max: 'Took the maximum of',
  conditional_count: 'Counted'
}

const fmtFilter = (f) => `${f.column} ${f.operator === 'equals' ? '=' : f.operator} ${JSON.stringify(f.value)}`
const fmtCondition = (c) => `${c.operator === 'equals' ? '=' : c.operator} ${JSON.stringify(c.value)}`

export function hasExplanation(message) {
  return Boolean(message?.query_spec && message.query_spec.operation)
}

export function buildExplanation(message) {
  const spec = message?.query_spec
  if (!spec) return null

  const op = String(spec.operation || 'count').toLowerCase()
  const measure = spec.column || (spec.columns && spec.columns[0]) || null
  const groupBy = spec.group_by || []
  const filters = spec.filters || []
  const sort = spec.sort || []
  const limit = spec.limit
  const meta = message.metadata || {}

  /* Intent chips */
  const intent = []
  if (filters.length || spec.condition) intent.push('FILTER')
  if (groupBy.length) intent.push('GROUP')
  intent.push(op === 'distinct' ? 'LIST' : 'AGGREGATE')
  if (groupBy.length && (sort.length || limit)) intent.push(limit ? 'TOP-N' : 'RANK')
  else if (groupBy.length) intent.push('COMPARE')

  /* Fields */
  const fields = [...new Set([measure, ...(spec.columns || []), ...groupBy, ...filters.map((f) => f.column), ...sort.map((s) => s.column)].filter(Boolean))]

  /* Pseudo-query expression */
  const agg = OP_LABEL[op] || op.toUpperCase()
  let expr = `${agg}(${measure || '*'})`
  if (filters.length) expr += ` WHERE ${filters.map(fmtFilter).join(' AND ')}`
  if (spec.condition && measure) expr += `${filters.length ? ' AND' : ' WHERE'} ${measure} ${fmtCondition(spec.condition)}`
  if (groupBy.length) expr += ` GROUP BY ${groupBy.join(', ')}`
  if (sort.length) expr += ` ORDER BY ${sort.map((s) => `${s.column} ${String(s.direction || 'desc').toUpperCase()}`).join(', ')}`
  if (limit) expr += ` LIMIT ${limit}`

  /* Plain-language steps */
  const steps = []
  if (measure) steps.push(`Identified “${measure}” as the field to measure.`)
  if (groupBy.length) steps.push(`Identified ${groupBy.map((g) => `“${g}”`).join(' and ')} as the grouping field${groupBy.length > 1 ? 's' : ''}.`)
  if (filters.length) steps.push(`Kept only rows where ${filters.map(fmtFilter).join(' and ')}.`)
  if (spec.condition && measure) steps.push(`Kept only rows where ${measure} ${fmtCondition(spec.condition)}.`)
  if (groupBy.length) steps.push(`Grouped records by ${groupBy.join(', ')}.`)
  steps.push(`${OP_WORD[op] || 'Applied ' + agg + ' to'} ${measure ? `“${measure}”` : 'the matching records'}${groupBy.length ? ' within each group' : ''}.`)
  if (sort.length) steps.push(`Sorted results by ${sort.map((s) => `${s.column} (${s.direction === 'asc' ? 'ascending' : 'descending'})`).join(', ')}.`)
  if (limit) steps.push(`Kept the top ${limit} result${limit > 1 ? 's' : ''}.`)
  if (meta.rows_analyzed !== undefined) {
    steps.push(`Analyzed ${Number(meta.rows_analyzed).toLocaleString()} rows${meta.filtered_rows !== undefined && meta.filtered_rows !== meta.rows_analyzed ? ` (${Number(meta.filtered_rows).toLocaleString()} after filters)` : ''}.`)
  }

  return {
    question: spec.raw_question || message.question || null,
    intent: message.intent?.operation ? [...new Set([String(message.intent.operation).toUpperCase(), ...intent])] : intent,
    fields,
    expression: expr,
    result: summarizeResult(message),
    steps,
    evidence: {
      fields,
      rows: meta.rows_analyzed,
      filteredRows: meta.filtered_rows,
      filters: filters.length ? filters.map(fmtFilter) : spec.condition && measure ? [`${measure} ${fmtCondition(spec.condition)}`] : [],
      transformation: groupBy.length ? `Group by ${groupBy.join(', ')}` : null,
      aggregation: agg,
      sort: sort.length ? sort.map((s) => `${s.column} ${s.direction === 'asc' ? 'ascending' : 'descending'}`).join(', ') : null,
      limit: limit || null
    }
  }
}

function summarizeResult(message) {
  const { scalar, table } = message
  if (scalar && scalar.value !== undefined) {
    const v = typeof scalar.value === 'number' ? scalar.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(scalar.value)
    return `${scalar.metric || 'Result'} = ${v}`
  }
  if (table?.headers?.length && table.rows?.length) {
    const fmt = (value) => (typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value)
    const last = (row) => row[row.length - 1]
    if (table.rows.length === 1 || table.headers.length < 2) {
      const row = table.rows[0]
      return `${row[0]}${table.headers.length > 1 ? ` = ${fmt(last(row))}` : ''}`
    }
    // Multi-row result: report the largest value in the last (measure) column.
    const numeric = table.rows.every((r) => typeof last(r) === 'number')
    const row = numeric ? table.rows.reduce((best, r) => (last(r) > last(best) ? r : best)) : table.rows[0]
    return numeric
      ? `${row[0]} = ${fmt(last(row))} (highest of ${table.rows.length})`
      : `${row[0]} = ${fmt(last(row))} (first of ${table.rows.length} rows)`
  }
  return null
}

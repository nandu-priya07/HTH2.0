import { useState } from 'react'
import { TableIcon, CopyIcon } from '../ui/Icons'
import { formatValue, formatColumnHeader } from './formatters'

export default function DataTable({
  title,
  headers = [],
  rows = [],
  data = [],
  description,
  format = 'number'
}) {
  const [copied, setCopied] = useState(false)

  // Construct headers and rows from either format
  let tableHeaders = headers
  let tableRows = rows

  if ((!tableHeaders || tableHeaders.length === 0) && data && data.length > 0) {
    tableHeaders = Object.keys(data[0])
    tableRows = data.map((item) => tableHeaders.map((h) => item[h]))
  }

  if (!tableHeaders || tableHeaders.length === 0 || !tableRows || tableRows.length === 0) {
    return null
  }

  const handleCopy = () => {
    const csvContent = [
      tableHeaders.join(','),
      ...tableRows.map((row) =>
        row
          .map((cell) => {
            const str = String(cell ?? '')
            return str.includes(',') ? `"${str}"` : str
          })
          .join(',')
      )
    ].join('\n')

    navigator.clipboard.writeText(csvContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Calculate max values per numeric column for proportional bar indicators
  const numericMaxMap = {}
  tableHeaders.forEach((h, colIdx) => {
    let maxVal = 0
    let isColNumeric = true
    tableRows.forEach((r) => {
      const val = parseFloat(r[colIdx])
      if (!isNaN(val)) {
        if (val > maxVal) maxVal = val
      } else if (r[colIdx] !== null && r[colIdx] !== undefined && r[colIdx] !== '') {
        isColNumeric = false
      }
    })
    if (isColNumeric && maxVal > 0) {
      numericMaxMap[colIdx] = maxVal
    }
  })

  return (
    <div className="vis-table-card animate-fade-in">
      <div className="vis-table-header">
        <div className="vis-table-title-group">
          <div className="vis-table-icon-pill">
            <TableIcon size={14} />
          </div>
          <span className="vis-table-title">{title || 'Data Results'}</span>
          <span className="vis-table-count-badge">{tableRows.length} rows</span>
        </div>

        <button
          className="vis-table-action-btn"
          onClick={handleCopy}
          title="Copy full data table as CSV"
        >
          <CopyIcon size={13} />
          <span>{copied ? 'Copied CSV!' : 'Copy CSV'}</span>
        </button>
      </div>

      {description && <div className="vis-table-desc">{description}</div>}

      <div className="vis-table-scroll-container">
        <table className="vis-analytics-table">
          <thead>
            <tr>
              {tableHeaders.map((h, i) => (
                <th
                  key={i}
                  className={numericMaxMap[i] !== undefined ? 'text-right' : 'text-left'}
                >
                  {formatColumnHeader(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row, rIdx) => (
              <tr key={rIdx}>
                {row.map((cell, cIdx) => {
                  const isNum = typeof cell === 'number' || (!isNaN(parseFloat(cell)) && numericMaxMap[cIdx] !== undefined)
                  const numVal = isNum ? (typeof cell === 'number' ? cell : parseFloat(cell)) : null
                  const maxVal = numericMaxMap[cIdx] || 0
                  const pct = isNum && maxVal > 0 ? Math.min((numVal / maxVal) * 100, 100) : 0

                  return (
                    <td
                      key={cIdx}
                      className={isNum ? 'text-right cell-numeric' : 'text-left'}
                    >
                      <div className="vis-cell-wrapper">
                        <span className="vis-cell-text">
                          {isNum ? formatValue(numVal, format) : String(cell ?? '-')}
                        </span>
                        {isNum && maxVal > 0 && (
                          <div className="vis-mini-progress">
                            <div
                              className="vis-mini-progress-fill"
                              style={{ width: `${Math.max(pct, 2)}%` }}
                            />
                          </div>
                        )}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

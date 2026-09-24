import { useMemo, useState } from 'react'
import { TypeBadge } from '../ui/primitives'
import { SearchIcon } from '../ui/Icons'
import { describeColumnSample } from '../../lib/dataset'

/**
 * "Schema Detected" — renders whatever columns the backend inferred.
 * columns: schema.columns[] ; profileColumns: profile.columns[] (optional)
 */
export default function SchemaTable({ columns = [], profileColumns = [], rows }) {
  const [query, setQuery] = useState('')
  const profileByName = useMemo(() => Object.fromEntries(profileColumns.map((p) => [p.name, p])), [profileColumns])
  const filtered = columns.filter((c) => c.name?.toLowerCase().includes(query.toLowerCase()))

  return (
    <section className="card schema-table-card" aria-labelledby="schema-detected-title">
      <header className="card-header" style={{ padding: '20px 24px 0', alignItems: 'center' }}>
        <div>
          <h3 id="schema-detected-title" className="card-title">Schema Detected</h3>
          <p className="card-subtitle">{columns.length} fields · types inferred automatically</p>
        </div>
        <label className="search-field">
          <SearchIcon size={14} />
          <span className="sr-only">Filter fields</span>
          <input className="input" placeholder="Filter fields" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </header>
      <div className="table-wrap schema-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Type</th>
              <th className="num">Missing</th>
              <th className="num">Unique</th>
              <th>Example / Range</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((col) => {
              const p = profileByName[col.name]
              const missing = col.missing_count ?? p?.missing_count ?? 0
              const pct = p?.missing_percentage ?? (rows ? (missing / rows) * 100 : null)
              return (
                <tr key={col.name}>
                  <td>
                    <span className="mono schema-field">{col.name}</span>
                    {col.original_name && col.original_name !== col.name && (
                      <span className="schema-orig" title="Original column name">was “{col.original_name}”</span>
                    )}
                  </td>
                  <td>
                    <TypeBadge type={col.semantic_type} />
                    {col.dtype && <span className="schema-dtype mono">{col.dtype}</span>}
                  </td>
                  <td className="num">
                    {missing.toLocaleString()}
                    {pct !== null && pct !== undefined && <span className="schema-pct"> ({Number(pct).toFixed(1)}%)</span>}
                  </td>
                  <td className="num">{(col.unique_count ?? p?.unique_count ?? 0).toLocaleString()}</td>
                  <td className="schema-example mono" title={describeColumnSample(p)}>{describeColumnSample(p)}</td>
                </tr>
              )
            })}
            {!filtered.length && (
              <tr><td colSpan={5} className="muted" style={{ textAlign: 'center', padding: 24 }}>No fields match “{query}”.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

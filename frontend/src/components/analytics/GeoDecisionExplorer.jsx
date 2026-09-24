import { useEffect, useState } from 'react'
import GeoInsightMap from './GeoInsightMap'
import '../../styles/geo.css'

export default function GeoDecisionExplorer({ geo, evidence, result }) {
  const points = geo?.map_data || []
  const rows = geo?.locations || []
  const [selected, setSelected] = useState(null)
  const [geojson, setGeojson] = useState(null)
  useEffect(() => { fetch('/geo/ne_110m_admin_0_countries.geojson').then((r) => r.ok ? r.json() : null).then(setGeojson).catch(() => setGeojson(null)) }, [])
  const active = rows.find((r) => r.location === selected) || rows[0]
  return <section className="geo-explorer">
    <header><div><span className="geo-eyebrow">Geo-intelligent decision explorer</span><h3>{result?.metric} by {result?.dimension}</h3></div><span className="geo-tag">{result?.ranking === 'ascending' ? 'Lowest first' : 'Highest first'}</span></header>
    <div className="geo-grid"><div className="geo-map"><GeoInsightMap geojson={geojson} mapData={points} results={rows} selected={selected || active?.location} onSelect={setSelected} metricName={result?.metric}/></div>
    <aside className="geo-insight"><span className="geo-eyebrow">Selected location</span>{active ? <><h4>{active.location}</h4><dl><dt>Metric</dt><dd>{Number(active.metric).toLocaleString()}</dd><dt>Rank</dt><dd>#{active.rank}</dd><dt>Share of total</dt><dd>{active.contribution == null ? '—' : `${active.contribution}%`}</dd></dl><p>Observed value ranked #{active.rank} among the locations in this analysis.</p></> : <p>No locations matched.</p>}</aside></div>
    <div className="geo-ranking"><h4>Location ranking</h4><div className="geo-table-scroll"><table><thead><tr><th>Location</th><th>Metric</th><th>Rank</th><th>Share</th></tr></thead><tbody>{rows.map((r) => <tr key={r.location} onClick={() => setSelected(r.location)} className={active?.location===r.location?'selected':''}><td>{r.location}</td><td>{Number(r.metric).toLocaleString()}</td><td>#{r.rank}</td><td>{r.contribution == null ? '—' : `${r.contribution}%`}</td></tr>)}</tbody></table></div></div>
    {result?.anomaly && <div className="geo-evidence"><b>Baseline:</b> {Number(result.anomaly.baseline?.value).toLocaleString()} · <b>Method:</b> {result.anomaly.method} ({result.anomaly.dispersion}), threshold {result.anomaly.threshold}</div>}
    {geo?.unresolved_count > 0 && <div className="geo-evidence">{geo.unresolved_count} locations could not be placed on the map; they remain in the ranking.</div>}
    <details className="geo-details"><summary>View analysis details</summary><pre>{JSON.stringify(evidence, null, 2)}</pre><p>Hierarchy: {(geo?.hierarchy || []).map((h) => h.level).join(' → ') || 'Not inferred'}</p></details>
  </section>
}

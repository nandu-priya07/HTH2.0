import { useCallback, useEffect, useRef, useState } from 'react'
import { useAnalyst } from '../state/analystContext'
import GeoInsightMap from '../components/analytics/GeoInsightMap'
import '../styles/explorer.css'

const money = (value) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })

export default function ExplorerPage() {
  const { activeConversationId, conversations, isLoadingConversations, selectConversation } = useAnalyst()
  const [context, setContext] = useState(null)
  const [geojson, setGeojson] = useState(null)
  const [geo, setGeo] = useState(null)
  const [geoStack, setGeoStack] = useState([])
  const [metricName, setMetricName] = useState('')
  const [dimension, setDimension] = useState('')
  const [direction, setDirection] = useState('highest')
  const [view, setView] = useState('map')
  const [question, setQuestion] = useState('')
  const [selected, setSelected] = useState('')
  const [loadingContext, setLoadingContext] = useState(false)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [error, setError] = useState('')
  const autoStarted = useRef(null)

  useEffect(() => {
    if (isLoadingConversations || activeConversationId) return
    const latestWithData = conversations.find((item) => item.dataset_id || item.files?.length)
    if (latestWithData) selectConversation(latestWithData.id)
  }, [activeConversationId, conversations, isLoadingConversations, selectConversation])

  useEffect(() => {
    let cancelled = false
    if (!activeConversationId) return undefined
    const loadingTimer=window.setTimeout(() => { setLoadingContext(true); setError('') }, 0)
    fetch(`/api/chats/${encodeURIComponent(activeConversationId)}/explorer`)
      .then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.detail || body.error || 'Could not load the selected chat dataset.'); return body })
      .then((body) => { if (!cancelled) { setContext(body); setGeo(null); setGeoStack([]); const initial=body.hierarchy?.[0]?.column || body.geographic_dimensions?.[0]?.column || ''; setDimension(initial); setMetricName(body.default_metric || body.metrics?.[0]?.name || '') } })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoadingContext(false) })
    return () => { cancelled = true; window.clearTimeout(loadingTimer) }
  }, [activeConversationId])

  useEffect(() => { fetch('/geo/ne_110m_admin_0_countries.geojson').then((r) => r.ok ? r.json() : null).then(setGeojson).catch(() => setGeojson(null)) }, [])

  const runAnalysis = useCallback(async (prompt) => {
    if (!context?.dataset?.file_id || context.chat_id !== activeConversationId || !metricName || !dimension) return
    setLoadingAnalysis(true); setError('')
    const metric=context.metrics.find((item) => item.name === metricName)
    const query=prompt?.trim() || `Show the ${direction === 'lowest' ? 'lowest' : 'highest'} ${metric?.aggregation || 'sum'} of ${metricName} by ${dimension}`
    try {
      const response=await fetch(`/api/chats/${encodeURIComponent(activeConversationId)}/messages`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:query,dataset_id:context.dataset.file_id}) })
      const body=await response.json()
      if (!response.ok) throw new Error(body.detail || body.error || 'Geographic analysis failed.')
      if (body.analysis_type !== 'geographic_analysis' || !body.geo) throw new Error(body.error || 'The planner did not return a geographic analysis. Try asking for a metric by a geographic field.')
      if (geo && geo.geography?.column !== body.geography?.column) setGeoStack((items) => [...items, geo])
      setGeo(body); setSelected('')
      setQuestion('')
    } catch (err) { setError(err.message) }
    finally { setLoadingAnalysis(false) }
  }, [activeConversationId, context, dimension, direction, metricName, geo])

  useEffect(() => {
    if (!context || context.chat_id !== activeConversationId || geo?.chat_id === activeConversationId || loadingContext || loadingAnalysis || !context.geographic_dimensions?.length || !metricName || !dimension) return
    const key = `${context.dataset.file_id}:${metricName}:${dimension}`
    if (autoStarted.current === key) return
    autoStarted.current = key
    runAnalysis()
  }, [activeConversationId, context, geo, loadingContext, loadingAnalysis, metricName, dimension, runAnalysis])

  const visibleContext=context?.chat_id===activeConversationId ? context : null
  const visibleGeo=geo?.chat_id===activeConversationId ? geo : null
  const metrics=visibleContext?.metrics || []
  const dimensions=visibleContext?.geographic_dimensions || []
  const responseGeo=visibleGeo?.geo
  const rows=visibleGeo?.results || visibleGeo?.result?.locations || []
  const resultMetric=visibleGeo?.metric_detail?.name || visibleGeo?.result?.metric || metricName
  const selectedRow=rows.find((row) => (row.location ?? row.name) === selected) || rows[0]
  const parentLabel=Object.values(selectedRow?.parents || {}).join(', ')
  const hierarchy=visibleContext?.hierarchy || []
  const currentLevelIndex=hierarchy.findIndex((item)=>item.column===visibleGeo?.geography?.column)
  const nextLevel=currentLevelIndex>=0 ? hierarchy[currentLevelIndex+1] : null
  const navigation=[...geoStack, ...(visibleGeo ? [visibleGeo] : [])]
  const breadcrumbs=(visibleGeo?.query_spec?.filters || []).map((filter) => {
    const levelIndex=hierarchy.findIndex((item)=>item.column===filter.column)
    const destination=levelIndex>=0 ? hierarchy[levelIndex+1]?.column : null
    const targetIndex=destination ? navigation.findIndex((item)=>item.geography?.column===destination) : -1
    return { ...filter, targetIndex }
  }).filter((item)=>item.targetIndex>=0)
  const currentConversation=conversations.find((item) => item.id === activeConversationId)

  const submitQuestion=(event) => { event.preventDefault(); runAnalysis(question) }
  const drillDown=() => {
    if (!nextLevel || !selectedRow) return
    const parentColumn=visibleGeo.geography.column
    const parentValue=selectedRow.entity ?? selectedRow[parentColumn] ?? selectedRow.location
    setDimension(nextLevel.column)
    runAnalysis(`Break ${parentColumn} ${parentValue} down by ${nextLevel.column} for ${metricName}`)
  }
  const goBack=(index) => {
    const target=navigation[index]
    if (!target) return
    setGeo(target); setDimension(target.geography.column); setSelected('')
    setGeoStack(navigation.slice(0,index))
  }

  return <div className="explorer-page">
    <div className="explorer-shell">
      <header className="explorer-heading"><div><div className="explorer-eyebrow">QueryLens · geographic analysis</div><h1>Geo-Intelligent Decision Explorer</h1><p>Analyze locations and compare the metrics in your selected chat dataset.</p></div>
        <label className="explorer-chat-picker"><span>Current chat</span><select value={activeConversationId || ''} onChange={(event) => event.target.value && selectConversation(event.target.value)}><option value="">Select a chat</option>{conversations.map((item) => <option key={item.id} value={item.id}>{item.title || item.id}</option>)}</select></label>
      </header>

      {!activeConversationId && !isLoadingConversations && <div className="explorer-state"><h2>No chat selected</h2><p>Select a chat with an uploaded dataset to explore its geographic data.</p></div>}
      {(loadingContext || loadingAnalysis) && <div className="explorer-state" role="status"><div className="explorer-spinner"/><h2>{loadingContext ? 'Detecting geographic fields…' : dimension && visibleContext?.hierarchy?.[0]?.column !== dimension ? 'Resolving geographic boundaries…' : 'Building geographic analysis…'}</h2><p>Detecting available metrics and resolving real locations…</p></div>}
      {error && !loadingContext && !loadingAnalysis && <div className="explorer-state is-error"><h2>Explorer could not load this analysis</h2><p>{error}</p><button type="button" onClick={() => context ? runAnalysis() : setContext(null)}>Retry</button></div>}

      {visibleContext && !loadingContext && <>
        <section className="explorer-dataset"><div><span>Dataset</span><strong>{visibleContext.dataset.filename}</strong></div><div><span>Size</span><strong>{Number(visibleContext.dataset.rows).toLocaleString()} rows · {visibleContext.dataset.columns} columns</strong></div><div><span>Chat</span><strong>{currentConversation?.title || activeConversationId}</strong></div></section>
        {!dimensions.length ? <div className="explorer-state"><h2>Geographic exploration isn’t available for this dataset.</h2><p>No geographic column was detected in its schema or values.</p></div>
          : !metrics.length ? <div className="explorer-state"><h2>Geographic fields were detected, but no suitable metric is available.</h2><p>Add a numeric measure to analyze these locations.</p></div>
          : <>
            <form className="explorer-controls" onSubmit={submitQuestion}>
              <label><span>Metric</span><select value={metricName} onChange={(e)=>setMetricName(e.target.value)}>{metrics.map((m)=><option value={m.name} key={m.name}>{m.name}{m.type==='derived'?' · derived':''}</option>)}</select></label>
              <label><span>Geographic level</span><select value={dimension} onChange={(e)=>setDimension(e.target.value)}>{(visibleContext.hierarchy?.length?visibleContext.hierarchy:dimensions).map((d)=><option value={d.column} key={d.column}>{d.label || d.column}</option>)}</select></label>
              <label><span>Ranking</span><select value={direction} onChange={(e)=>setDirection(e.target.value)}><option value="highest">Highest</option><option value="lowest">Lowest</option></select></label>
              <button type="button" className="explorer-run" disabled={loadingAnalysis} onClick={()=>runAnalysis()}>Run analysis</button>
              <div className="explorer-question"><input value={question} onChange={(e)=>setQuestion(e.target.value)} placeholder="Ask: Which countries generate the most revenue?" aria-label="Ask a geographic question"/><button type="submit" disabled={loadingAnalysis}>Ask</button></div>
              <div className="explorer-view-switch" role="group" aria-label="Explorer view">{['map','ranking','table'].map((item)=><button type="button" key={item} aria-pressed={view===item} onClick={()=>setView(item)}>{item[0].toUpperCase()+item.slice(1)}</button>)}</div>
            </form>
              {visibleGeo && <>
              <nav className="explorer-breadcrumb" aria-label="Geographic navigation"><button type="button" onClick={()=>geoStack.length&&goBack(0)}>All {hierarchy[0]?.label || hierarchy[0]?.column || 'locations'}</button>{breadcrumbs.map((item,index)=><span key={`${item.column}-${item.value}-${index}`}><i>/</i><button type="button" onClick={()=>goBack(item.targetIndex)}>{Array.isArray(item.value)?item.value.join(', '):item.value}</button></span>)}<strong>{visibleGeo.geography?.label || visibleGeo.geography?.column}</strong></nav>
              <div className="explorer-summary"><span>{visibleGeo.metric_detail?.type==='derived' ? `Derived: ${visibleGeo.metric_detail.formula?.replace('*','×').replace('-','−').replace('/','÷')}` : 'Existing dataset metric'}</span><span>Aggregation: {visibleGeo.metric_detail?.aggregation?.toUpperCase()}</span><span>Geography: {visibleGeo.geography?.column}</span><span>{rows.length.toLocaleString()} locations</span></div>
              {view==='map' && <div className="explorer-grid">
                <section className="explorer-panel explorer-map-panel"><header><div><h2>{resultMetric} by {visibleGeo.geography?.label || visibleGeo.geography?.column}</h2><span>{visibleGeo.map?.type==='choropleth'?'Country choropleth':visibleGeo.map?.boundary_status==='available'?'Administrative boundary choropleth':visibleGeo.map?.boundary_status==='partial'?'Partial administrative boundaries':'Administrative boundaries unavailable'}</span></div></header><GeoInsightMap geojson={visibleGeo.geography?.entity_type==='country' ? geojson : visibleGeo.map?.boundaries} mapData={visibleGeo.map?.features || responseGeo?.map_data} results={rows} selected={selected || (selectedRow?.location ?? selectedRow?.name)} onSelect={setSelected} metricName={resultMetric} level={visibleGeo.geography?.entity_type || 'country'} boundaryStatus={visibleGeo.map?.boundary_status} unresolvedCount={responseGeo?.unresolved_count} entityLabel={visibleGeo.geography?.label || visibleGeo.geography?.column || 'locations'}/>{visibleGeo.map?.boundary_sources?.length>0 && <small className="explorer-map-attribution">Boundary source: {visibleGeo.map.boundary_sources.join('; ')}</small>}</section>
                <section className="explorer-panel explorer-insight"><span className="explorer-eyebrow">Selected location</span>{selectedRow ? <><h2>{selectedRow.location ?? selectedRow.name}</h2><dl><dt>{resultMetric}</dt><dd>{money(selectedRow.value ?? selectedRow.metric)}</dd><dt>Rank{parentLabel ? ` in ${parentLabel}` : ''}</dt><dd>#{selectedRow.rank}</dd><dt>Share{parentLabel ? ` of ${parentLabel}` : ' of total'}</dt><dd>{selectedRow.share != null ? `${(selectedRow.share*100).toFixed(1)}%` : `${selectedRow.contribution}%`}</dd>{selectedRow.transactions != null && <><dt>Transactions</dt><dd>{Number(selectedRow.transactions).toLocaleString()}</dd></>}{selectedRow.difference_from_median != null && <><dt>Difference from median</dt><dd>{money(selectedRow.difference_from_median)}</dd></>}</dl><p>{selectedRow.location ?? selectedRow.name} contributes {selectedRow.contribution}% of {parentLabel || 'the analyzed total'} and ranks #{selectedRow.rank}{parentLabel ? ` within ${parentLabel}` : ''}.</p></> : <p>No matching results.</p>}</section>
              </div>}
              {nextLevel && selectedRow?.child_count > 0 && <section className="explorer-panel explorer-drilldown"><div><span className="explorer-eyebrow">Next geographic level</span><p>{selectedRow.location} · {selectedRow.child_count} {nextLevel.label || nextLevel.column} values detected</p></div><button type="button" className="explorer-run" onClick={drillDown}>Explore {nextLevel.label || nextLevel.column} →</button></section>}
              {view!=='table' && <section className="explorer-panel explorer-ranking"><header><div><h2>Location ranking</h2><span>{direction==='lowest'?'Lowest first':'Highest first'} · {visibleGeo.geography?.column}</span></div></header><div className="explorer-ranking-list">{rows.map((row)=>{const value=Number(row.value ?? row.metric); const top=Math.max(...rows.map((r)=>Math.abs(Number(r.value ?? r.metric))),1);return <button type="button" className={selected===(row.location??row.name)?'selected':''} key={row.location ?? row.name} onClick={()=>setSelected(row.location ?? row.name)}><span className="explorer-rank">#{row.rank}</span><span className="explorer-location"><strong>{row.location ?? row.name}</strong><i><b style={{width:`${Math.max(2,Math.abs(value)/top*100)}%`}}/></i></span><strong>{money(value)}</strong></button>})}</div></section>}
              {view==='table' && <section className="explorer-panel explorer-data-table"><h2>Location results</h2><div className="explorer-table-scroll"><table><thead><tr><th>Location</th><th>Rank</th><th>{resultMetric}</th><th>Share</th><th>Transactions</th></tr></thead><tbody>{rows.map((row)=><tr key={row.location} onClick={()=>setSelected(row.location)}><td>{row.location}</td><td>#{row.rank}</td><td>{money(row.value)}</td><td>{row.contribution}%</td><td>{row.transactions == null ? '—' : Number(row.transactions).toLocaleString()}</td></tr>)}</tbody></table></div></section>}
              {view!=='map' && selectedRow && <section className="explorer-panel explorer-selected-insight"><span className="explorer-eyebrow">Selected location</span><h2>{selectedRow.location}</h2><p>{resultMetric}: {money(selectedRow.value)} · Rank #{selectedRow.rank} · {selectedRow.contribution}% of total{selectedRow.transactions != null ? ` · ${Number(selectedRow.transactions).toLocaleString()} transactions` : ''}</p></section>}
              {visibleGeo.result?.anomaly && <section className="explorer-panel explorer-anomaly"><h2>Spatial anomaly lens</h2><p>Baseline: {money(visibleGeo.result.anomaly.baseline.value)} · Method: {visibleGeo.result.anomaly.method} ({visibleGeo.result.anomaly.dispersion}) · Threshold: {visibleGeo.result.anomaly.threshold}</p>{visibleGeo.result.anomaly.locations.map((item)=><span key={item.location}>{item.location}: {item.classification} ({item.anomaly_score})</span>)}</section>}
              <details className="explorer-details"><summary>View analysis details</summary><dl><dt>Metric</dt><dd>{visibleGeo.metric_detail?.name}</dd><dt>Metric type</dt><dd>{visibleGeo.metric_detail?.type}</dd><dt>Formula</dt><dd>{visibleGeo.metric_detail?.formula || 'Existing column'}</dd><dt>Source columns</dt><dd>{visibleGeo.metric_detail?.required_columns?.join(', ') || visibleGeo.metric_detail?.name}</dd><dt>Geography</dt><dd>{visibleGeo.geography?.column} ({visibleGeo.geography?.entity_type})</dd><dt>Aggregation</dt><dd>{visibleGeo.metric_detail?.aggregation?.toUpperCase()}</dd><dt>Filters</dt><dd>{visibleGeo.evidence?.filters?.map((item)=>`${item.column} ${item.operator} ${item.value}`).join('; ') || 'None'}</dd><dt>Map resolution</dt><dd>{responseGeo?.unresolved_count ? `${responseGeo.unresolved_count} values could not be joined to map geometry; they remain ranked.` : 'Dataset values matched to geographic geometry.'}</dd></dl></details>
            </>}
          </>}
      </>}
    </div>
  </div>
}

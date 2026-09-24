import { useMemo, useState } from 'react'

const normalize = (value) => String(value ?? '').normalize('NFKD').replace(/[^a-z0-9]/gi, '').toLowerCase()
function getFeatureName(feature, level) {
  const props=feature?.properties || {}
  if (level==='country') return props.querylens_name || props.ADMIN || props.NAME_EN || props.NAME || props.name
  return props.querylens_name || props.NAME_1 || props.name_1 || props.NAME_2 || props.name_2 || props.shapeName || props.admin1Name || props.admin2Name || props.name || props.NAME || props.NAME_EN || props.ADMIN
}
function getFeatureParent(feature) {
  const props=feature?.properties || {}
  return props.querylens_parent || props.NAME_0 || props.name_0 || props.admin || props.geonunit || props.country || props.parent
}
const coordsOf = (value, out = []) => {
  if (!Array.isArray(value)) return out
  if (value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))) out.push(value)
  else value.forEach((part) => coordsOf(part, out))
  return out
}
function createProject(features, fit) {
  if (!fit) return ([lon, lat]) => [((lon + 180) / 360) * 960, ((90 - lat) / 180) * 500]
  // Admin boundary collections can contain hundreds of thousands of vertices.
  // Avoid Math.min/max(...values): spreading that many coordinates overflows
  // the JS argument stack and prevents the SVG map from rendering at all.
  let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity
  for (const feature of features) {
    for (const [lon, lat] of coordsOf(feature.geometry?.coordinates)) {
      const x=Number(lon), y=Number(lat)
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue
      minX=Math.min(minX,x); maxX=Math.max(maxX,x)
      minY=Math.min(minY,y); maxY=Math.max(maxY,y)
    }
  }
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return ([lon, lat]) => [((lon + 180) / 360) * 960, ((90 - lat) / 180) * 500]
  const scale=Math.min(912/Math.max(maxX-minX,.01),452/Math.max(maxY-minY,.01))
  const offsetX=(960-(maxX-minX)*scale)/2, offsetY=(500-(maxY-minY)*scale)/2
  return ([lon,lat]) => [offsetX+(Number(lon)-minX)*scale, 500-offsetY-(Number(lat)-minY)*scale]
}
function ringPath(ring, project) {
  return ring.map((coordinate, index) => { const [x,y] = project(coordinate); return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}` }).join(' ') + 'Z'
}
function geometryPath(geometry, project) {
  if (!geometry) return ''
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : []
  return polygons.map((polygon) => polygon.map((ring) => ringPath(ring, project)).join(' ')).join(' ')
}

export default function GeoInsightMap({ geojson, mapData = [], results = [], selected, onSelect, metricName, level = 'country', boundaryStatus, unresolvedCount = 0, entityLabel = 'locations' }) {
  const [hovered, setHovered] = useState(null)
  const byGeometry = useMemo(() => {
    const result=new Map()
    mapData.forEach((item)=>{const key=normalize(item.geometry_name);result.set(key,[...(result.get(key)||[]),item])})
    return result
  }, [mapData])
  const valueMap = useMemo(() => new Map(results.map((item) => [normalize(item.location ?? item.name), item])), [results])
  const items = useMemo(() => geojson?.features || [], [geojson])
  const fitted = items.some((feature) => {
    const props=feature.properties || {}
    return props.NAME_1 || props.NAME_2 || props.name_1 || props.name_2 || props.querylens_name || props.shapeName || props.admin1Name
  })
  const project = useMemo(() => createProject(items, fitted), [items, fitted])
  const values = results.map((item) => Number(item.value ?? item.metric)).filter(Number.isFinite)
  const min = Math.min(...values), max = Math.max(...values)
  const color = (value) => {
    const t = max === min ? 0.65 : (Number(value) - min) / (max - min)
    return `rgba(139,92,246,${0.16 + Math.max(0, Math.min(1,t)) * 0.82})`
  }
  const active = hovered || valueMap.get(normalize(selected))
  if (!items.length) return <div className="geo-map-empty">{boundaryStatus === 'unavailable' ? <><strong>{entityLabel} boundaries could not be resolved.</strong><span>{unresolvedCount.toLocaleString()} {entityLabel} values were analyzed successfully. The ranking remains available.</span></> : <>No matching geographic boundaries are available. The location ranking remains available.</>}</div>
  return <div className="geo-map-wrap">
    <svg className="geo-world-map" viewBox="0 0 960 500" role="img" aria-label={`${metricName} choropleth map`}>
      {items.map((feature, index) => {
        const props = feature.properties || {}
        const geometryName = getFeatureName(feature,level)
        const candidates = byGeometry.get(normalize(geometryName)) || []
        const featureParent=getFeatureParent(feature)
        const matched = candidates.find((item)=>item.parent_name && normalize(item.parent_name)===normalize(featureParent)) || candidates[0]
        const row = matched && valueMap.get(normalize(matched.location ?? matched.name))
        const isSelected = row && normalize(row.location ?? row.name) === normalize(selected)
        return <path key={`${props.ADM0_A3 || props.HASC_1 || geometryName}-${index}`} d={geometryPath(feature.geometry, project)} fill={row ? color(row.value ?? row.metric) : '#252b38'} className={`geo-country${isSelected ? ' is-selected' : ''}${row ? ' has-value' : ''}`} onMouseEnter={() => row && setHovered(row)} onMouseLeave={() => setHovered(null)} onClick={() => row && onSelect(row.location ?? row.name)}>
          <title>{row ? `${row.location ?? row.name} · ${metricName}: ${Number(row.value ?? row.metric).toLocaleString()} · rank #${row.rank}` : ''}</title>
        </path>
      })}
    </svg>
    {active && <div className="geo-map-tooltip"><strong>{active.location ?? active.name}</strong><span>{metricName}: {Number(active.value ?? active.metric).toLocaleString()}</span><span>Rank #{active.rank}</span><span>Share of parent: {active.share != null ? `${(active.share * 100).toFixed(1)}%` : `${active.contribution ?? 0}%`}</span></div>}
    <div className="geo-map-legend"><span>Lower</span><i /><i /><i /><i /><i /><span>Higher</span></div>
  </div>
}

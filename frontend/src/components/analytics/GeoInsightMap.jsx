import { useMemo, useState } from 'react'

const normalize = (value) => String(value ?? '').normalize('NFKD').replace(/[^a-z0-9]/gi, '').toLowerCase()
const project = ([lon, lat]) => [((lon + 180) / 360) * 960, ((90 - lat) / 180) * 500]
function ringPath(ring) {
  return ring.map((coordinate, index) => { const [x,y] = project(coordinate); return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}` }).join(' ') + 'Z'
}
function geometryPath(geometry) {
  if (!geometry) return ''
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : []
  return polygons.map((polygon) => polygon.map(ringPath).join(' ')).join(' ')
}

export default function GeoInsightMap({ geojson, mapData = [], results = [], selected, onSelect, metricName }) {
  const [hovered, setHovered] = useState(null)
  const byGeometry = useMemo(() => new Map(mapData.map((item) => [normalize(item.geometry_name), item])), [mapData])
  const valueMap = useMemo(() => new Map(results.map((item) => [normalize(item.location ?? item.name), item])), [results])
  const values = results.map((item) => Number(item.value ?? item.metric)).filter(Number.isFinite)
  const min = Math.min(...values), max = Math.max(...values)
  const color = (v) => {
    const t = max === min ? 0.65 : (Number(v) - min) / (max - min)
    const alpha = 0.16 + Math.max(0, Math.min(1,t)) * 0.82
    return `rgba(139,92,246,${alpha})`
  }
  const active = hovered || valueMap.get(normalize(selected))
  const items = geojson?.features || []
  if (!items.length) return <div className="geo-map-empty">Country boundary data could not be loaded. The data ranking is still available.</div>
  return <div className="geo-map-wrap">
    <svg className="geo-world-map" viewBox="0 0 960 500" role="img" aria-label={`${metricName} choropleth map`}>
      {items.map((feature, index) => {
        const props = feature.properties || {}
        const geometryName = props.ADMIN || props.NAME_EN || props.NAME
        const matched = byGeometry.get(normalize(geometryName))
        const row = matched && valueMap.get(normalize(matched.name))
        const isSelected = row && normalize(row.location ?? row.name) === normalize(selected)
        return <path key={`${props.ADM0_A3 || geometryName}-${index}`} d={geometryPath(feature.geometry)} fill={row ? color(row.value ?? row.metric) : '#252b38'} className={`geo-country${isSelected ? ' is-selected' : ''}${row ? ' has-value' : ''}`} onMouseEnter={() => row && setHovered(row)} onMouseLeave={() => setHovered(null)} onClick={() => row && onSelect(row.location ?? row.name)}>
          <title>{row ? `${row.location ?? row.name} · ${metricName}: ${Number(row.value ?? row.metric).toLocaleString()} · rank #${row.rank}` : ''}</title>
        </path>
      })}
    </svg>
    {active && <div className="geo-map-tooltip"><strong>{active.location ?? active.name}</strong><span>{metricName}: {Number(active.value ?? active.metric).toLocaleString()}</span><span>Rank #{active.rank}</span><span>Share of total: {active.share != null ? `${(active.share * 100).toFixed(1)}%` : `${active.contribution ?? 0}%`}</span></div>}
    <div className="geo-map-legend"><span>Lower</span><i /><i /><i /><i /><i /><span>Higher</span></div>
  </div>
}

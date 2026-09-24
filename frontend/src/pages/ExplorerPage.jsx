import { useMemo, useState } from 'react'
import WorldDotMap from '../components/hero/WorldDotMap'
import ChartContainer from '../components/analytics/ChartContainer'
import { HBarList } from '../components/analytics/MiniCharts'
import { PreviewBadge } from '../components/ui/primitives'
import { EXPLORER_REGIONS } from '../mocks/previewData'
import { project } from '../lib/worldMask'

const METRICS = [
  { id: 'revenue', label: 'Revenue', scale: 1, unit: 'M', prefix: '$' },
  { id: 'orders', label: 'Orders', scale: 12.4, unit: 'k', prefix: '' },
  { id: 'profit', label: 'Profit', scale: 0.24, unit: 'M', prefix: '$' }
]
const HIERARCHY = ['Region', 'Country', 'State / Province', 'City']
const VIEWS = ['Heatmap', 'Points', 'Choropleth']

/* Sequential ramp (one hue, light → dark) for choropleth shading. */
const RAMP = ['#D7EFEF', '#9ED8DC', '#4FB3BC', '#097C87', '#064E55']

export default function ExplorerPage() {
  const [metricId, setMetricId] = useState('revenue')
  const [level, setLevel] = useState('Region')
  const [view, setView] = useState('Points')
  const metric = METRICS.find((m) => m.id === metricId)

  const regions = useMemo(
    () => EXPLORER_REGIONS.map((r) => ({ ...r, v: +(r.value * metric.scale).toFixed(2) })).sort((a, b) => b.v - a.v),
    [metric]
  )
  const max = Math.max(...regions.map((r) => r.v))
  const fmt = (v) => `${metric.prefix}${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}${metric.unit}`

  const nodes = view === 'Points'
    ? regions.map((r, i) => ({ lon: r.lon, lat: r.lat, tone: i === 0 ? 'yellow' : i < 3 ? 'cyan' : 'sage', r: 3 + 6 * (r.v / max), label: `${r.name}: ${fmt(r.v)}` }))
    : []
  const heat = view === 'Heatmap' ? regions.map((r) => ({ lon: r.lon, lat: r.lat, intensity: r.v / max })) : []

  const cellFill = useMemo(() => {
    if (view !== 'Choropleth') return undefined
    const centers = regions.map((r) => ({ ...project(r.lon, r.lat), t: r.v / max }))
    return (cell) => {
      let best = centers[0]
      let bestD = Infinity
      centers.forEach((c) => {
        const d = (c.col - cell.col) ** 2 + (c.row - cell.row) ** 2
        if (d < bestD) { bestD = d; best = c }
      })
      return RAMP[Math.min(RAMP.length - 1, Math.floor(best.t * RAMP.length))]
    }
  }, [view, regions, max])

  return (
    <div className="page">
      <div className="container">
        <header className="page-header">
          <div>
            <div className="eyebrow">Explorer</div>
            <h1>Explore by geography</h1>
            <p>When a dataset contains a geographic field, its values can be mapped at any level of the hierarchy.</p>
          </div>
          <PreviewBadge />
        </header>

        <div className="explorer-controls card" role="group" aria-label="Map controls">
          <label>
            <span className="field-label">Metric</span>
            <select className="select" value={metricId} onChange={(e) => setMetricId(e.target.value)}>
              {METRICS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
          <label>
            <span className="field-label">Geographic Hierarchy</span>
            <select className="select" value={level} onChange={(e) => setLevel(e.target.value)}>
              {HIERARCHY.map((h) => <option key={h}>{h}</option>)}
            </select>
          </label>
          <div>
            <span className="field-label" id="view-label">View</span>
            <div className="segmented" role="group" aria-labelledby="view-label">
              {VIEWS.map((v) => (
                <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>{v}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="explorer-grid">
          <ChartContainer
            title={`${metric.label} by ${level}`}
            subtitle={`${view} view`}
            className="explorer-map"
            footer={view === 'Choropleth' && (
              <div className="ramp-legend" aria-label="Color scale">
                <span>Low</span>
                {RAMP.map((c) => <span key={c} className="ramp-swatch" style={{ background: c }} />)}
                <span>High</span>
              </div>
            )}
          >
            <WorldDotMap nodes={nodes} heat={heat} cellFill={cellFill} animated={view !== 'Choropleth'} title={`${metric.label} by ${level}, ${view} view`} />
          </ChartContainer>

          <ChartContainer title="Ranking" subtitle={`${metric.label} · ${level}`}>
            <HBarList items={regions.map((r) => ({ label: r.name, value: r.v }))} format={fmt} />
          </ChartContainer>
        </div>
      </div>
    </div>
  )
}

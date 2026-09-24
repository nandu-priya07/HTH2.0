import { useState } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, LabelList } from 'recharts'
import ChartContainer from '../components/analytics/ChartContainer'
import { PreviewBadge } from '../components/ui/primitives'
import { SCENARIO_BASE } from '../mocks/previewData'
import { CHART_COLORS, AXIS_TICK, AXIS_LINE, GRID_STROKE } from '../components/visualization/formatters'

const LEVERS = [
  { id: 'sales', label: 'Increase Sales' },
  { id: 'price', label: 'Adjust Price' },
  { id: 'cost', label: 'Reduce Costs' }
]
const CURRENT = CHART_COLORS[0]
const SCENARIO = CHART_COLORS[1]
const money = (v) => `$${v.toFixed(2)}M`

function ScenarioTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="vis-tooltip-card">
      <div className="vis-tooltip-label">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="vis-tooltip-row">
          <span className="vis-tooltip-bullet" style={{ background: p.color }} />
          <span className="vis-tooltip-name">{p.name}:</span>
          <span className="vis-tooltip-val">{money(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

export default function ScenariosPage() {
  const [lever, setLever] = useState('sales')
  const [pct, setPct] = useState(10)

  // Placeholder arithmetic on sample values — the real scenario engine is a later phase.
  const factor = 1 + pct / 100
  const rows = [
    { metric: 'Revenue', current: SCENARIO_BASE.revenue, scenario: +(SCENARIO_BASE.revenue * factor).toFixed(2) },
    { metric: 'Profit', current: SCENARIO_BASE.profit, scenario: +(SCENARIO_BASE.profit * factor).toFixed(2) }
  ]

  return (
    <div className="page">
      <div className="container">
        <header className="page-header">
          <div>
            <div className="eyebrow">Scenarios</div>
            <h1>What if…?</h1>
            <p>Model a change to one lever and compare the outcome with today's baseline.</p>
          </div>
          <PreviewBadge>Sample data · linear placeholder</PreviewBadge>
        </header>

        <div className="scenario-grid">
          <section className="card card-pad scenario-controls" aria-labelledby="lever-title">
            <h2 id="lever-title" className="card-title">Scenario</h2>
            <div className="segmented" role="group" aria-label="Lever" style={{ marginTop: 12 }}>
              {LEVERS.map((l) => (
                <button key={l.id} type="button" aria-pressed={lever === l.id} onClick={() => setLever(l.id)}>{l.label}</button>
              ))}
            </div>
            <label className="scenario-slider">
              <span className="field-label">Change</span>
              <span className="scenario-pct">{pct > 0 ? '+' : ''}{pct}%</span>
              <input type="range" min={-20} max={30} step={1} value={pct} onChange={(e) => setPct(Number(e.target.value))} aria-valuetext={`${pct} percent`} />
              <span className="scenario-range"><span>−20%</span><span>0</span><span>+30%</span></span>
            </label>

            <dl className="scenario-kpis">
              {rows.map((r) => (
                <div key={r.metric} className="scenario-kpi">
                  <dt>Current {r.metric}</dt><dd>{money(r.current)}</dd>
                  <dt>Scenario {r.metric}</dt>
                  <dd className="is-scenario">{money(r.scenario)} <span className={`status ${r.scenario >= r.current ? 'status-good' : 'status-bad'}`}>{r.scenario >= r.current ? '↑' : '↓'} {money(Math.abs(r.scenario - r.current))}</span></dd>
                </div>
              ))}
            </dl>
          </section>

          <ChartContainer
            title="Current vs Scenario"
            subtitle={`${LEVERS.find((l) => l.id === lever).label} ${pct > 0 ? '+' : ''}${pct}%`}
            legend={[{ label: 'Current', color: CURRENT }, { label: 'Scenario', color: SCENARIO }]}
          >
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <BarChart data={rows} margin={{ top: 24, right: 16, left: -8, bottom: 4 }} barGap={2}>
                  <CartesianGrid vertical={false} stroke={GRID_STROKE} />
                  <XAxis dataKey="metric" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} />
                  <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}M`} />
                  <Tooltip cursor={{ fill: 'rgba(9, 124, 135, 0.06)' }} content={<ScenarioTooltip />} />
                  <Bar dataKey="current" name="Current" fill={CURRENT} radius={[4, 4, 0, 0]} maxBarSize={56}>
                    <LabelList dataKey="current" position="top" formatter={money} style={{ fill: '#557177', fontSize: 12 }} />
                  </Bar>
                  <Bar dataKey="scenario" name="Scenario" fill={SCENARIO} radius={[4, 4, 0, 0]} maxBarSize={56}>
                    <LabelList dataKey="scenario" position="top" formatter={money} style={{ fill: '#557177', fontSize: 12 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartContainer>
        </div>
      </div>
    </div>
  )
}

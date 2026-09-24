import { Sparkline, MiniBars } from '../analytics/MiniCharts'
import { HERO_TREND, HERO_BARS } from '../../mocks/previewData'
import { TrendingUpIcon, SparklesIcon, ShieldCheckIcon, GlobeIcon } from '../ui/Icons'

/** Illustrative analytics cards floating around the hero map: DATA → ANALYSIS → INSIGHT */
export default function FloatingCards() {
  return (
    <div className="float-layer" aria-hidden="true">
      <div className="float-card fc-revenue">
        <div className="fc-stage-tag stage-analysis">ANALYSIS</div>
        <div className="fc-label">Total Revenue</div>
        <div className="fc-value">$12.8M</div>
        <div className="fc-delta up"><TrendingUpIcon size={13} /> 12.9% <span>vs last period</span></div>
        <Sparkline data={HERO_TREND} height={36} label="Revenue trend" />
      </div>

      <div className="float-card fc-region">
        <div className="fc-stage-tag stage-analysis">ANALYSIS</div>
        <div className="fc-label"><GlobeIcon size={13} /> Top Performing Region</div>
        <div className="fc-value sm">West Region</div>
        <div className="fc-sub">$2.8M</div>
        <MiniBars data={HERO_BARS.map((b) => b.value)} labels={HERO_BARS.map((b) => b.label)} height={40} />
      </div>

      <div className="float-card fc-quality">
        <div className="fc-stage-tag stage-data">DATA</div>
        <div className="fc-ring" style={{ '--pct': 96 }}>
          <span>96%</span>
        </div>
        <div>
          <div className="fc-label"><ShieldCheckIcon size={13} /> Data Quality</div>
          <div className="fc-sub">Schema inferred · 28 fields</div>
        </div>
      </div>

      <div className="float-card fc-insight">
        <div className="fc-stage-tag stage-insight">INSIGHT</div>
        <div className="fc-label accent"><SparklesIcon size={13} /> AI Insight</div>
        <p>“West region shows higher profitability than the national average.”</p>
      </div>
    </div>
  )
}

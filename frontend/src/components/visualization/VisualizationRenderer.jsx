import React, { useState } from 'react'
import MetricCard from './MetricCard'
import BarChartComponent from './BarChart'
import LineChartComponent from './LineChart'
import PieChartComponent from './PieChart'
import ScatterChartComponent from './ScatterChart'
import DataTable from './DataTable'
import {
  BarChartIcon,
  PieChartIcon,
  LineChartIcon,
  TableIcon,
  SparklesIcon
} from '../Icons'

function getChartIcon(type, size = 14) {
  switch (type) {
    case 'bar':
    case 'horizontal_bar':
      return <BarChartIcon size={size} />
    case 'pie':
      return <PieChartIcon size={size} />
    case 'line':
      return <LineChartIcon size={size} />
    case 'table':
      return <TableIcon size={size} />
    default:
      return <BarChartIcon size={size} />
  }
}

function getChartLabel(type) {
  switch (type) {
    case 'bar':
      return 'Bar Chart'
    case 'horizontal_bar':
      return 'Horizontal Bar'
    case 'pie':
      return 'Pie Chart'
    case 'line':
      return 'Line Chart'
    case 'scatter':
      return 'Scatter Plot'
    case 'table':
      return 'Data Table'
    case 'kpi':
      return 'Metric Card'
    default:
      return type ? type.charAt(0).toUpperCase() + type.slice(1) : 'Chart'
  }
}

function VisualizationChoicePrompt({ vis, onSelectType, selectedType }) {
  const types = vis.available_types && vis.available_types.length > 0
    ? vis.available_types
    : ['bar', 'pie', 'line', 'table']

  return (
    <div className="vis-choice-card animate-slide-up">
      <div className="vis-choice-header">
        <div className="vis-choice-icon-wrap">
          <SparklesIcon size={16} />
        </div>
        <div className="vis-choice-text">
          <h4 className="vis-choice-title">
            {vis.message || 'How would you like to visualize these results?'}
          </h4>
          <p className="vis-choice-subtitle">
            Choose your preferred chart format to display the calculated data:
          </p>
        </div>
      </div>

      <div className="vis-choice-buttons-grid">
        {types.map((t) => (
          <button
            key={t}
            id={`vis-choice-btn-${t}`}
            className={`vis-choice-btn ${selectedType === t ? 'active' : ''}`}
            onClick={() => onSelectType(t)}
            title={`Render results as ${getChartLabel(t)}`}
          >
            {getChartIcon(t, 14)}
            <span>{getChartLabel(t)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function SingleVisualization({ vis, showTableToggle = true }) {
  // If vis requires user choice and user hasn't selected yet, default to null
  const [userSelectedType, setUserSelectedType] = useState(null)
  const [viewMode, setViewMode] = useState('chart') // 'chart' | 'table'

  if (!vis) return null

  const isChoiceRequired = Boolean(vis.requires_user_choice) && !userSelectedType
  const activeType = (userSelectedType || vis.visualization_type || vis.type || 'table').toLowerCase()
  const availableTypes = vis.available_types && vis.available_types.length > 0
    ? vis.available_types
    : ['bar', 'pie', 'line', 'table']

  const hasData = vis.data && vis.data.length > 0
  const hasTable = vis.rows && vis.rows.length > 0
  const isChart = ['bar', 'horizontal_bar', 'line', 'pie', 'scatter'].includes(activeType)

  // Handlers for dimension & metric keys across different chart types
  const dimKey = vis.x_key || vis.label_key || (vis.headers && vis.headers[0]) || 'column'
  const valKey = vis.y_key || vis.value_key || (vis.headers && vis.headers[1]) || 'count'

  const renderActiveChart = () => {
    switch (activeType) {
      case 'kpi':
        return <MetricCard {...vis} />
      case 'bar':
        return (
          <BarChartComponent
            {...vis}
            x_key={dimKey}
            y_key={valKey}
            orientation="vertical"
          />
        )
      case 'horizontal_bar':
        return (
          <BarChartComponent
            {...vis}
            x_key={dimKey}
            y_key={valKey}
            orientation="horizontal"
          />
        )
      case 'line':
        return (
          <LineChartComponent
            {...vis}
            x_key={dimKey}
            y_key={valKey}
          />
        )
      case 'pie':
        return (
          <PieChartComponent
            {...vis}
            label_key={dimKey}
            value_key={valKey}
          />
        )
      case 'scatter':
        return (
          <ScatterChartComponent
            {...vis}
            x_key={dimKey}
            y_key={valKey}
          />
        )
      case 'table':
        return (
          <DataTable
            {...vis}
            headers={vis.headers}
            rows={vis.rows}
            data={vis.data}
          />
        )
      default:
        return (
          <DataTable
            {...vis}
            headers={vis.headers}
            rows={vis.rows}
            data={vis.data}
          />
        )
    }
  }

  const renderComponent = () => {
    if (isChoiceRequired) {
      return (
        <VisualizationChoicePrompt
          vis={vis}
          selectedType={userSelectedType}
          onSelectType={(t) => setUserSelectedType(t)}
        />
      )
    }

    if (viewMode === 'table' && (hasData || hasTable)) {
      return (
        <DataTable
          title={`${vis.title || 'Data'} Table`}
          headers={vis.headers}
          rows={vis.rows}
          data={vis.data}
          format={vis.format}
          description={vis.description}
        />
      )
    }

    return renderActiveChart()
  }

  return (
    <div className="vis-section-wrapper">
      {/* If a chart is actively rendered, provide a toolbar to switch chart formats or toggle table */}
      {!isChoiceRequired && (hasData || hasTable) && (
        <div className="vis-mode-toggle-row">
          {/* Quick Chart Type Switcher Pills */}
          {availableTypes.length > 1 && viewMode === 'chart' && (
            <div className="vis-type-switcher">
              <span className="vis-switcher-label">View as:</span>
              <div className="vis-type-pill-group">
                {availableTypes.map((t) => (
                  <button
                    key={t}
                    className={`vis-type-pill ${activeType === t ? 'active' : ''}`}
                    onClick={() => setUserSelectedType(t)}
                    title={`Switch to ${getChartLabel(t)}`}
                  >
                    {getChartIcon(t, 12)}
                    <span>{getChartLabel(t)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chart / Data Table View Toggle */}
          {showTableToggle && (
            <div className="vis-mode-tabs">
              <button
                className={`vis-mode-tab ${viewMode === 'chart' ? 'active' : ''}`}
                onClick={() => setViewMode('chart')}
                title="Show Chart Visualization"
              >
                <BarChartIcon size={12} />
                <span>Chart</span>
              </button>
              <button
                className={`vis-mode-tab ${viewMode === 'table' ? 'active' : ''}`}
                onClick={() => setViewMode('table')}
                title="Show Raw Data Table"
              >
                <TableIcon size={12} />
                <span>Data Table</span>
              </button>
            </div>
          )}
        </div>
      )}

      {renderComponent()}
    </div>
  )
}

export default function VisualizationRenderer({
  visualization,
  visualizations = [],
  table,
  scalar
}) {
  // 1. If multiple visualizations are returned
  if (visualizations && visualizations.length > 0) {
    const hasMultiple = visualizations.length > 1
    return (
      <div className="visualizations-container">
        {visualizations.map((vis, idx) => (
          <SingleVisualization
            key={`vis-${idx}`}
            vis={vis}
            showTableToggle={!hasMultiple || idx === 0}
          />
        ))}
      </div>
    )
  }

  // 2. If single visualization is returned
  if (visualization) {
    return (
      <div className="visualizations-container">
        <SingleVisualization vis={visualization} showTableToggle={true} />
      </div>
    )
  }

  // 3. Fallback to scalar or table if no visualization metadata
  if (scalar) {
    return (
      <div className="visualizations-container">
        <MetricCard
          title={scalar.metric}
          value={scalar.value}
          aggregation={scalar.aggregation}
          format="number"
        />
      </div>
    )
  }

  if (table && table.headers && table.rows) {
    return (
      <div className="visualizations-container">
        <DataTable
          title="Data Results"
          headers={table.headers}
          rows={table.rows}
        />
      </div>
    )
  }

  return null
}

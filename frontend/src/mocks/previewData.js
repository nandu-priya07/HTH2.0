/**
 * ─────────────────────────────────────────────────────────────────────
 *  MOCK / PREVIEW DATA — NOT BACKEND OUTPUT
 * ─────────────────────────────────────────────────────────────────────
 * Used only for illustrative UI (hero visual, Insights / Explorer /
 * Scenarios / Decisions foundations, Home page product preview).
 * Every screen that renders this data shows a <PreviewBadge />.
 * Replace with real API data when the corresponding backend exists.
 */

export const HERO_NODES = [
  { lon: -122, lat: 37.7, tone: 'cyan', label: 'San Francisco' },
  { lon: -74, lat: 40.7, tone: 'cyan', label: 'New York' },
  { lon: -46.6, lat: -23.5, tone: 'sage', label: 'São Paulo' },
  { lon: -0.1, lat: 51.5, tone: 'cyan', label: 'London' },
  { lon: 3.4, lat: 6.5, tone: 'yellow', label: 'Lagos' },
  { lon: 55.3, lat: 25.2, tone: 'sage', label: 'Dubai' },
  { lon: 103.8, lat: 1.3, tone: 'yellow', label: 'Singapore' },
  { lon: 139.7, lat: 35.7, tone: 'cyan', label: 'Tokyo' },
  { lon: 151.2, lat: -33.8, tone: 'sage', label: 'Sydney' },
  { lon: -99.1, lat: 19.4, tone: 'yellow', label: 'Mexico City' }
]
export const HERO_MARKER = { lon: 80.2, lat: 13.1, label: 'Chennai — current dataset origin' }
export const HERO_ARCS = [[1, 3], [3, 5], [5, 6], [6, 7], [0, 1], [2, 4], [7, 8], [9, 1]]

export const HERO_TREND = [42, 48, 45, 53, 51, 60, 58, 66, 71, 69, 78, 84]
export const HERO_BARS = [
  { label: 'West', value: 2.8 },
  { label: 'East', value: 2.3 },
  { label: 'South', value: 1.9 },
  { label: 'North', value: 1.4 }
]

/* Example answer used on the Home page "what you get" preview */
export const EXAMPLE_ANSWER = {
  question: 'Which region generated the highest revenue?',
  answer: 'West Region generated the highest revenue at $2.48M.',
  bars: [
    { label: 'West', value: 2.48 },
    { label: 'East', value: 2.11 },
    { label: 'South', value: 1.76 },
    { label: 'North', value: 1.32 }
  ],
  intent: ['GROUP', 'AGGREGATE', 'COMPARE'],
  fields: ['Region', 'Revenue'],
  expression: 'SUM(Revenue) GROUP BY Region ORDER BY Revenue DESC',
  result: 'West = $2.48M'
}

export const INSIGHTS = [
  {
    id: 'top-region', title: 'Top Performing Region', metric: 'West', change: '+12.9%', direction: 'up',
    explanation: 'West contributes the largest share of total revenue this period.',
    visual: 'bars', data: [2.48, 2.11, 1.76, 1.32], labels: ['West', 'East', 'South', 'North'],
    evidence: { fields: ['Revenue', 'Region'], aggregation: 'SUM', transformation: 'Group by Region' }
  },
  {
    id: 'fastest-product', title: 'Fastest Growing Product', metric: 'Aurora Pro', change: '+34%', direction: 'up',
    explanation: 'Quarter-over-quarter unit growth is the highest among all products.',
    visual: 'spark', data: [12, 14, 13, 18, 22, 27, 31],
    evidence: { fields: ['Product', 'Quantity', 'Order Date'], aggregation: 'SUM', transformation: 'Group by Product, Quarter' }
  },
  {
    id: 'top-category', title: 'Highest Revenue Category', metric: 'Electronics', change: '41% share', direction: 'flat',
    explanation: 'Electronics accounts for the largest share of revenue across categories.',
    visual: 'bars', data: [41, 26, 19, 14], labels: ['Electronics', 'Home', 'Apparel', 'Other'],
    evidence: { fields: ['Category', 'Revenue'], aggregation: 'SUM', transformation: 'Group by Category' }
  },
  {
    id: 'trend', title: 'Revenue Trend', metric: '$12.8M', change: '+8.1%', direction: 'up',
    explanation: 'Monthly revenue has increased in 9 of the last 12 months.',
    visual: 'spark', data: HERO_TREND,
    evidence: { fields: ['Revenue', 'Order Date'], aggregation: 'SUM', transformation: 'Group by Month' }
  },
  {
    id: 'anomaly', title: 'Potential Anomaly', metric: '12 records', change: 'Review', direction: 'alert',
    explanation: 'A small set of transactions sit far above the typical order value.',
    visual: 'spark', data: [8, 9, 8, 10, 9, 31, 9, 8],
    evidence: { fields: ['Revenue', 'Order ID'], aggregation: 'Outlier check', transformation: 'Per-record comparison' }
  },
  {
    id: 'seasonal', title: 'Seasonal Pattern', metric: 'Q4 peak', change: '+22% vs avg', direction: 'up',
    explanation: 'Revenue repeatedly peaks in the final quarter of each year.',
    visual: 'bars', data: [21, 23, 24, 32], labels: ['Q1', 'Q2', 'Q3', 'Q4'],
    evidence: { fields: ['Revenue', 'Order Date'], aggregation: 'SUM', transformation: 'Group by Quarter' }
  }
]

export const ANOMALIES = [
  { record: 'Order #48213', reason: 'Unusually high value', severity: 'High', value: '$184,200' },
  { record: 'Order #51007', reason: 'Rare category', severity: 'Medium', value: 'Category: “Refurb-X”' },
  { record: 'Order #39920', reason: 'Unexpected combination', severity: 'Medium', value: 'Region: North · Channel: Export' },
  { record: 'Order #60114', reason: 'Unusually high value', severity: 'Low', value: '$62,950' }
]

export const SCENARIO_BASE = { revenue: 12.8, profit: 3.1 }

export const DECISIONS = [
  {
    id: 'd1',
    finding: 'West region revenue is 18% above the average of other regions.',
    evidence: ['SUM(Revenue) GROUP BY Region', '12,458 rows analyzed', 'No filters applied'],
    metrics: [{ label: 'West revenue', value: '$2.48M' }, { label: 'Avg. other regions', value: '$2.10M' }],
    analysis: 'Ranking + comparison across the Region field'
  },
  {
    id: 'd2',
    finding: 'Q4 revenue has exceeded Q3 in each of the last three years.',
    evidence: ['SUM(Revenue) GROUP BY Year, Quarter', 'Trend across 36 months'],
    metrics: [{ label: 'Avg. Q4 uplift', value: '+22%' }, { label: 'Years observed', value: '3' }],
    analysis: 'Trend analysis on the inferred date field'
  }
]

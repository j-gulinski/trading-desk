import { useEffect, useRef, useState } from 'react'
import { curveTitle } from '../../domain/curves.js'

const DEFAULT_WIDTH = 1040
const DESKTOP_HEIGHT = 340
const COMPACT_HEIGHT = 300
const TENOR_TICKS = [0.25, 1, 2, 5, 10, 20, 30]
const COMPACT_TENOR_TICKS = [1, 5, 10, 20, 30]
const TENOR_TICK_LABELS = { 0.25: '3M', 1: '1Y', 2: '2Y', 5: '5Y', 10: '10Y', 20: '20Y', 30: '30Y' }

function niceStep(span, count = 5) {
  const step = 10 ** Math.floor(Math.log10(span / count))
  const error = span / (count * step)
  const factor = error >= 7.5 ? 10 : error >= 3.5 ? 5 : error >= 1.5 ? 2 : 1
  return step * factor
}

function rateScale(curves) {
  const rates = curves.flatMap((curve) => curve.points.map((point) => point.rate))
  if (rates.length === 0) return { min: 0, max: 1, ticks: [0, 0.5, 1], decimals: 1 }
  const rawMin = Math.min(...rates)
  const rawMax = Math.max(...rates)
  const rawSpan = Math.max(rawMax - rawMin, 0.4)
  const pad = Math.max(rawSpan * 0.12, 0.05)
  const step = niceStep(rawSpan + 2 * pad)
  const min = Math.floor((rawMin - pad) / step) * step
  const max = Math.ceil((rawMax + pad) / step) * step
  const ticks = []
  for (let tick = min; tick <= max + step / 1000; tick += step) {
    ticks.push(Number(tick.toFixed(6)))
  }
  return { min, max, ticks, decimals: step < 0.1 ? 2 : 1 }
}

export default function CurveChart({ curves, colors, selectedId, onSelectPoint }) {
  const chartRef = useRef(null)
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const height = width < 640 ? COMPACT_HEIGHT : DESKTOP_HEIGHT
  const margin = {
    top: 22,
    right: width < 640 ? 12 : 24,
    bottom: 42,
    left: width < 640 ? 46 : 64,
  }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  useEffect(() => {
    const chart = chartRef.current
    if (chart == null) return undefined

    const updateWidth = () => {
      const next = Math.max(320, Math.round(chart.getBoundingClientRect().width))
      setWidth((previous) => previous === next ? previous : next)
    }
    updateWidth()

    const observer = new ResizeObserver(updateWidth)
    observer.observe(chart)
    return () => observer.disconnect()
  }, [])

  const maxTenor = Math.max(1, ...curves.flatMap((curve) =>
    curve.points.map((point) => point.years),
  ))
  const { min, max, ticks: rateTicks, decimals } = rateScale(curves)
  const xOf = (years) => margin.left + (years / maxTenor) * innerWidth
  const yOf = (rate) => margin.top + (1 - (rate - min) / (max - min)) * innerHeight
  const visibleTenorTicks = width < 640
    ? COMPACT_TENOR_TICKS
    : TENOR_TICKS
  const tenorTicks = visibleTenorTicks.filter((tick) => tick <= maxTenor)

  return (
    <svg
      ref={chartRef}
      className="curve-chart"
      viewBox={`0 0 ${width} ${height}`}
      style={{ height }}
      role="img"
      aria-label="Rate curves by tenor"
    >
      {rateTicks.map((tick) => (
        <g key={`rate-${tick}`}>
          <line
            className="curve-chart__grid"
            x1={margin.left}
            x2={width - margin.right}
            y1={yOf(tick)}
            y2={yOf(tick)}
          />
          <text className="curve-chart__tick" x={margin.left - 8} y={yOf(tick) + 3} textAnchor="end">
            {tick.toFixed(decimals)}%
          </text>
        </g>
      ))}
      {tenorTicks.map((tick) => (
        <g key={`tenor-${tick}`}>
          <line
            className="curve-chart__grid curve-chart__grid--minor"
            x1={xOf(tick)}
            x2={xOf(tick)}
            y1={margin.top}
            y2={height - margin.bottom}
          />
          <text
            className="curve-chart__tick"
            x={xOf(tick)}
            y={height - margin.bottom + 17}
            textAnchor="middle"
          >
            {TENOR_TICK_LABELS[tick] ?? `${tick}Y`}
          </text>
        </g>
      ))}
      <line
        className="curve-chart__axis"
        x1={margin.left}
        x2={width - margin.right}
        y1={height - margin.bottom}
        y2={height - margin.bottom}
      />
      <text className="curve-chart__axis-label" x={margin.left} y={13}>
        {width < 640 ? 'RATE % · AUTO' : 'RATE (%) · AUTO-SCALED'}
      </text>
      <text
        className="curve-chart__axis-label"
        x={width - margin.right}
        y={height - 8}
        textAnchor="end"
      >
        {width < 640 ? 'YEARS · LINEAR' : 'MATURITY · LINEAR YEARS'}
      </text>
      {curves.map((curve) => {
        const color = colors[curve.name]
        const path = curve.points
          .map((point, index) =>
            `${index === 0 ? 'M' : 'L'}${xOf(point.years).toFixed(1)} ${yOf(point.rate).toFixed(1)}`)
          .join(' ')
        return (
          <g key={curve.name}>
            <path className="curve-chart__line" d={path} style={{ stroke: color }} />
            {curve.points.map((point, index) => {
              const id = `${curve.name}:${point.label}`
              const selected = id === selectedId
              return (
                <circle
                  key={id}
                  className={[
                    'curve-chart__point',
                    point.derived ? 'curve-chart__point--derived' : '',
                    selected ? 'curve-chart__point--selected' : '',
                  ].filter(Boolean).join(' ')}
                  cx={xOf(point.years)}
                  cy={yOf(point.rate)}
                  r={selected ? 6 : 4}
                  style={{ stroke: color, fill: point.derived ? 'var(--bg-panel)' : color }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${curveTitle(curve)} ${point.label} ${point.rate.toFixed(3)}%${point.derived ? ' derived' : ''}`}
                  onClick={() => onSelectPoint(curve.name, index)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onSelectPoint(curve.name, index)
                    }
                  }}
                >
                  <title>
                    {`${curveTitle(curve)} · ${point.label} · ${point.rate.toFixed(3)}%${point.derived ? ' · derived' : ''}`}
                  </title>
                </circle>
              )
            })}
          </g>
        )
      })}
    </svg>
  )
}

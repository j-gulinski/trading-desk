const WIDTH = 760
const HEIGHT = 300
const MARGIN = { top: 18, right: 20, bottom: 34, left: 56 }
const TENOR_TICKS = [0.25, 1, 2, 5, 10, 20, 30]
const TENOR_TICK_LABELS = { 0.25: '3M', 1: '1Y', 2: '2Y', 5: '5Y', 10: '10Y', 20: '20Y', 30: '30Y' }

function niceTicks(min, max, count = 5) {
  if (!(max > min)) {
    const value = Number.isFinite(min) ? min : 0
    return [value - 0.5, value, value + 0.5]
  }
  const span = max - min
  const step = 10 ** Math.floor(Math.log10(span / count))
  const error = span / (count * step)
  const factor = error >= 7.5 ? 10 : error >= 3.5 ? 5 : error >= 1.5 ? 2 : 1
  const niceStep = step * factor
  const start = Math.ceil(min / niceStep) * niceStep
  const ticks = []
  for (let tick = start; tick <= max + niceStep / 1000; tick += niceStep) {
    ticks.push(Number(tick.toFixed(6)))
  }
  return ticks
}

function rateBounds(curves) {
  const rates = curves.flatMap((curve) => curve.points.map((point) => point.rate))
  if (rates.length === 0) return { min: 0, max: 1 }
  const min = Math.min(...rates)
  const max = Math.max(...rates)
  const pad = Math.max((max - min) * 0.12, 0.1)
  return { min: min - pad, max: max + pad }
}

export default function CurveChart({ curves, colors, selectedId, onSelectPoint }) {
  const innerWidth = WIDTH - MARGIN.left - MARGIN.right
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const maxTenor = Math.max(1, ...curves.flatMap((curve) =>
    curve.points.map((point) => point.years),
  ))
  const { min, max } = rateBounds(curves)
  const xOf = (years) => MARGIN.left + (Math.sqrt(years) / Math.sqrt(maxTenor)) * innerWidth
  const yOf = (rate) => MARGIN.top + (1 - (rate - min) / (max - min)) * innerHeight
  const tenorTicks = TENOR_TICKS.filter((tick) => tick <= maxTenor)
  const rateTicks = niceTicks(min, max).filter((tick) => tick >= min && tick <= max)

  return (
    <svg
      className="curve-chart"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="Rate curves by tenor"
    >
      {rateTicks.map((tick) => (
        <g key={`rate-${tick}`}>
          <line
            className="curve-chart__grid"
            x1={MARGIN.left}
            x2={WIDTH - MARGIN.right}
            y1={yOf(tick)}
            y2={yOf(tick)}
          />
          <text className="curve-chart__tick" x={MARGIN.left - 8} y={yOf(tick) + 3} textAnchor="end">
            {tick.toFixed(2)}%
          </text>
        </g>
      ))}
      {tenorTicks.map((tick) => (
        <g key={`tenor-${tick}`}>
          <line
            className="curve-chart__grid curve-chart__grid--minor"
            x1={xOf(tick)}
            x2={xOf(tick)}
            y1={MARGIN.top}
            y2={HEIGHT - MARGIN.bottom}
          />
          <text
            className="curve-chart__tick"
            x={xOf(tick)}
            y={HEIGHT - MARGIN.bottom + 16}
            textAnchor="middle"
          >
            {TENOR_TICK_LABELS[tick] ?? `${tick}Y`}
          </text>
        </g>
      ))}
      <line
        className="curve-chart__axis"
        x1={MARGIN.left}
        x2={WIDTH - MARGIN.right}
        y1={HEIGHT - MARGIN.bottom}
        y2={HEIGHT - MARGIN.bottom}
      />
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
                  aria-label={`${curve.name} ${point.label} ${point.rate.toFixed(3)}%${point.derived ? ' interpolated' : ''}`}
                  onClick={() => onSelectPoint(curve.name, index)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onSelectPoint(curve.name, index)
                    }
                  }}
                >
                  <title>
                    {`${curve.name} · ${point.label} · ${point.rate.toFixed(3)}%${point.derived ? ' · interpolated' : ''}`}
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

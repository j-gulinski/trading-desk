import { memo } from 'react'

function sparklineDescription(count, trend) {
  if (count < 2) return 'Not enough history to draw a trend yet'
  const direction = trend === 'pos' ? 'rising' : trend === 'neg' ? 'falling' : 'flat'
  return `${direction} trend over the last ${count} observations`
}

function Sparkline({ values = [], width = 84, height = 28, className }) {
  const classes = className ? `sparkline ${className}` : 'sparkline'

  if (values.length < 2) {
    const description = sparklineDescription(values.length)
    return (
      <svg
        className={classes}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={description}
      >
        <title>{description}</title>
      </svg>
    )
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min
  const padding = 3
  const chartWidth = width - padding * 2
  const chartHeight = height - padding * 2
  const step = chartWidth / (values.length - 1)

  const first = values[0]
  const last = values[values.length - 1]
  const trend = last > first ? 'pos' : last < first ? 'neg' : 'flat'
  const description = sparklineDescription(values.length, trend)

  const coordinates = values
    .map((value, i) => {
      const x = padding + i * step
      const y =
        range === 0
          ? height / 2
          : height - padding - ((value - min) / range) * chartHeight
      return { x, y }
    })

  const points = coordinates
    .map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`)
    .join(' ')
  const lastPoint = coordinates[coordinates.length - 1]
  const baseline = height - padding
  const areaPoints = `${padding},${baseline} ${points} ${width - padding},${baseline}`

  return (
    <svg
      className={`${classes} sparkline--${trend}`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={description}
    >
      <title>{description}</title>
      <polygon className="sparkline__area" points={areaPoints} />
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        className="sparkline__endpoint"
        cx={lastPoint.x}
        cy={lastPoint.y}
        r="2"
      />
    </svg>
  )
}

export default memo(Sparkline)

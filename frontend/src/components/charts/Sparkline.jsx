import { memo } from 'react'

function Sparkline({ points, values = [], label = 'history', width = 84, height = 28, className }) {
  const classes = className ? `sparkline ${className}` : 'sparkline'
  const series = Array.isArray(points)
    ? points
    : values.map((value, index) => [index, value])

  if (series.length < 2) {
    const description = `Not enough ${label} to draw a trend yet`
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

  const seriesValues = series.map(([, value]) => value)
  const times = series.map(([at]) => at)
  const min = Math.min(...seriesValues)
  const max = Math.max(...seriesValues)
  const range = max - min
  const firstTime = times[0]
  const timeSpan = times[times.length - 1] - firstTime
  const padding = 3
  const chartWidth = width - padding * 2
  const chartHeight = height - padding * 2

  const first = seriesValues[0]
  const last = seriesValues[seriesValues.length - 1]
  const trend = last > first ? 'rising' : last < first ? 'falling' : 'flat'
  const tone = last > first ? 'pos' : last < first ? 'neg' : 'flat'
  const description = `${trend} ${label} · ${series.length} observations`

  const coordinates = series.map(([at, value], i) => ({
    x:
      padding +
      (timeSpan > 0
        ? ((at - firstTime) / timeSpan) * chartWidth
        : (i / (series.length - 1)) * chartWidth),
    y:
      range === 0
        ? height / 2
        : height - padding - ((value - min) / range) * chartHeight,
  }))

  const line = coordinates
    .map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`)
    .join(' ')
  const lastPoint = coordinates[coordinates.length - 1]
  const baseline = height - padding
  const areaPoints = `${padding},${baseline} ${line} ${width - padding},${baseline}`

  return (
    <svg
      className={`${classes} sparkline--${tone}`}
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
        points={line}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle className="sparkline__endpoint" cx={lastPoint.x} cy={lastPoint.y} r="2" />
    </svg>
  )
}

export default memo(Sparkline)

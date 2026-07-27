function sparklineDescription(count) {
  if (count < 2) return 'Not enough history to draw a trend yet'
  return `Trend over the last ${count} observations`
}

export default function Sparkline({ values = [], width = 72, height = 24, className }) {
  const classes = className ? `sparkline ${className}` : 'sparkline'
  const description = sparklineDescription(values.length)

  if (values.length < 2) {
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
  const range = max - min || 1
  const step = width / (values.length - 1)
  const padding = 2
  const chartHeight = height - padding * 2

  const first = values[0]
  const last = values[values.length - 1]
  const trend = last > first ? 'pos' : last < first ? 'neg' : 'flat'

  const coordinates = values
    .map((value, i) => {
      const x = i * step
      const y = height - padding - ((value - min) / range) * chartHeight
      return { x, y }
    })

  const points = coordinates
    .map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`)
    .join(' ')
  const lastPoint = coordinates[coordinates.length - 1]
  const areaPoints = `0,${height} ${points} ${width},${height}`

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
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        className="sparkline__endpoint"
        cx={lastPoint.x}
        cy={lastPoint.y}
        r="1.75"
      />
    </svg>
  )
}

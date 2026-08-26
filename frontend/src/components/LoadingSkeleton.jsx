const DEFAULT_ROWS = {
  cards: 6,
  inline: 1,
  list: 4,
  panel: 5,
  table: 6,
}

export default function LoadingSkeleton({
  variant = 'table',
  rows = DEFAULT_ROWS[variant] ?? 5,
  label = 'Loading content',
}) {
  const inline = variant === 'inline'
  const Root = inline ? 'span' : 'div'
  const Row = inline ? 'span' : 'div'

  return (
    <Root
      className={`loading-skeleton loading-skeleton--${variant}`}
      role="status"
      aria-label={label}
      aria-busy="true"
    >
      {Array.from({ length: rows }, (_, index) => (
        <Row className="loading-skeleton__row" aria-hidden="true" key={index}>
          <span className="loading-skeleton__line loading-skeleton__line--primary" />
          <span className="loading-skeleton__line loading-skeleton__line--secondary" />
          <span className="loading-skeleton__line loading-skeleton__line--short" />
        </Row>
      ))}
    </Root>
  )
}

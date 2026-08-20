const DEFAULT_LABEL = {
  healthy: 'HEALTHY',
  degraded: 'DEGRADED',
  stale: 'STALE',
  down: 'DOWN',
  unknown: 'UNKNOWN',
}

export default function StatusPill({ level, label, title, compact = false }) {
  return (
    <span
      className={`pill pill--${level}${compact ? ' pill--compact' : ''}`}
      title={title}
    >
      <span className="pill__dot" aria-hidden="true" />
      {label ?? DEFAULT_LABEL[level] ?? level}
    </span>
  )
}

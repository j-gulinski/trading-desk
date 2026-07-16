const DEFAULT_LABEL = {
  healthy: 'HEALTHY',
  degraded: 'DEGRADED',
  stale: 'STALE',
  down: 'DOWN',
  unknown: 'UNKNOWN',
}

export default function StatusPill({ level, label }) {
  return (
    <span className={`pill pill--${level}`}>
      <span className="pill__dot" />
      {label ?? DEFAULT_LABEL[level] ?? level}
    </span>
  )
}

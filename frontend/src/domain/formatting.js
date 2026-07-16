export function formatElapsedTime(ms) {
  if (ms == null || Number.isNaN(ms)) return '—'
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

export function formatNumber(n) {
  if (n == null || Number.isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US').format(n)
}

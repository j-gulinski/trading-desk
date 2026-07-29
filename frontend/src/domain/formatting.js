export function formatElapsedTime(ms) {
  if (ms == null || Number.isNaN(ms)) return '—'
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

export function formatClockTime(ms, { millis = false } = {}) {
  if (!Number.isFinite(ms)) return '—'
  const d = new Date(ms)
  const p = (n, w = 2) => String(n).padStart(w, '0')
  const clock = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  return millis ? `${clock}.${p(d.getMilliseconds(), 3)}` : clock
}

export function formatNumber(n) {
  if (n == null || Number.isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US').format(n)
}

export function formatShortId(id) {
  return typeof id === 'string' && id.length > 0 ? id.slice(0, 8).toUpperCase() : '—'
}

export function directionOf(delta) {
  if (!Number.isFinite(delta) || delta === 0) return 'flat'
  return delta > 0 ? 'pos' : 'neg'
}

function amountDecimals(value) {
  return Math.abs(value) >= 10000 ? 0 : 2
}

export function formatAmount(value, decimals = amountDecimals(value)) {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

export function formatSignedAmount(value, decimals = amountDecimals(value)) {
  if (!Number.isFinite(value)) return '—'
  const rounded = Number(value.toFixed(decimals))
  if (rounded === 0) return formatAmount(0, decimals)
  return `${rounded > 0 ? '+' : '−'}${formatAmount(Math.abs(rounded), decimals)}`
}

const UNIT_PRICE_DECIMALS = { FX: 5 }

export function unitPriceDecimals(assetClass) {
  return UNIT_PRICE_DECIMALS[assetClass] ?? 2
}

export function formatUnitPrice(value, assetClass) {
  return formatAmount(value, unitPriceDecimals(assetClass))
}

export function formatPercent(value, decimals = 2) {
  if (!Number.isFinite(value)) return '—'
  const rounded = Number(value.toFixed(decimals))
  if (rounded === 0) return `${(0).toFixed(decimals)}%`
  return `${rounded > 0 ? '+' : '−'}${Math.abs(rounded).toFixed(decimals)}%`
}
